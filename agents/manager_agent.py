"""
Manager Agent — oversees delegation and routes tasks to specialists.

The Manager acts as a meta-agent that can:
- Route tasks to the most appropriate specialized agent
- Manage agent capabilities and discover what each agent can do
"""

import logging
from typing import TYPE_CHECKING

from agents import register
from agents.base_agent import BaseAgent

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor

logger = logging.getLogger(__name__)

_MANAGER_TOOLS = [
    "list_agents", "delegate_to_agent",
    "web_search", "web_fetch", "get_weather",
    "recall_memory", "save_memory",
    "process_file", "run_system_command",
    "capture_screen", "analyze_image",
]


@register
class ManagerAgent(BaseAgent):
    name = "manager"
    description = "Delegate tasks to specialized agents and manage capabilities"
    available_tools = _MANAGER_TOOLS + []  # Also all tools via delegation
    max_rounds = 12

    def run(self, query: str, llm: LLMClient, executor: ToolExecutor) -> str:
        # Load evolved agent memory
        agent_context = self._load_agent_memory(query)

        # For other requests, use the LLM with delegation tools available
        system_msg = (
            "You are Raphael's Manager Agent. You can:\n\n"
            "1. **Delegate tasks** — use `list_agents` to see available agents, "
            "then `delegate_to_agent` to route tasks to specialists\n"
            "2. **Solve tasks directly** — use your available tools for simple requests\n\n"
            "For complex tasks: delegate to the right agent. "
            "For simple tasks: handle them directly.\n\n"
            "**Cross-Agent Collaboration:**\n"
            "You can chain delegations. For complex workflows, delegate subtasks to "
            "specialized agents in sequence. Use `list_agents` to see capabilities "
            "and `delegate_to_agent(name, query)` to hand off work. "
            "Each agent returns its result — use it to decide the next step."
        )
        if agent_context:
            system_msg += f"\n\n{agent_context}"

        from orchestrator.tools import get_filtered_schemas
        schemas = get_filtered_schemas(self.available_tools)

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": query},
        ]

        result = llm.chat_tool_loop(messages, schemas, executor, max_rounds=self.max_rounds)
        self._record_outcome(query, self.available_tools)
        return result
