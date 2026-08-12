"""
Task 2 tests — three-lane processing-state contract.

Hermetic: no Qt, no LLM calls, no network. ProcessingLanes is a pure
thread-safe state object the controller uses to keep USER work separate
from PROACTIVE and BACKGROUND lanes, with generation IDs for discarding
late results from superseded rounds.
"""

import threading

import pytest

from controller.processing_lanes import (
    LANE_BACKGROUND,
    LANE_PROACTIVE,
    LANE_USER,
    ProcessingLanes,
)


def test_starts_idle():
    lanes = ProcessingLanes()
    assert lanes.is_any_processing() is False
    assert lanes.active_lane() is None
    for lane in (LANE_USER, LANE_PROACTIVE, LANE_BACKGROUND):
        assert lanes.is_active(lane) is False
        assert lanes.generation(lane) == 0


def test_user_lane_flips_on_begin_end():
    lanes = ProcessingLanes()
    lanes.begin_user()
    assert lanes.is_user_processing() is True
    assert lanes.is_any_processing() is True
    assert lanes.active_lane() == LANE_USER
    lanes.end_user()
    assert lanes.is_user_processing() is False
    assert lanes.active_lane() is None


def test_lanes_are_independent():
    """Proactive work never flips the user lane."""
    lanes = ProcessingLanes()
    lanes.begin_proactive()
    assert lanes.is_proactive_processing() is True
    assert lanes.is_user_processing() is False
    assert lanes.is_background_processing() is False
    assert lanes.is_any_processing() is True
    assert lanes.active_lane() == LANE_PROACTIVE
    lanes.end_proactive()
    assert lanes.active_lane() is None


def test_priority_user_over_proactive_over_background():
    lanes = ProcessingLanes()
    lanes.begin_background()
    assert lanes.active_lane() == LANE_BACKGROUND
    lanes.begin_proactive()
    assert lanes.active_lane() == LANE_PROACTIVE
    lanes.begin_user()
    assert lanes.active_lane() == LANE_USER
    # User leaves: proactive still beats background
    lanes.end_user()
    assert lanes.active_lane() == LANE_PROACTIVE
    lanes.end_proactive()
    assert lanes.active_lane() == LANE_BACKGROUND


def test_begin_returns_monotonic_generation():
    lanes = ProcessingLanes()
    g1 = lanes.begin_user()
    lanes.end_user()
    g2 = lanes.begin_user()
    assert g1 == 1 and g2 == 2
    assert lanes.generation(LANE_USER) == 2


def test_is_stale_detects_superseded_same_lane_round():
    lanes = ProcessingLanes()
    gen = lanes.begin_user()
    assert lanes.is_stale(LANE_USER, gen) is False
    lanes.begin_user()  # new request supersedes the first
    assert lanes.is_stale(LANE_USER, gen) is True


def test_user_begin_invalidates_inflight_proactive():
    """The moment a user request begins, in-flight proactive results go stale."""
    lanes = ProcessingLanes()
    gen = lanes.begin_proactive()
    lanes.begin_user()
    assert lanes.is_stale(LANE_PROACTIVE, gen) is True
    assert lanes.is_stale(LANE_BACKGROUND, lanes.generation(LANE_BACKGROUND)) is False


def test_overlapping_proactive_rounds_counter_based():
    """Two overlapping proactive checks: one end keeps the lane active."""
    lanes = ProcessingLanes()
    g1 = lanes.begin_proactive()
    g2 = lanes.begin_proactive()
    assert g1 != g2
    lanes.end_proactive()
    assert lanes.is_proactive_processing() is True
    lanes.end_proactive()
    assert lanes.is_proactive_processing() is False
    assert lanes.active_lane() is None


def test_double_end_is_clamped():
    """end_* on an idle lane is a no-op (never goes negative)."""
    lanes = ProcessingLanes()
    lanes.end_user()
    lanes.end_user()
    assert lanes.is_user_processing() is False
    assert lanes.active_lane() is None


def test_unknown_lane_rejected():
    lanes = ProcessingLanes()
    with pytest.raises(ValueError):
        lanes._begin("teleport")
    with pytest.raises(ValueError):
        lanes._end("teleport")
    with pytest.raises(ValueError):
        lanes.is_active("teleport")
    with pytest.raises(ValueError):
        lanes.generation("teleport")
    with pytest.raises(ValueError):
        lanes.is_stale("teleport", 1)


def test_thread_safety_hammer():
    """Concurrent begin/end across lanes ends fully idle."""
    lanes = ProcessingLanes()
    lanes_list = [LANE_USER, LANE_PROACTIVE, LANE_BACKGROUND]
    errors: list[Exception] = []

    def worker():
        try:
            for _ in range(200):
                lane = lanes_list[hash(threading.get_ident()) % 3]
                if lane == LANE_USER:
                    lanes.begin_user()
                    lanes.end_user()
                elif lane == LANE_PROACTIVE:
                    lanes.begin_proactive()
                    lanes.end_proactive()
                else:
                    lanes.begin_background()
                    lanes.end_background()
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert lanes.is_any_processing() is False
    assert lanes.active_lane() is None


def test_generations_advance_per_lane_independently():
    lanes = ProcessingLanes()
    u1 = lanes.begin_user()
    lanes.end_user()
    p1 = lanes.begin_proactive()
    assert lanes.generation(LANE_PROACTIVE) == p1
    assert lanes.generation(LANE_USER) == u1
    lanes.end_proactive()
    u2 = lanes.begin_user()
    assert lanes.generation(LANE_USER) == u1 + 1
    assert lanes.generation(LANE_PROACTIVE) == p1 + 1  # user preempt bumped it
