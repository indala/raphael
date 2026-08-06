"""
Startup Briefing Composer — rich first-session context assembly.

Pattern from Mark-XLVII startup pattern + Raphael's existing pop_last_session().

Composes a structured briefing from multiple sources, then feeds it to the
LLM as a single rich system prompt so the startup greeting is contextually
aware, not a generic "Hello!" every time.

Sources (in priority order):
  1. Time-of-day tone     — morning/afternoon/evening phrasing guide
  2. User name            — from user_memory if known
  3. Last session summary — pop_last_session() (consumed once, never repeats)
  4. Pending tasks        — daily_task_memory items (active, non-internal)
  5. Monitor alerts       — background topic monitor headlines (if any fired)
  6. Proactive suggestion — one optional forward-looking nudge

Usage::

    from orchestrator.startup_briefing import compose_briefing_prompt

    prompt = compose_briefing_prompt()
    # Inject into the startup LLM call as the user message
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NamedTuple

logger = logging.getLogger(__name__)


class BriefingContext(NamedTuple):
    """All data gathered for a startup briefing."""
    time_of_day: str          # "morning", "afternoon", "evening", "night"
    greeting_tone: str        # phrasing guide for the LLM
    user_name: str            # empty string if unknown
    last_session: str         # empty string if none
    pending_tasks: list[str]  # task descriptions from daily_task_memory
    monitor_alerts: list[str] # topic monitor alert headlines
    hour: int                 # current hour (0-23)


def _get_time_context() -> tuple[str, str, int]:
    """Return (time_of_day, greeting_tone, hour)."""
    hour = datetime.now().hour
    if 5 <= hour < 12:
        return "morning", "warm and energising — like a coffee chat", hour
    elif 12 <= hour < 17:
        return "afternoon", "productive and focused", hour
    elif 17 <= hour < 21:
        return "evening", "relaxed and winding-down", hour
    else:
        return "night", "quiet and calm", hour


def _get_user_name() -> str:
    """Retrieve user name from memory if available."""
    try:
        from memory.memory_manager import load_memory
        memory = load_memory()
        entry = memory.get("user_memory", {}).get("name")
        if isinstance(entry, dict):
            return str(entry.get("value", "")).strip()
        if isinstance(entry, str):
            return entry.strip()
    except Exception as e:
        logger.debug("Could not load user name: %s", e)
    return ""


def _get_last_session() -> str:
    """Pop and return the last session summary (consumed once)."""
    try:
        from memory.memory_manager import pop_last_session
        summary = pop_last_session()
        return (summary or "").strip()
    except Exception as e:
        logger.debug("Could not load last session: %s", e)
    return ""


def _get_pending_tasks() -> list[str]:
    """Return active task descriptions from daily_task_memory."""
    try:
        from memory.memory_manager import load_memory
        memory = load_memory()
        tasks = memory.get("daily_task_memory", {})
        if not isinstance(tasks, dict):
            return []

        results = []
        for key, entry in tasks.items():
            if key.startswith("_"):
                continue
            value = entry.get("value", "") if isinstance(entry, dict) else str(entry)
            if value and value.strip():
                results.append(value.strip())

        return results[:5]  # cap at 5 to keep briefing concise
    except Exception as e:
        logger.debug("Could not load pending tasks: %s", e)
    return []


def _get_monitor_alerts() -> list[str]:
    """Run topic monitor checks and return any new alerts."""
    try:
        # Mark-XLVII background_monitor pattern
        # Only runs if the background_monitor module exists
        from actions.background_monitor import check_all
        alerts = check_all()
        return [a.strip() for a in (alerts or []) if a.strip()]
    except ImportError:
        pass
    except Exception as e:
        logger.debug("Monitor check failed: %s", e)
    return []


def gather_briefing_context() -> BriefingContext:
    """Gather all data sources for the startup briefing."""
    time_of_day, greeting_tone, hour = _get_time_context()
    user_name    = _get_user_name()
    last_session = _get_last_session()
    pending      = _get_pending_tasks()
    alerts       = _get_monitor_alerts()

    return BriefingContext(
        time_of_day=time_of_day,
        greeting_tone=greeting_tone,
        user_name=user_name,
        last_session=last_session,
        pending_tasks=pending,
        monitor_alerts=alerts,
        hour=hour,
    )


def compose_briefing_prompt(ctx: BriefingContext | None = None) -> str:
    """Compose the full LLM prompt for a rich startup briefing.

    The returned string is used as the user message in the startup LLM call.
    The LLM is instructed to synthesize all provided context into a natural
    2-3 sentence greeting — never reading out lists robotically.

    Args:
        ctx: Pre-gathered context. If None, gathers fresh context automatically.
    """
    if ctx is None:
        ctx = gather_briefing_context()

    parts: list[str] = []

    # Tone instruction
    parts.append(
        f"It is {ctx.time_of_day} ({ctx.hour:02d}:00). "
        f"Your tone should be {ctx.greeting_tone}."
    )

    # Greeting target
    if ctx.user_name:
        parts.append(f"Greet the user by name: {ctx.user_name}.")
    else:
        parts.append("The user's name is not known — use a warm general greeting.")

    # Last session continuity
    if ctx.last_session:
        parts.append(
            f"\nLast session summary (reference naturally, do NOT read out verbatim):\n"
            f"{ctx.last_session}"
        )

    # Pending tasks
    if ctx.pending_tasks:
        task_lines = "\n".join(f"  • {t}" for t in ctx.pending_tasks)
        parts.append(
            f"\nPending tasks to mention (briefly, 1 sentence max):\n{task_lines}"
        )

    # Monitor alerts
    if ctx.monitor_alerts:
        alert_lines = "\n".join(f"  • {a}" for a in ctx.monitor_alerts[:3])
        parts.append(
            f"\nNew topic monitor alerts (mention naturally if relevant):\n{alert_lines}"
        )

    # Synthesis instructions
    parts.append(
        "\nInstructions:"
        "\n- Synthesise the above into a natural, warm greeting of 2-3 sentences maximum."
        "\n- Do NOT use markdown (no bold, bullets, code blocks) — this goes to TTS."
        "\n- Do NOT robotically list tasks or headlines. Weave them in conversationally."
        "\n- If there is nothing notable to mention, just give a warm welcome."
        "\n- Match the time-of-day tone described above."
    )

    return "\n".join(parts)


def build_briefing_system_prompt() -> str:
    """Return the system message for the startup briefing LLM call."""
    return (
        "You are Raphael, an advanced AI personal assistant on Windows. "
        "You are greeting the user at the start of a new session. "
        "Be warm, brief, and natural — like a knowledgeable companion, not a robot reading a report."
    )
