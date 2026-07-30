# Raphael

**Voice-first AI Desktop Assistant for Windows** — multimodal, multi-agent, and extensible.

Raphael is a desktop AI assistant that combines voice interaction (speech recognition + text-to-speech), a PyQt6 animated HUD overlay, and a flexible orchestrator that routes tasks to specialized agents and tools. It supports multiple LLM backends, STT engines, and TTS providers, all configurable through a single `settings.toml`.

---

## Features

- **Voice-first interaction** — Speak naturally; Raphael hears you via WinRT/Whisper/Groq STT and responds with edge-tts.
- **Animated HUD** — PyQt6 overlay with splash screen, real-time log widget, and markdown rendering.
- **Multi-LLM support** — Pluggable backend registry (OpenAI-compatible, local, or cloud). Switch at runtime.
- **Specialized agents** — Manager, researcher, coding, desktop automation, browser automation, and tool-manager agents.
- **Browser automation** — Playwright-based web agent for autonomous browsing and form filling.
- **Desktop automation** — Windows UI automation (pyautogui, pywin32), screen capture, clipboard, window management.
- **File & data processing** — PDF, Word, Excel, PowerPoint, images, audio metadata, YouTube downloads.
- **C# hybrid bridge** — Native Windows modules for speech recognition, TTS, screen capture, audio device state, and system monitoring.
- **Plugin system** — Dynamic discovery and registration of plugins at startup.
- **Skill system** — Extensible skill registry (e.g., librarian skill).
- **Memory system** — Persistent file-based memory with private + shared team scopes.
- **MCP support** — Model Context Protocol server mode (`--mcp`).
- **Knowledge base** — Built-in Windows CLI, desktop, and package management knowledge.
- **OAuth/token storage** — Secure credential management for API-backed tools (e.g., Upstox).
- **PyInstaller packaging** — Build a standalone Windows executable via `raphael.spec`.
- **Inno Setup installer** — Single-file `Raphael_Setup.exe` for end-user distribution with automatic Chromium browser installation.
- **Auto-update** — Checks GitHub Releases on startup; one-click download and silent install of new versions.
- **Playwright browser automation** — Bundled Chromium browser for web automation tasks (installed on first run or via installer).

---

## Quick Start

### Prerequisites

- **Python 3.11+** (tested on 3.14)
- **Windows 10/11** (some features require native Win32/WinRT APIs)
- **C# build tools** (optional, for the hybrid bridge) — .NET 8.0+ SDK

### Install

```bash
# Clone the repo
git clone <repo-url>
cd raphael

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for browser agent)
playwright install chromium
```

### Or download the installer

Download `Raphael_Setup.exe` from the [Releases](https://github.com/indala/raphael/releases) page and run it. The installer will:

1. Install Raphael to `C:\Program Files\Raphael`
2. Offer to download Playwright Chromium browser (~300 MB)
3. Create Start Menu and Desktop shortcuts
4. Launch Raphael automatically

### Configure

Copy the example settings file and edit:

```
~/.raphael/settings.toml
```

Minimal configuration requires at least one `[[endpoints]]` entry for your LLM backend.

### Run

```bash
# Standard mode — launches the PyQt6 HUD
python main.py

# MCP server mode — runs as an MCP tool server
python main.py --mcp

# Development mode — runs dependency checks at startup
python main.py --dev

# Install/download Playwright Chromium browser (also done by the installer)
python main.py --install-playwright
```

---

## Project Structure

```
raphael/
├── main.py                   # Entry point — HUD or MCP mode
├── config.py                 # Configuration loader (settings.toml + env vars)
├── raphael.spec              # PyInstaller build spec
├── raphael.iss               # Inno Setup installer script
├── build_app.py              # Build helper — PyInstaller + browser bundling
├── raphael_mcp_server.py     # MCP server implementation
├── raphael_app/              # pip-installable package wrapper
│   ├── __init__.py
│   ├── __main__.py
│   └── entry.py              # CLI entry point (`raphael` command)
├── pyproject.toml            # Project metadata + linting/typing config
├── requirements.txt          # Python dependencies
│
├── orchestrator/             # Core orchestration
│   ├── agent_orchestrator.py # Routes tasks to agents
│   ├── endpoint_registry.py  # LLM backend resolution
│   ├── plugin.py             # Plugin discovery and lifecycle
│   ├── skill_registry.py     # Skill registration
│   ├── dep_check.py          # Dev-mode dependency checks
│   ├── updater.py            # Auto-update (GitHub release checker)
│   ├── log_utils.py          # Logging utilities (request IDs)
│   ├── mcp/                  # MCP tool implementations
│   └── tools/                # Tool implementations
│       └── native/           # Browser, weather, web, chart
│
├── agents/                   # Specialized agents
├── controller/               # System controller
├── ui/                       # PyQt6 user interface
├── hybrid/                   # C# native bridge
├── modules/                  # Pluggable backend modules (STT, TTS)
│
├── skills/                   # Skills (librarian, etc.)
├── plugins/                  # Dynamic plugins
├── actions/                  # Action registry (browser_control, etc.)
├── knowledge/                # Knowledge base
├── memory/                   # Persistent file-based memory
├── workflows/                # Workflow definitions
├── tools_meta/               # Tool metadata and sandbox
├── tests/                    # Test suite
├── assets/                   # Static assets (icons, etc.)
├── audio/                    # Audio output directory
├── docs/                     # Documentation
├── installer/                # Inno Setup output directory
└── build/                    # Build artifacts
```

---

## Configuration

Settings are loaded from `~/.raphael/settings.toml` (user config) or the `_user_settings/` directory. Environment variables take precedence over file-based values.

Key configuration options:

| Setting | Default | Description |
|---|---|---|
| `LLM_BACKEND` | `"default"` | Active LLM endpoint name |
| `TTS_BACKEND` | `"edge-tts"` | Text-to-speech engine |
| `STT_BACKEND` | `"winrt"` | Speech-to-text engine |
| `TTS_VOICE` | `"en-US-JennyNeural"` | TTS voice selection |
| `DEBUG` | `False` | Enable debug logging |

---

## Tools & Capabilities

- **Web search** — DuckDuckGo search integration
- **Web fetch** — URL content retrieval
- **Browser automation** — Playwright-based browser agent
- **Weather** — Weather lookup
- **Charts** — Static (matplotlib) and interactive (plotly) chart generation
- **File processing** — PDF, DOCX, PPTX, XLSX, images, audio
- **YouTube** — Audio search and download via yt-dlp
- **Clipboard** — Read/write system clipboard
- **Screen capture** — Fast MSS-based screen capture
- **Desktop control** — Mouse/keyboard automation, window management
- **Memory** — Persistent private/team memory storage
- **Upstox** — Stock market API integration

---

## Building

Two-step build process:

```bash
# Step 1: Build standalone executable with PyInstaller
python build_app.py

# Step 1b: (optional) Bundle Chromium browser into the .exe (~500 MB)
python build_app.py --with-browsers

# Step 2: Package into single-file Inno Setup installer
iscc raphael.iss

# Output: installer\Raphael_Setup.exe
```

> **Note:** `build_app.py` also compiles the C# hybrid bridge if `build_hybrid.py` is present, generates app icon assets, and creates a Windows Start Menu shortcut. Pass `--clean` to force a clean PyInstaller cache rebuild.

---

## License

This project is licensed under the MIT License.
