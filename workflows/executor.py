"""Workflow executor: loads and runs workflows step-by-step via ToolExecutor."""

import logging
import re

from orchestrator.event_bus import TASK_COMPLETED, EventBus
from orchestrator.event_payloads import TaskCompletedPayload

logger = logging.getLogger(__name__)


def interpolate(template: str, params: dict) -> str:
    """Replace {{param}} placeholders with values from params dict."""
    def replacer(match):
        key = match.group(1)
        return str(params.get(key, match.group(0)))
    return re.sub(r"\{\{(\w+)\}\}", replacer, template)


def interpolate_args(args: dict, params: dict) -> dict:
    """Recursively interpolate all string values in a dict."""
    result = {}
    for k, v in args.items():
        if isinstance(v, str):
            result[k] = interpolate(v, params)
        elif isinstance(v, dict):
            result[k] = interpolate_args(v, params)  # type: ignore[assignment]
        else:
            result[k] = v
    return result


def execute_workflow(
    workflow_name: str,
    params: dict | None = None,
) -> str:
    """Execute a saved workflow by name.

    Args:
        workflow_name: Name of the workflow to run.
        params: Parameter values to interpolate into step args.

    Returns:
        Summary string of all step results.
    """
    from workflows import load_workflow

    workflow = load_workflow(workflow_name)
    if not workflow:
        return f"Workflow '{workflow_name}' not found."

    params = params or {}
    steps = workflow.get("steps", [])
    results = []
    step_results = []

    for i, step in enumerate(steps):
        tool = step["tool"]
        args = interpolate_args(step.get("args", {}), params)
        label = step.get("label", f"Step {i + 1}")

        logger.info("Workflow '%s': %s → %s(%s)", workflow_name, label, tool, args)

        try:
            # Execute via ToolExecutor
            from orchestrator.core import ToolExecutor
            executor = ToolExecutor()
            result = executor.execute(tool, args)
            status = "✓" if not result.startswith("Error:") else "✗"
            step_results.append({
                "step": label,
                "tool": tool,
                "status": "success" if status == "✓" else "error",
                "result": result[:200],
            })
            results.append(f"  {status} {label}: {result[:100]}")
        except Exception as e:
            error = str(e)
            step_results.append({
                "step": label,
                "tool": tool,
                "status": "error",
                "result": error,
            })
            results.append(f"  ✗ {label}: {error}")
            break

    summary = "\n".join(results)
    full = f"Workflow '{workflow_name}' completed.\n{summary}" if results else \
           f"Workflow '{workflow_name}' has no steps."

    EventBus().publish_typed(
        TASK_COMPLETED,
        TaskCompletedPayload(workflow=workflow_name, steps=len(steps), results=step_results),
    )

    return full
