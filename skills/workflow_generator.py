"""
Workflow Generator — LLM-powered creation of reusable workflows.

Given a user's natural-language description of a multi-step task, the
WorkflowGenerator skill uses the LLM to design a structured workflow
with named steps, parameters, and required tools.
"""

import json
import logging

from workflows import save_workflow

logger = logging.getLogger(__name__)


def generate_workflow(description: str, llm=None) -> str:
    """Use the LLM to design and save a workflow from a user description.

    Args:
        description: Natural-language description of the workflow (e.g.,
                     "Find all PDFs in the Downloads folder, compress them,
                     then email the archive").
        llm: Optional LLMClient instance. If None, one is created.

    Returns:
        Status string with workflow name or error.
    """
    if llm is None:
        from orchestrator.core import LLMClient
        llm = LLMClient()

    schema_hint = json.dumps({
        "name": "unique_workflow_name",
        "description": "brief description",
        "parameters": [{"name": "param_name", "type": "string", "description": "what it does"}],
        "steps": [{"tool": "tool_name", "args": {"key": "{{param_name}} or literal value"}, "label": "Step description"}],
        "required_tools": ["tool1", "tool2"],
    }, indent=2)

    prompt = (
        "You design reusable multi-step workflows for an AI assistant. "
        "Given a user's request, create a workflow JSON definition.\n\n"
        f"Request: {description}\n\n"
        f"Respond with ONLY valid JSON following this schema:\n{schema_hint}\n\n"
        "Rules:\n"
        "- Use {{param_name}} syntax for user-provided parameter values\n"
        "- Include all necessary steps as separate entries\n"
        "- Set 'label' to a short human-readable description of each step\n"
        "- List all tools needed in 'required_tools'\n"
        "- The workflow name must be lowercase with underscores"
    )

    messages = [{"role": "user", "content": prompt}]
    response = llm.chat(messages, reason="workflow_gen")

    if hasattr(response, "content"):
        content = response.content
    elif isinstance(response, dict):
        content = response.get("content", "")
    else:
        content = str(response)

    if content.startswith("[Error"):
        return f"LLM error generating workflow: {content}"

    # Extract JSON from response (handle markdown code fences)
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    content = content.strip()

    try:
        workflow = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error("LLM returned invalid JSON: %s\n%s", e, content[:500])
        return f"Failed to parse workflow: {e}"

    # Validate and save
    err = save_workflow(workflow)
    if err:
        return f"Invalid workflow: {err}"

    name = workflow["name"]
    step_count = len(workflow["steps"])
    return (f"Workflow '{name}' created with {step_count} steps. "
            f"You can run it with: execute_workflow(name='{name}', params=...)")


def list_workflows() -> str:
    """Return a formatted list of saved workflows."""
    from workflows import list_workflows as _list
    workflows = _list()
    if not workflows:
        return "No workflows saved yet."

    lines = ["**Saved Workflows:**\n"]
    for w in workflows:
        lines.append(f"**{w['name']}** — {w['description']}")
        lines.append(f"  Steps: {w['steps']}  |  Updated: {w['updated'][:10]}")
    return "\n".join(lines)
