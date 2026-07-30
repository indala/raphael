"""
Proactive Engine — idle-time check-in system for Raphael.

After a configurable cooldown of user inactivity, sends a read-only
proactive check to the LLM for brief check-ins, system alerts, or
time-based suggestions.

Architecture:
  - Idle monitor using the existing ``_last_interaction_time`` in
    RaphaelController (no new threads or timers needed)
  - ``check()`` is called from the main VAD poll loop (50ms QTimer)
  - Sends ``[PROACTIVE_CHECK]`` prefix in system prompt to signal
    a read-only, no-tools mode to the orchestrator

Inspired by Mark-XLVIII's JARVIS proactive check pattern (idle cooldown
→ read-only LLM call → brief TTS check-in).
"""

import logging
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# System prompt appended when running a proactive check
# The LLM sees this and knows to: be brief, use no tools, read-only
PROACTIVE_SYSTEM_INSTRUCTION = (
    "\n\n[PROACTIVE_CHECK] The user has been idle for a while. "
    "If you have something useful to say, respond with 1-2 sentences maximum. "
    "Otherwise respond with '__noop__' to stay silent. "
    "Do NOT use any tools. This is a READ-ONLY check. "
    "Topics: idle reminders, system alerts, time-based suggestions."
)


class ProactiveEngine:
    """
    Manages proactive check-in timing and integration.

    Usage (called from RaphaelController._poll_vad on the main thread)::

        self.proactive_engine = ProactiveEngine(
            submit_cb=self._submit_proactive,
            get_idle_time_cb=lambda: time.time() - self._last_interaction_time,
        )

        # Inside _poll_vad():
        self.proactive_engine.check()
    """

    def __init__(
        self,
        submit_cb: Callable[[str], None],
        get_idle_time_cb: Callable[[], float],
        cooldown: float = 60.0,
        min_interval: float = 120.0,
    ):
        """
        Args:
            submit_cb: Called with "[PROACTIVE_CHECK]" text to submit to LLM.
            get_idle_time_cb: Returns seconds since last user interaction.
            cooldown: Minimum idle seconds before first proactive check (default 60).
            min_interval: Minimum seconds between consecutive checks (default 120).
        """
        self._submit_cb = submit_cb
        self._get_idle_time = get_idle_time_cb
        self._cooldown = cooldown
        self._min_interval = min_interval
        self._last_check_time = 0.0
        self._enabled = True
        self._pending_proactive = False

    # ── Public API ─────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool):
        """Enable or disable proactive checks at runtime."""
        self._enabled = enabled

    def reset_timer(self):
        """Called after user interaction — resets the idle counter."""
        self._pending_proactive = False

    def check(self) -> bool:
        """
        Called from the main poll loop (every 50ms).

        Returns True if a proactive check was triggered this cycle.
        """
        if not self._enabled:
            return False

        # Don't fire if we already have one pending
        if self._pending_proactive:
            return False

        idle_time = self._get_idle_time()
        now = time.time()

        # Check cooldown and min interval
        if idle_time < self._cooldown:
            return False

        if (now - self._last_check_time) < self._min_interval:
            return False

        # Trigger proactive check
        self._pending_proactive = True
        self._last_check_time = now

        logger.debug("Proactive check triggered (idle: %.0fs)", idle_time)
        self._submit_cb(PROACTIVE_SYSTEM_INSTRUCTION)
        return True

    def on_check_complete(self):
        """Called after the proactive check result is processed."""
        self._pending_proactive = False
