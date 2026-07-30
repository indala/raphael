import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# Set env to prevent PyQt window popups/errors
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Setup logging to stderr only
import logging
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("raphael_mcp_server")

try:
    import config
    from controller.state import state
    from orchestrator.plugin import discover_and_register, startup as plugin_startup
    from orchestrator.dep_check import check_dependencies
    from orchestrator.core import RaphaelOrchestrator

    # Initialize components
    discover_and_register()
    plugin_startup()
    check_dependencies()

    orchestrator = RaphaelOrchestrator()
except Exception as e:
    logger.exception("Failed to initialize Raphael Orchestrator: %s", e)
    sys.exit(1)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Raphael")

@mcp.tool()
def ask_raphael(query: str) -> str:
    """
    Send an instruction, query, or task to Raphael's multi-agent orchestrator.
    This will process the message through Raphael's conversation loop and return the result.
    """
    try:
        logger.info(f"Received query for Raphael: {query}")
        response = orchestrator.process_message(query)
        orchestrator.wait_for_memory()
        return response
    except Exception as e:
        logger.exception("Error executing query through Raphael")
        return f"Error: {e}"

@mcp.tool()
def get_raphael_status() -> dict:
    """
    Get current status, configuration details, and backend state of the Raphael instance.
    """
    try:
        return {
            "llm_backend": config.LLM_BACKEND,
            "fallback_backends": config.LLM_FALLBACK_BACKENDS,  # type: ignore[attr-defined]
            "tts_enabled": state.tts_enabled,
            "audio_input_available": state.audio_input_available,
            "audio_output_available": state.audio_output_available,
            "screenshot_dir": config.SCREENSHOT_DIR,
            "chart_dir": config.CHART_DIR,
            "debug_mode": config.DEBUG
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def list_raphael_agents() -> list[dict]:
    """
    List the registered specialist sub-agents within Raphael.
    """
    try:
        from orchestrator.subagents import STANDARD_SUBAGENTS
        agents_list = []
        for name, profile in STANDARD_SUBAGENTS.items():
            agents_list.append({
                "name": name,
                "role": profile.purpose.description,
                "description": profile.system_hint.behavior,
                "allowed_tools": profile.allowed_tools,
                "effort_level": profile.effort_level,
                "purpose_category": profile.purpose.category,
                "capabilities": list(profile.purpose.capabilities),
                "risk_tolerance": profile.system_hint.risk_tolerance,
                "interaction_mode": profile.system_hint.interaction_mode,
            })
        return agents_list
    except Exception as e:
        logger.exception("Error listing agents")
        return [{"error": str(e)}]

@mcp.tool()
def view_raphael_logs(lines: int = 50) -> str:
    """
    Read the last N lines of the Raphael system log.
    """
    try:
        log_path = Path(project_root) / "raphael.log"
        if not log_path.exists():
            return "Log file not found."

        with open(log_path, encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()

        last_lines = all_lines[-lines:]
        return "".join(last_lines)
    except Exception as e:
        return f"Error reading logs: {e}"

@mcp.tool()
def list_goals(status: str | None = None) -> list[dict]:
    """
    List all long-term goals tracked by Raphael, including priority, status, deadline, and sub-task progress.
    """
    try:
        from goals import GoalManager
        gm = GoalManager()
        goals = gm.list(status=status)
        return [
            {
                "name": g.name,
                "description": g.description,
                "status": g.status,
                "priority": g.priority,
                "deadline": g.deadline,
                "progress": g.progress,
                "sub_tasks": g.sub_tasks,
            }
            for g in goals
        ]
    except Exception as e:
        logger.exception("Error listing goals")
        return [{"error": str(e)}]

@mcp.tool()
def create_goal(name: str, description: str = "", priority: str = "medium", deadline: str | None = None, sub_tasks: list[str] | None = None) -> str:
    """
    Create a new long-term goal in Raphael with optional priority, deadline, and sub-tasks.
    """
    try:
        from goals import GoalManager
        gm = GoalManager()
        err = gm.create(name=name, description=description, priority=priority, deadline=deadline, sub_tasks=sub_tasks)
        if err:
            return f"Error: {err}"
        return f"Goal '{name}' created successfully."
    except Exception as e:
        logger.exception("Error creating goal")
        return f"Error: {e}"

@mcp.tool()
def update_goal(name: str, description: str | None = None, priority: str | None = None, status: str | None = None, sub_task: str | None = None, deadline: str | None = None) -> str:
    """
    Update an existing goal's status, priority, description, or toggle a sub-task.
    """
    try:
        from goals import GoalManager
        gm = GoalManager()
        err = gm.update(name=name, description=description, priority=priority, status=status, sub_task=sub_task, deadline=deadline)
        if err:
            return f"Error: {err}"
        return f"Goal '{name}' updated successfully."
    except Exception as e:
        logger.exception("Error updating goal")
        return f"Error: {e}"

@mcp.tool()
def search_memories(query: str) -> list[dict]:
    """
    Search Raphael's long-term recalled user memories and preferences.
    """
    try:
        from orchestrator.memory_agent import get_relevant_context
        ctx = get_relevant_context(query)
        return [{"query": query, "memory_context": ctx}]
    except Exception as e:
        logger.exception("Error searching memories")
        return [{"error": str(e)}]

if __name__ == "__main__":
    logger.info("Starting Raphael MCP Server...")
    mcp.run()
