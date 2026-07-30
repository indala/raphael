"""
LLM-callable tools for background task management.

These tools let Raphael dispatch long-running work to the background thread pool
and check on results later, so the main voice loop stays responsive.
"""

from __future__ import annotations

import contextlib
import json


def _runner():
    from orchestrator.background import get_runner
    return get_runner()


# ── Tool functions ────────────────────────────────────────────────────────────

def run_in_background(tool_name: str, args: str | dict, label: str = "") -> str:
    """
    Run a tool asynchronously in a background worker thread.

    Use this when a task will take more than a few seconds (e.g. web search,
    file processing, browser automation) so Raphael stays responsive.

    Args:
        tool_name: The name of the tool to execute (e.g. "web_search").
        args:      The tool arguments as a JSON string or dict.
        label:     Optional human-readable label shown in task list.

    Returns:
        A task_id string. Use get_task_status(task_id) to check progress.
    """
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return f"Error: args must be a valid JSON object, got: {args!r}"
    if not isinstance(args, dict):
        return "Error: args must be a dict or JSON object string."

    task_id = _runner().submit_tool(tool_name, args, label=label or tool_name)
    return (
        f"Task started in background (ID: {task_id}). "
        f"I'll notify you when '{label or tool_name}' is complete. "
        f"You can check progress with get_task_status('{task_id}')."
    )


def get_task_status(task_id: str) -> str:
    """
    Check the status and result of a background task.

    Args:
        task_id: The task ID returned by run_in_background.

    Returns:
        A status description including result or error if finished.
    """
    task = _runner().get_task(task_id)
    if not task:
        return f"No task found with ID '{task_id}'."

    status = task.status.value
    elapsed = f" ({task.elapsed}s)" if task.elapsed else ""

    if status == "pending":
        return f"Task {task_id} ({task.label}) is waiting to start."
    if status == "running":
        return f"Task {task_id} ({task.label}) is running{elapsed}..."
    if status == "done":
        result = task.result or "(no output)"
        # Truncate very long results
        if len(result) > 800:
            result = result[:800] + "... [truncated]"
        return f"Task {task_id} ({task.label}) completed{elapsed}:\n{result}"
    if status == "failed":
        return f"Task {task_id} ({task.label}) failed{elapsed}: {task.error}"
    if status == "canceled":
        return f"Task {task_id} ({task.label}) was canceled."

    return f"Task {task_id}: unknown status '{status}'"


def list_background_tasks() -> str:
    """
    List all recent background tasks with their current status.

    Returns:
        A formatted summary of the last 10 background tasks.
    """
    tasks = _runner().list_tasks(limit=10)
    active = _runner().active_count()

    if not tasks:
        return "No background tasks have been submitted yet."

    lines = [f"Background tasks ({active} active):"]
    for t in tasks:
        elapsed = f" | {t['elapsed']}s" if t["elapsed"] else ""
        lines.append(
            f"  [{t['task_id']}] {t['status'].upper()}{elapsed} — {t['label']}"
        )
    return "\n".join(lines)


def cancel_task(task_id: str) -> str:
    """
    Cancel or stop a background task (pending or running).

    Args:
        task_id: The task ID to cancel.

    Returns:
        Confirmation message.
    """
    import time

    from orchestrator.background import TaskStatus
    from orchestrator.event_bus import EventBus

    runner = _runner()
    task = runner.get_task(task_id)
    if not task:
        return f"No task found with ID '{task_id}'."

    # Try canceling pending first
    success = runner.cancel(task_id)
    if success:
        return f"Task {task_id} ({task.label}) has been canceled."

    # If running, cooperative stop
    if task.status.value == "running":
        with runner._lock:
            task.status = TaskStatus.CANCELED
            task.error = "Stopped by user"
            task.finished = time.time()
        with contextlib.suppress(Exception):
            EventBus().publish("task.status_changed", **task.to_dict())
        return f"Stop request sent to running task {task_id} ({task.label}). It will terminate shortly."

    return f"Task {task_id} is already in state '{task.status.value}' and cannot be canceled."


def get_immediate_response(task_id: str) -> str:
    """
    Get the immediate response of a running background task, blocking the caller
    briefly to wait for it.

    Args:
        task_id: The task ID.

    Returns:
        Response string.
    """
    runner = _runner()
    task = runner.get_task(task_id)
    if not task:
        return f"No task found with ID '{task_id}'."

    if task.status.value == "done":
        return task.result or "(no output)"
    if task.status.value == "failed":
        return f"Task failed: {task.error}"
    if task.status.value == "canceled":
        return "Task was canceled."

    if task.status.value == "running" and task.future:
        try:
            result = task.future.result(timeout=6.0)
            return f"Task completed: {result}"
        except TimeoutError:
            action = getattr(task, "current_action", None)
            act_str = f" Currently: {action}." if action else ""
            return f"Task is still running.{act_str} You can check status later using get_task_status('{task_id}')."
        except Exception as e:
            return f"Error while waiting for task: {e}"

    return f"Task is in state '{task.status.value}'."


# ── Schemas ───────────────────────────────────────────────────────────────────

def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "run_in_background",
                "description": (
                    "Run a tool asynchronously in a background worker so Raphael stays responsive. "
                    "Use for slow tasks: web searches, file processing, browser automation, "
                    "anything that takes more than a few seconds. "
                    "Returns a task_id immediately. Raphael will speak a notification when done."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the tool to execute in background (e.g. 'web_search', 'process_file').",
                        },
                        "args": {
                            "type": "string",
                            "description": "JSON string of arguments to pass to the tool.",
                        },
                        "label": {
                            "type": "string",
                            "description": "Optional human-readable label for the task (e.g. 'Search for Python tutorials').",
                        },
                    },
                    "required": ["tool_name", "args"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_task_status",
                "description": "Check the status and result of a background task by its task_id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "The task ID returned by run_in_background.",
                        }
                    },
                    "required": ["task_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_background_tasks",
                "description": "List all recent background tasks and their current status.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "cancel_task",
                "description": "Cancel a pending background task or stop a running task in the background.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "The task ID to cancel.",
                        }
                    },
                    "required": ["task_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_immediate_response",
                "description": "Get the immediate response of a running background task, blocking briefly to wait for it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "The task ID.",
                        }
                    },
                    "required": ["task_id"],
                },
            },
        },
    ]
