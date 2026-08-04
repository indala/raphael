"""
Librarian Skill — memory recall and management.

Handles retrieving relevant memory context and saving new information.
Replaces the previous separate LLMClient-based memory_agent approach
with a focused skill using only memory tools.
"""

import logging
from typing import ClassVar

from skills import register
from skills.base_skill import Skill

logger = logging.getLogger(__name__)


@register
class LibrarianSkill(Skill):
    name = "librarian"
    description = "Recall and manage long-term memory about the user"
    required_tools: ClassVar[list[str]] = ["recall_memory", "save_memory", "list_memory_categories"]

    def execute(self, llm, executor, query: str = "", **kwargs) -> str:  # noqa: ARG002
        """Retrieve memory context relevant to a query."""
        try:
            from orchestrator.memory_agent import get_relevant_context
            context = get_relevant_context(query)
            return context
        except Exception as e:
            logger.error("Librarian skill failed: %s", e)
            return ""
