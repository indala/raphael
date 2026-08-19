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
    "view_file", "replace_file_content", "write_file", "read_file", "edit_file",
    "search_codebase", "index_codebase", "get_code_outline", "read_file_range",
    "list_directory", "tree_directory", "count_lines_of_code",
    "grep_search", "find_files", "query_json", "scan_secrets",
    "git_status", "git_diff", "run_tests", "run_linter",
    "process_file", "run_command", "copy_to_clipboard",
    "read_clipboard", "list_knowledge_files", "read_knowledge_file",
    "web_search", "web_fetch", "delegate_to_agent", "list_agents",
]


@register
class CodingAgent(BaseAgent):
    name = "coding"
    description = "Write, search, inspect, debug, and test code across codebases"
    available_tools = _CODING_TOOLS
    max_rounds = 12

    def run(self, query: str, llm: LLMClient, executor: ToolExecutor) -> str:
        schemas = get_filtered_schemas(_CODING_TOOLS)

        # Load evolved agent memory
        agent_context = self._load_agent_memory(query)

        system_msg = (
            "You are Raphael's Coding Agent — you write, read, search, debug, and test code across codebases.\n\n"
            "**Code RAG & Semantic Search:**\n"
            "- Use `search_codebase(query)` to find relevant function/class implementations, architecture patterns, and logic across the entire codebase.\n"
            "- Use `get_code_outline` to inspect symbol structures and line numbers in specific files.\n"
            "- Use `grep_search` for exact string or regex matches across files.\n"
            "- Use `find_files` to locate files by pattern (e.g. `*.py`, `*.ts`, `*controller*`).\n\n"
            "**Codebase Navigation & Structure:**\n"
            "- Use `view_file` (with `start_line`/`end_line`) to inspect specific line ranges with 1-based numbering and metadata.\n"
            "- Use `tree_directory` to visualize project structure and folder hierarchy.\n"
            "- Use `count_lines_of_code` (cloc) to analyze project metrics, blank lines, comments, and code by language.\n"
            "- Use `query_json` (jq) to inspect JSON/YAML configurations or package.json files.\n\n"
            "**Editing & Verification:**\n"
            "- Use `view_file` or `read_file` before making modifications.\n"
            "- Use `replace_file_content` for precise surgical text replacement with exact whitespace and line context.\n"
            "- Use `write_file` when creating new files or doing full overwrites.\n"
            "- Run `run_tests` and `run_linter` to verify your changes and prevent regressions.\n"
            "- Use `scan_secrets` to audit repositories for exposed API keys, private keys, and passwords.\n"
            "- Use `git_status` and `git_diff` to review working tree modifications.\n"
            "- For code output snippets, use `copy_to_clipboard` so the user can easily paste it.\n\n"
            "**Cross-Agent Collaboration:**\n"
            "You can delegate subtasks. Use `list_agents` to see who is available "
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
