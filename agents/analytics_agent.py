"""
Analytics Agent — stock portfolio analytics and market insights.

Uses Upstox API to fetch portfolio holdings, positions, market quotes,
and historical data. The LLM analyzes the data to provide insights.
Learns from corrections over time via agent evolution memory.
"""

import logging
from typing import ClassVar
from agents import register
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


@register
class AnalyticsAgent(BaseAgent):
    name = "analytics"
    description = "Stock portfolio analytics — P&L analysis, market quotes, buy/sell suggestions, risk warnings"
    available_tools: ClassVar[list[str]] = [
        "get_portfolio_holdings", "get_positions", "get_market_quote",
        "get_historical_data", "get_portfolio_summary",
    ]
    max_rounds = 6

    def run(self, query, llm, executor) -> str:
        from orchestrator.memory_agent import get_relevant_context
        from orchestrator.tools import get_filtered_schemas

        # 1. Load user memory context (relevant user data)
        memory_context = get_relevant_context(query)

        # 2. Load evolved agent memory (learned rules, corrections)
        agent_context = self._load_agent_memory(query)

        # 3. Build system prompt
        system_content = (
            "You are Raphael's Analytics Agent — a stock market and portfolio analytics assistant.\n\n"
            "**Your capabilities:**\n"
            "- Fetch portfolio holdings and P&L with `get_portfolio_holdings`\n"
            "- Get intraday positions with `get_positions`\n"
            "- Check live market quotes with `get_market_quote`\n"
            "- Analyze historical trends with `get_historical_data`\n"
            "- Get a comprehensive portfolio summary with `get_portfolio_summary`\n\n"
            "**How to analyze:**\n"
            "1. Start by fetching the portfolio summary or holdings\n"
            "2. For specific stocks, get live quotes and historical data\n"
            "3. Provide clear insights, not just raw numbers\n"
            "4. Flag warnings: concentration risk, underperformance, market trends\n"
            "5. For buy/sell suggestions: show your reasoning—always say "
            "'this is not financial advice'\n\n"
            "Be honest: if data is unavailable or the API fails, say so clearly.\n\n"
            "**Cross-Agent Collaboration:**\n"
            "You can delegate subtasks to other agents. Use `list_agents` to see who's available "
            "and `delegate_to_agent(name, query)` to hand off work. For example, delegate web "
            "searches (\"search for latest news on this stock\") to the researcher agent."
        )

        if memory_context:
            system_content += f"\n\n[User Context]\n{memory_context}"
        if agent_context:
            system_content += f"\n\n{agent_context}"

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]

        # 4. Run focused LLM loop with only analytics tools
        schemas = get_filtered_schemas(self.available_tools)
        tools_used: list[str] = []

        for _round_idx in range(self.max_rounds):
            response = llm.chat(messages, schemas, reason="analytics_agent")
            if not response:
                break

            if not hasattr(response, "tool_calls") or not response.tool_calls:
                result = ""
                if response and hasattr(response, "content") and response.content:
                    result = response.content
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

        self._record_outcome(query, tools_used)
        return "I couldn't complete the analysis. Try a more specific query."
