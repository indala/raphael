"""Goal management tools — create, track, and manage long-term goals."""

import logging

from goals import GoalManager

logger = logging.getLogger(__name__)

_manager = GoalManager()


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "create_goal",
                "description": "Create a new long-term goal with optional sub-tasks and deadline.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Goal name (e.g., 'Learn Rust', 'Build Portfolio')",
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description of the goal.",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Priority level. Default: medium.",
                        },
                        "deadline": {
                            "type": "string",
                            "description": "Optional deadline date (ISO format, e.g., '2026-08-15').",
                        },
                        "sub_tasks": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of sub-task names to track progress.",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_goals",
                "description": "List all goals with their progress, priority, and sub-tasks. Optionally filter by status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["active", "completed", "archived"],
                            "description": "Optional status filter. Omit for all goals.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_goal",
                "description": "Update a goal's fields or toggle a sub-task's completion status.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the goal to update.",
                        },
                        "description": {
                            "type": "string",
                            "description": "New description.",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "New priority level.",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["active", "completed", "archived"],
                            "description": "Change status (e.g., 'completed' when done, 'archived' to archive).",
                        },
                        "sub_task": {
                            "type": "string",
                            "description": "Toggle a sub-task by name (completed ↔ not completed).",
                        },
                        "deadline": {
                            "type": "string",
                            "description": "New deadline date (ISO format).",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "archive_goal",
                "description": "Archive a goal to remove it from the active list without deleting it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the goal to archive.",
                        },
                    },
                    "required": ["name"],
                },
            },
        },
    ]


def create_goal(name: str, description: str = "",
                priority: str = "medium",
                deadline: str | None = None,
                sub_tasks: list[str] | None = None) -> str:
    """Create a new long-term goal."""
    err = _manager.create(name, description, priority, deadline, sub_tasks)
    if err:
        return f"Failed to create goal: {err}"
    return f"Goal '{name}' created."


def list_goals(status: str | None = None) -> str:
    """List all goals, optionally filtered by status."""
    goals = _manager.list(status)
    if not goals:
        return f"No {status or ''} goals found.".strip()
    lines = [f"**Goals ({status or 'all'})**"]
    for g in goals:
        pbar = "█" * (g.progress // 10) + "░" * (10 - g.progress // 10)
        d = f"  Due: {g.deadline}" if g.deadline else ""
        lines.append(f"\n**{g.name}** [{g.priority}] {pbar} {g.progress}%{d}")
        if g.description:
            lines.append(f"  _{g.description}_")
        if g.sub_tasks:
            for s in g.sub_tasks:
                c = "✅" if s["completed"] else "☐"
                lines.append(f"  {c} {s['name']}")
    return "\n".join(lines)


def update_goal(name: str, **kwargs) -> str:
    """Update a goal's fields."""
    # Rebuild kwargs from explicit params (remove None values)
    clean = {k: v for k, v in kwargs.items() if v is not None}
    err = _manager.update(name, **clean)
    if err:
        return f"Failed to update goal: {err}"
    return f"Goal '{name}' updated."


def archive_goal(name: str) -> str:
    """Archive a goal."""
    err = _manager.archive(name)
    if err:
        return f"Failed to archive goal: {err}"
    return f"Goal '{name}' archived."
