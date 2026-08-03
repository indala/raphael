# Raphael Hybrid Bridge Framework — Architecture Design

Status: Draft v0.1
Scope: Rearchitect the C#/Python boundary so the two sides stop drifting apart.

## 1. Problem statement

Raphael talks to native Windows code through `RaphaelBridge.exe`, a JSON
stdin/stdout subprocess. Today that boundary has six concrete defects that
produce exactly the symptom "I'm not getting all the C# features":

| # | Defect | Evidence | Consequence |
|---|--------|----------|-------------|
| 1 | **Orphaned C# methods** | `Program.cs` dispatches `desktop_taskbar_info` / `desktop_tray_icons` (from `DesktopHelper.cs`), but `hybrid/bridge.py` exposes **no wrappers** for them. | Native features exist in C# but are unreachable from Python — "missing modules". |
| 2 | **Silent feature death** | `LazyBridge.call` (`bridge.py:228`) catches **every** exception and returns `None`. | A missing method, a crash, a timeout, and a legitimate empty result are indistinguishable. Features vanish with no trace in `bridge_debug.log`. |
| 3 | **No version handshake** | `RaphaelBridge.csproj` targets `net10.0-windows`; `bridge.py` targets nothing. No `min_version` / `list_methods`. | Stale exe next to newer python produces "Unknown method" — the classic "some features missing" case. |
| 4 | **Slow calls block the whole bridge** | `system_snapshot` took **7.4 s** in `bridge_debug.log` (`21:30:20.578` → `21:30:27.940`); `LazyBridge` uses a single global `_lock`. | One slow/WMI-stalled call serializes and starves every other feature. |
| 5 | **One-shot availability** | `modules/clipboard.py:14` caches `is_available()` at import. | If the bridge starts late or dies at runtime, features never recover. Health monitor logs but does not restart. |
| 6 | **Hand-rolled wiring everywhere** | Each module does its own `try: from hybrid.bridge import … except ImportError: fallback`. No single provider registry. | Duplication, drift, impossible to audit what actually runs where. |

## 2. Design goals

- **Contract over convention.** One machine-readable manifest, generated on the
  C# side, consumed on the Python side. Any mismatch is logged loudly, not silent.
- **Capability awareness.** Python knows, at runtime, whether a feature is
  `native-csharp`, `python-fallback`, or `disabled`, and *why*.
- **Failure is visible.** Missing methods, stale versions, and timeouts surface
  as structured logs, not swallowed `None`s.
- **Non-blocking.** Slow native calls are isolated from the fast path.
- **Pluggable transport.** JSON subprocess stays default, but the contract layer
  is transport-agnostic so pythonnet/gRPC can be swapped in later without
  rewriting callers.

## 3. Target layout (3 layers)

```
Python app (callers)                   e.g. modules/clipboard.py, orchestrator/tools/*
      │  ask for logical capability, not a raw method
      ▼
Layer 3  ProviderRegistry ── decides route: csharp | python | disabled (+ why)
      ▼
Layer 2  Client  (generated) ── JSON over stdin/stdout, async, timeout-hinted
      ▼
RaphaelBridge.exe
      ▼
Layer 1  Contract: manifest generated at build time from C# attributes
```

### Layer 1 — Contract

**Source of truth lives in C# attributes.** Each public bridge method gets a
small attribute declaring its shape:

```csharp
[BridgeMethod(
    Id = "desktop.tray_icons",
    TimeoutMs = 5000,
    FallbackTo = "native.NextProvider",   // optional python fallback
    Slow = false)]
public static string TrayIcons() => ...;
```

A build step (in `RaphaelBridge.csproj` via a target) emits `manifest.json`:

```json
{
  "bridge_version": "1.1.0",
  "protocol_version": 2,
  "methods": [
    {
      "id": "desktop.tray_icons",
      "arg_types": [],
      "result_type": "string|json",
      "timeout_ms": 5000,
      "slow": true,
      "fallback_to": "native.python",
      "available": true
    }
  ]
}
```

