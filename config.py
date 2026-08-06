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

# ── Voice pipeline (VAD gate) — Rhasspy-style wake→VAD→ASR ──
# When enabled, the mic is gated by a voice-activity detector instead of
# streaming continuously to an ASR engine. Requires a batch-capable STT
# backend (winrt is streaming-only and excluded). Degrades gracefully.
STT_USE_VAD_GATE = os.getenv("STT_USE_VAD_GATE", "true").lower() in ("1", "true", "yes")
# Batch ASR backends used for on-demand utterances (winrt cannot batch).
# When unset, the VAD gate falls back to STT_PREFERRED_BACKENDS so a single
# stt_preferred_backends setting is honored app-wide.
_BATCH_PREFS_ENV = os.getenv("STT_BATCH_PREFERRED_BACKENDS", "").strip()
STT_BATCH_PREFERRED_BACKENDS = (
    [p.strip() for p in _BATCH_PREFS_ENV.split(",") if p.strip()] if _BATCH_PREFS_ENV else []
)
# VAD engine: "auto" (silero if model present, else energy), "silero", "energy"
VAD_ENGINE = os.getenv("VAD_ENGINE", "auto")
# silero-vad ONNX model (download silero_vad.onnx here to enable it)
VAD_MODEL_PATH = os.getenv(
    "VAD_MODEL_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "models", "silero_vad.onnx"),
)
VAD_RMS_THRESHOLD = float(os.getenv("VAD_RMS_THRESHOLD", "0.005"))
# Max length (ms) of a wake-word probe utterance
STT_WAKE_PROBE_MS = int(os.getenv("STT_WAKE_PROBE_MS", "1500"))
# Min utterance length (ms) before ASR is attempted
STT_MIN_UTTERANCE_MS = int(os.getenv("STT_MIN_UTTERANCE_MS", "350"))
# Frames (32 ms each) of trailing silence that end an utterance
STT_VAD_TAIL_FRAMES = int(os.getenv("STT_VAD_TAIL_FRAMES", "10"))

# Cloud STT fallback keys
# Cloud STT API keys are shared with LLM backend config above

# ── Proactive Engine ──
# After PROACTIVE_COOLDOWN seconds of inactivity, sends a read-only
# LLM check-in for idle reminders, system alerts, time-based suggestions.
PROACTIVE_ENABLED = os.getenv("PROACTIVE_ENABLED", "true").lower() in ("1", "true", "yes")
PROACTIVE_COOLDOWN = int(os.getenv("PROACTIVE_COOLDOWN", "60"))
PROACTIVE_MIN_INTERVAL = int(os.getenv("PROACTIVE_MIN_INTERVAL", "120"))

# Topic monitoring with DDG news (inspired by Mark-XLVII)
PROACTIVE_TOPICS_ENABLED = os.getenv("PROACTIVE_TOPICS_ENABLED", "true").lower() in ("1", "true", "yes")
PROACTIVE_DDG_CHECK_INTERVAL_HOURS = float(os.getenv("PROACTIVE_DDG_CHECK_INTERVAL_HOURS", "24"))
PROACTIVE_MAX_TOPICS = int(os.getenv("PROACTIVE_MAX_TOPICS", "5"))

# Event watching (reminders)
PROACTIVE_REMINDERS_ENABLED = os.getenv("PROACTIVE_REMINDERS_ENABLED", "true").lower() in ("1", "true", "yes")

# Storage location for proactive engine data
PROACTIVE_STORAGE_DIR = DATA_DIR / "proactive"

# ── Cron Scheduler ──
# Background job scheduler inspired by hermes-agent/cron/
# Jobs are defined in _user_settings/cron/jobs.json
CRON_ENABLED = os.getenv("CRON_ENABLED", "true").lower() in ("1", "true", "yes")
CRON_TICK_INTERVAL = int(os.getenv("CRON_TICK_INTERVAL", "60"))  # seconds
CRON_MAX_PARALLEL_JOBS = int(os.getenv("CRON_MAX_PARALLEL_JOBS", "5"))
CRON_SCRIPT_TIMEOUT = int(os.getenv("CRON_SCRIPT_TIMEOUT", "3600"))  # 1 hour
CRON_JOB_DIR = DATA_DIR / "cron"
CRON_VERBOSE_LOGGING = os.getenv("CRON_VERBOSE_LOGGING", "false").lower() in ("1", "true", "yes")

