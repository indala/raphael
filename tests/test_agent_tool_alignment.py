"""Tests to audit and verify that all agents have valid, reachable tools matching their roles."""

from agents import _AGENT_REGISTRY, discover_agents
from orchestrator.tools import get_tool_map, get_tool_schemas


def test_all_agents_have_valid_registered_tools():
    """Verify that every tool declared by every agent actually exists in the tool registry."""
    discover_agents()
    tool_map = get_tool_map()
    all_schemas = get_tool_schemas()
    schema_names = {s["function"]["name"] for s in all_schemas if "function" in s}

    assert len(_AGENT_REGISTRY) >= 7, "Expected at least 7 registered agents"

    for agent_name, agent in _AGENT_REGISTRY.items():
        tools = getattr(agent, "available_tools", [])
        if not tools:
            # e.g. PersonalAgent has all tools available
            continue

        for tool_name in tools:
            assert tool_name in schema_names or tool_name in tool_map, (
                f"Agent '{agent_name}' specifies unknown tool '{tool_name}'"
            )


def test_specific_agent_role_alignments():
    """Verify specialized capabilities assigned to agents."""
    discover_agents()

    coding = _AGENT_REGISTRY["coding"]
    assert "grep_search" in coding.available_tools
    assert "find_files" in coding.available_tools
    assert "search_codebase" in coding.available_tools
    assert "index_codebase" in coding.available_tools
    assert "get_code_outline" in coding.available_tools
    assert "read_file_range" in coding.available_tools
    assert "run_tests" in coding.available_tools
    assert "run_linter" in coding.available_tools

    analytics = _AGENT_REGISTRY["analytics"]
    assert "generate_chart" in analytics.available_tools
    assert "get_portfolio_summary" in analytics.available_tools

    desktop = _AGENT_REGISTRY["desktop"]
    assert "get_active_window_info" in desktop.available_tools
    assert "ui_minimize_window" in desktop.available_tools
    assert "ui_close_window" in desktop.available_tools
    assert "launch_app" in desktop.available_tools

    researcher = _AGENT_REGISTRY["researcher"]
    assert "delegate_to_agent" in researcher.available_tools

    tool_manager = _AGENT_REGISTRY["tool_manager"]
    assert "check_tool_health" in tool_manager.available_tools

    librarian = _AGENT_REGISTRY["librarian"]
    assert "recall_memory" in librarian.available_tools
    assert "list_memories" in librarian.available_tools
    assert "save_memory" in librarian.available_tools
