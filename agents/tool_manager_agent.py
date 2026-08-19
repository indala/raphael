"""
Tool Manager Agent — full lifecycle management for Raphael's tools.

Raphael delegates tool creation/update/management to this agent.
It runs the rigorous pipeline: DESIGN → GENERATE → VALIDATE → SANDBOX TEST → SELF REVIEW → REGISTER
"""

import logging

from agents import register
from agents.base_agent import BaseAgent
from orchestrator.core import LLMClient, ToolExecutor
from orchestrator.skill_registry import execute_skill

logger = logging.getLogger(__name__)

_TOOL_MGMT_TOOLS = [
    "run_command", "process_file", "web_search", "web_fetch",
    "read_file", "write_file",
    "check_tool_health", "show_capability_graph", "export_tool",
    "recall_memory", "save_memory",
    "list_agents", "delegate_to_agent",
]


@register
class ToolManagerAgent(BaseAgent):
    name = "tool_manager"
    description = "Create, update, test, benchmark, and manage Raphael's tools through a rigorous pipeline"
    available_tools = _TOOL_MGMT_TOOLS
    max_rounds = 15

    def run(self, query: str, llm: LLMClient, executor: ToolExecutor) -> str:
        """Execute the tool management operation with a focused LLM loop."""
        logger.info("ToolManagerAgent: handling query: %s", query[:80])

        # Load evolution memory
        agent_context = self._load_agent_memory(query)

        # Build system prompt
        system_content = (
            "You are Raphael's Tool Manager Agent. Your job is to create, update, "
            "test, benchmark, and manage the tools that Raphael uses.\n\n"

            "**Your Pipeline (for CREATING new tools):**\n"
            "1. **DESIGN** — Understand what the user needs, design the tool interface\n"
            "2. **GENERATE** — Write the Python code following the strict template\n"
            "3. **VALIDATE** — Check syntax, structure, and security\n"
            "4. **SANDBOX TEST** — Run in an isolated subprocess with test cases\n"
            "5. **BENCHMARK** — Measure execution time (min/avg/max ms)\n"
            "6. **SELF REVIEW** — Review the code for issues\n"
            "7. **REGISTER** — Save and reload so all agents can use it\n\n"

            "**Lifecycle Operations:**\n"
            "- Create new tools through the full pipeline\n"
            "- Update existing tools with new requirements\n"
            "- Benchmark tool performance\n"
            "- List tool registry status and metadata\n"
            "- Archive or delete outdated tools\n\n"

            "To execute the pipeline, use the 'tool_manager' skill via execute_skill.\n"
            "You can also use your tools directly for simple operations like reading/writing files."
        )
        if agent_context:
            system_content += f"\n\n{agent_context}"

        system_content += (
            "\n\n**Cross-Agent Collaboration:**\n"
            "If you need help during tool creation (e.g., searching docs, writing complex test code), "
            "delegate to other agents using `list_agents` and `delegate_to_agent(name, query)`."
        )


        # Try running the skill first
        try:
            result = execute_skill("tool_manager", llm, executor, query=query)
        except Exception as e:
            logger.error("ToolManagerAgent: skill execution failed: %s", e)
            result = f"Failed to execute tool management: {e}"

        self._record_outcome(query, ["tool_manager_skill"], "completed" if result else "failed")
        return result
