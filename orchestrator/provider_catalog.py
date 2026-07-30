"""
Provider Catalog — known LLM providers, base URLs, and supported models.

Used to pre-populate endpoint configuration in the settings UI and to seed
default endpoints on first run. Inspired by OpenClaude's gateway catalog.

Two data sources merged together:
  1. ``providers/provider.json`` — 37 providers from OpenClaude's integration manifest.
  2. ``CATALOG`` — legacy inline catalog (8 providers) kept as fallback.

Each entry maps cleanly to the ``[[endpoints]]`` format in ``settings.toml``.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


# ── JSON-backed provider data ─────────────────────────────────

_PROVIDER_JSON_PATH = Path(__file__).resolve().parent.parent / "providers" / "provider.json"

# When bundled with PyInstaller, sys._MEIPASS points to the _internal directory
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    _PROVIDER_JSON_PATH = Path(sys._MEIPASS) / "providers" / "provider.json"

# Fields a JSON entry may contain
_JSON_FIELDS = {
    "id": str,
    "name": str,
    "base_url": str,
    "default_model": (str, type(None)),
    "fallback_model": (str, type(None)),
    "api_key_env": (str, type(None)),
}


def _load_json_sources() -> list[dict]:
    """Load provider entries from ``providers/provider.json``."""
    if not _PROVIDER_JSON_PATH.is_file():
        logger.warning("provider.json not found at %s", _PROVIDER_JSON_PATH)
        return []
    try:
        with open(_PROVIDER_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        raw: list[dict] = data.get("providers", [])
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to load provider.json: %s", exc)
        return []

    out: list[dict] = []
    seen_ids: set[str] = set()
    for entry in raw:
        sid = entry.get("id", "")
        if not sid or sid in seen_ids:
            continue
        seen_ids.add(sid)
        models = entry.get("models") or []
        if isinstance(models, str):
            models = []
        # Check if this source uses dynamic model discovery
        needs_disco = any(
            isinstance(m, str) and ("dynamic" in m.lower() or m.startswith("1000"))
            for m in models
        )
        default = entry.get("default_model") or ""
        # Normalise to the catalog dict format the UI expects
        out.append({
            "name": sid,
            "label": entry.get("name", sid),
            "base_url": entry.get("base_url", ""),
            "known_env_var": entry.get("api_key_env") or "",
            "text_model": default,
            "vision_model": "",
            "fallback_model": entry.get("fallback_model") or "",
            "stt_model": "",
            "tts_model": "",
            # Filter out placeholder strings (e.g. "dynamic discovery — hybrid source")
            "text_models": [m for m in models if m and not m.lower().startswith("dynamic") and not (m[0].isdigit() and "+" in m)],
            "vision_models": _guess_vision_models(models),
            "stt_models": [],
            "tts_models": [],
            # Metadata for smart UI
            "_id": sid,
            "_env_var": entry.get("api_key_env") or "",
            "_needs_discovery": needs_disco,
            "_has_static_models": len([m for m in models if m and not m.lower().startswith("dynamic") and not (m[0].isdigit() and "+" in m)]) > 0,
        })
    return out


def _guess_vision_models(all_models: list[str]) -> list[str]:
    """Heuristic: pick models likely to support vision."""
    keywords = ("vision", "vl-", "vl/", "-vl-", "omni", "multimodal", "image")
    return [m for m in all_models if any(k in m.lower() for k in keywords)]


_JSON_SOURCES: list[dict] = _load_json_sources()
_JSON_INDEX: dict[str, dict] = {e["name"]: e for e in _JSON_SOURCES}


# ── Merged lookup helpers ─────────────────────────────────────


def _all_sources() -> list[dict]:
    """All known provider entries from ``providers/provider.json``."""
    return list(_JSON_SOURCES)


def search_sources(query: str, max_results: int = 20) -> list[dict]:
    """Fuzzy-search endpoint sources, returning up to *max_results* matches.

    Matches against ``name`` (id), ``label``, and ``base_url``.
    Returns normalised catalog dicts.
    """
    if not query or not query.strip():
        return list_providers()[:max_results]

    q = query.strip().lower()
    results: list[tuple[int, dict]] = []  # (score, entry)

    for src in _all_sources():
        name = (src.get("name") or "").lower()
        label = (src.get("label") or "").lower()
        url = (src.get("base_url") or "").lower()

        best = 0
        if q in (name, label):
            best = 100
        elif q in name or q in label:
            best = 50
        elif q in url:
            best = 30
        # prefix match
        if name.startswith(q) or label.startswith(q):
            best = max(best, 40)

        if best > 0:
            results.append((-best, src))  # negative for ascending sort

    results.sort(key=lambda x: x[0])
    return [src for _, src in results][:max_results]


def get_source(name: str) -> dict | None:
    """Look up a specific provider source by name from ``providers/provider.json``."""
    return _JSON_INDEX.get(name)


def get_models_for_source(name: str) -> dict[str, list[str]]:
    """Return typed model lists for a given source."""
    src = get_source(name)
    if not src:
        return {"text_models": [], "vision_models": [], "stt_models": [], "tts_models": []}
    return {
        "text_models": src.get("text_models") or [src.get("text_model", "")] if src.get("text_model") else [],
        "vision_models": src.get("vision_models") or [],
        "stt_models": src.get("stt_models") or [],
        "tts_models": src.get("tts_models") or [],
    }


def get(name: str) -> dict | None:
    """Look up a provider spec by name from ``providers/provider.json``."""
    src = get_source(name)
    return src


def list_providers() -> list[dict]:
    """Return all provider specs sorted by label."""
    return sorted(_all_sources(), key=lambda p: (p.get("label") or p.get("name") or "").lower())


def provider_labels() -> dict[str, str]:
    """Return a name → label mapping for UI dropdowns."""
    return {src.get("name", ""): src.get("label", src.get("name", "")) for src in _all_sources()}


def default_endpoint_dicts(filter_to: list[str] | None = None) -> list[dict]:
    """Generate default endpoint dicts.

    Each entry has: name, base_url, api_key (empty), text_model, vision_model,
    fallback_model, stt_model, tts_model, priority.

    Args:
        filter_to: Optional list of provider names to include. If None, all
                   providers are included.
    """
    result = []
    for i, spec in enumerate(_all_sources()):
        sn = spec.get("name", "")
        if filter_to and sn not in filter_to:
            continue
        result.append({
            "name": spec.get("label", sn),
            "base_url": spec.get("base_url", ""),
            "api_key": "",
            "text_model": spec.get("text_model", ""),
            "vision_model": spec.get("vision_model", ""),
            "fallback_model": spec.get("fallback_model", ""),
            "stt_model": spec.get("stt_model", ""),
            "tts_model": spec.get("tts_model", ""),
            "priority": i,
        })
    return result