# ── Remote Marketplace Integration ──
# Support for multiple AI skill marketplaces (2026)
# Supported sources: skillexchange, smithery, agensi, promptspace, skills_sh, skillsmp, claudeskills
MARKETPLACE_REMOTE_ENABLED = os.getenv("MARKETPLACE_REMOTE_ENABLED", "false").lower() in ("1", "true", "yes")
MARKETPLACE_SOURCE = os.getenv("MARKETPLACE_SOURCE", "skillexchange")
MARKETPLACE_AUTO_UPDATE = os.getenv("MARKETPLACE_AUTO_UPDATE", "false").lower() in ("1", "true", "yes")

# ── MCP (Model Context Protocol) ──
# Each entry defines an MCP server process. Servers are spawned on first use.
# Tools are prefixed "mcp_<server>_<tool>" and auto-registered.
MCP_SERVERS = os.getenv("MCP_SERVERS", "")

INTERRUPT_WORDS = os.getenv("INTERRUPT_WORDS",
    "stop,cancel,shut up,quiet,enough,never mind,abort").split(",")

# ============================================================
# LoopGuard — tool-loop breakers (OpenJarvis pattern)
# ============================================================
# Guards the LLM tool-call loop against degenerate repetition:
#   * IDENTICAL   — same exact tool call (args hashed) N times in a row
#   * PINGPONG    — A/B/A/B… oscillation between two tools
#   * POLL_BUDGET — cap on poll/status-style calls per request
# Warnings are injected rather than hard-failing the request.
LOOP_GUARD_ENABLED = os.getenv("LOOP_GUARD_ENABLED", "true").lower() in ("1", "true", "yes")
LOOP_GUARD_IDENTICAL_THRESHOLD = int(os.getenv("LOOP_GUARD_IDENTICAL_THRESHOLD", "3"))
LOOP_GUARD_PINGPONG_THRESHOLD = int(os.getenv("LOOP_GUARD_PINGPONG_THRESHOLD", "4"))
LOOP_GUARD_POLL_BUDGET = int(os.getenv("LOOP_GUARD_POLL_BUDGET", "5"))

# ============================================================
# Endpoint Health Checking
# ============================================================
# Probe all configured endpoints on startup in parallel
ENDPOINT_HEALTH_CHECK = os.getenv("ENDPOINT_HEALTH_CHECK", "false").lower() in ("1", "true", "yes")

# ============================================================
# Prompt Caching (Anthropic)
# ============================================================
# When enabled, Raphael injects cache_control breakpoints into requests sent
# to Anthropic-compatible endpoints (claude-* models / api.anthropic.com).
# Reduces cost by up to 90% on long sessions by caching the system prompt
# and stable history. Opt-in because it modifies the message structure.
ANTHROPIC_PROMPT_CACHE = os.getenv("ANTHROPIC_PROMPT_CACHE", "false").lower() in ("1", "true", "yes")

# ============================================================
# Background Self-Improvement Reviewer
# ============================================================
# After every turn, spawn a silent daemon thread that reviews the exchange for:
# (1) behavioral corrections, (2) new user facts. Writes to agent_evolution.json
# and memory. Surfaces a one-line UI log when something is saved.
BACKGROUND_REVIEWER_ENABLED = os.getenv("BACKGROUND_REVIEWER_ENABLED", "true").lower() in ("1", "true", "yes")
BACKGROUND_REVIEWER_MODEL = os.getenv("BACKGROUND_REVIEWER_MODEL", "")  # empty = use main model
BACKGROUND_REVIEWER_MIN_TURN_CHARS = int(os.getenv("BACKGROUND_REVIEWER_MIN_TURN_CHARS", "60"))

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
