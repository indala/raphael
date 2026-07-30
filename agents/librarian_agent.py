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
    description = "Handle memory-related queries (recall, save, manage memories)"
    available_tools = ["recall_memory", "save_memory", "list_memory_categories"]
    max_rounds = 3

    def run(self, query, llm, executor) -> str:
        # 1. Load user memory context
        from orchestrator.memory_agent import get_relevant_context
        memory_context = get_relevant_context(query)

        # 2. Load evolved agent memory (learned rules, corrections)
        agent_context = self._load_agent_memory(query)

        if not memory_context and not agent_context:
            return "I don't have any memories related to that yet."

        # 3. Build system prompt with evolved context
        system_content = (
            "You are a memory librarian. Below is the relevant memory context "
            "for the user's query. Answer based only on this context.\n\n"
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

        response = llm.chat(messages, reason="librarian")
        result = ""
        result = response.content if response and response.content else memory_context

        # 4. Record outcome for evolution
        self._record_outcome(query, self.available_tools)

        return result
