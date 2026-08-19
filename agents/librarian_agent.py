"""
Librarian Agent — handles memory recall and storage queries.

Uses only memory tools — fast and focused.
Learns from corrections over time via agent evolution memory.
"""

import logging
from agents import register
from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)


@register
class LibrarianAgent(BaseAgent):
    name = "librarian"
    description = "Handle memory-related queries (recall, search, save, and manage memories)"
    available_tools = [
        "recall_memory", "save_memory", "list_memories",
        "delete_memory_entry", "learn_from_feedback",
        "delegate_to_agent", "list_agents",
    ]
    max_rounds = 6

    def run(self, query, llm, executor) -> str:
        # 1. Load user memory context
        from orchestrator.memory_agent import get_relevant_context
        from orchestrator.tools import get_filtered_schemas
        memory_context = get_relevant_context(query)

        # 2. Load evolved agent memory (learned rules, corrections)
        agent_context = self._load_agent_memory(query)

        # 3. Build system prompt with evolved context
        system_content = (
            "You are a memory librarian. Below is the relevant memory context "
            "for the user's query. You can recall memories with `recall_memory`, "
            "save new facts with `save_memory`, or check categories.\n\n"
            f"Memory Context:\n{memory_context or 'None available.'}\n"
        )
        if agent_context:
            system_content += f"\n{agent_context}"

        system_content += (
            "\n\n**Cross-Agent Collaboration:**\n"
            "If you can't find the answer in memory, delegate a search to the researcher agent "
            "using `list_agents` and `delegate_to_agent(name, query)`."
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": query},
        ]

        schemas = get_filtered_schemas(self.available_tools)
        result = llm.chat_tool_loop(messages, schemas, executor, max_rounds=self.max_rounds)
        if not result or not result.strip():
            result = memory_context or "I don't have any memories related to that yet."

        # 4. Record outcome for evolution
        self._record_outcome(query, self.available_tools)

        return result
