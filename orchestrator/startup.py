"""
StartupManager — Manages the asynchronous launch briefing, memory initialization,
and daily tasks run.
"""

import logging
import threading
from collections.abc import Callable
from datetime import datetime

from controller.state import state
from memory.memory_manager import format_memory_for_prompt, load_memory
from orchestrator.core import LLMClient

logger = logging.getLogger(__name__)


def run_agent_task(agent_name: str, query: str):
    from agents import discover_agents, get_agent
    discover_agents()
    agent = get_agent(agent_name)
    if not agent:
        raise ValueError(f"Agent '{agent_name}' not found")
    from orchestrator.core import LLMClient, ToolExecutor
    llm = LLMClient()
    executor = ToolExecutor()
    return agent.run(query, llm, executor)


class StartupManager:
    """Manages proactive background startup operations and UI log notifications."""

    def __init__(
        self,
        write_log_cb: Callable[[str, str], None],
        set_state_cb: Callable[[str], None],
        speak_cb: Callable[[str], None]
    ):
        self.write_log = write_log_cb
        self.set_state = set_state_cb
        self.speak_cb = speak_cb
        self._thread: threading.Thread | None = None

    def start(self):
        """Launches the startup briefing asynchronously in a background thread."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            # 1. Initializing
            self.set_state("THINKING")
            self.write_log("sys", "Initializing...")

            # 2. Load Memory
            memory = load_memory()

            # Check daily tasks
            daily_tasks = memory.get("daily_task_memory", {})
            if daily_tasks:
                today_str = datetime.now().strftime("%Y-%m-%d")
                last_run = daily_tasks.get("_last_run_date")
                last_run_val = last_run.get("value") if isinstance(last_run, dict) else last_run

                if last_run_val == today_str:
                    self.write_log("sys", "Daily tasks already executed today.")
                else:
                    self.write_log("sys", "Found daily tasks...")
                    try:
                        from memory.memory_manager import update_memory
                        update_memory({"daily_task_memory": {"_last_run_date": today_str}})
                    except Exception as e:
                        logger.error("Failed to update daily tasks last run date: %s", e)

                    from orchestrator.background import get_runner
                    runner = get_runner()
                    if isinstance(daily_tasks, dict):
                        for task_name, task_data in daily_tasks.items():
                            if task_name.startswith("_"):
                                continue
                            task_query = task_data.get("value") if isinstance(task_data, dict) else task_data
                            if task_query:
                                runner.submit(
                                    run_agent_task,
                                    "manager",
                                    task_query,
                                    label=task_name,
                                    tool_name="manager_agent"
                                )
                    elif isinstance(daily_tasks, list):
                        for item in daily_tasks:
                            if isinstance(item, dict):
                                task_name = item.get("task", "task")
                                if task_name.startswith("_"):
                                    continue
                                task_query = item.get("description", "")
                                if task_query:
                                    runner.submit(
                                        run_agent_task,
                                        "manager",
                                        task_query,
                                        label=task_name,
                                        tool_name="manager_agent"
                                    )

            # 3. Preparing briefing using the rich startup_briefing composer
            self.write_log("sys", "Preparing briefing...")

            client = LLMClient()

            # Warm up KV cache for local LLMs (background thread, non-blocking)
            client.warmup_kv_cache()

            # Gather rich context (last session, pending tasks, monitor alerts, time-of-day)
            from orchestrator.startup_briefing import (
                gather_briefing_context,
                compose_briefing_prompt,
                build_briefing_system_prompt,
            )
            ctx = gather_briefing_context()

            # Log what we found for debugging
            if ctx.last_session:
                self.write_log("sys", "Resuming from last session...")
            if ctx.pending_tasks:
                self.write_log("sys", f"{len(ctx.pending_tasks)} pending task(s) found.")
            if ctx.monitor_alerts:
                self.write_log("sys", f"{len(ctx.monitor_alerts)} new topic alert(s).")

            briefing_user_prompt = compose_briefing_prompt(ctx)
            briefing_system      = build_briefing_system_prompt()

            messages = [
                {"role": "system", "content": briefing_system},
                {"role": "user",   "content": briefing_user_prompt},
            ]
            resp = client.chat(messages, None, reason="startup_briefing")

            from orchestrator.core import _is_llm_error as _check_err

            if resp and resp.content and not _check_err(resp.content):  # type: ignore[union-attr]
                briefing = resp.content.strip()  # type: ignore[union-attr]
                self.write_log("ai", briefing)
                if state.tts_enabled:
                    self.speak_cb(briefing)

            # 4. Ready
            self.write_log("sys", "Ready.")
        except Exception as e:
            logger.error("Startup briefing failed: %s", e)
            self.write_log("err", f"Startup error: {e}")
        finally:
            if not state.tts_enabled:
                if state.muted:
                    self.set_state("MUTED")
                elif state.wake_word_required:
                    self.set_state("SLEEPING")
                else:
                    self.set_state("LISTENING")
