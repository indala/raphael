"""
Raphael Agent Configuration

Settings are loaded from ~/.raphael/settings.toml.
settings.toml is the ONLY source of configuration — no environment
variable fallbacks are supported.
"""

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
LLM_BACKEND = "default"

# ============================================================
# Voice / TTS Configuration
# ============================================================
TTS_ENABLED = True
TTS_BACKEND = "edge-tts"
TTS_ORDER = ["edge-tts"]

# Edge TTS voice (e.g. en-US-JennyNeural)
TTS_VOICE = "en-US-JennyNeural"
EDGETTS_VOICE = "en-US-JennyNeural"

# TTS rate/pitch/volume (persisted from Settings UI)
TTS_RATE = "+0%"
TTS_PITCH = "+0Hz"
TTS_VOLUME = "+0%"

# ============================================================
# Speech-to-Text — Multi-Backend
# ============================================================
STT_ENABLED = True
STT_DEVICE_ID = 1

# Backend selection: ordered fallback list (STT_PREFERRED_BACKENDS).
# Cloud / API STT comes from any endpoint that declares an stt_model.
STT_BACKEND = "moonshine"
STT_PREFERRED_BACKENDS = ["moonshine"]
STT_MOONSHINE_MODEL = "moonshine/tiny"

STT_PROCESS_ISOLATION = True

STT_WAKE_WORD_REQUIRED = True
STT_WAKE_WORDS = ["hey raphael", "raphael", "hey rafael", "rafael"]
STT_MUTED = False
STT_AUDIO_INPUT_AVAILABLE = True
STT_LOG_IGNORED = True
STT_ACTIVE_LISTENING_TIMEOUT = 300

# ── Voice pipeline (VAD gate) — Rhasspy-style wake→VAD→ASR ──
# When enabled, the mic is gated by a voice-activity detector instead of
# streaming continuously to an ASR engine. Requires a batch-capable STT
# backend (winrt is streaming-only and excluded). Degrades gracefully.
STT_USE_VAD_GATE = True
# Batch ASR backends used for on-demand utterances (winrt cannot batch).
# When unset, the VAD gate falls back to STT_PREFERRED_BACKENDS so a single
# stt_preferred_backends setting is honored app-wide.
STT_BATCH_PREFERRED_BACKENDS: list[str] = []
# VAD engine: "auto" (silero if model present, else energy), "silero", "energy"
VAD_ENGINE = "auto"
# silero-vad ONNX model (download silero_vad.onnx here to enable it)
VAD_MODEL_PATH = str(
    Path(__file__).resolve().parent / "assets" / "models" / "silero_vad.onnx"
)
VAD_RMS_THRESHOLD = 0.005
# Max length (ms) of a wake-word probe utterance
STT_WAKE_PROBE_MS = 1500
# Min utterance length (ms) before ASR is attempted
STT_MIN_UTTERANCE_MS = 350
# Frames (32 ms each) of trailing silence that end an utterance
STT_VAD_TAIL_FRAMES = 10

# Cloud STT fallback keys
# Cloud STT API keys are shared with LLM backend config above

# ── Proactive Engine ──
# After PROACTIVE_COOLDOWN seconds of inactivity, sends a read-only
# LLM check-in for idle reminders, system alerts, time-based suggestions.
PROACTIVE_ENABLED = True
PROACTIVE_COOLDOWN = 60
PROACTIVE_MIN_INTERVAL = 120

# Topic monitoring with DDG news (inspired by Mark-XLVII)
PROACTIVE_TOPICS_ENABLED = True
PROACTIVE_DDG_CHECK_INTERVAL_HOURS = 24.0
PROACTIVE_MAX_TOPICS = 5

# Event watching (reminders)
PROACTIVE_REMINDERS_ENABLED = True

# Storage location for proactive engine data
PROACTIVE_STORAGE_DIR = DATA_DIR / "proactive"

# ── Performance Baseline ──
# When True, the LLM turn pipeline is wrapped in BaselineRecorder, which
# samples stage timings (total turn, prompt build, routing, tool exec)
# and writes baseline_YYYYMMDD.json (p50/p95/p99) under DATA_DIR/baselines.
# Default False — the recorder is a no-op while disabled.
PERF_BASELINE_ENABLED = False

