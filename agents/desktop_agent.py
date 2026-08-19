"""
Desktop Agent — UI automation specialist.

Handles mouse, keyboard, window management, screenshots, and screen analysis.
"""

import logging
from typing import TYPE_CHECKING

from agents import register
from agents.base_agent import BaseAgent
from orchestrator.tools import get_filtered_schemas

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor

logger = logging.getLogger(__name__)

_DESKTOP_TOOLS = [
    "capture_screen", "analyze_image", "get_active_window_info",
    "ui_click", "ui_type_text", "ui_press_key", "ui_hotkey", "ui_get_mouse_position",
    "ui_focus_window", "ui_enum_windows", "ui_close_window",
    "ui_minimize_window", "ui_maximize_window", "ui_get_window_rect",
    "ui_move_window", "ui_resize_window", "launch_app",
    "delegate_to_agent", "list_agents",
]


@register
class DesktopAgent(BaseAgent):
    name = "desktop"
    description = "Control mouse, keyboard, windows, and applications on Windows"
    available_tools = _DESKTOP_TOOLS
    max_rounds = 8

    def run(self, query: str, llm: LLMClient, executor: ToolExecutor) -> str:
        schemas = get_filtered_schemas(_DESKTOP_TOOLS)

        # Load evolved agent memory
        agent_context = self._load_agent_memory(query)

        system_msg = (
            "You are Raphael's Desktop Agent — you control mouse, keyboard, windows, and applications on Windows.\n\n"
            "**Capabilities:**\n"
            "- Launch applications with `launch_app`.\n"
            "- List open windows with `ui_enum_windows`.\n"
            "- Focus, move, resize, minimize, maximize, or close windows with `ui_focus_window`, `ui_move_window`, `ui_minimize_window`, `ui_close_window`.\n"
            "- Simulate mouse & keyboard actions with `ui_click`, `ui_type_text`, `ui_press_key`, `ui_hotkey`.\n"
            "- Take and analyze screenshots with `capture_screen` and `analyze_image`.\n\n"
            "**Cross-Agent Collaboration:**\n"
            "You can delegate subtasks. Use `list_agents` to see who's available "
            "and `delegate_to_agent(name, query)` to hand off work."
        )
        if agent_context:
            system_msg += f"\n\n{agent_context}"

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": query},
        ]

        result = llm.chat_tool_loop(messages, schemas, executor, max_rounds=self.max_rounds)
        self._record_outcome(query, self.available_tools)
        return result
