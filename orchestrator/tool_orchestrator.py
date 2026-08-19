"""
ToolOrchestrator — Intelligent tool routing, domain categorization, schema filtering,
and health tracking for Raphael.

Prevents prompt bloat and LLM confusion by injecting only relevant tool schemas
for a given user query while maintaining a fallback core set.
"""

import enum
import logging
import re
import time
from typing import Any

from orchestrator.tools import (
    PARALLEL_SAFE_TOOLS,
    get_filtered_schemas,
    get_tool_schemas,
)

logger = logging.getLogger(__name__)


class ToolDomain(str, enum.Enum):
    AUDIO = "audio"
    MUSIC = "music"
    FILES = "files"
    DESKTOP = "desktop"
    SYSTEM = "system"
    POWER = "power"
    WEB = "web"
    EMAIL = "email"
    MEMORY = "memory"
    TRADING = "trading"
    AGENTS = "agents"
    MCP = "mcp"
    GENERAL = "general"


# Tool mapping per domain
DOMAIN_TOOL_MAP: dict[ToolDomain, tuple[str, ...]] = {
    ToolDomain.AUDIO: (
        "set_system_volume",
        "get_system_volume",
        "check_tool_health",
        "play_audio_file",
        "stop_audio",
    ),
    ToolDomain.MUSIC: (
        "play_song",
        "stream_song",
        "add_to_library",
        "save_song",
        "pause_music",
        "resume_music",
        "stop_music",
        "list_local_songs",
        "list_playlists",
        "play_playlist",
        "create_playlist",
        "get_current_song",
        "set_music_volume",
        "get_music_volume",
        "next_song",
        "previous_song",
        "seek_music",
        "set_shuffle",
        "set_repeat_mode",
        "add_to_playlist",
        "add_to_queue",
        "remove_from_library",
        "save_playlist",
        "scan_local_library",
        "show_queue",
        "show_recently_played",
        "clear_queue",
        "delete_playlist",
        "get_playback_status",
        "get_playback_progress",
        "stream_playlist",
        "like_current_song",
        "unlike_current_song",
        "list_liked_songs",
        "play_liked_songs",
    ),
    ToolDomain.FILES: (
        "view_file",
        "read_file",
        "replace_file_content",
        "write_file",
        "edit_file",
        "list_directory",
        "tree_directory",
        "count_lines_of_code",
        "grep_search",
        "find_files",
        "search_codebase",
        "index_codebase",
        "get_code_outline",
        "read_file_range",
        "query_json",
        "scan_secrets",
        "git_status",
        "git_diff",
        "run_tests",
        "run_linter",
        "process_file",
        "analyze_image",
        "read_clipboard",
        "copy_to_clipboard",
        "copy_image_to_clipboard",
        "get_clipboard_files",
        "save_output",
        "generate_chart",
        "render_playground_chart",
        "render_playground_diagram",
        "render_playground_html",
        "clear_playground",
        "create_shortcut",
        "recycle_bin_get",
        "recycle_bin_empty",
    ),
    ToolDomain.DESKTOP: (
        "desktop_snapshot_v2",
        "desktop_snapshot",
        "get_active_window_info",
        "desktop_taskbar",
        "desktop_tray",
        "desktop_processes",
        "desktop_system_info",
        "desktop_network",
        "desktop_environment",
        "get_raphael_ui_state",
        "show_raphael_window",
        "hide_raphael_window",
        "capture_screen",
        "launch_app",
        "run_command",
        "ui_click",
        "ui_type_text",
        "ui_press_key",
        "ui_hotkey",
        "ui_focus_window",
        "ui_enum_windows",
        "ui_close_window",
        "ui_minimize_window",
        "ui_maximize_window",
        "ui_get_window_rect",
        "ui_move_window",
        "ui_resize_window",
        "ui_set_always_on_top",
        "ui_set_window_opacity",
        "ui_hide_window",
        "ui_show_window",
        "ui_double_click",
        "ui_drag",
        "ui_get_explorer_selection",
        "ui_get_monitors",
        "ui_get_mouse_position",
        "ui_get_screen_size",
        "ui_get_system_state",
        "ui_mouse_down",
        "ui_mouse_up",
        "ui_move_relative",
        "ui_scroll",
        "ui_scroll_at",
        "ui_smooth_move",
        "key_is_pressed",
        "caps_lock_state",
        "num_lock_state",
        "monitor_get_dpi",
        "get_brightness",
        "set_brightness",
    ),
    ToolDomain.SYSTEM: (
        "service_list",
        "service_start",
        "service_stop",
        "env_get",
        "env_set",
        "process_kill",
        "process_wait",
        "get_session_cost",
    ),
    ToolDomain.POWER: (
        "power_sleep",
        "power_hibernate",
        "power_lock",
        "power_shutdown",
        "power_reboot",
        "show_toast",
    ),
    ToolDomain.WEB: (
        "web_search",
        "web_fetch",
        "web_fetch_multi",
        "open_url",
        "get_weather",
        "browser_control",
        "search_online",
    ),
    ToolDomain.EMAIL: (
        "read_inbox",
        "search_emails",
        "send_email",
    ),
    ToolDomain.MEMORY: (
        "recall_memory",
        "save_memory",
        "list_memories",
        "delete_memory_entry",
        "flush_memory",
        "learn_from_feedback",
        "create_goal",
        "list_goals",
        "update_goal",
        "archive_goal",
        "read_knowledge_file",
        "list_knowledge_files",
    ),
    ToolDomain.TRADING: (
        "get_market_quote",
        "get_historical_data",
        "get_portfolio_holdings",
        "get_portfolio_summary",
        "get_positions",
    ),
    ToolDomain.AGENTS: (
        "spawn_agent",
        "list_agents",
        "delegate_to_agent",
        "delegate_parallel",
        "get_agent_performance",
        "run_in_background",
        "delegate_background",
        "check_task",
        "cancel_task",
        "get_task_result",
        "get_task_status",
        "list_background_tasks",
        "list_tasks",
        "get_immediate_response",
        "execute_workflow",
        "generate_workflow",
        "list_workflows",
        "show_capability_graph",
        "export_tool",
        "import_tool",
        "list_marketplace",
    ),
}