# ── Cron Scheduler ──
# Background job scheduler inspired by hermes-agent/cron/
# Jobs are defined in _user_settings/cron/jobs.json
CRON_ENABLED = True
CRON_TICK_INTERVAL = 60  # seconds
CRON_MAX_PARALLEL_JOBS = 5
CRON_SCRIPT_TIMEOUT = 3600  # 1 hour
CRON_JOB_DIR = DATA_DIR / "cron"
CRON_VERBOSE_LOGGING = False

# ── Remote Marketplace Integration ──
# Support for multiple AI skill marketplaces (2026)
# Supported sources: skillexchange, smithery, agensi, promptspace, skills_sh, skillsmp, claudeskills
MARKETPLACE_REMOTE_ENABLED = False
MARKETPLACE_SOURCE = "skillexchange"
MARKETPLACE_AUTO_UPDATE = False

# ── MCP (Model Context Protocol) ──
# Each entry defines an MCP server process. Servers are spawned on first use.
# Tools are prefixed "mcp_<server>_<tool>" and auto-registered.
MCP_SERVERS = ""
# JSON blob of user-defined custom MCP server configs.
MCP_SERVERS_JSON = ""

INTERRUPT_WORDS = ["stop", "cancel", "shut up", "quiet", "enough", "never mind", "abort"]

# ============================================================
# LoopGuard — tool-loop breakers (OpenJarvis pattern)
# ============================================================
# Guards the LLM tool-call loop against degenerate repetition:
#   * IDENTICAL   — same exact tool call (args hashed) N times in a row
#   * PINGPONG    — A/B/A/B… oscillation between two tools
#   * POLL_BUDGET — cap on poll/status-style calls per request
# Warnings are injected rather than hard-failing the request.
LOOP_GUARD_ENABLED = True
LOOP_GUARD_IDENTICAL_THRESHOLD = 3
LOOP_GUARD_PINGPONG_THRESHOLD = 4
LOOP_GUARD_POLL_BUDGET = 5

# ============================================================
# Endpoint Health Checking
# ============================================================
# Probe all configured endpoints on startup in parallel
ENDPOINT_HEALTH_CHECK = False

# ============================================================
# Prompt Caching (Anthropic)
# ============================================================
# When enabled, Raphael injects cache_control breakpoints into requests sent
# to Anthropic-compatible endpoints (claude-* models / api.anthropic.com).
# Reduces cost by up to 90% on long sessions by caching the system prompt
# and stable history. Opt-in because it modifies the message structure.
ANTHROPIC_PROMPT_CACHE = False

# ============================================================
# Background Self-Improvement Reviewer
# ============================================================
# After every turn, spawn a silent daemon thread that reviews the exchange for:
# (1) behavioral corrections, (2) new user facts. Writes to agent_evolution.json
# and memory. Surfaces a one-line UI log when something is saved.
BACKGROUND_REVIEWER_ENABLED = True
BACKGROUND_REVIEWER_MODEL = ""  # empty = use main model
BACKGROUND_REVIEWER_MIN_TURN_CHARS = 60

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
    "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
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
EMAIL_USER = ""
EMAIL_PASSWORD = ""
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# ============================================================
# External MCP Server Credentials
# ============================================================
POSTGRES_URL = ""
GITHUB_TOKEN = ""

# ============================================================
# LLM Priorities (Text and Vision)
# ============================================================
TEXT_PRIORITY: list[str] = []
VISION_PRIORITY: list[str] = []

# ============================================================
# Stock Analytics (Upstox)
# ============================================================
UPSTOX_ANALYTICS_API = ""
UPSTOX_API_KEY = ""

# ============================================================
# System Settings
# ============================================================
MAX_HISTORY = 50
SCREENSHOT_DIR = str(_DATA_DIR / "outputs")
CHART_DIR = str(_DATA_DIR / "outputs")
DEBUG = False
# Manual speaker-presence override ("" = auto-detect via pycaw).
HAS_SPEAKER = ""

