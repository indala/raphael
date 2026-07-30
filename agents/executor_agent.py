"""
Personal Agent — general-purpose capable assistant.

Go-to agent for day-to-day tasks. Has access to ALL tools,
remembers context, plans complex tasks, and gets things done.
Learns from corrections over time via agent evolution memory.
"""

import logging
from typing import TYPE_CHECKING, Any

from agents import register
from agents.base_agent import BaseAgent
import contextlib

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor

logger = logging.getLogger(__name__)


@register
class PersonalAgent(BaseAgent):
    name = "personal"
    description = "General-purpose personal assistant — handles everyday tasks, research, automation"
    available_tools = []  # All tools available
    max_rounds = 15

    def run(self, query: str, llm: LLMClient, executor: ToolExecutor) -> str:
        from orchestrator.tools import get_tool_schemas
        from orchestrator.memory_agent import get_relevant_context
        from orchestrator.plugin import get_hooks

        # 1. Load user memory context
        memory_context = get_relevant_context(query)

        # 2. Load evolved agent memory (learned rules, corrections)
        agent_context = self._load_agent_memory(query)

        # 3. Build system prompt with both memory sources
        system_content = (
            "You are Raphael, a voice-first AI desktop assistant. "
            "You have a wide range of tools at your disposal to help "
            "the user with their tasks.\n\n"
            "Be concise and direct. When you need information, use your tools.\n"
            "When you have all the information you need, provide a clear answer.\n"
            "You can plan multi-step tasks.\n\n"
            "**Cross-Agent Collaboration:**\n"
            "You can delegate subtasks to specialized agents. Use `list_agents` to see who's available "
            "and `delegate_to_agent(name, query)` to hand off work. For example:\n"
            '- Delegate stock analysis to the analytics agent\n'
            '- Delegate web research to the researcher agent\n'
            '- Delegate browser automation to the browser agent\n'
            '- Delegate file/coding tasks to the coding agent\n'
            '- Delegate desktop UI control to the desktop agent\n'
            '- Delegate tool creation to the tool_manager agent\n'
            '- Delegate delegation decisions to the manager agent\n\n'
            "When an agent returns a result, incorporate it into your response and continue."
        )

        if memory_context:
            system_content += (
                f"\n[User Context]\n{memory_context}\n"
            )

        if agent_context:
            system_content += f"\n{agent_context}\n"

        # 4. Inject evolved agent memory into the system message
        messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]

        # Check if query includes an image attachment
        image_ctx = getattr(executor, '_image_context', None)
        if image_ctx:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    image_ctx,
                ],
            })
        else:
            messages.append({"role": "user", "content": query})

        # 5. Run the tool loop
        schemas = get_tool_schemas()

        for hook in get_hooks("on_llm_request"):
            with contextlib.suppress(Exception):
                hook(messages)

        tools_used: list[str] = []
        for _round_idx in range(self.max_rounds):
            response = llm.chat(messages, schemas, reason="executor_agent")
            if not response:
                break

            if not hasattr(response, "tool_calls") or not response.tool_calls:
                result = ""
                if response and hasattr(response, "content") and response.content:
                    result = response.content

                # Record outcome with tools used
                self._record_outcome(query, tools_used)
                return result

            response_content = ""
            if hasattr(response, "content") and response.content:
                response_content = response.content

            assistant_msg = {
                "role": "assistant",
                "content": response_content or None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in response.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Track tools used for evolution
            for tc in response.tool_calls:
                if tc.function.name not in tools_used:
                    tools_used.append(tc.function.name)

            for tc in response.tool_calls:
                try:
                    import json
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    result = executor.execute(tc.function.name, args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": str(result),
                    })
                except Exception as e:
                    logger.error("Tool %s failed: %s", tc.function.name, e)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"Error: {e}",
                    })

        # Record outcome at loop end
        self._record_outcome(query, tools_used)
        return "I've completed the task. Let me know if you need anything else."
