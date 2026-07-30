"""Tests for the Agent Performance Metrics collector."""

from orchestrator.event_bus import EventBus
from orchestrator.agent_metrics import MetricsCollector


def setup_function():
    """Reset singleton state before each test."""
    bus = EventBus()
    bus.clear()
    # Reset MetricsCollector singleton by clearing internal state
    mc = MetricsCollector()
    with mc._lock:
        mc._calls.clear()
        mc._delegations.clear()
        mc._tool_usage.clear()
        mc._subscribed = False


def test_record_tool_call():
    """Recording a successful call should update stats."""
    mc = MetricsCollector()
    mc._record("raphael", "get_weather", success=True, latency_ms=42.0)

    stats = mc.get_stats("raphael")
    assert stats["raphael"]["call_count"] == 1
    assert stats["raphael"]["success_count"] == 1
    assert stats["raphael"]["failure_count"] == 0
    assert stats["raphael"]["success_rate"] == 1.0


def test_record_failure():
    """Recording a failed call should decrement success rate."""
    mc = MetricsCollector()
    mc._record("raphael", "get_weather", success=True, latency_ms=10.0)
    mc._record("raphael", "bad_tool", success=False, latency_ms=0.0)

    stats = mc.get_stats("raphael")
    assert stats["raphael"]["call_count"] == 2
    assert stats["raphael"]["success_count"] == 1
    assert stats["raphael"]["failure_count"] == 1
    assert stats["raphael"]["success_rate"] == 0.5


def test_latency_calculation():
    """Average/min/max latency should only count successful calls."""
    mc = MetricsCollector()
    mc._record("raphael", "t1", success=True, latency_ms=10.0)
    mc._record("raphael", "t2", success=True, latency_ms=20.0)
    mc._record("raphael", "t3", success=True, latency_ms=30.0)
    mc._record("raphael", "t4", success=False, latency_ms=0.0)  # ignored

    stats = mc.get_stats("raphael")
    assert stats["raphael"]["avg_latency_ms"] == 20.0
    assert stats["raphael"]["min_latency_ms"] == 10.0
    assert stats["raphael"]["max_latency_ms"] == 30.0


def test_tool_usage_tracking():
    """Tool usage should count how many times each tool was called."""
    mc = MetricsCollector()
    mc._record("raphael", "get_weather", success=True, latency_ms=5.0)
    mc._record("raphael", "get_weather", success=True, latency_ms=5.0)
    mc._record("raphael", "web_search", success=True, latency_ms=10.0)

    stats = mc.get_stats("raphael")
    assert stats["raphael"]["tool_usage"]["get_weather"] == 2
    assert stats["raphael"]["tool_usage"]["web_search"] == 1


def test_multiple_agents():
    """Should track separate stats per agent."""
    mc = MetricsCollector()
    mc._record("raphael", "get_weather", success=True, latency_ms=10.0)
    mc._record("analytics", "get_market_quote", success=True, latency_ms=50.0)

    all_stats = mc.get_stats()
    assert "raphael" in all_stats
    assert "analytics" in all_stats
    assert all_stats["raphael"]["call_count"] == 1
    assert all_stats["analytics"]["call_count"] == 1


def test_ring_buffer_limit():
    """Should not exceed MAX_CALLS_PER_AGENT records."""
    mc = MetricsCollector()
    from orchestrator.agent_metrics import _MAX_CALLS_PER_AGENT
    for i in range(_MAX_CALLS_PER_AGENT + 10):
        mc._record("raphael", f"tool_{i}", success=True, latency_ms=1.0)

    stats = mc.get_stats("raphael")
    assert stats["raphael"]["call_count"] == _MAX_CALLS_PER_AGENT


def test_delegation_tracking():
    """Delegation counts should be tracked per agent."""
    mc = MetricsCollector()
    mc._on_agent_delegated("agent.delegated", {"to_agent": "analytics"})
    mc._on_agent_delegated("agent.delegated", {"to_agent": "analytics"})
    mc._on_agent_delegated("agent.delegated", {"to_agent": "researcher"})

    mc.get_stats()
    assert "analytics" in mc._delegations
    assert mc._delegations["analytics"] == 2
    assert mc._delegations["researcher"] == 1


def test_format_report():
    """Format report should return a non-empty string with agent names."""
    mc = MetricsCollector()
    mc._record("raphael", "get_weather", success=True, latency_ms=10.0)
    mc._record("analytics", "get_market_quote", success=True, latency_ms=50.0)

    report = mc.format_report()
    assert "RAPHAEL" in report
    assert "ANALYTICS" in report
    assert "get_weather" in report


def test_format_report_empty():
    """Empty collector should return a friendly message."""
    mc = MetricsCollector()
    report = mc.format_report()
    assert "No agent performance data" in report


def test_event_bus_integration():
    """Publishing TOOL_EXECUTED should update metrics."""
    mc = MetricsCollector()
    mc.subscribe()

    EventBus().publish("tool.executed", agent="raphael", tool="get_weather", latency_ms=42.0)
    EventBus().publish("tool.executed", agent="raphael", tool="web_search", latency_ms=15.0)
    EventBus().publish("tool.failed", agent="raphael", tool="bad_tool")

    stats = mc.get_stats("raphael")
    assert stats["raphael"]["call_count"] == 3
    assert stats["raphael"]["success_count"] == 2
    assert stats["raphael"]["failure_count"] == 1
    assert stats["raphael"]["tool_usage"]["get_weather"] == 1
    assert stats["raphael"]["tool_usage"]["web_search"] == 1
