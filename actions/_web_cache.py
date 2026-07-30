"""Shared in-memory cache for web_search and web_fetch.

Thread-safe dict with time-based expiry. Entries older than TTL
are dropped on access. Periodic cleanup on every 50th write prevents
memory leaks from stale keys.
"""

import threading
import time

_CACHE: dict[str, tuple[float, str]] = {}
_LOCK = threading.Lock()
_WRITE_COUNT = 0
_MAX_ENTRIES = 200


def get(key: str) -> str | None:
    """Return cached value if fresh, else None."""
    with _LOCK:
        entry = _CACHE.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() < ts:  # Not expired
            return value
        # Expired — delete lazily
        del _CACHE[key]
        return None


def set(key: str, value: str, ttl_seconds: int):
    """Store value with TTL."""
    global _WRITE_COUNT
    with _LOCK:
        _CACHE[key] = (time.monotonic() + ttl_seconds, value)
        _WRITE_COUNT += 1
        # Trim oldest entries every 50 writes to avoid memory leaks
        if _WRITE_COUNT % 50 == 0 and len(_CACHE) > _MAX_ENTRIES:
            _trim()


def _trim():
    """Remove expired and oldest entries when cache is over limit."""
    now = time.monotonic()
    # Remove expired
    expired = [k for k, (ts, _) in _CACHE.items() if ts <= now]
    for k in expired:
        del _CACHE[k]
    # If still over, remove oldest
    if len(_CACHE) > _MAX_ENTRIES:
        sorted_keys = sorted(_CACHE.keys(), key=lambda k: _CACHE[k][0])
        for k in sorted_keys[:len(_CACHE) - _MAX_ENTRIES]:
            del _CACHE[k]


def clear():
    """Clear all cached entries."""
    with _LOCK:
        _CACHE.clear()
