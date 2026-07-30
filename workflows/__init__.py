"""Workflow system: reusable multi-step capabilities for Raphael."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_WORKFLOW_DIR = Path(__file__).resolve().parent


# ── Schema ──

WORKFLOW_SCHEMA = {
    "type": "object",
    "required": ["name", "description", "steps"],
    "properties": {
        "name": {"type": "string", "description": "Unique workflow name"},
        "description": {"type": "string", "description": "What this workflow does"},
        "parameters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["tool", "args"],
                "properties": {
                    "tool": {"type": "string"},
                    "args": {"type": "object"},
                },
            },
        },
        "required_tools": {"type": "array", "items": {"type": "string"}},
    },
}


def _path(name: str) -> Path:
    """Get the file path for a workflow by name."""
    return _WORKFLOW_DIR / f"{name}.json"


def save_workflow(workflow: dict) -> str:
    """Validate and save a workflow definition. Returns error msg or empty string."""
    # Basic validation
    if not workflow.get("name"):
        return "Workflow must have a 'name'."
    if not workflow.get("description"):
        return "Workflow must have a 'description'."
    if not workflow.get("steps"):
        return "Workflow must have at least one 'step'."

    for step in workflow["steps"]:
        if not step.get("tool"):
            return "Each step must have a 'tool'."
        if "args" not in step:
            step["args"] = {}

    workflow.setdefault("parameters", [])
    workflow.setdefault("required_tools", [])
    workflow["updated"] = datetime.now().isoformat()

    path = _path(workflow["name"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved workflow: %s", workflow["name"])
    return ""


def load_workflow(name: str) -> dict | None:
    """Load a workflow by name. Returns None if not found."""
    path = _path(name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Failed to load workflow '%s': %s", name, e)
        return None


def list_workflows() -> list[dict]:
    """List all saved workflows (name + description)."""
    workflows = []
    for f in sorted(_WORKFLOW_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            workflows.append({
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "steps": len(data.get("steps", [])),
                "updated": data.get("updated", ""),
            })
        except Exception as e:
            logger.debug("Skipping %s: %s", f.name, e)
    return workflows


def delete_workflow(name: str) -> str:
    """Delete a workflow. Returns error msg or empty string."""
    path = _path(name)
    if not path.exists():
        return f"Workflow '{name}' not found."
    path.unlink()
    logger.info("Deleted workflow: %s", name)
    return ""
