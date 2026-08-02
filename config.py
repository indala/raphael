"""
Raphael Agent Configuration

Settings are loaded from ~/.raphael/settings.toml.
Environment variables take precedence over settings.toml values.
"""

import os
from pathlib import Path

VERSION = "0.1.0"

# Resolve user settings, data, and roaming directories
try:
    from _user_settings.paths import get_config_dir, get_data_dir, get_roaming_dir
    CONFIG_DIR = get_config_dir()
    DATA_DIR = get_data_dir()
    ROAMING_DIR = get_roaming_dir()
except Exception:
    CONFIG_DIR = Path(".").resolve()
    DATA_DIR = Path(".").resolve()
    ROAMING_DIR = Path(".").resolve()

ROOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT_DIR

# Backward compatibility alias
_DATA_DIR = DATA_DIR

# ============================================================
# LLM Backend — resolved dynamically via endpoint_registry (settings.toml)
# ============================================================
LLM_BACKEND = os.getenv("LLM_BACKEND", "default")

# ============================================================
# Voice / TTS Configuration
# ============================================================
TTS_ENABLED = True
TTS_BACKEND = os.getenv("TTS_BACKEND", "edge-tts")
TTS_ORDER = os.getenv("TTS_ORDER", "edge-tts").split(",")

# Edge TTS voice (e.g. en-US-JennyNeural)
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-JennyNeural")
EDGETTS_VOICE = os.getenv("EDGETTS_VOICE", "en-US-JennyNeural")

# TTS rate/pitch/volume (persisted from Settings UI)
TTS_RATE = "+0%"
TTS_PITCH = "+0Hz"
TTS_VOLUME = "+0%"

# ============================================================
# Speech-to-Text — Multi-Backend
# ============================================================
STT_ENABLED = True
STT_DEVICE_ID = 1

# Backend selection: comma-separated fallback order
# e.g. "groq,azure" = try Groq first, fall to Azure
# Cloud STT
STT_BACKEND = os.getenv("STT_BACKEND", "winrt")
STT_PREFERRED_BACKENDS = os.getenv("STT_PREFERRED_BACKENDS", "winrt,whisper_local,groq").split(",")
STT_WHISPER_LOCAL_MODEL = os.getenv("STT_WHISPER_LOCAL_MODEL", "base")
STT_WHISPER_DEVICE = os.getenv("STT_WHISPER_DEVICE", "auto")

# Process isolation — disabled by default because WinRT SpeechRecognizer
# requires main-process COM apartment + microphone permissions (subprocess
# breaks speech detection). Enable for cloud-only backends.
STT_PROCESS_ISOLATION = os.getenv("STT_PROCESS_ISOLATION", "false").lower() in ("1", "true", "yes")

STT_WAKE_WORD_REQUIRED = True
STT_WAKE_WORDS = os.getenv("STT_WAKE_WORDS", "hey raphael,raphael,hey rafael,rafael").split(",")
STT_MUTED = False
STT_AUDIO_INPUT_AVAILABLE = True
STT_LOG_IGNORED = True
STT_ACTIVE_LISTENING_TIMEOUT = 300

# Cloud STT fallback keys
# Cloud STT API keys are shared with LLM backend config above

# ── Proactive Engine ──
# After PROACTIVE_COOLDOWN seconds of inactivity, sends a read-only
# LLM check-in for idle reminders, system alerts, time-based suggestions.
PROACTIVE_ENABLED = os.getenv("PROACTIVE_ENABLED", "true").lower() in ("1", "true", "yes")
PROACTIVE_COOLDOWN = int(os.getenv("PROACTIVE_COOLDOWN", "60"))
PROACTIVE_MIN_INTERVAL = int(os.getenv("PROACTIVE_MIN_INTERVAL", "120"))

# ── MCP (Model Context Protocol) ──
# Each entry defines an MCP server process. Servers are spawned on first use.
# Tools are prefixed "mcp_<server>_<tool>" and auto-registered.
MCP_SERVERS = os.getenv("MCP_SERVERS", "")

INTERRUPT_WORDS = os.getenv("INTERRUPT_WORDS",
    "stop,cancel,shut up,quiet,enough,never mind,abort").split(",")

# ============================================================
# Application Registry
# ============================================================
APPS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "chrome": os.getenv("CHROME_PATH", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"),
    "edge": "msedge.exe",
    "vscode": "code",
    "youtube": "https://youtube.com",
    "github": "https://github.com",
    "gmail": "https://gmail.com",
    "spotify": "spotify",
}

# ============================================================
# Email Integration
# ============================================================
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

# ============================================================
# LLM Priorities (Text and Vision)
# ============================================================
TEXT_PRIORITY: list[str] = []
VISION_PRIORITY: list[str] = []

# ============================================================
# Stock Analytics (Upstox)
# ============================================================
UPSTOX_ANALYTICS_API = os.getenv("UPSTOX_ANALYTICS_API", "")
UPSTOX_API_KEY = os.getenv("UPSTOX_ANALYTICS_API", "")

# ============================================================
# System Settings
# ============================================================
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "50"))
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR") or str(_DATA_DIR / "outputs")
CHART_DIR = os.getenv("CHART_DIR") or str(_DATA_DIR / "outputs")
DEBUG = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")

# ============================================================
# Background Task Runner
# ============================================================
BACKGROUND_MAX_WORKERS = int(os.getenv("BACKGROUND_MAX_WORKERS", "4"))
BACKGROUND_NOTIFY_TTS = os.getenv("BACKGROUND_NOTIFY_TTS", "true").lower() in ("1", "true")
BACKGROUND_NOTIFY_LOG = os.getenv("BACKGROUND_NOTIFY_LOG", "true").lower() in ("1", "true")
BACKGROUND_RESULT_PREVIEW_CHARS = int(os.getenv("BACKGROUND_RESULT_PREVIEW_CHARS", "300"))

# ============================================================
# Performance & Streaming
# ============================================================
MAX_TOOL_RESULT_CHARS = int(os.getenv("MAX_TOOL_RESULT_CHARS", "5000"))
LLM_READ_TIMEOUT = int(os.getenv("LLM_READ_TIMEOUT", "180"))
LLM_CONNECT_TIMEOUT = int(os.getenv("LLM_CONNECT_TIMEOUT", "10"))
LLM_RETRY_BACKOFF = float(os.getenv("LLM_RETRY_BACKOFF", "1.5"))

# ============================================================
# Overlay user settings from settings.toml (user data dir)
# settings.toml values take precedence over env defaults but
# not over directly-set environment variables.
# ============================================================
try:
    import sys
    from _user_settings.settings_manager import apply_to_config
    apply_to_config(sys.modules[__name__])
except Exception:
    pass

# Ensure UPSTOX_API_KEY is synchronized with UPSTOX_ANALYTICS_API
if UPSTOX_ANALYTICS_API:
    UPSTOX_API_KEY = UPSTOX_ANALYTICS_API

# Synchronize LLM_BACKEND with primary text priority backend
if TEXT_PRIORITY:
    LLM_BACKEND = TEXT_PRIORITY[0]

# Synchronize TTS_VOICE with active engine-specific voice config
if TTS_BACKEND == "edge-tts" and EDGETTS_VOICE:
    TTS_VOICE = EDGETTS_VOICE
