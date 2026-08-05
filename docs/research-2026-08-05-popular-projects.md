# Popular-Projects Comparison — Feature Extract for Raphael (2026-08-05)

Deep code-level dive (not README-only) of the four substantive sibling projects in the workspace.
obs-studio and win32 are references only (screen recording / WinRT SDK docs) — no features lifted.

## Raphael's existing state (baseline — avoid recommending duplicates)
STT (winrt / whisper_local / groq) + silero VAD + wake word · TTS (edge-tts) · proactive engine ·
routine engine (time/interval/event, `workflows/routines.py`) · memory (`memory/memory_manager.py`,
`agent_memory.py`) · background task pool (`orchestrator/background.py`) · delegation/subagents ·
24 tool modules (browser, files, email, music, power, screen, weather, clipboard, goals, knowledge,
memory, upstox, web, chart, tts, ui...) · plugins (`orchestrator/plugin.py`) · MCP · hybrid C# bridge ·
system metrics (`ui/system_metrics.py`) · skills (`skills/tool_manager.py`).

---

## 1. hermes-agent (Nous) — memory crown jewel
- **FTS5 cross-session recall** — external-content `messages_fts` virtual table (unicode61) + INSERT/UPDATE/DELETE
  triggers over `messages`; queries use `snippet()`, `bm25`, `MATCH`. **Genuinely absent in Raphael.**
  Note: current impl is pure recall — no LLM summarization in the search path.
- **MEMORY.md / USER.md frozen-snapshot** — agent notes vs user knowledge, loaded as a snapshot at session
  start; mid-session edits durable on disk but NEVER touch the system prompt (preserves prefix cache).
  Single `memory` tool with `add/replace/remove` + delimiter (`§`) + unique substring match.
- **Background forked review** — after each response, a daemon agent replays the warm-cached turn and
  proposes memory/skill updates, non-blocking. Fits Raphael's background pool.
- **Memory nudge** on a turn-count threshold (`_memory_nudge_interval`).
- **Curator lifecycle** — usage telemetry → auto-archive (never delete), `created_by:"agent"` guard.
- **execute_code RPC** — auto-generated Python stubs wrap `handle_function_call()` so scripts call tools
  by name over UDS/file sockets.
- Cron scheduler (60s tick, file lock, delivery per platform). Multi-platform gateway — SKIP for personal app.

## 2. OpenJarvis (Stanford) — safety + routing
- **LoopGuard** — SHA-256 identical-call blocking, A-B-A-B ping-pong detection, poll-tool budget,
  4-stage context-overflow compression. Small and directly liftable.
- **Hybrid local↔cloud conductor** — static-DAG planner, plan-then-execute, cost/energy-aware worker pools
  (~10pp accuracy, ~15× cheaper than cloud-only).
- **Tiered proactive approval** — trivial → auto-approve / always_deny / pending queue.
- **Skills-as-markdown** (frontmatter manifests, discovered + wrapped as tools), hybrid search
  (BM25 + semantic rerank), **Windows service installer** (auto-start, restart-on-fail, loopback bind —
  no WSL/Docker), 5-primitive architecture (Intelligence/Engine/Agents/Tools/Learning).

## 3. Mark-XLVII (MARK L) — proactive / continuity
- **Proactive engine 2.0** — rotates 3 focus areas (projects→welfare→facts), gates on
  `min_silence_secs` + cooldown, injects last 8 session turns. **Superior to Raphael's proactive engine.**
- **Consumed session summaries** — `save_session_summary` (caps 3) + `pop_last_session` (returns AND deletes
  newest) so briefings never repeat it.
- **Topic monitor** — MD5-hash dedup, crypto/finance hard blocklist, 1 DDG news check/day/topic.
- **Parallel news race** — two threads (Gemini-grounded + DDG), shared result box + Event, first valid
  (>60 chars) wins, 10s timeout.
- **Telemetry** — ctypes/NVML (zero subprocess), streak-based CPU alerts (3-strike) + 300s cooldown.
- **Two-phase async brief** — greeting first, news only after phase-1 `turn_complete` + 0.8s audio buffer.
- Auto-start (winreg / LaunchAgent / autostart), QR phone dashboard — SKIP.

## 4. openclaude — plumbing (round-2 harvest; round-1 items already taken)
- **Provider abstraction + local fallback** — OpenAI-compatible shim with native Ollama tool-call parsing,
  model aliases (sonnet/opus/haiku/best → provider-aware), env-key auto-detection, schema sanitizer.
- **Rules-based permission/allowlist** — allow/deny/ask with regex/glob rules, shadowing detection,
  shell-redirection awareness.
- **Hooks decision pipeline** — pre/post tool hooks, `approve/block` + `systemMessage`, `UserPromptSubmit`.
- **MCP client** — stdio/SSE/streamable-http transports, server allow/deny, AJV JSON-schema validation.
- **Token/cost accounting** — per-model tokens, cache read/write, USD cost.
- Skill discovery, plan mode, multi-agent/statusline. Push-to-talk `services/voice.ts` mirrors Raphael's audio.

---

## Ranked extract for Raphael (value ÷ effort ÷ fit; personal / no over-engineering)

### Tier 1 — next single improvements (one at a time)
1. **Consumed morning summaries** (Mark-XLVII) — smallest; plugs into existing routine engine + memory manager.
   **→ round-2 #4 (recommended next).**
2. **LoopGuard** (OpenJarvis) — small; prevents degenerate loop/ping-pong death in a long-running voice agent.
   **→ round-2 #5 or #6.**
3. **FTS5 cross-session recall** (hermes) — most differentiating memory feature; genuinely absent; moderate effort.
   **→ round-2 #5 (if LoopGuard is #6).**

### Tier 2 — good follow-ups
4. **Proactive rotation 2.0** (Mark-XLVII) — direct upgrade to Raphael's existing proactive engine.
5. **MEMORY.md frozen-snapshot + background consolidation** (hermes) — upgrades existing memory_manager;
   snapshot-at-start + durable-mid-session-writes pattern preserves prefix cache.
6. **Parallel first-wins search** (Mark-XLVII) — tiny wiring on the existing background pool.

### Tier 3 — bigger architectural changes (multi-file; later, not single-session)
- Provider abstraction + local (Ollama) fallback (openclaude) — privacy win, but touches LLM wiring everywhere.
- Permission/allowlist system, hooks `approve/block` pipeline, MCP client upgrade, token/cost accounting,
  hybrid local↔cloud conductor, tiered proactive approval.

### Skip for a personal desktop app
Multi-platform gateway (hermes), QR phone dashboard (Mark-XLVII), ~150-skill DSPy hub, energy-per-watt
eval harness (OpenJarvis), OBS Studio integration, WinRT docs.

---

## Recommended next implementation — round-2 #4: Consumed morning summaries (Mark-XLVII pattern)
Mechanic: at session end write a 1–2 sentence summary (caps 3 entries); at morning routine, surface the
newest naturally, then **delete it** (`pop_last_session` returns AND deletes) so it never repeats.
- Fits: `memory/memory_manager.py` (add `save_session_summary` / `pop_last_session`),
  `workflows/routines.py` (morning routine calls pop), memory agent or routine prompt renders it.
- Keep simple: JSON file under the existing memory dir; cap 3; pop-on-read.
- OpenJarvis tiered approval + hermes nudge can layer onto the proactive engine later.