# ============================================================
# Task 19: Adaptive Model Fallback & State Management
# ============================================================
MODEL_STATE_TRACKING_ENABLED = True

# Exponential backoff for rate limits: base * (2 ^ failures)
MODEL_BACKOFF_BASE_SECONDS = 2
MODEL_BACKOFF_MAX_SECONDS = 600  # 10 minutes

# Request deduplication: cache LLM responses for this long
MODEL_CACHE_TTL_SECONDS = 300  # 5 minutes

# Endpoints to monitor (populated by endpoint_registry)
MONITORED_ENDPOINTS = {
    "openrouter": {
        "fallback_models": [
            "openrouter/openrouter/free",
            "openrouter/mistralai/mistral-nemo:free",
            "openrouter/cohere/north-mini-code:free",
        ]
    },
    "mistral": {
        "fallback_models": ["mistral-small-latest", "mistral-tiny-latest"]
    },
    "opencode": {
        "fallback_models": ["ling-3.0-flash-free"]
    },
}

# ============================================================
# Background Task Runner
# ============================================================
BACKGROUND_MAX_WORKERS = 4
BACKGROUND_NOTIFY_TTS = True
BACKGROUND_NOTIFY_LOG = True
BACKGROUND_RESULT_PREVIEW_CHARS = 300

# ============================================================
# Performance & Streaming
# ============================================================
MAX_TOOL_RESULT_CHARS = 5000
LLM_READ_TIMEOUT = 180
LLM_CONNECT_TIMEOUT = 10
LLM_RETRY_BACKOFF = 1.5

# ============================================================
# Task 11: Write-Invalidation Map & Background Cooldown
# ============================================================
# Cache invalidation triggers: when certain tools are executed, which caches
# should be invalidated? Maps tool name → list of cache namespaces to clear.
# Used by agent_orchestrator to invalidate routing cache when context changes.
WRITE_INVALIDATION_MAP = {
    # File operations invalidate all caches (context may have changed)
    "write_file": ["routing", "memory"],
    "edit_file": ["routing", "memory"],
    "save_output": ["routing"],
    "process_file": ["routing"],
    # Tool registry changes (add/remove tools) invalidate routing
    "reload_tools": ["routing", "tool_guide"],
    # Memory operations invalidate routing cache
    "save_memory": ["routing", "memory"],
    "delete_memory": ["routing", "memory"],
    # Browser/desktop state changes
    "browser_control": ["routing"],
    "desktop_snapshot_v2": ["routing"],
    "launch_app": ["routing"],
    "run_command": ["routing"],
    # UI operations
    "ui_click": ["routing"],
    "ui_type_text": ["routing"],
}

# Background task execution constraints (Task 11)
BACKGROUND_COOLDOWN_SECONDS = 30  # Min time between background task submissions
BACKGROUND_MAX_CONCURRENT = 3  # Max concurrent background tasks
BACKGROUND_TASK_TIMEOUT = 300  # Timeout for background tasks (seconds)
BACKGROUND_RESULT_DELIVERY_DELAY = 1.0  # Delay before delivering BG result to UI (seconds)

# ============================================================
# Overlay user settings from settings.toml (user data dir)
# settings.toml is the single source of configuration.
# ============================================================
try:
    import sys
    from _user_settings.settings_manager import apply_to_config
    apply_to_config(sys.modules[__name__])
except Exception:
    pass

# Ensure UPSTOX_API_KEY is synchronized with UPSTOX_ANALYTICS_API
if UPSTOX_ANALYTICS_API != "":
    UPSTOX_API_KEY = UPSTOX_ANALYTICS_API

# Synchronize LLM_BACKEND with primary text priority backend
if TEXT_PRIORITY:
    LLM_BACKEND = TEXT_PRIORITY[0]

# Synchronize TTS_VOICE with active engine-specific voice config
if TTS_BACKEND == "edge-tts" and EDGETTS_VOICE:
    TTS_VOICE = EDGETTS_VOICE

# Keep process isolation enabled for isolated STT execution
STT_PROCESS_ISOLATION = True
