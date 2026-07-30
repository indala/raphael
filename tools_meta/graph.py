"""Capability Graph — dependency visualization for all tools.

Reads tools_meta/registry.json and generates:
  - Mermaid.js flowchart (text-based, no dependencies)
  - matplotlib PNG (if available)
  - Text summary of dependency chains
"""

import logging
from tools_meta.manager import list_tools

logger = logging.getLogger(__name__)

NODE_COLORS = {
    "active": "#22c55e",
    "degraded": "#eab308",
    "broken": "#ef4444",
    "archived": "#6b7280",
    "designed": "#3b82f6",
    "generated": "#8b5cf6",
    "validated": "#a855f7",
    "tested": "#06b6d4",
    "benchmarked": "#14b8a6",
    "reviewed": "#10b981",
    "registered": "#6366f1",
}


def build_mermaid() -> str:
    """Generate a Mermaid.js flowchart from the tool registry."""
    tools = list_tools()
    if not tools:
        return "```mermaid\nflowchart LR\n  empty[No tools in registry]\n```"

    lines = ["```mermaid", "flowchart LR"]
    edges = []

    for t in tools:
        name = t["name"]
        status = t.get("status", "unknown")
        color = NODE_COLORS.get(status, "#94a3b8")
        safe_name = name.replace("-", "_").replace(" ", "_")
        lines.append(f"  {safe_name}[{name}]:::s{status}")

        # Dependencies
        for dep in t.get("dependencies", []):
            dep_safe = dep.replace("-", "_").replace(" ", "_")
            edges.append(f"  {safe_name} --> {dep_safe}")

        # Depended by
        for dep in t.get("depended_by", []):
            dep_safe = dep.replace("-", "_").replace(" ", "_")
            edges.append(f"  {dep_safe} --> {safe_name}")

    lines.extend(edges)

    # Style definitions
    for status, color in NODE_COLORS.items():
        lines.append(f"  classDef s{status} fill:{color}22,stroke:{color},stroke-width:2px;")

    lines.append("```")
    return "\n".join(lines)


def build_summary() -> str:
    """Generate a text summary of tool dependency chains."""
    tools = list_tools()
    if not tools:
        return "No tools in registry."

    lines = ["**Capability Dependency Summary:**\n"]
    for t in sorted(tools, key=lambda x: x["name"]):
        name = t["name"]
        status = t.get("status", "unknown")
        deps = t.get("dependencies", [])
        depended_by = t.get("depended_by", [])
        lines.append(f"**{name}** [{status}]")
        if deps:
            lines.append(f"  depends on: {', '.join(deps)}")
        if depended_by:
            lines.append(f"  used by: {', '.join(depended_by)}")
        if not deps and not depended_by:
            lines.append("  No dependencies")
        lines.append("")
    return "\n".join(lines)


def show_capability_graph() -> str:
    """Render the capability graph (mermaid) in chat."""
    return build_mermaid()
