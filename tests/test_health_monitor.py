"""Tests for the Continuous Health Monitor."""

from orchestrator.health_monitor import HealthMonitor
from tools_meta.manager import (init_tool, set_state, delete_tool,
                                 STATE_DESIGNED, STATE_ACTIVE)


def setup_function():
    """Remove any test tool from registry."""
    for name in ("test_tool_a", "test_tool_b", "test_tool_c"):
        delete_tool(name)


def _ensure_test_tool(name: str, status: str = STATE_DESIGNED):
    """Helper: create a tool entry at the desired state."""
    err = init_tool(name, f"Test tool {name}", author="test")
    if err and "already exists" not in err:
        raise RuntimeError(f"init_tool failed: {err}")
    # Walk through valid states to reach target
    state_order = [STATE_DESIGNED, "generated", "validated", "tested",
                   "benchmarked", "reviewed", "registered", STATE_ACTIVE]
    if status in state_order:
        idx = state_order.index(status)
        for s in state_order[:idx + 1]:
            err = set_state(name, s)
            if err and "Cannot transition" not in err:
                raise RuntimeError(f"set_state to {s} failed: {err}")


def test_healthy_tool():
    """A tool with no execution data should show no issues."""
    _ensure_test_tool("test_tool_a", STATE_ACTIVE)
    monitor = HealthMonitor()
    result = monitor.check_tool("test_tool_a", {
        "test_tool_a": {"avg_ms": 10.0, "count": 5, "error_rate": 0.0}
    })
    assert result["tool"] == "test_tool_a"
    assert len(result["issues"]) == 0


def test_high_latency():
    """Tool with avg_latency > threshold should be flagged."""
    monitor = HealthMonitor()
    result = monitor.check_tool("some_tool", {
        "some_tool": {"avg_ms": 3000.0, "count": 10, "error_rate": 0.0}
    })
    assert len(result["issues"]) == 1
    assert "High latency" in result["issues"][0]


def test_high_error_rate():
    """Tool with high error rate should be flagged."""
    monitor = HealthMonitor()
    result = monitor.check_tool("some_tool", {
        "some_tool": {"avg_ms": 100.0, "count": 10, "error_rate": 0.5}
    })
    assert len(result["issues"]) == 1
    assert "High error rate" in result["issues"][0]


def test_both_issues():
    """Tool with both high latency and high error rate should flag both."""
    monitor = HealthMonitor()
    result = monitor.check_tool("some_tool", {
        "some_tool": {"avg_ms": 600.0, "count": 10, "error_rate": 0.3}
    })
    assert len(result["issues"]) == 2


def test_insufficient_data():
    """Tool with fewer than MIN_CALLS_FOR_EVAL calls should skip evaluation."""
    monitor = HealthMonitor()
    result = monitor.check_tool("some_tool", {
        "some_tool": {"avg_ms": 9999.0, "count": 1, "error_rate": 0.0}
    })
    assert len(result["issues"]) == 0
    assert any("Insufficient data" in r for r in result["recommendations"])


def test_check_all():
    """check_all should return reports for all tools in registry."""
    _ensure_test_tool("test_tool_a", STATE_ACTIVE)
    _ensure_test_tool("test_tool_b", STATE_ACTIVE)

    exec_stats = {
        "test_tool_a": {"avg_ms": 10.0, "count": 10, "error_rate": 0.0},
        "test_tool_b": {"avg_ms": 1000.0, "count": 10, "error_rate": 0.3},
    }
    monitor = HealthMonitor()
    results = monitor.check_all(exec_stats)

    names = [r["tool"] for r in results]
    assert "test_tool_a" in names
    assert "test_tool_b" in names

    for r in results:
        if r["tool"] == "test_tool_a":
            assert len(r["issues"]) == 0
        elif r["tool"] == "test_tool_b":
            assert len(r["issues"]) >= 1


def test_format_report():
    """Format report should render text with tool names and issues."""
    _ensure_test_tool("test_tool_a", STATE_ACTIVE)
    monitor = HealthMonitor()
    results = [
        monitor.check_tool("test_tool_a", {
            "test_tool_a": {"avg_ms": 600.0, "count": 10, "error_rate": 0.0}
        }),
    ]
    report = monitor.format_report(results)
    assert "test_tool_a" in report
    assert "High latency" in report


def test_format_report_healthy():
    """A healthy report should show healthy count."""
    _ensure_test_tool("test_tool_a", STATE_ACTIVE)
    monitor = HealthMonitor()
    results = [
        monitor.check_tool("test_tool_a", {
            "test_tool_a": {"avg_ms": 10.0, "count": 10, "error_rate": 0.0}
        }),
    ]
    report = monitor.format_report(results)
    assert "healthy" in report.lower() or "1 total" in report


def test_auto_heal():
    """auto_heal should transition ACTIVE tools with high error to DEGRADED."""
    _ensure_test_tool("test_tool_a", STATE_ACTIVE)
    exec_stats = {
        "test_tool_a": {"avg_ms": 100.0, "count": 10, "error_rate": 0.5}
    }
    monitor = HealthMonitor()
    actions = monitor.auto_heal(exec_stats)

    assert any("test_tool_a" in a for a in actions)
    from tools_meta.manager import get_tool_meta
    meta = get_tool_meta("test_tool_a")
    # ACTIVE → DEGRADED (BROKEN only from DEGRADED)
    assert meta.get("status") == "degraded"  # type: ignore[union-attr]


def test_auto_heal_degraded_to_broken():
    """DEGRADED tool with high error rate should go to BROKEN."""
    _ensure_test_tool("test_tool_a", STATE_ACTIVE)
    set_state("test_tool_a", "degraded")
    exec_stats = {
        "test_tool_a": {"avg_ms": 100.0, "count": 10, "error_rate": 0.5}
    }
    monitor = HealthMonitor()
    actions = monitor.auto_heal(exec_stats)

    assert any("BROKEN" in a for a in actions)
    from tools_meta.manager import get_tool_meta
    meta = get_tool_meta("test_tool_a")
    assert meta.get("status") == "broken"  # type: ignore[union-attr]


def test_auto_heal_skips_healthy():
    """auto_heal should not touch healthy tools."""
    _ensure_test_tool("test_tool_a", STATE_ACTIVE)
    exec_stats = {
        "test_tool_a": {"avg_ms": 10.0, "count": 10, "error_rate": 0.0}
    }
    monitor = HealthMonitor()
    actions = monitor.auto_heal(exec_stats)
    assert all("test_tool_a" not in a for a in actions)
    from tools_meta.manager import get_tool_meta
    meta = get_tool_meta("test_tool_a")
    assert meta.get("status") == "active"  # type: ignore[union-attr]
