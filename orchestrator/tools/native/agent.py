"""
Sub-agent tools — spawn background agents and retrieve their results.

Mirrors OpenClaude's AgentTool pattern: spawn a fully isolated LLM loop
that runs in a background thread, returns immediately, and stores results
for the parent to retrieve.

Usage (as an LLM)::

    1. Call spawn_agent({description: "...", prompt: "Your task here"})
       → Returns: {"task_id": "t_a1b2c3", "status": "running"}

    2. Continue your work. The sub-agent runs in background.

    3. Call list_tasks(status="completed") to check, or just keep going
       — completed results will be injected into your context automatically.
"""

import json
import logging
import threading
import traceback

from orchestrator.task_manager import TaskManager, TaskState

logger = logging.getLogger(__name__)

# ── Background runner ────────────────────────────────────────────


def _run_sub_agent(task_id: str, prompt: str, model: str = "") -> None:
    """Run a fully isolated LLM orchestrator in background.

    Creates its own RaphaelOrchestrator instance, calls process_message,
    and stores the result via TaskManager.
    """
    from orchestrator.core import RaphaelOrchestrator
    try:
        logger.info("Sub-agent %s starting: %.80s", task_id, prompt)
        kwargs = {}
        if model:
            kwargs["model"] = model
        orchestrator = RaphaelOrchestrator(**kwargs)
        result = orchestrator.process_message(prompt)
        TaskManager.complete_task(task_id, result)
        logger.info("Sub-agent %s completed (%d chars)", task_id, len(result))
    except Exception as exc:
        err = traceback.format_exc()
        TaskManager.fail_task(task_id, f"{exc}\n{err}")
        logger.error("Sub-agent %s failed: %s", task_id, exc)

# ── Tools ────────────────────────────────────────────────────────


def spawn_agent(_description: str, prompt: str, model: str = "") -> str:
    """Spawn a sub-agent to handle a task autonomously in background.

    The sub-agent runs its own LLM conversation loop with full tool access.
    This returns immediately — the sub-agent processes in background.

    Args:
        description: Short label for the sub-agent's purpose (e.g. "Research auth bug").
        prompt: Full task description for the sub-agent to execute.
        model: Optional model override (e.g. "claude-sonnet-4-20250514").
               Leave empty to use the default model.

    Returns:
        JSON with task_id and status. Use list_tasks() to check progress.
    """
    task_id = TaskManager.create_task(prompt[:300], "sub_agent")
    TaskManager.start_task(task_id)

    # Link as sub-task of the current main task
    current = TaskManager.get_current_task()
    if current:
        with TaskManager._lock:
            current.sub_task_ids.append(task_id)

    # Launch background thread
    thread = threading.Thread(
        target=_run_sub_agent,
        args=(task_id, prompt, model),
        daemon=True,
        name=f"sub-agent-{task_id}",
    )
    thread.start()

    return json.dumps({"task_id": task_id, "status": "running"}, indent=2)


def get_task_result(task_id: str) -> str:
    """Get the result of a completed sub-agent task.

    Args:
        task_id: The task ID returned by spawn_agent.

    Returns:
        JSON with the task status, result (if completed), or error (if failed).
    """
    task = TaskManager.get_task(task_id)
    if not task:
        return json.dumps({"error": f"Task {task_id} not found"})

    payload = {
        "task_id": task.id,
        "status": task.status.value,
        "type": task.type,
        "created": task.created,
        "completed": task.completed,
    }

    if task.status == TaskState.COMPLETED:
        payload["result"] = task.result
    elif task.status == TaskState.FAILED:
        payload["error"] = task.error
    elif task.status == TaskState.RUNNING:
        payload["steps_completed"] = len(task.steps)

    return json.dumps(payload, indent=2, default=str)


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "spawn_agent",
                "description": "Spawn a background sub-agent to handle a task autonomously. "
                               "The agent runs its own LLM conversation with full tool access. "
                               "Returns immediately — use get_task_result or list_tasks to check progress. "
                               "Results are also auto-injected into your context when complete.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Short label (e.g. 'Research auth bug')",
                        },
                        "prompt": {
                            "type": "string",
                            "description": "Full task description for the sub-agent to execute",
                        },
                        "model": {
                            "type": "string",
                            "description": "Optional model override (leave empty for default)",
                        },
                    },
                    "required": ["description", "prompt"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_task_result",
                "description": "Get the final result and output of a completed sub-agent task by its task_id. Use when a delegated task has finished and the user wants to see what it produced.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "The task ID (e.g. 't_a1b2c3')",
                        },
                    },
                    "required": ["task_id"],
                },
            },
        },
    ]
