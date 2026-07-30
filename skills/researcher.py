"""
Researcher Skill — web search and page content retrieval.

Uses a focused LLM loop with only web_search, web_fetch, get_weather tools,
reducing token usage and avoiding irrelevant tool calls during research.

Supports extra_context injection from agent evolution memory.
"""

import json
import logging
from skills import register
from skills.base_skill import Skill

logger = logging.getLogger(__name__)

_BASE_PROMPT = """You are a research assistant. Your tools are web_search, web_fetch, and get_weather.

Given a research query, use your tools to find information:
1. Search for relevant results using web_search
2. Fetch the most promising pages using web_fetch
3. For weather queries, use get_weather with the location
4. Synthesize a concise, accurate summary of what you found
5. Cite your sources (URLs)

Keep your response focused on facts. If you cannot find good results, say so clearly.
Do not use any tools other than web_search, web_fetch, and get_weather.
"""


@register
class ResearcherSkill(Skill):
    name = "researcher"
    description = "Search the web and fetch page content to research topics"
    required_tools = ["web_search", "web_fetch", "get_weather"]

    def execute(self, llm, executor, query: str = "", **kwargs) -> str:
        """Research a topic using web search and page fetch."""
        max_rounds = kwargs.get("max_rounds", 6)
        extra_context = kwargs.get("extra_context", "")

        # Build system prompt with optional evolved context
        system_prompt = _BASE_PROMPT
        if extra_context:
            system_prompt += f"\n\n[Learned Behavior]\n{extra_context}\n"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Research this: {query}"},
        ]

        from orchestrator.tools import get_filtered_schemas
        schemas = get_filtered_schemas(self.required_tools)

        for _round_idx in range(max_rounds):
            response = llm.chat(messages, schemas, reason="researcher")
            if not response or not hasattr(response, "content"):
                break

            # Check for tool calls
            if hasattr(response, "tool_calls") and response.tool_calls:
                assistant_msg = {
                    "role": "assistant",
                    "content": response.content or None,
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
                messages.append(assistant_msg)  # type: ignore[arg-type]

                for tc in response.tool_calls:
                    func_name = tc.function.name
                    try:
                        func_args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        func_args = {}

                    logger.info("Researcher: %s(%s)", func_name, func_args)
                    result = executor.execute(func_name, func_args)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                continue

            # Text response — final answer
            if response.content:
                return response.content  # type: ignore[no-any-return]
            break

        return "I couldn't find enough information on that topic. Try a different search query."
