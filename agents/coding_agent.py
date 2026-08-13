"""
Coding Agent — code generation and file operations specialist.

Handles writing code, reading/processing files, running commands,
and using the knowledge base for technical lookups.
"""

import logging
from typing import TYPE_CHECKING

from agents import register
from agents.base_agent import BaseAgent
from orchestrator.tools import get_filtered_schemas

if TYPE_CHECKING:
    from orchestrator.core import LLMClient, ToolExecutor

logger = logging.getLogger(__name__)

_CODING_TOOLS = [
    "write_file", "read_file", "edit_file", "list_directory",
    "process_file", "run_command", "copy_to_clipboard",
    "read_clipboard", "list_knowledge_files", "read_knowledge_file",
    "web_search", "web_fetch",
]


@register
class CodingAgent(BaseAgent):
    name = "coding"
    description = "Write code, process files, run commands, use technical knowledge"
    available_tools = [
        "write_file", "read_file", "edit_file", "list_directory",
        "process_file", "run_command", "copy_to_clipboard",
        "read_clipboard", "list_knowledge_files", "read_knowledge_file",
        "web_search", "web_fetch",
    ]
    max_rounds = 10

    def run(self, query: str, llm: LLMClient, executor: ToolExecutor) -> str:
        schemas = get_filtered_schemas(_CODING_TOOLS)

        # Load evolved agent memory
        agent_context = self._load_agent_memory(query)

        system_msg = (
            "You are Raphael's Coding Agent — you write, read, and process code and files. "
            "When writing code: include docstrings, handle errors, and show the user what you created. "
            "Use the knowledge base for CLI syntax and package manager commands. "
            "Process files with process_file for images, PDFs, docs, spreadsheets, archives. "
            "For code output, use copy_to_clipboard so the user can paste it easily.\n\n"
            "FILE EDITING RULE: When asked to fix or edit a file you previously created, "
            "check the conversation history for the exact file path first. "
            "Then: (1) read_file to load it, (2) edit_file to patch the bug, done. "
            "Do NOT use run_command to search for the file — use the path from history.\n\n"
            "**Cross-Agent Collaboration:**\n"
            "You can delegate subtasks. Use `list_agents` to see who's available "
            "and `delegate_to_agent(name, query)` to hand off work. For example, delegate "
            'web research ("find how to use this API") to the researcher agent, '
            'or browser testing to the browser agent.'
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
