"""
Agent Performance Metrics Collector.

Subscribes to event bus events (TOOL_EXECUTED, TOOL_FAILED, AGENT_DELEGATED)
and maintains rolling per-agent statistics.

Exposed via the 'get_agent_performance' tool.
"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from orchestrator.event_bus import AGENT_DELEGATED, TOOL_EXECUTED, TOOL_FAILED, EventBus

logger = logging.getLogger(__name__)

# ── Constants ──

_MAX_CALLS_PER_AGENT = 100  # ring buffer size
_DEFAULT_AGENT = "raphael"


# ── Data Structures ──


@dataclass
class CallRecord:
    """A single recorded tool call."""
    tool: str
    success: bool
    latency_ms: float
    timestamp: float = field(default_factory=time.time)


class MetricsCollector:
    """Thread-safe collector that subscribes to the event bus and tracks agent metrics."""

    _instance: MetricsCollector | None = None
    _lock: threading.Lock = threading.Lock()
    _calls: dict[str, list[CallRecord]] = field(default_factory=lambda: defaultdict(list))
    _delegations: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _tool_usage: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))
    _subscribed: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._lock = threading.Lock()  # type: ignore[attr-defined]
            cls._instance._calls: dict[str, list[CallRecord]] = defaultdict(list)  # type: ignore[misc]
            cls._instance._delegations: dict[str, int] = defaultdict(int)  # type: ignore[misc]
            cls._instance._tool_usage: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))  # type: ignore[misc, attr-defined]
            cls._instance._subscribed = False  # type: ignore[attr-defined]
        return cls._instance

    def subscribe(self):
        """Attach to the event bus (call once at startup)."""
        if self._subscribed:
            return
        bus = EventBus()
        bus.subscribe(TOOL_EXECUTED, self._on_tool_executed)
        bus.subscribe(TOOL_FAILED, self._on_tool_failed)
        bus.subscribe(AGENT_DELEGATED, self._on_agent_delegated)
        self._subscribed = True
        logger.info("MetricsCollector subscribed to event bus")

    # ── Event Handlers ──

    def _on_tool_executed(self, _event: str, data: dict):
        agent = data.get("agent", _DEFAULT_AGENT)
        tool = data.get("tool", "unknown")
        latency = data.get("latency_ms", 0.0)
        self._record(agent, tool, success=True, latency_ms=latency)

    def _on_tool_failed(self, _event: str, data: dict):
        agent = data.get("agent", _DEFAULT_AGENT)
        tool = data.get("tool", "unknown")
        self._record(agent, tool, success=False, latency_ms=0.0)

    def _on_agent_delegated(self, _event: str, data: dict):
        to_agent = data.get("to_agent", "unknown")
        with self._lock:
            self._delegations[to_agent] += 1

    # ── Recording ──

    def _record(self, agent: str, tool: str, success: bool, latency_ms: float):
        record = CallRecord(tool=tool, success=success, latency_ms=latency_ms)
        with self._lock:
            calls = self._calls[agent]
            calls.append(record)
            if len(calls) > _MAX_CALLS_PER_AGENT:
                calls.pop(0)
            self._tool_usage[agent][tool] += 1

    # ── Queries ──

    def get_stats(self, agent: str | None = None) -> dict:
        """Return metrics dict for one agent or all agents."""
        with self._lock:
            if agent:
                return {agent: self._agent_summary(agent)}
            return {a: self._agent_summary(a) for a in list(self._calls.keys())}

    def _agent_summary(self, agent: str) -> dict:
        calls = self._calls.get(agent, [])
        if not calls:
            return {
                "call_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "min_latency_ms": 0.0,
                "max_latency_ms": 0.0,
                "tool_usage": dict(self._tool_usage.get(agent, {})),
                "delegation_count": self._delegations.get(agent, 0),
            }

        latencies = [c.latency_ms for c in calls if c.success]
        success_count = sum(1 for c in calls if c.success)
        failure_count = len(calls) - success_count

        return {
            "call_count": len(calls),
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": round(success_count / len(calls), 4) if calls else 0.0,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
            "min_latency_ms": round(min(latencies), 1) if latencies else 0.0,
            "max_latency_ms": round(max(latencies), 1) if latencies else 0.0,
            "tool_usage": dict(self._tool_usage.get(agent, {})),
            "delegation_count": self._delegations.get(agent, 0),
        }

    def get_all_agents(self) -> list[str]:
        """Return list of all agents with recorded data."""
        with self._lock:
            return list(self._calls.keys()) + list(self._delegations.keys())

    def format_report(self) -> str:
        """Return a human-readable formatted report."""
        stats = self.get_stats()
        if not stats:
            return "No agent performance data recorded yet."

        lines = ["**Agent Performance Report**\n"]
        for agent, s in sorted(stats.items()):
            lines.append(f"**{agent.upper()}**")
            if s["call_count"] == 0:
                lines.append("  No calls recorded.\n")
                continue
            lines.append(f"  Calls: {s['call_count']}  "
                         f"✓ {s['success_count']}  "
                         f"✗ {s['failure_count']}  "
                         f"Rate: {s['success_rate']*100:.0f}%")
            lines.append(f"  Latency: avg {s['avg_latency_ms']}ms  "
                         f"min {s['min_latency_ms']}ms  "
                         f"max {s['max_latency_ms']}ms")
            lines.append(f"  Top tools: {', '.join(sorted(s['tool_usage'].keys())[:5])}")
            lines.append(f"  Delegation count: {s['delegation_count']}\n")

        lines.append("---\n")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return "\n".join(lines)


# ── Singleton accessor ──
