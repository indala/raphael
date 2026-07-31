"""
Lightweight sub-agent profiles for Raphael.

Raphael stays as the single personality. Sub-agents are scoped worker profiles
that describe which tools are appropriate for a task category.

Communication between agents uses structured schemas (not plain strings)
so that profiles are typed, validated, and machine-readable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class AgentPurpose:
    """Structured purpose schema for agent-to-agent communication."""
    category: str
    description: str
    capabilities: tuple[str, ...] = ()
    priority: Literal["low", "normal", "high"] = "normal"


@dataclass(frozen=True, slots=True)
class AgentSystemHint:
    """Structured system hint schema for agent-to-agent communication."""
    behavior: str
    output_format: Literal["natural", "concise_summary", "structured", "verbose"] = "natural"
    constraints: tuple[str, ...] = ()
    risk_tolerance: Literal["none", "low", "medium", "high"] = "low"
    interaction_mode: Literal["autonomous", "confirm_each", "supervised"] = "autonomous"


@dataclass(frozen=True, slots=True)
class SubAgentProfile:
    name: str
    purpose: AgentPurpose
    allowed_tools: tuple[str, ...]
    system_hint: AgentSystemHint
    effort_level: Literal["low", "medium", "high"] = "medium"

    def can_use(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools


# ── Domain keywords for query-to-profile routing ──
DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "desktop": (
        "click", "type", "keyboard", "mouse", "press", "hotkey", "shortcut",
        "scroll", "drag", "move", "cursor", "focus", "window", "launch",
        "open app", "start program", "screen", "monitor", "display",
        "taskbar", "tray", "desktop", "close window",
    ),
    "research": (
        "search", "google", "look up", "find", "what is", "who is",
        "weather", "news", "information about", "tell me about",
        "define", "explain", "summarize", "research",
    ),
    "files": (
        "file", "read", "write", "edit", "save", "open file",
        "analyze", "process", "image", "pdf", "document",
        "clipboard", "copy", "paste", "directory", "folder",
        "rename", "move file", "delete file",
    ),
    "coding": (
        "code", "program", "script", "python", "javascript",
        "function", "class", "bug", "debug", "compile",
        "refactor", "implement", "algorithm",
    ),
    "browser": (
        "browser", "webpage", "website", "url", "http",
        "navigate", "playwright", "web automation",
    ),
    "upstox": (
        "stock", "share", "market", "portfolio", "holding",
        "position", "nse", "bse", "trading", "upstox",
        "investment", "equity", "mf", "mutual fund",
    ),
    "email": (
        "email", "mail", "inbox", "send", "message",
        "outlook", "gmail", "compose",
    ),
    "music": (
        "music", "song", "playlist", "play", "pause", "resume",
        "skip", "volume", "shuffle", "repeat", "album",
        "artist", "track", "music player",
    ),
    "goals": (
        "goal", "plan", "milestone", "track", "progress",
        "objective", "deadline",
    ),
    "system": (
        "system", "process", "cpu", "memory", "disk",
        "network", "command", "terminal", "powershell",
        "background task", "run",
    ),
}


def route_query(query: str) -> str:
    """Classify a user query into the best-matching sub-agent domain.

    Uses simple keyword overlap scoring. Returns the domain name
    with the highest number of keyword matches.
    """
    query_lower = query.lower()
    scores: dict[str, int] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in query_lower)
        if score > 0:
            scores[domain] = score
    if not scores:
        return "general"
    return max(scores, key=lambda k: scores[k])  # type: ignore[arg-type]


def get_tools_for_query(query: str) -> tuple[str, ...] | None:
    """Return allowed tools for the domain that best matches the query via ToolOrchestrator.

    Returns None for 'general' (no filtering — use fallback core tools).
    """
    from orchestrator.tool_orchestrator import ToolOrchestrator, ToolDomain
    orch = ToolOrchestrator()
    domains = orch.classify_query(query)
    if ToolDomain.GENERAL in domains:
        return None
    allowed: set[str] = set()
    for d in domains:
        profile = STANDARD_SUBAGENTS.get(d.value)
        if profile:
            allowed.update(profile.allowed_tools)
    return tuple(allowed) if allowed else None


STANDARD_SUBAGENTS: dict[str, SubAgentProfile] = {
    "research": SubAgentProfile(
        name="research",
        purpose=AgentPurpose(
            category="research",
            description="Current information such as weather, stocks, quick facts, and web summaries.",
            capabilities=("web_search", "fact_retrieval", "summarization"),
            priority="normal",
        ),
        allowed_tools=(
            "web_search", "web_fetch", "web_fetch_multi", "open_url",
            "get_weather",
            "recall_memory", "save_memory",
        ),
        system_hint=AgentSystemHint(
            behavior="Gather current information and summarize briefly.",
            output_format="concise_summary",
            constraints=("avoid taking desktop actions",),
            risk_tolerance="low",
            interaction_mode="autonomous",
        ),
        effort_level="high",
    ),
    "files": SubAgentProfile(
        name="files",
        purpose=AgentPurpose(
            category="files",
            description="Read, inspect, summarize, and prepare safe file operations.",
            capabilities=("file_reading", "file_analysis", "clipboard_access"),
            priority="normal",
        ),
        allowed_tools=(
            "read_file", "write_file", "edit_file", "list_directory",
            "process_file", "analyze_image",
            "read_clipboard", "copy_to_clipboard", "copy_image_to_clipboard",
            "get_clipboard_files",
        ),
        system_hint=AgentSystemHint(
            behavior="Prefer dry-run previews before file changes and never delete without explicit approval.",
            output_format="structured",
            constraints=("never delete without approval",),
            risk_tolerance="low",
            interaction_mode="confirm_each",
        ),
        effort_level="medium",
    ),
    "desktop": SubAgentProfile(
        name="desktop",
        purpose=AgentPurpose(
            category="desktop",
            description="Windows app launching, UI control, keyboard, mouse, and screen tasks.",
            capabilities=("app_launch", "ui_control", "screen_capture"),
            priority="normal",
        ),
        allowed_tools=(
            "launch_app", "open_url",
            "capture_screen",
            "ui_click", "ui_double_click",
            "ui_type_text", "ui_press_key", "ui_hotkey",
            "ui_focus_window", "ui_get_mouse_position", "ui_get_screen_size",
            "ui_scroll", "ui_scroll_at", "ui_drag", "ui_smooth_move", "ui_move_relative",
            "ui_mouse_down", "ui_mouse_up",
            "ui_close_window", "ui_enum_windows", "ui_get_explorer_selection",
            "ui_get_monitors", "ui_get_system_state",
            "desktop_processes", "desktop_environment", "desktop_tray",
            "desktop_taskbar", "desktop_network", "desktop_system_info",
            "desktop_snapshot", "desktop_snapshot_v2",
            "run_command",
        ),
        system_hint=AgentSystemHint(
            behavior="Ask before controlling the desktop, type slowly, and stop immediately on interruption.",
            output_format="natural",
            constraints=("ask before desktop control", "stop on interruption"),
            risk_tolerance="medium",
            interaction_mode="confirm_each",
        ),
        effort_level="medium",
    ),
    "coding": SubAgentProfile(
        name="coding",
        purpose=AgentPurpose(
            category="coding",
            description="Code reading, writing, analysis, and software development tasks.",
            capabilities=("code_analysis", "code_generation", "debugging"),
            priority="normal",
        ),
        allowed_tools=(
            "read_file", "write_file", "edit_file", "list_directory",
            "run_command", "save_output",
            "web_search", "process_file",
            "recall_memory",
        ),
        system_hint=AgentSystemHint(
            behavior="Analyze code thoroughly, suggest improvements, and always explain the rationale.",
            output_format="natural",
            constraints=("never execute arbitrary code without approval",),
            risk_tolerance="low",
            interaction_mode="confirm_each",
        ),
        effort_level="high",
    ),
    "browser": SubAgentProfile(
        name="browser",
        purpose=AgentPurpose(
            category="browser",
            description="Web browsing, page interaction, and form filling using Playwright.",
            capabilities=("web_browsing", "form_filling", "page_interaction"),
            priority="normal",
        ),
        allowed_tools=("browser_control",),
        system_hint=AgentSystemHint(
            behavior="Use Playwright to control the browser, wait for elements, and extract data.",
            output_format="natural",
            constraints=("always ask before navigating to new sites",),
            risk_tolerance="medium",
            interaction_mode="confirm_each",
        ),
        effort_level="medium",
    ),
    "upstox": SubAgentProfile(
        name="upstox",
        purpose=AgentPurpose(
            category="upstox",
            description="Stock market portfolio tracking, positions, and market data via Upstox.",
            capabilities=("portfolio_analytics", "market_data", "stock_analysis"),
            priority="normal",
        ),
        allowed_tools=(
            "get_portfolio_holdings", "get_positions", "get_market_quote",
            "get_historical_data", "get_portfolio_summary",
            "list_stocks", "get_stock_data",
        ),
        system_hint=AgentSystemHint(
            behavior="Present portfolio data clearly with numbers and percentages.",
            output_format="structured",
            constraints=("never execute trades without explicit approval",),
            risk_tolerance="low",
            interaction_mode="supervised",
        ),
        effort_level="medium",
    ),
    "email": SubAgentProfile(
        name="email",
        purpose=AgentPurpose(
            category="email",
            description="Send, read, and manage emails.",
            capabilities=("email_management",),
            priority="normal",
        ),
        allowed_tools=("send_email", "read_inbox", "search_emails"),
        system_hint=AgentSystemHint(
            behavior="Handle emails professionally, ask for confirmation before sending.",
            output_format="natural",
            constraints=("confirm before sending",),
            risk_tolerance="low",
            interaction_mode="confirm_each",
        ),
        effort_level="medium",
    ),
    "music": SubAgentProfile(
        name="music",
        purpose=AgentPurpose(
            category="music",
            description="Music playback, library management, and playlist control.",
            capabilities=("music_playback", "library_management"),
            priority="low",
        ),
        allowed_tools=(
            "play_song", "pause_music", "resume_music", "stop_music",
            "next_song", "previous_song", "seek_music",
            "set_music_volume", "get_music_volume",
            "set_repeat_mode", "set_shuffle",
            "get_current_song", "get_playback_status", "get_playback_progress",
            "show_recently_played",
            "add_to_library", "remove_from_library", "scan_local_library",
            "play_playlist", "create_playlist", "delete_playlist", "list_playlists",
            "add_to_playlist", "save_playlist",
            "stream_song", "stream_playlist", "search_online",
            "add_to_queue", "clear_queue", "show_queue",
            "save_song",
        ),
        system_hint=AgentSystemHint(
            behavior="Control music playback and manage the music library smoothly.",
            output_format="natural",
            constraints=(),
            risk_tolerance="low",
            interaction_mode="autonomous",
        ),
        effort_level="low",
    ),
    "goals": SubAgentProfile(
        name="goals",
        purpose=AgentPurpose(
            category="goals",
            description="Long-term goal tracking, progress monitoring, and task management.",
            capabilities=("goal_management", "progress_tracking"),
            priority="normal",
        ),
        allowed_tools=(
            "create_goal", "list_goals", "update_goal", "archive_goal",
            "execute_workflow", "list_workflows", "generate_workflow",
        ),
        system_hint=AgentSystemHint(
            behavior="Track goals clearly, highlight progress and upcoming deadlines.",
            output_format="structured",
            constraints=(),
            risk_tolerance="low",
            interaction_mode="autonomous",
        ),
        effort_level="medium",
    ),
    "system": SubAgentProfile(
        name="system",
        purpose=AgentPurpose(
            category="system",
            description="System commands, background tasks, process management, and diagnostics.",
            capabilities=("system_management", "task_orchestration"),
            priority="normal",
        ),
        allowed_tools=(
            "run_command", "save_output",
            "run_in_background", "get_task_status", "cancel_task", "list_background_tasks",
            "generate_chart",
            "speak",
            "list_agents", "delegate_to_agent",
            "spawn_agent", "list_tasks", "get_task_result",
            "delegate_background", "check_task",
            "get_agent_performance", "show_capability_graph",
            "read_file", "write_file",
        ),
        system_hint=AgentSystemHint(
            behavior="Manage system-level operations, background tasks, and diagnostics. Execute system commands carefully, avoid destructive operations without confirmation.",
            output_format="natural",
            constraints=("never rm -rf or format without explicit approval",),
            risk_tolerance="medium",
            interaction_mode="confirm_each",
        ),
        effort_level="medium",
    ),
    "automation": SubAgentProfile(
        name="automation",
        purpose=AgentPurpose(
            category="automation",
            description="Startup routines, recurring checks, reminders, and personal workflows.",
            capabilities=("tool_orchestration", "memory_access"),
            priority="low",
        ),
        allowed_tools=(
            "get_weather", "web_search", "recall_memory", "save_memory", "speak",
            "execute_workflow",
        ),
        system_hint=AgentSystemHint(
            behavior="Run small personal routines quietly, report only useful changes, and respect frequency limits.",
            output_format="concise_summary",
            constraints=("respect frequency limits",),
            risk_tolerance="low",
            interaction_mode="autonomous",
        ),
        effort_level="low",
    ),
    "safety": SubAgentProfile(
        name="safety",
        purpose=AgentPurpose(
            category="safety",
            description="Risk review for commands, file access, permissions, and privacy-sensitive actions.",
            capabilities=("risk_classification", "permission_management"),
            priority="high",
        ),
        allowed_tools=(),
        system_hint=AgentSystemHint(
            behavior="Classify risk, explain the permission needed, and block destructive or credential-related requests.",
            output_format="structured",
            constraints=("block destructive actions", "block credential requests"),
            risk_tolerance="none",
            interaction_mode="supervised",
        ),
        effort_level="medium",
    ),
    "general": SubAgentProfile(
        name="general",
        purpose=AgentPurpose(
            category="general",
            description="General-purpose assistant — all tools available for complex or mixed-domain tasks.",
            capabilities=("all_capabilities",),
            priority="normal",
        ),
        allowed_tools=(),  # empty = all tools
        system_hint=AgentSystemHint(
            behavior="Handle general queries, combine tools from multiple domains as needed.",
            output_format="natural",
            constraints=(),
            risk_tolerance="low",
            interaction_mode="autonomous",
        ),
        effort_level="high",
    ),
}


def get_subagent(name: str) -> SubAgentProfile:
    """Return a named sub-agent profile, defaulting to general."""
    return STANDARD_SUBAGENTS.get(name, STANDARD_SUBAGENTS["general"])


def route_tool_to_subagent(tool_name: str) -> SubAgentProfile:
    """Find the first standard sub-agent that is allowed to use a tool."""
    for profile in STANDARD_SUBAGENTS.values():
        if profile.can_use(tool_name):
            return profile
    return STANDARD_SUBAGENTS["safety"]
