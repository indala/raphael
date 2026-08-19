"""
Researcher Agent — web search and content retrieval agent.

Uses the researcher skill for focused web tool calls.
Learns from corrections over time via agent evolution memory.
"""

import logging
from typing import ClassVar

from agents import register
from agents.base_agent import BaseAgent
from orchestrator.skill_registry import execute_skill

logger = logging.getLogger(__name__)


@register
class ResearcherAgent(BaseAgent):
    name = "researcher"
    description = "Search the web, fetch page content, check weather, and delegate findings"
    available_tools: ClassVar[list[str]] = [
        "web_search", "web_fetch", "get_weather", "delegate_to_agent", "list_agents"
    ]
    max_rounds = 6

    def run(self, query, llm, executor) -> str:
        # Load evolved agent memory to inject into research context
        agent_context = self._load_agent_memory(query)

        # Execute the researcher skill with evolved context
        result = execute_skill(
            "researcher",
            llm=llm,
            executor=executor,
            query=query,
            max_rounds=self.max_rounds,
            extra_context=agent_context,
        )

        # Record outcome for evolution
        self._record_outcome(query, self.available_tools)

        return result
