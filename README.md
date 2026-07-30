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
```

---

## Project Structure

```
raphael/
├── main.py                   # Entry point — HUD or MCP mode
├── config.py                 # Configuration loader (settings.toml + env vars)
├── raphael.spec              # PyInstaller build spec
├── raphael_mcp_server.py     # MCP server implementation
├── pyproject.toml            # Project metadata + linting/typing config
├── requirements.txt          # Python dependencies
│
├── orchestrator/             # Core orchestration
│   ├── agent_orchestrator.py # Routes tasks to agents
│   ├── endpoint_registry.py  # LLM backend resolution
│   ├── plugin.py             # Plugin discovery and lifecycle
│   ├── skill_registry.py     # Skill registration
│   ├── dep_check.py          # Dev-mode dependency checks
│   ├── log_utils.py          # Logging utilities (request IDs)
│   ├── mcp/                  # MCP tool implementations
│   └── tools/                # Tool implementations
│       └── native/           # Browser, weather, web, chart
│
├── agents/                   # Specialized agents
│   ├── manager_agent.py
│   ├── researcher_agent.py
│   ├── coding_agent.py
│   ├── desktop_agent.py
│   ├── browser_agent.py
│   └── tool_manager_agent.py
│
├── controller/               # System controller
│   └── raphael_controller.py # Main controller logic
│
├── ui/                       # PyQt6 user interface
│   └── raphael_ui.py         # HUD overlay, splash, log widget
│
├── hybrid/                   # C# native bridge
│   ├── RaphaelBridge/        # .NET C# bridge project
│   ├── AudioPlayer.cs        # Audio playback
│   ├── SpeechRecognition.cs  # WinRT speech recognition
│   ├── TtsEngine.cs          # Windows TTS engine
│   ├── ScreenCapture.cs      # Screen capture
│   ├── SystemMonitor.cs      # CPU/memory/process monitoring
│   └── ...
│
├── modules/                  # Pluggable backend modules
│   ├── stt_backends/         # Speech-to-text (WinRT, Whisper, Groq)
│   └── tts_backends/         # Text-to-speech (edge-tts, etc.)
│
├── skills/                   # Skills
│   └── librarian.py
│
├── plugins/                  # Dynamic plugins
├── actions/                  # Action registry
├── knowledge/                # Knowledge base (Windows CLI, etc.)
├── memory/                   # Persistent file-based memory
├── workflows/                # Workflow definitions
├── tools_meta/               # Tool metadata and sandbox
├── tests/                    # Test suite
├── assets/                   # Static assets
├── audio/                    # Audio output directory
├── docs/                     # Documentation
└── build/                    # Build output
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

```bash
# Build standalone executable with PyInstaller
pyinstaller raphael.spec
```

---

## License

This project is licensed under the MIT License.
