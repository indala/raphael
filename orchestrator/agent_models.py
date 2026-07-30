"""
Agent model assignments — auto-routes agents to endpoints based on
text_priority / vision_priority from settings.toml.

Each agent type has a capability profile (text vs vision, default effort).
Endpoints are assigned automatically from the user's priority lists.

Usage:
    from orchestrator.agent_models import create_agent_llm, auto_effort

    llm = create_agent_llm("coding")
    llm = create_agent_llm("coding", query="build a full web app")
"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Agent capability profiles (internal, not user-facing) ─────

_AGENT_PROFILES: dict[str, dict] = {
    "raphael":      {"need": "text",   "effort": "medium",
                     "description": "Main loop — needs fast responses, good quality"},
    "manager":      {"need": "text",   "effort": "low",
                     "description": "Routing decisions — speed matters"},
    "executor":     {"need": "text",   "effort": "medium",
                     "description": "Catch-all — balanced speed/reliability"},
    "browser":      {"need": "vision", "effort": "low",
                     "description": "Playwright automation — fast turn-around"},
    "desktop":      {"need": "vision", "effort": "low",
                     "description": "UI clicks, simple instructions"},
    "librarian":    {"need": "text",   "effort": "low",
                     "description": "Memory queries — simple lookups"},
    "coding":       {"need": "text",   "effort": "high",
                     "description": "Code generation — coding-specialized endpoint"},
    "researcher":   {"need": "text",   "effort": "high",
                     "description": "Web research — needs reasoning quality"},
    "analytics":    {"need": "text",   "effort": "high",
                     "description": "Stock data, calculations — accuracy matters"},
    "tool_manager": {"need": "text",   "effort": "high",
                     "description": "Tool creation pipeline — good reasoning"},
}


def _auto_assign_backend(agent_name: str) -> str | None:
    """Pick the best endpoint for an agent based on its capability needs.

    Vision agents (browser, desktop) prefer vision_priority with ``vision_model``.
    All others use text_priority with ``text_model``.

    Falls back gracefully: no vision endpoint → use text endpoint;
    nothing in priority lists → use any registered endpoint.
    """
    from orchestrator.endpoint_registry import (
        all as _all_eps,
    )
    from orchestrator.endpoint_registry import (
        get as _get_ep,
    )
    from orchestrator.endpoint_registry import (
        get_text_priority,
        get_vision_priority,
    )

    profile = _AGENT_PROFILES.get(agent_name, {"need": "text", "effort": "medium"})
    text_priority = get_text_priority()
    vision_priority = get_vision_priority()

    if profile.get("need") == "vision":
        for ep_name in vision_priority:
            ep = _get_ep(ep_name)
            if ep and ep.vision_model:
                return ep_name
        # Fallback: use text priority (vision model optional)
        for ep_name in text_priority:
            ep = _get_ep(ep_name)
            if ep and ep.text_model:
                return ep_name
    else:
        for ep_name in text_priority:
            ep = _get_ep(ep_name)
            if ep and ep.text_model:
                return ep_name

    # Last resort: any available endpoint
    all_eps = _all_eps()
    return all_eps[0].name if all_eps else None


def get_agent_config(agent_name: str) -> dict:
    """Get the capability profile for a specific agent.

    Returns dict with keys: need, effort, description.
    Falls back to a general text profile if agent not found.
    """
    return dict(_AGENT_PROFILES.get(agent_name, {"need": "text", "effort": "medium"}))


def list_agent_assignments() -> dict[str, dict]:
    """Return all agent capability profiles (for inspection/debugging)."""
    return dict(_AGENT_PROFILES)


# ── Effort / complexity detection ─────────────────────────────

# Signals HIGH effort — needs complex reasoning
_HIGH_SIGNALS = re.compile(
    r"(create|build|develop|implement|design|architect|generate|write\s+(a\s+)?(function|program|code|app))"
    r"|(explain|analyze|compare|evaluate|diagnose|debug|optimize|refactor)"
    r"|(calculate|compute|forecast|predict|simulate)"
    r"|(research|investigate|summarize|synthesize)"
    r"|(chart|graph|plot|visualize|dashboard)"
    r"|(portfolio|pnl|profit|loss|stock|market)"
    r"|(migration|deployment|pipeline|workflow)"
    r"|(tool|agent|plugin|extension)",
    re.IGNORECASE,
)

# Signals LOW effort — simple/tiny tasks
_LOW_SIGNALS = re.compile(
    r"\b(hi|hello|hey|thanks|ok|okay|yes|no|sure|done|bye|goodbye)\b"
    r"|\b(clipboard|copy|paste)"
    r"|\b(mute|unmute|sleep|wake)"
    r"|\b(say|speak|read|tell)\s+(this|that|it)"
    r"|\b(what(\'s|s)?\s+(on|in)\s+(my\s+)?(clipboard|screen))",
    re.IGNORECASE,
)


def auto_effort(query: str, agent_name: str = "") -> str:
    """Detect the appropriate effort level from a query string.

    Returns "low", "medium", or "high".

    Uses two signals:
    1. Query content (keywords, complexity hints)
    2. Agent's default effort (used as baseline / floor)
    """
    if not query:
        return _default_effort(agent_name)

    # Check high-effort signals first (complex tasks)
    if _HIGH_SIGNALS.search(query):
        return "high"

    # Check low-effort signals
    if _LOW_SIGNALS.search(query):
        agent_floor = _default_effort(agent_name)
        if agent_floor == "high":
            return "high"
        return "low"

    # Medium by default (or agent floor)
    return _default_effort(agent_name)


def _default_effort(agent_name: str) -> str:
    """Get the default effort level for an agent from its profile."""
    profile = _AGENT_PROFILES.get(agent_name, {})
    return str(profile.get("effort", "medium"))


# ── Effort level config (from models.json) ────────────────────

_effort_levels: dict | None = None


def _load_effort_levels() -> dict:
    """Load effort level config from models.json (cached)."""
    global _effort_levels
    if _effort_levels is not None:
        return _effort_levels

    path = Path(__file__).resolve().parent.parent / "models.json"
    try:
        with open(path) as f:
            data = json.load(f)
        _effort_levels = data.get("effort_levels", {})
        logger.info("Loaded %d effort levels from models.json", len(_effort_levels))
    except Exception as e:
        logger.error("Failed to load models.json: %s", e)
        _effort_levels = {}

    return _effort_levels


def get_effort_config(effort: str) -> dict:
    """Get config for a given effort level.

    Returns dict with keys: max_tokens, temperature, description.
    Falls back to medium if effort level not found.
    """
    levels = _load_effort_levels()
    if effort in levels:
        return dict(levels[effort])

    logger.warning("Unknown effort level '%s' — falling back to medium", effort)
    return dict(levels.get("medium", {"max_tokens": 2048, "temperature": 0.5}))


def create_agent_llm(agent_name: str, query: str = "", effort: str = "", **overrides):
    """Create an LLMClient for a specific agent, with auto-assigned endpoint.

    Backend is auto-selected from ``text_priority`` / ``vision_priority``
    in settings.toml. Models are resolved from the matched endpoint's config.

    Args:
        agent_name: Agent name (e.g., "coding", "researcher")
        query: The user's query (for auto-effort detection)
        effort: Force a specific effort level ("low", "medium", "high").
                If empty, auto-detected from query + agent default.
        **overrides: Override backend, model, or fallback_model

    Returns:
        LLMClient instance configured for this query+agent
    """
    from orchestrator.core import LLMClient

    _AGENT_PROFILES.get(agent_name, {"need": "text", "effort": "medium"})

    # Determine effort level
    eff = effort or auto_effort(query, agent_name)
    get_effort_config(eff)

    # Resolve backend: override > auto-assign
    backend = overrides.get("backend") or _auto_assign_backend(agent_name)

    # Resolve model from endpoint registry
    model = overrides.get("model")
    if not model and backend:
        try:
            from orchestrator.endpoint_registry import get as _get_ep
            ep = _get_ep(backend)
            if ep:
                # Low effort → first fallback model (cheaper/faster)
                if eff == "low" and ep.fallback_models:
                    model = ep.fallback_models[0]
                else:
                    model = ep.text_model
        except Exception:
            pass

    # Resolve fallback model — try override, then endpoint's own fallback
    fallback = overrides.get("fallback_model") or overrides.get("fallback", "")
    if not fallback and backend:
        try:
            from orchestrator.endpoint_registry import get as _get_ep
            ep = _get_ep(backend)
            if ep and ep.fallback_models:
                fallback = ep.fallback_models[0]
        except Exception:
            pass

    logger.debug("create_agent_llm(%s, effort=%s) → %s/%s (fb: %s)",
                 agent_name, eff, backend, model, fallback)
    return LLMClient(backend=backend, model=model, fallback_model=fallback)
