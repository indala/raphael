"""
Routine Engine — Event-driven and time-based workflow automation.

Manages scheduled routines (e.g. daily news briefing at 8:00 AM) and system event triggers
(e.g. on PC wake, on new email, on battery status change).
"""

import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Callable

import config

logger = logging.getLogger(__name__)

_ROUTINES_FILE = config.ROAMING_DIR / "workflows" / "routines.json"
_lock = threading.RLock()


@dataclass
class Routine:
    name: str
    description: str
    trigger_type: str  # "time" | "interval" | "event"
    trigger_value: str  # "08:00" for time, "30" for 30m interval, "on_startup" / "on_email" for event
    action_type: str  # "prompt" (LLM query) | "workflow" (saved workflow)
    action_value: str
    enabled: bool = True
    last_run: str | None = None


class RoutineEngine:
    """Manages background routine scheduling and event-driven automation."""

    def __init__(self, orchestrator_cb: Callable | None = None) -> None:
        self._routines: dict[str, Routine] = {}
        self._orchestrator_cb = orchestrator_cb
        self._running = False
        self._thread: threading.Thread | None = None
        self._load()
        self._subscribe_events()

    # ── Persistence ─────────────────────────────────────────────

    def _load(self):
        with _lock:
            if not _ROUTINES_FILE.exists():
                self._create_default_routines()
                return
            try:
                content = _ROUTINES_FILE.read_text(encoding="utf-8").strip()
                if not content:
                    self._create_default_routines()
                    return
                data = json.loads(content)
                self._routines = {k: Routine(**v) for k, v in data.items()}
                logger.debug("Loaded %d routines from %s", len(self._routines), _ROUTINES_FILE)
            except Exception as e:
                logger.error("Failed to load routines: %s", e)
                self._create_default_routines()

    def _save(self):
        with _lock:
            try:
                _ROUTINES_FILE.parent.mkdir(parents=True, exist_ok=True)
                data = {k: asdict(r) for k, r in self._routines.items()}
                _ROUTINES_FILE.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.error("Failed to save routines: %s", e)

    def _create_default_routines(self):
        """Create sample default routines."""
        defaults = [
            Routine(
                name="Morning Briefing",
                description="Daily morning news and schedule summary at 8:00 AM",
                trigger_type="time",
                trigger_value="08:00",
                action_type="prompt",
                action_value="Provide a concise morning briefing with top world headlines, current date/time, and active goals.",
                enabled=False,
            ),
            Routine(
                name="System Startup Check",
                description="Runs system health check when Raphael starts",
                trigger_type="event",
                trigger_value="on_startup",
                action_type="prompt",
                action_value="Perform a quick health check of active tools and background services.",
                enabled=True,
            ),
        ]
        self._routines = {r.name: r for r in defaults}
        self._save()

    # ── Management API ──────────────────────────────────────────

    def add_routine(self, routine: Routine) -> bool:
        with _lock:
            self._routines[routine.name] = routine
            self._save()
            return True

    def toggle_routine(self, name: str, enabled: bool) -> bool:
        with _lock:
            if name in self._routines:
                self._routines[name].enabled = enabled
                self._save()
                return True
            return False

    def list_routines(self) -> list[dict]:
        with _lock:
            return [asdict(r) for r in self._routines.values()]

    # ── Execution ───────────────────────────────────────────────

    def start(self):
        """Start background scheduler loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="routine-engine")
        self._thread.start()
        logger.info("Routine Engine started")

        # Trigger on_startup event routines
        self.trigger_event("on_startup")

    def stop(self):
        self._running = False

    def _loop(self):
        """Background thread checking time triggers every 30 seconds."""
        while self._running:
            try:
                now = datetime.now()
                current_hhmm = now.strftime("%H:%M")

                with _lock:
                    for r in self._routines.values():
                        if not r.enabled:
                            continue
                        if r.trigger_type == "time" and r.trigger_value == current_hhmm:
                            # Avoid running multiple times within the same minute
                            today_str = now.strftime("%Y-%m-%d %H:%M")
                            if r.last_run != today_str:
                                r.last_run = today_str
                                self._execute_routine(r)
            except Exception as e:
                logger.error("Routine loop error: %s", e)

            time.sleep(30)

    def trigger_event(self, event_name: str, event_data: dict | None = None):
        """Trigger any routines waiting for the specified system event."""
        with _lock:
            for r in self._routines.values():
                if not r.enabled:
                    continue
                if r.trigger_type == "event" and r.trigger_value.lower() == event_name.lower():
                    self._execute_routine(r, event_data)

    def _execute_routine(self, routine: Routine, event_data: dict | None = None):
        """Execute routine prompt or workflow."""
        logger.info("Executing routine '%s' (action=%s)", routine.name, routine.action_type)
        routine.last_run = datetime.now().isoformat()[:19]
        self._save()

        def _run():
            try:
                if routine.action_type == "prompt" and self._orchestrator_cb:
                    self._orchestrator_cb(routine.action_value)
                elif routine.action_type == "workflow":
                    from workflows.executor import execute_workflow
                    from workflows import load_workflow
                    execute_workflow(routine.action_value)
            except Exception as e:
                logger.error("Failed to execute routine '%s': %s", routine.name, e)

        # Run routine execution in background thread
        threading.Thread(target=_run, daemon=True, name=f"routine-{routine.name}").start()

    def _subscribe_events(self):
        """Subscribe routine engine to system EventBus events."""
        try:
            from orchestrator.event_bus import EventBus
            EventBus().subscribe("*", lambda evt, data: self.trigger_event(evt, data))
        except Exception:
            pass
