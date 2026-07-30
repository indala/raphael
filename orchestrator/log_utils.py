"""
Logging utilities for Raphael — request correlation IDs, structured events.

Provides:
  - RequestIDFilter: injects [req=<uuid>] into every log record
  - set_request_id / get_request_id / clear_request_id: contextvar-based
  - log_event: high-level lifecycle event logging with timing
"""

import logging
import time as _time
from contextvars import ContextVar
from uuid import uuid4

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_event_timeline: ContextVar[list[tuple[str, float]]] = ContextVar("event_timeline", default=None)  # type: ignore[arg-type]

logger = logging.getLogger(__name__)


class RequestIDFilter(logging.Filter):
    """Logging filter that appends [req=<uuid>] to every record with an active request."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = _request_id.get()
        if rid:
            record.msg = f"[req={rid}] {record.msg}"
        return True


def set_request_id() -> str:
    """Generate and set a new request ID for the current context.

    Returns the new ID.
    """
    rid = uuid4().hex[:12]
    _request_id.set(rid)
    return rid


def get_request_id() -> str:
    """Return the current request ID, or empty string if none."""
    return _request_id.get()


def clear_request_id() -> None:
    """Clear the request ID for the current context."""
    _request_id.set("")


# ── Event Timeline ──────────────────────────────────────────────────


def start_timeline() -> None:
    """Reset and start a new event timeline for the current request."""
    _event_timeline.set([("Request Started", _time.monotonic())])


def log_event(event: str, extra: str = "") -> None:
    """Log a lifecycle event with cumulative timing.

    Example:
        log_event("Memory Read")        → "[req=abc] Memory Read         (+0.12s)"
        log_event("LLM Call")           → "[req=abc] LLM Call           (+1.34s, total 2.10s)"
    """
    timeline = _event_timeline.get() or []
    now = _time.monotonic()
    start_time = timeline[0][1] if timeline else now
    elapsed_since_start = now - start_time

    delta = ""
    if len(timeline) >= 1:
        delta = f"+{now - timeline[-1][1]:.2f}s"

    timeline.append((event, now))
    _event_timeline.set(timeline)

    parts = [event]
    if extra:
        parts.append(extra)
    if delta:
        parts.append(f"({delta}, total {elapsed_since_start:.2f}s)")
    logger.info("  ".join(parts))


def finalize_timeline() -> str | None:
    """Log the final Done event and return the total duration string.

    Returns None if no timeline was active.
    """
    timeline = _event_timeline.get()
    if not timeline:
        return None
    elapsed = _time.monotonic() - timeline[0][1]
    log_event("Done")
    logger.info("Total: %.2fs", elapsed)
    return f"{elapsed:.2f}s"
