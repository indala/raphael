"""
Agent delegation tools — let agents discover and delegate to each other.

Provides two tools:
- ``list_agents`` — returns all registered agents with their capabilities
- ``delegate_to_agent`` — routes a task to another agent

Every agent gets these tools automatically (via BaseAgent.__init_subclass__).
Delegation depth is tracked per thread to prevent infinite loops (max 3 hops).
"""

import json
import logging
import threading

from orchestrator.event_bus import AGENT_DELEGATED, TASK_COMPLETED, EventBus

logger = logging.getLogger(__name__)

# ── Delegation depth tracking ───────────────────────────────────────
# Prevents infinite loops when agents delegate to each other.
# Uses thread-local storage since each agent runs in its own thread.

_thread_local = threading.local()
_MAX_DELEGATION_DEPTH = 3


def _get_depth() -> int:
    """Get current delegation depth for this thread."""
    return getattr(_thread_local, 'delegation_depth', 0)


def _push_depth() -> int:
    """Increment depth. Returns new depth."""
    depth = _get_depth() + 1
    _thread_local.delegation_depth = depth
    return depth


def _pop_depth():
    """Decrement depth."""
    depth = max(0, _get_depth() - 1)
    _thread_local.delegation_depth = depth


def list_agents() -> str:
    """List all available agents and their capabilities.

    Returns a JSON string with agent names, descriptions, and available tools.
    Use this to find the right agent to delegate a task to.
    """
    from agents import _AGENT_REGISTRY, discover_agents

    discover_agents()

    capabilities = []
    for _name, agent in _AGENT_REGISTRY.items():
        caps = agent.get_capabilities()
        capabilities.append(caps)

    return json.dumps(capabilities, indent=2)


def delegate_to_agent(agent_name: str, query: str) -> str:
    """Delegate a task to another agent.

    Args:
        agent_name: The name of the agent to handle the task.
        query: The task description to delegate.

    Returns:
        The other agent's response as a string.
    """
    # Prevent self-delegation
    current_depth = _get_depth()
    if current_depth >= _MAX_DELEGATION_DEPTH:
        return (
            f"Cannot delegate to '{agent_name}': max delegation depth "
            f"({_MAX_DELEGATION_DEPTH}) reached. Complete the current task "
            "using your own tools instead."
        )

    from agents import _AGENT_REGISTRY, discover_agents

    discover_agents()
    agent = _AGENT_REGISTRY.get(agent_name)
    if agent is None:
        return f"Agent '{agent_name}' not found. Use list_agents to see available agents."

    new_depth = _push_depth()
    logger.info("Delegating to agent '%s' (depth %d/%d): %s",
                agent_name, new_depth, _MAX_DELEGATION_DEPTH, query)
    EventBus().publish(AGENT_DELEGATED, from_agent="raphael",
                        to_agent=agent_name, query=query, depth=new_depth)
    try:
        from orchestrator.agent_models import create_agent_llm
        from orchestrator.core import ToolExecutor

        llm = create_agent_llm(agent_name, query=query)
        executor = ToolExecutor()

        response = agent.run(query, llm, executor)
        EventBus().publish(TASK_COMPLETED, from_agent="raphael",
                            agent=agent_name, query=query, result=response[:200])
        return response
    except Exception as e:
        logger.error("Delegation to '%s' failed: %s", agent_name, e)
        return f"Delegation to '{agent_name}' failed: {e}"
    finally:
        _pop_depth()


def delegate_background(agent_name: str, query: str) -> str:
    """Delegate a task to run in background. Returns task_id immediately.

    Use check_task(task_id) to get the result later.
    The agent runs asynchronously — Raphael can respond right away.
    """
    from orchestrator.background import get_runner
    from orchestrator.startup import run_agent_task

    runner = get_runner()
    task_id = runner.submit(
        run_agent_task,
        agent_name, query,
        label=f"Agent: {agent_name}",
        tool_name="agent_delegation",
    )
    logger.info("Background delegation: agent=%s task=%s query=%.80s", agent_name, task_id, query)
    return task_id


def check_task(task_id: str) -> str:
    """Check status and result of a background agent task."""
    from orchestrator.background import get_runner

    runner = get_runner()
    task = runner.get_task(task_id)
    if not task:
        return f"Task '{task_id}' not found."

    lines = [
        f"Status: {task.status.value}",
    ]
    if task.started:
        lines.append(f"Duration: {task.elapsed}s")
    if task.current_action:
        lines.append(f"Current action: {task.current_action}")
    if task.result:
        lines.append(f"Result: {task.result[:2000]}")
    if task.error:
        lines.append(f"Error: {task.error}")

    return "\n".join(lines)


