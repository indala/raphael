"""
Browser Agent — web browsing automation specialist.

Handles browser navigation, form filling, tab management, screenshots.
"""

import logging
from typing import TYPE_CHECKING

from agents import register
from agents.base_agent import BaseAgent
from orchestrator.tools import get_filtered_schemas

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor

logger = logging.getLogger(__name__)

_BROWSER_TOOLS = [
    "browser_control", "web_search", "web_fetch",
    "capture_screen", "analyze_image",
    "delegate_to_agent", "list_agents",
]


@register
class BrowserAgent(BaseAgent):
    name = "browser"
    description = "Control a web browser — navigate, fill forms, take screenshots"
    available_tools = _BROWSER_TOOLS
    max_rounds = 8

    def run(self, query: str, llm: LLMClient, executor: ToolExecutor) -> str:
        schemas = get_filtered_schemas(_BROWSER_TOOLS)

        # Load evolved agent memory
        agent_context = self._load_agent_memory(query)

        system_msg = (
            "You are Raphael's Browser Agent — you control a web browser via Playwright. "
            "You can navigate to URLs, click elements, fill forms, take screenshots, "
            "and extract page content. Be step-by-step: navigate first, then interact. "
            "If a page doesn't load, try web_fetch for a simpler text version.\n\n"
            "**Cross-Agent Collaboration:**\n"
            "You can delegate subtasks. Use `list_agents` to see who's available "
            "and `delegate_to_agent(name, query)` to hand off work. For example, delegate "
            'web searches ("find the URL for X") to the researcher agent.'
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
