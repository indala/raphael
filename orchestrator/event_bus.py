"""
Lightweight thread-safe pub/sub event bus for Raphael.

Allows decoupled communication between components. Any component can
publish events and any component can subscribe to events without
direct import dependencies.

Supports both synchronous (default) and asynchronous publishing
via an internal thread pool for non-blocking dispatch.

Usage:
    from orchestrator.event_bus import EventBus, TOOL_EXECUTED

    bus = EventBus()
    bus.subscribe(TOOL_EXECUTED, my_handler)
    bus.publish(TOOL_EXECUTED, tool="get_weather", latency_ms=42)
    bus.publish_async(TOOL_EXECUTED, tool="get_weather", latency_ms=42)
"""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.event_payloads import EventPayload

logger = logging.getLogger(__name__)

# ── Event Name Constants ──────────────────────────────────────────

# Tool lifecycle
TOOL_EXECUTED = "tool.executed"
TOOL_FAILED = "tool.failed"
TOOL_CREATED = "tool.created"
TOOL_OPTIMIZED = "tool.optimized"
TOOL_ARCHIVED = "tool.archived"
TOOL_DEGRADED = "tool.degraded"
TOOL_BROKEN = "tool.broken"

# Memory
MEMORY_UPDATED = "memory.updated"

# Agent / Delegation / Tasks
AGENT_DELEGATED = "agent.delegated"
TASK_COMPLETED = "task.completed"
TASK_STATUS_CHANGED = "task.status_changed"
TASK_FINISHED = "task.finished"

# System
SYSTEM_STARTUP = "system.startup"
SYSTEM_SHUTDOWN = "system.shutdown"

EventHandler = Callable[[str, dict], None]


class EventBus:
    """Simple thread-safe event bus singleton with optional async publishing."""

    _instance: EventBus | None = None
    _lock = threading.RLock()
    _pool: ThreadPoolExecutor | None = None
    _subscribers: dict[str, list[EventHandler]] = {}

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._subscribers: dict[str, list[EventHandler]] = {}  # type: ignore[misc]
                    cls._instance._pool = ThreadPoolExecutor(
                        max_workers=4,
                        thread_name_prefix="eventbus",
                    )
        return cls._instance

    def subscribe(self, event: str, handler: EventHandler):
        """Register a handler for an event type.

        Use '*' to subscribe to all events.
        """
        with self._lock:
            self._subscribers.setdefault(event, []).append(handler)

    def unsubscribe(self, event: str, handler: EventHandler):
        """Remove a handler for an event type."""
        with self._lock:
            handlers = self._subscribers.get(event, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(self, event: str, **data):
        """Publish an event synchronously — handlers run in the caller's thread.

        Blocks until all handlers have completed. Errors in individual
        handlers are logged and do not propagate.
        """
        with self._lock:
            handlers = list(self._subscribers.get(event, []))
            wildcard = list(self._subscribers.get("*", []))
        for handler in handlers + wildcard:
            try:
                handler(event, data)
            except Exception as e:
                logger.error("Event handler '%s' failed for '%s': %s",
                             getattr(handler, "__name__", str(handler)), event, e)

    def publish_async(self, event: str, **data):
        """Publish an event asynchronously — handlers run in a background thread pool.

        Returns immediately. Handlers that need ordering guarantees or
        access to thread-local state should use ``publish()`` instead.
        Errors are logged but do not interrupt other handlers.
        """
        with self._lock:
            handlers = list(self._subscribers.get(event, []))
            wildcard = list(self._subscribers.get("*", []))
        for handler in handlers + wildcard:
            self._pool.submit(self._run_handler, handler, event, data)  # type: ignore[union-attr]

    def publish_typed(self, event_name: str, payload: EventPayload) -> None:
        """Publish an event with a typed :class:`EventPayload`.

        The payload class is validated against the ``EVENT_PAYLOAD`` registry
        before dispatch: a mismatch (or an event with no registered payload) is
        logged and the publish is dropped — it never raises, so a publisher
        can't crash on a wrong payload. Delegates to :meth:`publish`, so
        subscribers still receive ``(event_name, dict)`` unchanged.
        """
        from orchestrator.event_payloads import EVENT_PAYLOAD  # local import avoids a module cycle

        expected = EVENT_PAYLOAD.get(event_name)
        if expected is None:
            logger.warning(
                "No typed payload registered for event '%s'; publish dropped",
                event_name,
            )
            return
        if not isinstance(payload, expected):
            logger.warning(
                "Typed payload mismatch for '%s': expected %s, got %s; publish dropped",
                event_name,
                expected.__name__,
                type(payload).__name__,
            )
            return
        self.publish(event_name, **payload.to_dict())

    def _run_handler(self, handler: EventHandler, event: str, data: dict):
        """Execute a single handler, logging any error."""
        try:
            handler(event, data)
        except Exception as e:
            logger.error("Async handler '%s' failed for '%s': %s",
                         getattr(handler, "__name__", str(handler)), event, e)

    def clear(self):
        """Remove all subscribers (useful for testing)."""
        with self._lock:
            self._subscribers.clear()

    def shutdown(self, wait: bool = True):
        """Shut down the internal thread pool.

        Call during application shutdown. With ``wait=True`` (default),
        blocks until all pending async handlers complete.
        """
        if self._pool:
            self._pool.shutdown(wait=wait)  # type: ignore[union-attr]
            self._pool = None

    @property
    def subscriber_count(self) -> int:
        """Return total number of subscriber registrations."""
        with self._lock:
            return sum(len(v) for v in self._subscribers.values())