def execute_workflow(workflow_name: str, params: dict | None = None) -> str:
    """Run a saved workflow by name."""
    from workflows.executor import execute_workflow as _exec
    return _exec(workflow_name, params)


def list_workflows() -> str:
    """List all saved workflows."""
    from workflows import list_workflows
    workflows = list_workflows()
    if not workflows:
        return "No workflows saved yet."
    lines = ["**Saved Workflows:**\n"]
    for w in workflows:
        lines.append(f"**{w['name']}** — {w['description']}")
        lines.append(f"  Steps: {w['steps']}  |  Updated: {w['updated'][:10]}\n")
    return "\n".join(lines)


def generate_workflow(description: str) -> str:
    """Create a workflow from a description using the LLM."""
    from orchestrator.core import LLMClient
    from skills.workflow_generator import generate_workflow as _gen
    llm = LLMClient()
    return _gen(description, llm)


def list_tasks(status: str = "") -> str:
    """List all tracked tasks and their current status.

    Args:
        status: Optional filter — "running", "completed", "failed", etc.
                Empty string returns all tasks.

    Returns:
        Formatted text listing task IDs, types, statuses, and goals.
    """
    from orchestrator.task_manager import TaskManager, TaskState
    state_filter = TaskState(status) if status else None
    tasks = TaskManager.list_tasks(state_filter)
    if not tasks:
        return "No tasks found." if status else "No tasks tracked yet."
    lines = ["**Tracked Tasks:**\n"]
    for t in tasks:
        lines.append(
            f"  **{t['id']}** — {t['status']}  "
            f"| type: {t['type']}  "
            f"| steps: {t['steps']}  "
            f"| goal: {t['goal'][:80]}"
        )
    return "\n".join(lines)


def get_schemas() -> list[dict]:
    """Return OpenAI function-calling schemas for delegation tools."""
    return [
        {
            "type": "function",
            "function": {
                "name": "list_agents",
                "description": "List all available agents and their capabilities (tools they can use). "
                               "Use this to find which agent to delegate a task to.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delegate_to_agent",
                "description": "Delegate a task to another agent. Use list_agents first to find "
                               "the right agent for the job.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Name of the agent to delegate to (e.g., 'researcher', 'browser', 'coding', 'desktop').",
                        },
                        "query": {
                            "type": "string",
                            "description": "The task description to delegate to the other agent.",
                        },
                    },
                    "required": ["agent_name", "query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_workflow",
                "description": "Run a saved multi-step workflow by name. Use 'list_workflows' to see available workflows "
                               "or 'generate_workflow' to create a new one from a description.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workflow_name": {
                            "type": "string",
                            "description": "Name of the workflow to execute (e.g., 'compress_pdfs').",
                        },
                        "params": {
                            "type": "object",
                            "description": "Optional parameter values to interpolate into step args (e.g., {\"folder\": \"Downloads\"}).",
                        },
                    },
                    "required": ["workflow_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_workflows",
                "description": "List all saved reusable workflows with their descriptions and step counts. Use when the user asks which workflows exist or to review saved automations.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_workflow",
                "description": "Create a reusable multi-step workflow from a natural-language description. "
                               "Describe what you want to automate (e.g., 'Find PDFs, compress them, and email the archive').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Natural-language description of the workflow steps.",
                        },
                    },
                    "required": ["description"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_tasks",
                "description": "List all tracked tasks and their current status. Use to check on running or completed tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Optional filter: 'running', 'pending', 'completed', 'failed', 'killed'. Empty returns all.",
                        },
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delegate_background",
                "description": "Delegate a task to an agent in the background. Returns a task_id immediately. "
                               "Use check_task(task_id) to get the result later. "
                               "The agent runs asynchronously — you can respond to the user right away.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Name of the agent to delegate to (e.g., 'researcher', 'browser', 'coding', 'desktop').",
                        },
                        "query": {
                            "type": "string",
                            "description": "The task description for the agent.",
                        },
                    },
                    "required": ["agent_name", "query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_task",
                "description": "Check the status and result of a background task. Returns Status, Duration, and Result if complete. "
                               "Use with task_ids returned by delegate_background.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "The task ID returned by delegate_background.",
                        },
                    },
                    "required": ["task_id"],
                },
            },
        },
    ]
