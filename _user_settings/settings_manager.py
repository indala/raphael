"""
Settings persistence layer - loads/saves settings.toml from the user data directory.

The settings file uses TOML format and stores user-editable configuration.
Module-level config.py takes precedence for hardcoded defaults and env vars;
settings.toml merges on top as the user's overrides.
"""

import re
from pathlib import Path
from typing import Any

from .paths import get_config_dir
import contextlib

SETTINGS_FILE = "settings.toml"


_SECTION_MAP: dict[str, str] = {
    "LLM_FALLBACK_BACKENDS": "llm",
    "TEXT_PRIORITY": "llm",
    "VISION_PRIORITY": "llm",
    "CODING_BACKEND": "llm",
    "CODING_MODEL": "llm",
    "CODING_FALLBACK_MODEL": "llm",
    "TTS_ENABLED": "voice",
    "TTS_ORDER": "voice",
    "TTS_BACKEND": "voice",
    "EDGETTS_VOICE": "voice",
    "TTS_RATE": "voice",
    "TTS_PITCH": "voice",
    "TTS_VOLUME": "voice",
    "STT_ENABLED": "voice",
    "STT_BACKEND": "voice",
    "STT_PREFERRED_BACKENDS": "voice",
    "STT_BATCH_PREFERRED_BACKENDS": "voice",
    "STT_WAKE_WORD_REQUIRED": "voice",
    "STT_WAKE_WORDS": "voice",
    "STT_ACTIVE_LISTENING_TIMEOUT": "voice",
    "STT_PROCESS_ISOLATION": "voice",
    "STT_WHISPER_LOCAL_MODEL": "voice",
    "INTERRUPT_WORDS": "voice",
    "MAX_HISTORY": "general",
    "EDITOR_PATH": "general",
    "CHROME_PATH": "general",
    "DEBUG": "general",
    "PROACTIVE_ENABLED": "general",
    "PROACTIVE_COOLDOWN": "general",
    "PROACTIVE_MIN_INTERVAL": "general",
    "BACKGROUND_MAX_WORKERS": "general",
    "BACKGROUND_NOTIFY_TTS": "general",
    "BACKGROUND_NOTIFY_LOG": "general",
    "BACKGROUND_RESULT_PREVIEW_CHARS": "general",
    "MAX_TOOL_RESULT_CHARS": "general",
    "LLM_READ_TIMEOUT": "general",
    "LLM_CONNECT_TIMEOUT": "general",
    "LLM_RETRY_BACKOFF": "general",
    "EMAIL_USER": "tools",
    "EMAIL_PASSWORD": "tools",
    "UPSTOX_ANALYTICS_API": "tools",
}


def settings_path() -> Path:
    return get_config_dir() / SETTINGS_FILE


def load() -> dict[str, Any]:
    """Load settings.toml from the data directory. Returns a flat key->value dict."""
    path = settings_path()
    if not path.exists():
        return {}

    try:
        import tomllib as _toml
    except ImportError:
        try:
            import importlib
            _toml = importlib.import_module("tomli")
        except ImportError:
            return _load_fallback(path)

    try:
        with open(path, "rb") as f:
            data = _toml.load(f)
    except Exception:
        return {}

    # Flatten: section.key -> uppercased key name
    flat: dict[str, Any] = {}
    for _section, values in data.items():
        if isinstance(values, dict):
            for key, val in values.items():
                flat[key.upper().strip()] = val
    return flat


def save(settings: dict[str, Any]):
    """Save flat key->value dict to settings.toml, organized by sections.

    Uses full key names to guarantee lossless roundtrip.
    """
    nested: dict[str, dict[str, Any]] = {}
    for key, val in settings.items():
        upper_key = key.upper().strip()
        section = _SECTION_MAP.get(upper_key, "general")
        if section not in nested:
            nested[section] = {}
        nested[section][upper_key] = val

    path = settings_path()
    with open(path, "w", encoding="utf-8") as f:
        first = True
        for section, values in nested.items():
            if not first:
                f.write("\n")
            first = False
            f.write(f"[{section}]\n")
            for key, val in values.items():
                if val is not None and val != "":
                    f.write(_toml_value(key.lower(), val) + "\n")


def _toml_value(key: str, val: Any) -> str:
    if isinstance(val, bool):
        return f"{key} = {'true' if val else 'false'}"
    elif isinstance(val, (int, float)):
        return f"{key} = {val}"
    elif isinstance(val, list):
        items = ", ".join(f'"{v}"' for v in val)
        return f"{key} = [{items}]"
    else:
        s = str(val).replace("\\", "\\\\").replace('"', '\\"')
        return f'{key} = "{s}"'


def _to_toml_key(upper_key: str) -> str:
    prefix_map = [
        "LLM_", "STT_", "TTS_", "BACKGROUND_", "PROACTIVE_", "MAX_",
        "CODING_", "UPSTOX_",
    ]
    result = upper_key
    for prefix in prefix_map:
        if result.startswith(prefix):
            result = result[len(prefix):]
            break
    return result.lower()


def _load_fallback(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    flat: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if re.match(r"^\[.+]$$", line):
            continue
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.lower() in ("true", "false"):
                val = val.lower() == "true"  # type: ignore[assignment]
            else:
                try:
                    val = int(val)  # type: ignore[assignment]
                except ValueError:
                    with contextlib.suppress(ValueError):
                        val = float(val)  # type: ignore[assignment]
            flat[key.upper()] = val
    return flat


def apply_to_config(config_module):
    """Merge loaded settings into a config module's namespace."""
    settings = load()
    for key, val in settings.items():
        if not hasattr(config_module, key):
            continue
        existing = getattr(config_module, key)
        if isinstance(existing, bool):
            setattr(config_module, key, bool(val) if not isinstance(val, bool) else val)
        elif isinstance(existing, int):
            setattr(config_module, key, int(val))
        elif isinstance(existing, float):
            setattr(config_module, key, float(val))
        elif (isinstance(existing, str) and isinstance(val, str)) or (isinstance(existing, list) and isinstance(val, list)):
            setattr(config_module, key, val)
