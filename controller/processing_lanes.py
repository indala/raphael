"""
Three-lane processing-state contract (Task 2).

Distinguishes USER work from PROACTIVE and BACKGROUND work so that
proactive checks and background tasks never flip the controller's
"processing" flag, which is reserved for user LLM work only.

Each lane tracks an active-work counter and a generation counter.
``begin_*`` returns the lane generation at start; callers compare that
value with :meth:`is_stale` when a result arrives to drop late results
from superseded rounds.

Lane priority: USER > PROACTIVE > BACKGROUND. Beginning a user request
bumps the generations of the lower-priority lanes, so any in-flight
proactive/background result becomes stale the moment the user takes
over — the work itself is not cancellable, only its result delivery is
gated.
"""

import threading

LANE_USER = "user"
LANE_PROACTIVE = "proactive"
LANE_BACKGROUND = "background"

# Priority order: lower index wins when multiple lanes are active.
_PRIORITY = (LANE_USER, LANE_PROACTIVE, LANE_BACKGROUND)


class ProcessingLanes:
    """Thread-safe three-lane processing state (user / proactive / background)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[str, int] = {lane: 0 for lane in _PRIORITY}
        self._generation: dict[str, int] = {lane: 0 for lane in _PRIORITY}

    @staticmethod
    def _validate(lane: str) -> None:
        if lane not in _PRIORITY:
            raise ValueError(f"unknown lane: {lane!r}")

    # ── Begin / end ────────────────────────────────────────────────

    def begin_user(self) -> int:
        """Enter the user lane and invalidate lower-priority lanes.

        Returns the user-lane generation for this request.
        """
        with self._lock:
            self._generation[LANE_USER] += 1
            # User always preempts: supersede any in-flight lower-lane work.
            for lower in (LANE_PROACTIVE, LANE_BACKGROUND):
                self._generation[lower] += 1
            self._active[LANE_USER] += 1
            return self._generation[LANE_USER]

    def end_user(self) -> None:
        """Leave the user lane (idempotent)."""
        self._end(LANE_USER)

    def begin_proactive(self) -> int:
        """Enter the proactive lane; returns its generation."""
        return self._begin(LANE_PROACTIVE)

    def end_proactive(self) -> None:
        self._end(LANE_PROACTIVE)

    def begin_background(self) -> int:
        """Enter the background lane; returns its generation."""
        return self._begin(LANE_BACKGROUND)

    def end_background(self) -> None:
        self._end(LANE_BACKGROUND)

    def _begin(self, lane: str) -> int:
        self._validate(lane)
        with self._lock:
            self._generation[lane] += 1
            self._active[lane] += 1
            return self._generation[lane]

    def _end(self, lane: str) -> None:
        self._validate(lane)
        with self._lock:
            if self._active[lane] > 0:
                self._active[lane] -= 1

    # ── Queries ────────────────────────────────────────────────────

    def is_user_processing(self) -> bool:
        return self.is_active(LANE_USER)

    def is_proactive_processing(self) -> bool:
        return self.is_active(LANE_PROACTIVE)

    def is_background_processing(self) -> bool:
        return self.is_active(LANE_BACKGROUND)

    def is_active(self, lane: str) -> bool:
        """True while *lane* has at least one in-flight work item."""
        self._validate(lane)
        with self._lock:
            return self._active[lane] > 0

    def is_any_processing(self) -> bool:
        """True while any lane has work in flight."""
        with self._lock:
            return any(count > 0 for count in self._active.values())

    def active_lane(self) -> str | None:
        """Highest-priority lane with work in flight, or None when idle."""
        with self._lock:
            for lane in _PRIORITY:
                if self._active[lane] > 0:
                    return lane
            return None

    def generation(self, lane: str) -> int:
        """Current generation of *lane* (0 when no round has started)."""
        self._validate(lane)
        with self._lock:
            return self._generation[lane]

    def is_stale(self, lane: str, generation: int) -> bool:
        """True if a result captured under *generation* is superseded.

        A result is stale when a newer round of the same lane started,
        or (for lower-priority lanes) when a user request began after it.
        """
        self._validate(lane)
        with self._lock:
            return generation != self._generation[lane]
