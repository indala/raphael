"""
Endpoint Registry — dynamic LLM backend configuration.

Manages a list of endpoint profiles (name, base_url, api_key, models, priority)
persisted in settings.toml. Replaces the hardcoded 5-backend system in config.py.

Each endpoint represents one OpenAI-compatible API endpoint.
Priority determines the fallback order (lower = higher priority).
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Endpoint:
    """A single LLM endpoint profile."""

    name: str
    base_url: str
    api_key: str = ""
    text_model: str = ""
    vision_model: str = ""
    fallback_model: str = ""
    stt_model: str = ""
    tts_model: str = ""
    priority: int = 0
    fallback_models: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return bool(self.name and self.base_url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "text_model": self.text_model,
            "vision_model": self.vision_model,
            "fallback_model": self.fallback_model,
            "fallback_models": self.fallback_models,
            "stt_model": self.stt_model,
            "tts_model": self.tts_model,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Endpoint:
        fallback_models = d.get("fallback_models", [])
        if not isinstance(fallback_models, list):
            fallback_models = [str(fallback_models)] if fallback_models else []

        fallback_model = d.get("fallback_model", "")
        if not fallback_models and fallback_model:
            fallback_models = [fallback_model]
        elif fallback_models and not fallback_model:
            fallback_model = fallback_models[0] if fallback_models else ""

        return cls(
            name=d.get("name", ""),
            base_url=d.get("base_url", "").rstrip("/"),
            api_key=d.get("api_key", ""),
            text_model=d.get("text_model", ""),
            vision_model=d.get("vision_model", ""),
            fallback_model=fallback_model,
            fallback_models=fallback_models,
            stt_model=d.get("stt_model", ""),
            tts_model=d.get("tts_model", ""),
            priority=int(d.get("priority", 0)),
        )


# ── In-memory registry ───────────────────────────────────────
_registry: dict[str, Endpoint] = {}
_loaded: bool = False


# ── Public API ────────────────────────────────────────────────


def load() -> list[Endpoint]:
    """Load endpoints from settings.toml. Returns empty list if none configured.

    API keys are read directly from [[endpoints]] in settings.toml — no env vars.
    The user adds and manages endpoints via the Settings UI.
    """
    global _loaded
    items = _load_from_settings()
    _loaded = True
    _rebuild_index(items)
    return items


def get(name: str) -> Endpoint | None:
    """Get a single endpoint by name."""
    if not _loaded:
        load()
    return _registry.get(name)


def all() -> list[Endpoint]:
    """Return all registered endpoints in their loaded/added order."""
    if not _loaded:
        load()
    return list(_registry.values())


def add(endpoint: Endpoint) -> None:
    """Add or replace an endpoint. Persists to settings.toml."""
    _registry[endpoint.name] = endpoint
    _save_to_settings(all())


def remove(name: str) -> bool:
    """Remove an endpoint by name. Returns True if existed."""
    if name in _registry:
        del _registry[name]
        _save_to_settings(all())
        return True
    return False


def update(name: str, **kwargs) -> Endpoint | None:
    """Update fields on an existing endpoint. Returns the updated endpoint or None."""
    ep = _registry.get(name)
    if not ep:
        return None
    for key, val in kwargs.items():
        if hasattr(ep, key):
            setattr(ep, key, val)
    _save_to_settings(all())
    return ep


def _rebuild_index(items: list[Endpoint]) -> None:
    _registry.clear()
    for ep in items:
        _registry[ep.name] = ep


def _settings_path() -> Path:
    """Resolve settings.toml path."""
    try:
        from _user_settings.paths import get_config_dir
        return get_config_dir() / "settings.toml"
    except Exception:
        return Path.home() / ".raphael" / "settings.toml"


# ── LLM config (priority lists) ──────────────────────────────

_llm_config: dict | None = None


def _load_llm_config() -> dict:
    """Load the [llm] section from settings.toml (cached)."""
    global _llm_config
    if _llm_config is not None:
        return _llm_config

    path = _settings_path()
    if not path.exists():
        _llm_config = {}
        return _llm_config

    try:
        import tomllib as _toml_lib
    except ImportError:
        try:
            import tomli as _toml_lib  # type: ignore[no-redef]
        except ImportError:
            _llm_config = {}
            return _llm_config

    try:
        with open(path, "rb") as f:
            data = _toml_lib.load(f)
        _llm_config = data.get("llm", {})
    except Exception:
        _llm_config = {}

    return _llm_config


def reload_llm_config() -> None:
    """Force re-read of [llm] section on next access."""
    global _llm_config
    _llm_config = None


def get_text_priority() -> list[str]:
    """Return the ordered list of endpoint names for text/chat tasks.

    Reads from settings.toml ``[llm].text_priority``. Returns empty list if
    not configured — callers should fall back to :func:`all()` order.
    """
    cfg = _load_llm_config()
    raw = cfg.get("text_priority", [])
    if isinstance(raw, list):
        return [str(n) for n in raw]
    return []


def get_vision_priority() -> list[str]:
    """Return the ordered list of endpoint names for vision tasks.

    Reads from settings.toml ``[llm].vision_priority``. Returns empty list if
    not configured — callers should fall back to text priority or all().
    """
    cfg = _load_llm_config()
    raw = cfg.get("vision_priority", [])
    if isinstance(raw, list):
        return [str(n) for n in raw]
    return []


def _load_from_settings() -> list[Endpoint]:
    """Parse endpoints from the [[endpoints]] TOML table."""
    path = _settings_path()
    if not path.exists():
        return []

    try:
        import tomllib as _toml_lib
    except ImportError:
        try:
            import tomli as _toml_lib  # type: ignore[no-redef]
        except ImportError:
            logger.warning("No TOML parser available for endpoint registry")
            return []

    try:
        with open(path, "rb") as f:
            data = _toml_lib.load(f)
    except Exception as e:
        logger.warning("Failed to parse settings.toml: %s", e)
        return []

    raw_list = data.get("endpoints", [])
    if isinstance(raw_list, dict):
        raw_list = [raw_list]
    if not isinstance(raw_list, list):
        return []

    return [Endpoint.from_dict(item) for item in raw_list if isinstance(item, dict)]


def _save_to_settings(endpoints: list[Endpoint]) -> None:
    """Write endpoints as TOML [[endpoints]] entries into settings.toml."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing settings.toml to preserve other sections
    existing_text = ""
    with contextlib.suppress(FileNotFoundError, OSError):
        existing_text = path.read_text(encoding="utf-8")

    # Strip existing [[endpoints]] section and any blank lines after it
    lines = existing_text.splitlines(keepends=True) if existing_text else []
    kept_lines: list[str] = []
    in_endpoints = False
    for line in lines:
        stripped = line.strip()
        if stripped == "[[endpoints]]":
            in_endpoints = True
            continue
        if in_endpoints:
            if stripped.startswith("[") or stripped == "":
                in_endpoints = False
                if stripped.startswith("["):
                    kept_lines.append(line)
            continue
        kept_lines.append(line)

    # Build the new [[endpoints]] block
    ep_lines: list[str] = []
    for ep in endpoints:
        ep_lines.append("[[endpoints]]\n")
        for key, val in ep.to_dict().items():
            if key in ("priority", "fallback_model"):
                continue
            if isinstance(val, list):
                if val:
                    items = ", ".join(f'"{v}"' for v in val)
                    ep_lines.append(f'{key} = [{items}]\n')
                else:
                    ep_lines.append(f"{key} = []\n")
            elif isinstance(val, bool):
                ep_lines.append(f"{key} = {'true' if val else 'false'}\n")
            elif isinstance(val, int):
                ep_lines.append(f"{key} = {val}\n")
            elif val:  # non-empty string
                s = str(val).replace("\\", "\\\\").replace('"', '\\"')
                ep_lines.append(f'{key} = "{s}"\n')
        ep_lines.append("\n")

    # Reconstruct file
    kept_text = "".join(kept_lines).rstrip()
    if kept_text:
        kept_text += "\n\n"
    kept_text += "".join(ep_lines)

    try:
        path.write_text(kept_text, encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to save endpoints to settings.toml: %s", e)
