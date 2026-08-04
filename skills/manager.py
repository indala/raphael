"""
Manager Skill — create new tools and manage agent capabilities.

This skill can dynamically generate new tool modules, register them
in the tool registry, and make them available to all agents immediately.

Use cases:
- "Create a weather alert tool that checks for severe weather"
- "Make a tool that sends email via SMTP"
- "Add a calculator tool for complex math"
"""

import ast
import json
import logging
import os
from typing import ClassVar

from skills import register
from skills.base_skill import Skill

logger = logging.getLogger(__name__)

_TOOL_CREATION_PROMPT = """You are a tool creator. Given a user's request for a new capability,
generate a Python module that implements it as a tool for Raphael's tool registry.

The module MUST follow this exact pattern:

```python
\"\"\"
{tool_description}
\"\"\"

import logging

logger = logging.getLogger(__name__)


def {function_name}({params}) -> str:
    \"\"\"{param_docstring}

    Returns:
        Result string.
    \"\"\"
    {implementation}
    return result


def get_schemas() -> list[dict]:
    \"\"\"Return OpenAI function-calling schemas for this tool.\"\"\"
    return [
        {{
            "type": "function",
            "function": {{
                "name": "{function_name}",
                "description": "{description}",
                "parameters": {{
                    "type": "object",
                    "properties": {{
                        {parameters_schema}
                    }},
                    "required": [{required_params}],
                }},
            }},
        }},
    ]
```

RULES:
1. The function MUST return a string (not None, not a complex object)
2. Use ONLY Python standard library + requests (no exotic imports)
3. The get_schemas() function MUST be present at module level
4. Parameter types MUST be "string" (not "number", "boolean", etc.)
5. Always try/except and return error messages as strings
6. API keys should be read from os.getenv() or config module
7. No file I/O unless explicitly requested
8. Keep implementation under 50 lines

Generate ONLY the Python code, no explanation.
"""


@register
class ManagerSkill(Skill):
    name = "manager"
    description = "Create new tools dynamically and manage agent capabilities"
    required_tools: ClassVar[list[str]] = ["list_agents", "delegate_to_agent"]

    def execute(self, llm, executor, query: str = "", **_kwargs) -> str:
        """Execute the manager skill.

        The Manager Skill handles:
        - Creating new tools from natural language descriptions
        - Routing tasks to the right agent via delegation
        """
        query_lower = query.lower()

        # Check if this is a tool creation request
        if any(kw in query_lower for kw in [
            "create a tool", "make a tool", "new tool", "add tool",
            "create tool", "build a tool", "generate tool",
        ]):
            return self._create_tool(query, llm, executor)

        # Otherwise, route to the right agent
        return self._route_task(query, llm, executor)

    def _create_tool(self, query: str, llm, _executor) -> str:
        """Generate a new tool module from a natural language description."""
        logger.info("Manager: creating tool from: %s", query[:80])

        # 1. LLM generates the tool code
        messages = [
            {"role": "system", "content": _TOOL_CREATION_PROMPT},
            {"role": "user", "content": query},
        ]
        response = llm.chat(messages, reason="tool_creation")
        if not response or not response.content:
            return "Failed to generate tool code."

        code = response.content.strip()
        # Strip markdown code fences if present
        if code.startswith("```"):
            code = code.split("\n", 1)[1]
            if code.endswith("```"):
                code = code[:-3]
            code = code.strip()

        # 2. Extract tool name from the code
        tool_name = self._extract_tool_name(code)
        if not tool_name:
            logger.error("Manager: could not extract tool name from generated code")
            return "Failed to parse generated tool. The code may be malformed."

        # 3. Validate syntax
        try:
            ast.parse(code)
        except SyntaxError as e:
            logger.error("Manager: generated tool has syntax error: %s", e)
            return f"Generated tool has a syntax error: {e}"

        # 4. Save to orchestrator/tools/
        tools_dir = os.path.join(os.path.dirname(__file__), "..", "orchestrator", "tools")
        filepath = os.path.abspath(os.path.join(tools_dir, f"{tool_name}.py"))

        # Safety check — don't overwrite existing tools
        if os.path.exists(filepath):
            return (
                f"A tool named '{tool_name}' already exists at {filepath}. "
                f"Choose a different name or delete the existing one first."
            )

        try:
            with open(filepath, "w") as f:
                f.write(code)
        except OSError as e:
            logger.error("Manager: failed to write tool file: %s", e)
            return f"Failed to save tool file: {e}"

        # 5. Reload tool registry
        try:
            from orchestrator.tools import reload_tools
            reload_tools()
        except Exception as e:
            logger.warning("Manager: tool saved but reload failed: %s", e)
            return (
                f"Tool '{tool_name}' was saved to {filepath} but registry reload "
                f"failed: {e}. Restart Raphael to use it."
            )

        # 6. Get the new tool schema
        from orchestrator.tools import get_tool_schemas
        schemas = get_tool_schemas()
        new_schema = next(
            (s for s in schemas if s["function"]["name"] == tool_name),
            None,
        )

        if new_schema:
            return (
                f"✅ Tool '{tool_name}' created and registered successfully!\n\n"
                f"**File:** {filepath}\n"
                f"**Schema:** {new_schema['function']['description']}\n\n"
                f"All agents can now use this tool. Try asking: \"Use the {tool_name} tool to...\""
            )
        else:
            return (
                f"✅ Tool '{tool_name}' was saved to {filepath} but the schema "
                f"wasn't found in the registry. Check the file for correctness."
            )

    def _extract_tool_name(self, code: str) -> str | None:
        """Extract the tool function name from generated code."""
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name != "get_schemas":
                    return node.name
        except SyntaxError:
            return None
        return None

    def _route_task(self, query: str, llm, _executor) -> str:
        """Route a task to the appropriate agent using delegation."""
        # First, list available agents
        from orchestrator.tools.native.delegation import delegate_to_agent, list_agents

        agents_info_raw = list_agents()
        agents_info = json.loads(agents_info_raw)

        # LLM decides which agent is best
        routing_messages = [
            {"role": "system", "content": (
                "You are a task router. Given a user request and a list of available agents, "
                "choose the best agent to handle the task.\n\n"
                f"Available agents:\n{agents_info_raw}\n\n"
                "Respond with ONLY the agent name, nothing else. If no agent fits, say 'none'."
            )},
            {"role": "user", "content": query},
        ]
        response = llm.chat(routing_messages, reason="agent_routing")
        agent_name = response.content.strip().lower() if response and response.content else "none"

        if agent_name == "none" or agent_name not in [
            a["name"] for a in agents_info
        ]:
            return (
                f"No suitable agent found for: {query}\n"
                f"Available: {', '.join(a['name'] for a in agents_info)}"
            )

        logger.info("Manager: routing to '%s': %s", agent_name, query[:60])
        return delegate_to_agent(agent_name, query)