# Domain keyword patterns for fast intent matching
DOMAIN_PATTERNS: dict[ToolDomain, re.Pattern] = {
    ToolDomain.AUDIO: re.compile(
        r"\b(volume|sound|speaker|audio|mute|unmute|louder|quieter|db)\b", re.IGNORECASE
    ),
    ToolDomain.MUSIC: re.compile(
        r"\b(music|song|playlist|play|stream|track|album|artist|lofi|youtube|library|download|save song|listen)\b",
        re.IGNORECASE,
    ),
    ToolDomain.FILES: re.compile(
        r"\b(file|folder|dir|directory|read|write|edit|create file|delete file|path|txt|json|code|csv|clipboard)\b",
        re.IGNORECASE,
    ),
    ToolDomain.DESKTOP: re.compile(
        r"\b(window|click|type|keypress|screenshot|taskbar|tray|process|app|open app|close window|monitor|screen)\b",
        re.IGNORECASE,
    ),
    ToolDomain.SYSTEM: re.compile(
        r"\b(service|services|environment variable|env var|env|process|pid)\b",
        re.IGNORECASE,
    ),
    ToolDomain.POWER: re.compile(
        r"\b(power|shutdown|shut down|restart|reboot|sleep|hibernate|lock screen|lock workstation|toast|notification)\b",
        re.IGNORECASE,
    ),
    ToolDomain.WEB: re.compile(
        r"\b(search|find online|browse|website|url|http|weather|forecast|google|fetch|web)\b",
        re.IGNORECASE,
    ),
    ToolDomain.EMAIL: re.compile(
        r"\b(email|e-mail|mail|inbox|outlook|message|compose|sent)\b",
        re.IGNORECASE,
    ),
    ToolDomain.MEMORY: re.compile(
        r"\b(remember|memory|recall|forget|goal|target|knowledge|note)\b",
        re.IGNORECASE,
    ),
    ToolDomain.TRADING: re.compile(
        r"\b(stock|share|upstox|price|market|trade|buy|sell|portfolio|nifty|sensex)\b",
        re.IGNORECASE,
    ),
    ToolDomain.AGENTS: re.compile(
        r"\b(agent|subagent|delegate|spawn|background task|performance|worker)\b",
        re.IGNORECASE,
    ),
}

