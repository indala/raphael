# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Raphael is a **Windows voice-first AI desktop assistant** (formerly CEIL). Python 3.11+/3.14, PyQt6 HUD, multi-LLM backend routing, specialized agents, tools, a C# hybrid bridge, and PyInstaller/Inno Setup packaging. Only runs on Windows (Win32/WinRT, .NET 8+ for the bridge).

## Common commands

All commands run from the repo root (`D:\lab 3\raphael`):

```bash
# Run the assistant (PyQt6 HUD)
python main.py
python main.py --dev        # dev mode: dependency checks at startup
python main.py --mcp        # run as an MCP tool server instead of the HUD
python main.py --install-playwright   # download bundled Chromium

# Tests (uses pytest)
python -m pytest tests/ -v --tb=short
python -m pytest tests/test_tool_audit.py -v     # single test file
python -m pytest tests/test_smoke.py::test_name -v   # single test

# Lint / format / type-check
ruff check .                # linter (config in pyproject.toml)
ruff format .               # formatter
mypy .                      # type checking

# Syntax check the whole tree without executing
python -m compileall -q .

# Build (two-step: executable, then installer)
python build_app.py                # PyInstaller -> dist/Raphael/
python build_app.py --clean       # wipe PyInstaller cache first
python build_app.py --skip-hybrid # don't recompile the C# bridge
python build_hybrid.py            # compiles the C# RaphaelBridge.exe
iscc raphael.iss                  # Inno Setup -> installer/Raphael_Setup.exe
```

## Architecture (the big picture)

### Entry point & config

- `main.py` is the single entry point. It suppresses Qt DPI warnings, resolves dirs, applies user settings, then launches either the PyQt6 HUD or MCP mode (`--mcp`).
- `config.py` holds all settings. **Resolved in order: defaults -> `_user_settings/settings_toml/apply_config(config)` -> environment variables (env wins).** Runtime dirs come from `_user_settings/paths.py`.
- Tests override the three dirs **before importing config** via env vars — do not import `config` above tests:
  ```
  RAPHAEL_CONFIG_DIR / RAPHAEL_DATA_DIR / RAPHAEL_ROAMING_DIR
  ```
  (see `tests/conftest.py`, which must remain the first import in the test session).

### Runtime structure

- `orchestrator/` is the core engine. `core.py` is the LLM client: it picks a backend via `endpoint_registry.py`, and on failure falls back through a list of providers (visible in logs as `Gitlawb ... -> tencent/hy3 -> mindai/...`). `error_classifier.py` maps raw API errors into typed `FailoverReason` (billing/rate-limit/auth/context-overflow/...) that `core` uses to decide fallback/retry. `_is_llm_error` (a response-content error sniffer, module-private) lives in `core.py`, **not** in `error_classifier.py`.
- `orchestrator/agent_orchestrator.py` routes tasks to **specialized agents** in `agents/` (manager, researcher, coding, browser, desktop, tool-manager, executor, ...).
- Single-purpose capabilities live in `modules/` (STT see below, TTS, clipboard, screen, weather, chart_gen, file/process/UI control). Autonomy/loop-guard/proactivity live in `orchestrator/proactive_engine.py`, `loop_guard.py`, `health_monitor.py`.
- Tools are dual-registered: the executable layer in `tools_meta/` (`registry.json`, `manager.py`, `marketplace.py`) plus orchestration in `orchestrator/tool_orchestrator.py`. `orchestrator/tool_audit.py` verifies every registered tool is ALSO exposed to the LLM in a domain map / core fallback / the prompt tool guide — a warning like `UNREACHABLE TOOL` means it is registered but the model can never call it.
- `controller/raphael_controller` ties the chat loop, voice pipeline, memory, and orchestrator together; chat-only mode engages when no mic is present.

### Voice pipeline (`modules/voice_pipeline.py`, `stt.py`, `tts.py`)

- STT backends (`modules/stt_backends/`): WinRT (streaming, main-process COM — `STT_PROCESS_ISOLATION` must be off for it), Whisper-local, Groq. No mic => chat-only WAV workflow.
- Optional VAD gate (Rhasspy-style wake -> VAD -> ASR); streaming-only backends like WinRT are excluded from it (`STT_PREFERRED_BACKENDS`, `STT_WAKE_WORDS`).
- TTS via `tts_engines.py`/`tts_registry.py` (default edge-tts).

### C# hybrid bridge (`hybrid/`)

- Python talks to native Windows code through `RaphaelBridge.exe`, a JSON stdin/stdout subprocess (`hybrid/bridge.py`, `LazyBridge.call`). Native modules: speech rec, TTS, screen capture, audio device state, system monitoring.
- Caveat: today `LazyBridge.call` swallows exceptions and returns `None`, and several C# methods (e.g. `desktop_tray_icons`) have no Python wrapper — so a `None`/missing feature does NOT mean the bridge works. `docs/architecture/bridge-framework.md` is a **draft** describing the intended manifest/provider-registry contract the current code does NOT fully implement yet.

### Memory (`memory/`)

Persistent file-based memory with private + team scopes, indexed in each scope's `MEMORY.md`. SQLite+FTS5 backend (`orchestrator/memory_agent.py`, `memory_manager`).

## Gotchas

- Lint config in `pyproject.toml` (ruff: py-314 target, line length 100, E501 ignored; imports frozen via `unfixable = ["I"]`). mypy starts strict for `orchestrator.*`.
- Never `pip install` new deps — add them to `requirements.txt` only.
- Private/underscore helpers like `_is_llm_error` must be imported from `orchestrator.core`, not `error_classifier`.
- Browser/mic/GUI features require the actual Windows session; headless/CI runs skip them (tests cover orchestrator/cron/tool logic only).