**Python side renders this into callable stubs** (one Python module per
capability area, e.g. `bridge/api/desktop.py`), so calling a C# method is
reflective, not hand-rewritten:

```python
from hybrid.contract import manifest
desktop = manifest.api("desktop")          # generated proxy
result = desktop.tray_icons()              # raises BridgeMethodMissing if absent
```

Consequence: the day a new `DesktopHelper` method lands in C#, Python can call
it immediately — no per-method wrapper hand-written. Item #1 disappears.

### Layer 2 — Transport

Replace the `switch (req.Method)` in `Program.cs` with **dispatch-by-reflection**
over the same attribute registry:

- One generic handler; adding a C# feature requires no new `case`.
- Requests carry `"timeout_ms"`. C# runs any `Slow=true` method on a worker
  thread and returns on its own schedule, so a hang never blocks the loop.
- Python side: **two pipe queues** — a fast synchronous path and a slow
  async path (fresh response handling per request id). `clipboard_copy` no
  longer waits behind `system_snapshot`. Sequential-responses supported.
- `ping` + `list_methods` + `version` introspection endpoints, checked once at
  startup and re-checked on health events.

### Layer 3 — ProviderRegistry

Replace the scattered `if _CS_CLIP:` / `except ImportError` blocks with:

```python
from hybrid.registry import get_provider
clip = get_provider("clipboard")
clip.copy_text("hi")          # may route to csharp, then fall back to pyperclip
```

`get_provider("x")`:
1. Checks manifest: is there a `csharp` implementation and is the bridge
   healthy?
2. Checks health probe: last ping age < threshold → `csharp`, else degrade.
3. On degraded, consult `fallback_to` and route to the python provider.
4. Logs every route decision at DEBUG with the *reason*.

Health monitor (`orchestrator/health_monitor.py`) gains a **restart action**, not
just an alert. On N consecutive missed pings it restarts the subprocess and
re-probes the manifest.

## 4. Incremental rollout (each step lands, tests, keeps working)

Because the current code works — badly in places — we never big-bang it.

- **M1 — Contract + introspection (no behavior change):** add attributes to C#,
  emit a manifest, add `ping` / `list_methods` / `version`. Python loads the
  manifest, logs a diff vs `manifest.json` and logs "missing" methods loudly.
  *Outcome: all #1, #3 problem visibility fixed; zero callers changed.*
- **M2 — Reflective dispatch:** C# dispatches by attribute id, not switch;
  Python calls through generated stubs instead of hand classes. Port one module
  (`clipboard`) fully as a pilot. *Outcome: proves the wiring is thin.*
- **M3 — Slow/fast split:** `slow` methods go async; kill the global lock with
  a per-request tracking table. Re-test `system_snapshot` under load.
- **M4 — ProviderRegistry:** fold `modules/*` breadth of try/except into the
  registry; add `disabled` option per capability; surface a `raphael --bridge-diag`
  command. Write the reason for every route.
- **M5 — health → restart:** wire restart + manifest re-probe.

## 5. Out of scope / deferred

- gRPC transport migration (manifest layer already prepares for it; the
  proto/DLLs are already shipped in `bin/Bridge`).
- Moving more python modules native (audio volume etc.) — route bodies up via
  the registry rather than ad-hoc.
- Cross-platform (all C# is Windows-only by design; manifest keeps the door
  open for `fallback_to: python`).

## 6. Open questions for the owner

1. **Priority:** which is the actual pain today — (a) *wiring gap* (C# exists
   but python lacks), or (b) *missing native features* (need new C#), or (c)
   *runtime flakiness* (slow/hang/silent drop)? M1 fixes visibility for all
   three, but M2–M5 ordering matters if (c) is dominant.
2. **Timeout budget**: is 10 s acceptable for any bridge call, or should
   `system_snapshot` be allowed up to e.g. 30 s on a dedicated worker?
3. **Deployment**: is the bridge shipped with the app installer (`installer/`
   + `build_hybrid.py`), so manifest must also ship and be validated at install?