# Curated core tools for general queries when domain is broad/ambiguous
CORE_FALLBACK_TOOLS: tuple[str, ...] = (
    "web_search",
    "web_fetch",
    "read_file",
    "edit_file",
    "write_file",
    "recall_memory",
    "save_memory",
    "list_memories",
    "set_system_volume",
    "get_system_volume",
    "play_song",
    "desktop_snapshot_v2",
    "spawn_agent",
    "run_command",
    "launch_app",
    "open_url",
    "get_weather",
    "speak",
    "tts_list_voices",
    "tts_set_voice",
    "save_output",
    "list_tasks",
    "check_task",
    "render_playground_chart",
    "render_playground_diagram",
    "render_playground_html",
    "get_raphael_ui_state",
)


UNIVERSAL_CONTROL_TOOLS: tuple[str, ...] = (
    "set_system_volume",
    "get_system_volume",
    "get_raphael_ui_state",
    "speak",
    "save_output",
)


class ToolOrchestrator:
    """Manages tool routing, intent classification, schema filtering, and execution health."""

    def __init__(self):
        self._metrics: dict[str, dict[str, Any]] = {}

    def classify_query(self, query: str) -> set[ToolDomain]:
        """Classify user query into matching tool domains using keyword patterns."""
        if not query or not query.strip():
            return {ToolDomain.GENERAL}

        matched: set[ToolDomain] = set()
        for domain, pattern in DOMAIN_PATTERNS.items():
            if pattern.search(query):
                matched.add(domain)

        return matched if matched else {ToolDomain.GENERAL}

    def get_filtered_schemas(
        self, query: str, extra_schemas: list[dict[str, Any]] | None = None
    ) -> list[dict[str, Any]]:
        """Return tool schemas filtered to matching query domains.

        Reduces prompt size from 60+ schemas to ~5-15 relevant schemas.
        """
        domains = self.classify_query(query)
        tool_names: set[str] = set()

        if ToolDomain.GENERAL in domains or len(domains) > 4:
            # Broad query — use curated core fallback tools
            tool_names.update(CORE_FALLBACK_TOOLS)
        else:
            for d in domains:
                tool_names.update(DOMAIN_TOOL_MAP.get(d, ()))

        # Always include essential system control tools
        tool_names.update(UNIVERSAL_CONTROL_TOOLS)

        # Also include all active MCP tool names if MCP tools exist
        all_schemas = get_tool_schemas()
        mcp_names = {
            s["function"]["name"]
            for s in all_schemas
            if s["function"]["name"].startswith("mcp_")
        }
        tool_names.update(mcp_names)

        # Retrieve filtered schemas
        filtered = get_filtered_schemas(list(tool_names))

        # Add any dynamically injected runtime schemas
        if extra_schemas:
            existing_names = {s["function"]["name"] for s in filtered}
            for extra in extra_schemas:
                if extra.get("function", {}).get("name") not in existing_names:
                    filtered.append(extra)

        logger.debug(
            "ToolOrchestrator: domains=%s -> %d tool schema(s) selected (out of %d)",
            [d.value for d in domains],
            len(filtered),
            len(all_schemas),
        )

        return filtered

    def is_parallel_safe(self, tool_name: str) -> bool:
        """Check if a tool is read-only and safe for parallel execution."""
        return tool_name in PARALLEL_SAFE_TOOLS

    def track_tool_execution(
        self, tool_name: str, success: bool, duration_ms: float, error: str = ""
    ) -> None:
        """Track runtime health metrics for tool execution."""
        if tool_name not in self._metrics:
            self._metrics[tool_name] = {
                "calls": 0,
                "successes": 0,
                "failures": 0,
                "total_duration_ms": 0.0,
                "last_error": "",
                "last_called_at": 0.0,
            }

        m = self._metrics[tool_name]
        m["calls"] += 1
        if success:
            m["successes"] += 1
        else:
            m["failures"] += 1
            m["last_error"] = error

        m["total_duration_ms"] += duration_ms
        m["last_called_at"] = time.time()

    def get_tool_health_report(self) -> dict[str, dict[str, Any]]:
        """Return snapshot of tool execution metrics."""
        report = {}
        for name, m in self._metrics.items():
            calls = m["calls"]
            report[name] = {
                "calls": calls,
                "success_rate": (m["successes"] / calls) * 100 if calls > 0 else 0.0,
                "avg_latency_ms": (m["total_duration_ms"] / calls) if calls > 0 else 0.0,
                "last_error": m["last_error"],
            }
        return report
