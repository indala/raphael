import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.loop_guard import LoopGuard


# ── Identical-call block ────────────────────────────────────────────────

def test_identical_calls_trigger_at_threshold():
    guard = LoopGuard(identical_threshold=3)
    assert guard.check("web_search", {"q": "x"}) is None
    assert guard.check("web_search", {"q": "x"}) is None
    warning = guard.check("web_search", {"q": "x"})
    assert warning is not None and "web_search" in warning and "identical" in warning


def test_identical_does_not_trigger_below_threshold():
    guard = LoopGuard(identical_threshold=5)
    for _ in range(4):
        assert guard.check("web_search", {"q": "x"}) is None


def test_identical_args_must_match_exactly():
    guard = LoopGuard(identical_threshold=3)
    assert guard.check("web_search", {"q": "x"}) is None
    assert guard.check("web_search", {"q": "y"}) is None
    # Different args never form a block even at threshold
    assert guard.check("web_search", {"q": "x"}) is None


def test_identical_dict_key_order_ignored():
    guard = LoopGuard(identical_threshold=2)
    assert guard.check("calc", {"a": 1, "b": 2}) is None
    warning = guard.check("calc", {"b": 2, "a": 1})
    assert warning is not None


def test_identical_fires_once_then_goes_silent():
    guard = LoopGuard(identical_threshold=3)
    guard.check("web_search", {"q": "x"})
    guard.check("web_search", {"q": "x"})
    assert guard.check("web_search", {"q": "x"}) is not None
    # Same call again must NOT spam a second warning in one request
    assert guard.check("web_search", {"q": "x"}) is None
    assert guard.check("web_search", {"q": "x"}) is None


def test_identical_fires_on_successful_results_too():
    guard = LoopGuard(identical_threshold=2)
    guard.check("get_status", {}, result="ok")
    warning = guard.check("get_status", {}, result="ok")
    assert warning is not None


# ── A-B-A-B ping-pong ───────────────────────────────────────────────────

def test_pingpong_trigger():
    guard = LoopGuard(pingpong_threshold=4)
    assert guard.check("volume_up") is None
    assert guard.check("volume_down") is None
    assert guard.check("volume_up") is None
    warning = guard.check("volume_down")
    assert warning is not None and "oscillating" in warning


def test_pingpong_not_triggered_by_random_run():
    guard = LoopGuard(pingpong_threshold=4)
    assert guard.check("a") is None
    assert guard.check("b") is None
    assert guard.check("a") is None
    assert guard.check("c") is None  # breaks the alternation


def test_pingpong_fires_once():
    guard = LoopGuard(pingpong_threshold=4)
    guard.check("open")
    guard.check("close")
    guard.check("open")
    assert guard.check("close") is not None
    # after the first warning the flag is set; keep alternating without new warning
    assert guard.check("open") is None
    assert guard.check("close") is None


# ── Poll-tool budget ────────────────────────────────────────────────────

def test_poll_budget_triggers_after_budget():
    guard = LoopGuard(poll_budget=2)
    assert guard.check("check_status") is None
    assert guard.check("check_status") is None
    warning = guard.check("check_status")
    assert warning is not None
    assert "poll" in warning.lower() or "status" in warning


def test_poll_budget_ignores_non_poll_tools():
    guard = LoopGuard(poll_budget=2, identical_threshold=10)
    for _ in range(5):
        assert guard.check("open_app") is None


def test_poll_budget_counts_distinct_names():
    guard = LoopGuard(poll_budget=3)
    # Budget is a cap: warning fires on the first call that exceeds it (4th)
    assert guard.check("check_status") is None
    assert guard.check("wait_for_file") is None
    assert guard.check("get_progress") is None
    warning = guard.check("refresh_window")
    assert warning is not None


# ── Per-request reset semantics ─────────────────────────────────────────

def test_fresh_guard_resets_between_requests():
    guard = LoopGuard(identical_threshold=3)
    guard.check("web_search", {"q": "x"})
    guard.check("web_search", {"q": "x"})
    assert guard.check("web_search", {"q": "x"}) is not None

    # New request = new instance: identical sequence must warn again cleanly
    guard2 = LoopGuard(identical_threshold=3)
    assert guard2.check("web_search", {"q": "x"}) is None
    assert guard2.check("web_search", {"q": "x"}) is None
    assert guard2.check("web_search", {"q": "x"}) is not None


def test_identical_stays_silent_after_warning_in_same_request():
    # Fire-once is per request: a different identical block must not re-warn
    guard = LoopGuard(identical_threshold=2)
    assert guard.check("web_search", {"q": "x"}) is None
    assert guard.check("web_search", {"q": "x"}) is not None
    assert guard.check("read_file", {"path": "a.py"}) is None
    assert guard.check("read_file", {"path": "a.py"}) is None
