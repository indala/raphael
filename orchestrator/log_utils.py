"""
Logging utilities for Raphael — request correlation IDs, structured events.

Provides:
  - RequestIDFilter: injects [req=<uuid>] [phase=user|proactive|background]
    into every log record
  - set_request_id / get_request_id / clear_request_id: contextvar-based
  - set_phase / get_phase / clear_phase: processing-lane context (the
    three-lane contract: user / proactive / background)
  - log_prefixed: log under a stable subsystem prefix constant
  - log_event: high-level lifecycle event logging with timing
"""

import logging
import time as _time
from contextvars import ContextVar
from uuid import uuid4

_request_id: ContextVar[str] = ContextVar("request_id", default="")
_phase: ContextVar[str] = ContextVar("phase", default="user")
_event_timeline: ContextVar[list[tuple[str, float]]] = ContextVar("event_timeline", default=None)  # type: ignore[arg-type]

logger = logging.getLogger(__name__)

# ── Log Prefix Constants ───────────────────────────────────────────
# Stable per-subsystem prefixes (Task 1). Every subsystem logs through
# these so lines are greppable: grep "[CACHE]" logs/raphael.log
LOG_PREFIX_CACHE = "[CACHE]"
LOG_PREFIX_PARALLEL = "[PARALLEL]"
LOG_PREFIX_INTENT = "[INTENT]"
LOG_PREFIX_PROACTIVE = "[PROACTIVE]"
LOG_PREFIX_PRIORITY = "[PRIORITY]"
LOG_PREFIX_ROUTING = "[ROUTING]"
LOG_PREFIX_PROMPT = "[PROMPT]"


def log_prefixed(prefix: str, level: int, msg: str, *args) -> None:
    """Log *msg* (%-formatted with *args*) under a subsystem *prefix*.

    Example:
        log_prefixed(LOG_PREFIX_CACHE, logging.INFO, "hit key=%s", key)
    """
    logger.log(level, "%s %s", prefix, msg % args if args else msg)


class RequestIDFilter(logging.Filter):
    """Filter that appends [req=<uuid>] [phase=<lane>] to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        tags = []
        rid = _request_id.get()
        if rid:
            tags.append(f"[req={rid}]")
        tags.append(f"[phase={_phase.get()}]")
        if tags and not str(record.msg).startswith(tags[0]):
            record.msg = f"{' '.join(tags)} {record.msg}"
        return True


def set_phase(phase: str) -> str:
    """Set the processing-lane phase for the current context.

    One of "user" | "proactive" | "background" (defaults to "user").
    Returns the phase that was set.
    """
    if phase not in ("user", "proactive", "background"):
        raise ValueError(f"unknown phase: {phase!r}")
    _phase.set(phase)
    return phase


def get_phase() -> str:
    """Return the current phase, or 'user' if none was set."""
    return _phase.get()


def clear_phase() -> None:
    """Reset the phase to the default 'user'."""
    _phase.set("user")


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
