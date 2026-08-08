"""
Tests for the core orchestrator — ToolExecutor and RaphaelOrchestrator.
Run with: python -m pytest tests/test_orchestrator.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.core import ToolExecutor


# ── ToolExecutor tests ──


def test_tool_executor_has_correct_number():
    """ToolExecutor should have all tools registered."""
    executor = ToolExecutor()
    assert len(executor.tool_map) == 173


def test_tool_executor_has_expected_tools():
    """All core tool functions must be present."""
    executor = ToolExecutor()
    expected = {
        "copy_to_clipboard", "read_clipboard", "launch_app", "open_url",
        "speak", "generate_chart", "run_command",
        "recall_memory", "save_memory", "web_search", "process_file", "browser_control",
        # System volume
        "set_system_volume", "get_system_volume", "get_session_cost",
        "ui_click", "ui_type_text", "ui_press_key", "ui_hotkey",
        "ui_focus_window", "ui_get_mouse_position", "capture_screen",
        "copy_image_to_clipboard", "get_weather", "analyze_image",
        "run_in_background", "get_task_status", "cancel_task", "list_background_tasks",
        "list_knowledge_files", "read_knowledge_file",
        "web_fetch",
        "list_agents", "delegate_to_agent", "delegate_parallel",
        # Upstox analytics
        "get_portfolio_holdings", "get_positions", "get_market_quote",
        "get_historical_data", "get_portfolio_summary",
        # Raphael evolution
        "learn_from_feedback",
        # Agent performance
        "get_agent_performance",
        # Tool health
        "check_tool_health",
        # Session cost
        "get_session_cost",
        # Workflow
        "execute_workflow",
        "list_workflows",
        "generate_workflow",
        # Capability graph
        "show_capability_graph",
        # Marketplace
        "export_tool",
        "import_tool",
        "list_marketplace",
        # Goals
        "create_goal",
        "list_goals",
        "update_goal",
        "archive_goal",
        # File operations
        "read_file", "write_file", "edit_file",
        "list_directory", "desktop_snapshot",
        "get_clipboard_files",
        # Email
        "send_email", "read_inbox", "search_emails",
        # Agent / Tasks
        "spawn_agent", "list_tasks", "get_task_result",
        # UI tools
        "ui_close_window", "ui_enum_windows",
        "ui_get_explorer_selection", "ui_get_monitors",
        "ui_get_system_state",
        "ui_get_screen_size", "ui_double_click", "ui_scroll", "ui_scroll_at",
        "ui_drag", "ui_smooth_move", "ui_move_relative",
        "ui_mouse_down", "ui_mouse_up",
        # Window state & deep control (C# bridge)
        "ui_minimize_window", "ui_maximize_window", "ui_get_window_rect",
        "ui_move_window", "ui_resize_window",
        "ui_set_always_on_top", "ui_set_window_opacity",
        "ui_hide_window", "ui_show_window",
        # Audio playback
        "play_audio_file", "stop_audio",
        # TTS voicing
        "tts_list_voices", "tts_set_voice",
        # Power & notifications (C# bridge)
        "power_sleep", "power_hibernate", "power_lock",
        "power_shutdown", "power_reboot",
        "show_toast",
        # Desktop inspection
        "desktop_processes", "desktop_environment", "desktop_tray",
        "desktop_taskbar", "desktop_network", "desktop_system_info",
        "desktop_snapshot_v2",
        # Background delegation
        "delegate_background", "check_task", "save_output",
        # Extra/New
        "save_song",
        "delete_memory_entry",
        "flush_memory",
        "list_memories",
        "get_immediate_response",
        "play_song",
        "web_fetch_multi",
        # Music Player
        "add_to_library", "remove_from_library", "scan_local_library",
        "list_local_songs",
        "play_playlist",
        "stream_song", "stream_playlist", "search_online",
        "add_to_queue", "clear_queue", "show_queue",
        "pause_music", "resume_music", "stop_music",
        "next_song", "previous_song", "seek_music",
        "set_music_volume", "get_music_volume",
        "set_repeat_mode", "set_shuffle",
        "get_current_song", "get_playback_status", "get_playback_progress",
        "show_recently_played",
        "create_playlist", "delete_playlist", "list_playlists",
        "add_to_playlist", "save_playlist",
        "like_current_song", "unlike_current_song",
        "list_liked_songs", "play_liked_songs",
        # Phase D: services, env vars, process lifecycle
        "service_list", "service_start", "service_stop",
        "env_get", "env_set", "process_kill", "process_wait",
        # Phase D: shortcuts + recycle bin
        "create_shortcut", "recycle_bin_get", "recycle_bin_empty",
        # Phase D: keyboard state + DPI/brightness
        "key_is_pressed", "caps_lock_state", "num_lock_state",
        "monitor_get_dpi", "get_brightness", "set_brightness",
        # Raphael UI Presentation State
        "get_raphael_ui_state", "show_raphael_window", "hide_raphael_window",
        # Raphael Playground Tools
        "render_playground_chart", "render_playground_diagram",
        "render_playground_html", "clear_playground",
    }
    missing = expected - set(executor.tool_map.keys())
    extra = set(executor.tool_map.keys()) - expected
    assert not missing, f"Missing tools: {missing}"
    assert not extra, f"Extra tools: {extra}"


def test_tool_executor_unknown_tool():
    """Unknown tool should return an error message."""
    executor = ToolExecutor()
    result = executor.execute("nonexistent_tool", {})
    assert "Unknown tool" in result


def test_tool_executor_execute_read_clipboard():
    """read_clipboard should return a string (no crash)."""
    executor = ToolExecutor()
    result = executor.execute("read_clipboard", {})
    assert isinstance(result, str)
    assert len(result) > 0


def test_tool_executor_execute_with_none_args():
    """ToolExecutor should handle None arguments gracefully without crashing."""
    executor = ToolExecutor()
    result = executor.execute("ui_get_mouse_position", None)  # type: ignore[arg-type]
    assert isinstance(result, str)
    assert "Failed to get mouse position" in result or "Current mouse position" in result


# ── RaphaelOrchestrator tests ──


@patch("orchestrator.core.LLMClient")
def test_process_message_simple(mock_llm_class):
    """Simple text response without tool calls."""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Hello! How can I help you?"
    mock_response.tool_calls = None
    mock_llm.chat.return_value = mock_response
    mock_llm_class.return_value = mock_llm

    from orchestrator.core import RaphaelOrchestrator
    orch = RaphaelOrchestrator()
    orch.llm = mock_llm

    result = orch.process_message("Say hello")
    assert "Hello" in result


@patch("orchestrator.memory_agent.get_relevant_context", return_value="")
@patch("memory.agent_memory.get_context", return_value="")
@patch("orchestrator.core.LLMClient")
def test_process_message_with_tool_call(mock_llm_class, mock_get_context, mock_get_relevant):
    """Single tool call followed by text response."""
    mock_llm = MagicMock()

    # First response: tool call
    tool_response = MagicMock()
    tool_response.content = None
    tool_call = MagicMock()
    tool_call.id = "call_1"
    tool_call.function.name = "read_clipboard"
    tool_call.function.arguments = "{}"
    tool_response.tool_calls = [tool_call]
    tool_response.reasoning_content = None

    # Second response: text
    text_response = MagicMock()
    text_response.content = "Clipboard has text."
    text_response.tool_calls = None

    mock_llm.chat.side_effect = [
        tool_response,
        text_response,
    ]
    mock_llm_class.return_value = mock_llm

    from orchestrator.core import RaphaelOrchestrator
    orch = RaphaelOrchestrator()
    orch.llm = mock_llm

    result = orch.process_message("What's on my clipboard?")
    assert "Clipboard has text" in result


@patch("orchestrator.core.LLMClient")
def test_orchestrator_reset_conversation(mock_llm_class):
    """reset_conversation should clear history."""
    mock_llm_class.return_value = MagicMock()
    from orchestrator.core import RaphaelOrchestrator
    orch = RaphaelOrchestrator()
    orch.history = [{"role": "user", "content": "hello"}]
    assert len(orch.history) == 1
    orch.reset_conversation()
    assert len(orch.history) == 0


def test_policy_allows_safe_read_only_command():
    """Safe read-only commands should run without confirmation."""
    from orchestrator.policy import evaluate_tool_call
    decision = evaluate_tool_call("run_command", {"command": "git status"})
    assert decision.allowed
    assert decision.risk == "safe"


def test_policy_auto_allows_unknown_command():
    """Previously confirm-required commands are now auto-allowed."""
    from orchestrator.policy import evaluate_tool_call
    decision = evaluate_tool_call("run_command", {"command": "pip install something"})
    assert decision.allowed, "Non-destructive commands should be auto-allowed"


def test_policy_blocks_destructive_command():
    """Destructive commands should be blocked instead of merely confirmed."""
    from orchestrator.policy import evaluate_tool_call
    decision = evaluate_tool_call("run_command", {"command": "del /s important"})
    assert decision.blocked
    assert "destructive" in decision.reason


def test_tool_executor_auto_allows_risky_desktop_tools():
    """Previously risky tools like ui_click are now auto-allowed (no permission prompt)."""
    executor = ToolExecutor()
    result = executor.execute("ui_click", {"x": 100, "y": 100})
    assert "Permission required" not in result, "No permission prompt should appear"


def test_startup_routine_daily_runs_once_per_day():
    """Daily routines should skip after they have already run today."""
    from datetime import datetime
    from orchestrator.routines import RoutineSpec, should_run
    routine = RoutineSpec(name="weather", tool_name="get_weather", last_run="2026-06-30", frequency="daily")
    due, reason = should_run(routine, datetime(2026, 6, 30, 9, 0))
    assert not due
    assert reason == "already ran today"


def test_startup_routine_builds_weather_and_stock_tasks():
    """Personal startup preferences should become standard routine specs."""
    from orchestrator.routines import build_default_startup_routines
    routines = build_default_startup_routines(location="Hyderabad", stock_symbols=["NVDA"])
    assert [routine.name for routine in routines] == ["daily_weather", "stock_nvda"]
    assert routines[0].tool_name == "get_weather"
    assert routines[1].tool_name == "web_search"


def test_subagent_routes_tools_to_standard_profiles():
    """Tools should map to scoped worker profiles."""
    from orchestrator.subagents import route_tool_to_subagent
    assert route_tool_to_subagent("get_weather").name == "research"
    assert route_tool_to_subagent("ui_click").name == "desktop"
    assert route_tool_to_subagent("run_command").name == "desktop"


@patch("memory.memory_manager.search_memory")
@patch("memory.memory_manager.load_memory")
def test_get_relevant_context_librarian(mock_load_memory, mock_search_memory):
    """Test that get_relevant_context extracts core profile and matches relevant facts."""
    from orchestrator.memory_agent import _context_cache, get_relevant_context

    _context_cache.clear()  # cache is module-level; isolate from prior calls

    mock_load_memory.return_value = {
        "user_memory": {
            "name": {"value": "Mohan Kumar", "updated": "2026-07-01"},
            "job": {"value": "Web Developer", "updated": "2026-07-01"},
            "motto": {"value": "Learning new things", "updated": "2026-07-01"},
            "city": {"value": "Indala's Location", "updated": "2026-07-01"},
            "favorite_food": {"value": "Pizza", "updated": "2026-07-01"}
        },
        "daily_task_memory": {},
        "chat_memory": {},
        "feature_memory": {
            "programming_language": {"value": "Python", "updated": "2026-07-01"}
        }
    }
    # FTS5 search returns the matching feature entry
    mock_search_memory.return_value = [
        {"key": "programming_language", "value": "Python", "category": "feature_memory"},
    ]

    context = get_relevant_context("What programming language do I use?")

    assert "Mohan Kumar" in context
    assert "Web Developer" in context
    # FTS5 result on "programming_language" key finds "Python" value
    assert "Python" in context
    assert "programming_language" in context


@patch("orchestrator.memory_agent.update_memory")
@patch("orchestrator.core.LLMClient")
def test_run_memory_agent_organizer(mock_llm_class, mock_update_memory):
    """Test that run_memory_agent extracts facts and triggers update_memory."""
    from orchestrator.memory_agent import run_memory_agent

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = '{"user_memory": {"favorite_editor": "VS Code"}}'
    mock_llm.chat.return_value = mock_response
    mock_llm_class.return_value = mock_llm

    run_memory_agent("I switched my editor to VS Code", "I will remember that.")

    mock_update_memory.assert_called_once_with({"user_memory": {"favorite_editor": "VS Code"}})
