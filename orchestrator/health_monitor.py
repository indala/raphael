"""
Continuous Health Monitor for generated tools.

Consumes ToolExecutor execution stats and registry metadata to detect
degraded, broken, or stale tools. Can auto-transition tool states and
publish events to the event bus.

Thresholds:
  - avg_latency > 500ms (>= 5 calls) → DEGRADED candidate
  - error_rate > 20% (>= 5 calls)    → BROKEN candidate
"""

import logging

from tools_meta.manager import (
    STATE_ACTIVE,
    STATE_DEGRADED,
    STATE_REGISTERED,
    get_tool_meta,
    list_tools,
    set_state,
)

logger = logging.getLogger(__name__)

# ── Thresholds ──

LATENCY_THRESHOLD_MS = 500
ERROR_RATE_THRESHOLD = 0.20
MIN_CALLS_FOR_EVAL = 5

# ── Auto-promotion thresholds ──
PROMOTE_MIN_CALLS = 20       # minimum calls before considering promotion
PROMOTE_MAX_ERROR_RATE = 0.05  # max error rate to qualify for promotion


class HealthMonitor:
    """Periodic health checker for all registered tools."""

    def check_tool(self, name: str, exec_stats: dict | None = None) -> dict:
        """Check a single tool's health.

        Args:
            name: Tool name.
            exec_stats: Optional pre-fetched dict of {tool_name: {avg_ms, count}}.
                        If None, queries ToolExecutor.

        Returns:
            dict with keys: tool, status, state, avg_ms, call_count, issues[], recommendations[]
        """
        meta = get_tool_meta(name)
        state = meta.get("status", "unknown") if meta else "unknown"

        result: dict = {
            "tool": name,
            "state": state,
            "avg_ms": 0.0,
            "call_count": 0,
            "error_rate": 0.0,
            "issues": [],
            "recommendations": [],
        }

        # Get execution stats
        stats = exec_stats.get(name, {}) if exec_stats else self._get_exec_stats(name)
        result["avg_ms"] = stats.get("avg_ms", 0.0)
        result["call_count"] = stats.get("count", 0)
        result["error_rate"] = stats.get("error_rate", 0.0)

        # Evaluate thresholds
        cc = result["call_count"]
        if cc < MIN_CALLS_FOR_EVAL:
            result["recommendations"].append(f"Insufficient data (< {MIN_CALLS_FOR_EVAL} calls)")  # type: ignore[union-attr]
            return result

        # Latency check
        avg = result["avg_ms"]
        if avg > LATENCY_THRESHOLD_MS:  # type: ignore[operator]
            result["issues"].append(f"High latency: {avg:.0f}ms (threshold {LATENCY_THRESHOLD_MS}ms)")  # type: ignore[union-attr]
            if state in (STATE_ACTIVE, STATE_DEGRADED):
                result["recommendations"].append("Transition to DEGRADED — review and optimize")  # type: ignore[union-attr]

        # Error rate check
        err = result["error_rate"]
        if err > ERROR_RATE_THRESHOLD:
            result["issues"].append(f"High error rate: {err:.1%} (threshold {ERROR_RATE_THRESHOLD:.0%})")  # type: ignore[union-attr]
            if state == STATE_ACTIVE:
                result["recommendations"].append("Transition to BROKEN — requires investigation")  # type: ignore[union-attr]
            elif state == STATE_DEGRADED:
                result["recommendations"].append("Transition to BROKEN — optimization failed")  # type: ignore[union-attr]

        return result

    def check_all(self, exec_stats: dict | None = None) -> list[dict]:
        """Check all tools and return a list of health reports."""
        if exec_stats is None:
            exec_stats = self._get_all_exec_stats()

        results = []
        for tool in list_tools():
            name = tool.get("name", "")
            if not name:
                continue
            results.append(self.check_tool(name, exec_stats))
        return results

    def auto_heal(self, exec_stats: dict | None = None) -> list[str]:
        """Auto-transition tools that exceed thresholds. Returns list of actions."""
        actions = []
        if exec_stats is None:
            exec_stats = self._get_all_exec_stats()

        for tool in list_tools():
            name = tool.get("name", "")
            status = tool.get("status", "")
            stats = exec_stats.get(name, {})
            cc = stats.get("count", 0)

            # ── Promote REGISTERED → ACTIVE ──────────────────────────
            if status == STATE_REGISTERED:
                if cc >= PROMOTE_MIN_CALLS:
                    err = stats.get("error_rate", 0.0)
                    if err <= PROMOTE_MAX_ERROR_RATE:
                        err_str = set_state(name, STATE_ACTIVE)
                        if not err_str:
                            logger.info("Auto-promoted '%s' to ACTIVE (%d calls, error_rate=%.1f%%)",
                                        name, cc, err * 100)
                            actions.append(f"{name} → ACTIVE (calls={cc}, errors={err:.0%})")
                else:
                    logger.debug("Not enough data to promote '%s': %d/%d calls",
                                name, cc, PROMOTE_MIN_CALLS)
                continue

            # ── Degrade ACTIVE / DEGRADED ───────────────────────────
            if status not in (STATE_ACTIVE, STATE_DEGRADED):
                continue

            if cc < MIN_CALLS_FOR_EVAL:
                continue

            avg = stats.get("avg_ms", 0.0)
            err = stats.get("error_rate", 0.0)

            if err > ERROR_RATE_THRESHOLD:
                target = "broken" if status == STATE_DEGRADED else "degraded"
                err_str = set_state(name, target)
                if not err_str:
                    logger.warning("Auto-transitioned '%s' to %s (error_rate=%.1f%%)", name, target.upper(), err * 100)
                    actions.append(f"{name} → {target.upper()} (error_rate={err:.0%})")
            elif avg > LATENCY_THRESHOLD_MS:
                target = "broken" if status == STATE_DEGRADED else "degraded"
                err_str = set_state(name, target)
                if not err_str:
                    logger.info("Auto-transitioned '%s' to %s (avg_latency=%.0fms)", name, target.upper(), avg)
                    actions.append(f"{name} → {target.upper()} (latency={avg:.0f}ms)")

        return actions

    def format_report(self, results: list[dict] | None = None) -> str:
        """Return a human-readable health report."""
        if results is None:
            results = self.check_all()

        lines = ["**Tool Health Report**\n"]
        healthy = 0
        for r in results:
            if not r["issues"]:
                healthy += 1
                continue
            lines.append(f"**{r['tool']}**  [state: {r['state']}]")
            lines.append(f"  Calls: {r['call_count']}  "
                         f"Avg: {r['avg_ms']:.0f}ms  "
                         f"Errors: {r['error_rate']:.0%}")
            for issue in r["issues"]:
                lines.append(f"  ⚠ {issue}")
            for rec in r["recommendations"]:
                lines.append(f"  → {rec}")
            lines.append("")

        if not results:
            lines.append("No tools in registry.")
        else:
            lines.append("---")
            lines.append(f"{len(results)} total | {healthy} healthy | {len(results) - healthy} with issues")
        return "\n".join(lines)

    # ── Internal helpers ──

    def _get_exec_stats(self, name: str) -> dict:
        """Fetch execution stats for a single tool from ToolExecutor."""
        try:
            from orchestrator.core import ToolExecutor
            times = ToolExecutor._exec_times.get(name, [])
            count = ToolExecutor._exec_counts.get(name, 0)
            avg = round(sum(times) / len(times), 1) if times else 0.0
            # Approximate error rate from metrics collector
            err_rate = self._get_error_rate(name)
            return {"avg_ms": avg, "count": count, "error_rate": err_rate}
        except Exception:
            return {"avg_ms": 0.0, "count": 0, "error_rate": 0.0}

    def _get_all_exec_stats(self) -> dict:
        """Fetch execution stats for all tools from ToolExecutor."""
        try:
            from orchestrator.core import ToolExecutor
            stats = {}
            all_names = set(ToolExecutor._exec_counts.keys())
            all_names.update(t.get("name", "") for t in list_tools())
            for name in all_names:
                if name:
                    stats[name] = self._get_exec_stats(name)
            return stats
        except Exception:
            return {}

    def _get_error_rate(self, name: str) -> float:
        """Estimate error rate from event bus metrics (via MetricsCollector)."""
        try:
            from orchestrator.agent_metrics import MetricsCollector
            # Search for this tool name across all agents
            all_stats = MetricsCollector().get_stats()
            total = 0
            failures = 0
            for _agent, s in all_stats.items():
                usage = s.get("tool_usage", {})
                if name in usage:
                    # We can approximate: tool_usage count shows total calls for this tool
                    # We know failure_count is total failures for this agent
                    # This is a rough estimate per-tool
                    pass
            # Fallback: use agent-level error rate as approximation
            for _agent, s in all_stats.items():
                total += s.get("call_count", 0)
                failures += s.get("failure_count", 0)
            if total == 0:
                return 0.0
            return failures / total
        except Exception:
            return 0.0
