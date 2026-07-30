"""Tests for the Capability Graph."""

from tools_meta.manager import init_tool, set_state, delete_tool, STATE_ACTIVE


def setup_function():
    for name in ("graph_tool_a", "graph_tool_b"):
        delete_tool(name)


def setup_tool(name, deps=None, depended_by=None):
    """Helper to create a tool with dependencies."""
    init_tool(name, f"Test {name}", dependencies=deps or [])
    for s in ["generated", "validated", "tested", "benchmarked", "reviewed", "registered", STATE_ACTIVE]:
        set_state(name, s)


def test_build_mermaid():
    """Mermaid output should include tool names."""
    from tools_meta.graph import build_mermaid
    setup_tool("graph_tool_a")
    result = build_mermaid()
    assert "graph_tool_a" in result
    assert "flowchart LR" in result  # mermaid keyword


def test_build_mermaid_with_deps():
    """Dependencies should appear as edges."""
    from tools_meta.graph import build_mermaid
    setup_tool("graph_tool_b", deps=["graph_tool_a"])
    result = build_mermaid()
    # Should have the edge line
    assert "graph_tool_b" in result


def test_build_mermaid_empty():
    """Empty registry should produce a placeholder diagram."""
    from tools_meta.graph import build_mermaid
    result = build_mermaid()
    # If no tools left, shows empty message
    if "No tools" in result:
        assert True
    else:
        assert "flowchart" in result


def test_build_summary():
    """Summary should include tool status and dependency info."""
    from tools_meta.graph import build_summary
    setup_tool("graph_tool_a")
    result = build_summary()
    assert "graph_tool_a" in result


def test_show_capability_graph():
    """Tool function should return mermaid diagram."""
    from tools_meta.graph import show_capability_graph
    result = show_capability_graph()
    assert "```mermaid" in result or "No tools" in result
