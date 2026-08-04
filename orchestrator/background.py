"""
Background task runner — sandboxed thread pool for Raphael.

Allows long-running tools (web searches, file processing, browser automation,
scheduled routines) to execute concurrently without blocking the main
voice/LLM conversation loop.

Architecture:
  - ThreadPoolExecutor (not multiprocessing) — safe for PyQt6, COM objects,
    and shared config/memory state on Windows.
  - Each task gets a unique ID, tracks status, and fires an on_done callback
    when complete (used to speak results via TTS and log to HUD).
  - Results are kept in a ring buffer (last 50 tasks).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import StrEnum

import config

logger = logging.getLogger(__name__)

# ── Task state ────────────────────────────────────────────────────────────────

class TaskStatus(StrEnum):
    PENDING  = "pending"
    RUNNING  = "running"
    DONE     = "done"
    FAILED   = "failed"
    CANCELED = "canceled"


@dataclass
class BackgroundTask:
    task_id:   str
    label:     str
    tool_name: str
    status:    TaskStatus = TaskStatus.PENDING
    result:    str | None = None
    error:     str | None = None
    submitted: float = field(default_factory=time.time)
    started:   float | None = None
    finished:  float | None = None
    future:    Future | None = field(default=None, repr=False, compare=False)
    current_action: str | None = None

    @property
    def elapsed(self) -> float | None:
        if self.started and self.finished:
            return round(self.finished - self.started, 2)
        if self.started:
            return round(time.time() - self.started, 2)
        return None

    def to_dict(self) -> dict:
        return {
            "task_id":   self.task_id,
            "label":     self.label,
            "tool_name": self.tool_name,
            "status":    self.status.value,
            "result":    self.result,
            "error":     self.error,
            "elapsed":   self.elapsed,
            "current_action": self.current_action,
        }


def publish_status_changed(task: BackgroundTask) -> None:
    """Publish a typed ``task.status_changed`` event from a BackgroundTask.

    Never raises: status events are observability side-effects and must not
    break the task lifecycle if the bus is unavailable.
    """
    try:
        from orchestrator.event_bus import TASK_STATUS_CHANGED, EventBus
        from orchestrator.event_payloads import TaskStatusChangedPayload
        EventBus().publish_typed(
            TASK_STATUS_CHANGED, TaskStatusChangedPayload(**task.to_dict())
        )
    except Exception:
        pass


# ── Runner ────────────────────────────────────────────────────────────────────

_MAX_HISTORY = 50


class BackgroundTaskRunner:
    """
    Thread-pool sandbox for long-running Raphael tool calls.

    Usage::

        runner = BackgroundTaskRunner(on_done=my_callback)
        task_id = runner.submit_tool("web_search", {"query": "..."}, label="Web search")
        runner.status(task_id)   # -> "running"
        runner.cancel(task_id)   # best-effort
    """

    def __init__(
        self,
        max_workers: int | None = None,
        on_done: Callable[[BackgroundTask], None] | None = None,
    ):
        max_workers = max_workers or getattr(config, "BACKGROUND_MAX_WORKERS", 4)
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="raphael-bg",
        )
        self._tasks: dict[str, BackgroundTask] = {}
        self._history: list[str] = []
        self._lock = threading.Lock()
        self._on_done = on_done
        self._executor = None  # Set by RaphaelOrchestrator after init
        self._thread_to_task: dict[int, str] = {}
        self._subscribe_to_events()

    def _subscribe_to_events(self):
        try:
            from orchestrator.event_bus import (
                AGENT_DELEGATED,
                TOOL_EXECUTED,
                TOOL_FAILED,
                EventBus,
            )
            bus = EventBus()
            bus.subscribe(TOOL_EXECUTED, self._on_bus_event)
            bus.subscribe(TOOL_FAILED, self._on_bus_event)
            bus.subscribe(AGENT_DELEGATED, self._on_bus_event)
        except Exception as e:
            logger.debug("Failed to subscribe background runner to EventBus: %s", e)

    def _on_bus_event(self, event: str, data: dict):
        tid = threading.get_ident()
        task_id = self.get_thread_task_id(tid)
        if task_id:
            with self._lock:
                task = self._tasks.get(task_id)
                if task:
                    if event in ("tool.executed", "tool.failed"):
                        task.current_action = f"Running tool: {data.get('tool')}"
                    elif event == "agent.delegated":
                        task.current_action = f"Delegating to: {data.get('to_agent')}"
                    # Publish status change
                    publish_status_changed(task)

    def get_thread_task_id(self, thread_id: int) -> str | None:
        with self._lock:
            return self._thread_to_task.get(thread_id)

    def is_cancelled(self, task_id: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            return task.status == TaskStatus.CANCELED if task else False

    # ── Public API ────────────────────────────────────────────────────────

    def set_executor(self, executor) -> None:
        """Attach the ToolExecutor so submit_tool() can call tools."""
        self._executor = executor

    def submit_tool(
        self,
        tool_name: str,
        args: dict,
        label: str = "",
        on_done: Callable[[BackgroundTask], None] | None = None,
    ) -> str:
        """Submit a named tool call to run in background. Returns task_id."""
        task_id = str(uuid.uuid4())[:8]
        label = label or tool_name
        task = BackgroundTask(task_id=task_id, label=label, tool_name=tool_name)

        with self._lock:
            self._tasks[task_id] = task
            self._history.append(task_id)
            if len(self._history) > _MAX_HISTORY:
                oldest = self._history.pop(0)
                self._tasks.pop(oldest, None)

        effective_done = on_done or self._on_done
        future = self._pool.submit(self._run_tool, task_id, tool_name, args, effective_done)
        with self._lock:
            task.future = future

        logger.info("Background task %s submitted: %s(%s)", task_id, tool_name, args)
        publish_status_changed(task)
        return task_id

    def submit(
        self,
        fn: Callable,
        *args,
        label: str = "task",
        tool_name: str = "custom",
        on_done: Callable[[BackgroundTask], None] | None = None,
        **kwargs,
    ) -> str:
        """Submit any callable to run in background. Returns task_id."""
        task_id = str(uuid.uuid4())[:8]
        task = BackgroundTask(task_id=task_id, label=label, tool_name=tool_name)

        with self._lock:
            self._tasks[task_id] = task
            self._history.append(task_id)
            if len(self._history) > _MAX_HISTORY:
                oldest = self._history.pop(0)
                self._tasks.pop(oldest, None)

        effective_done = on_done or self._on_done
        future = self._pool.submit(self._run_fn, task_id, fn, args, kwargs, effective_done)
        with self._lock:
            task.future = future

        logger.info("Background task %s submitted: %s", task_id, label)
        publish_status_changed(task)
        return task_id

    def cancel(self, task_id: str) -> bool:
        """Cancel a pending task (best-effort). Returns True if cancelled before start."""
        with self._lock:
            task = self._tasks.get(task_id)
        if not task:
            return False
        if task.future and task.future.cancel():
            with self._lock:
                task.status = TaskStatus.CANCELED
                task.finished = time.time()
            logger.info("Background task %s canceled", task_id)
            publish_status_changed(task)
            return True
        return False

    def status(self, task_id: str) -> str:
        """Return status string for a task, or 'not_found'."""
        with self._lock:
            task = self._tasks.get(task_id)
        return task.status.value if task else "not_found"

    def get_task(self, task_id: str) -> BackgroundTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 10) -> list[dict]:
        """Return the most recent tasks as dicts (newest first)."""
        with self._lock:
            ids = list(reversed(self._history[-limit:]))
            return [self._tasks[i].to_dict() for i in ids if i in self._tasks]

    def active_count(self) -> int:
        """Number of tasks currently running or pending."""
        with self._lock:
            return sum(
                1 for t in self._tasks.values()
                if t.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
            )

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the thread pool gracefully."""
        self._pool.shutdown(wait=wait, cancel_futures=True)

    # ── Internal ──────────────────────────────────────────────────────────

    def _run_tool(
        self,
        task_id: str,
        tool_name: str,
        args: dict,
        on_done: Callable[[BackgroundTask], None] | None,
    ) -> None:
        """Worker: execute a tool via ToolExecutor."""
        with self._lock:
            task = self._tasks.get(task_id)
        if not task:
            return

        tid = threading.get_ident()
        with self._lock:
            task.status = TaskStatus.RUNNING
            task.started = time.time()
            self._thread_to_task[tid] = task_id

        publish_status_changed(task)

        try:
            if self._executor is None:
                raise RuntimeError("BackgroundTaskRunner: no ToolExecutor attached")
            result = self._executor.execute(tool_name, args)  # type: ignore[unreachable]
            with self._lock:
                if task.status != TaskStatus.CANCELED:
                    task.status = TaskStatus.DONE
                    task.result = str(result)
        except Exception as e:
            with self._lock:
                if task.status != TaskStatus.CANCELED:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
            logger.error("Background task %s failed: %s", task_id, e)
        finally:
            with self._lock:
                task.finished = time.time()
                self._thread_to_task.pop(tid, None)
            publish_status_changed(task)
            if on_done:
                try:
                    on_done(task)
                except Exception as cb_err:
                    logger.error("Background on_done callback failed for %s: %s", task_id, cb_err)

    def _run_fn(
        self,
        task_id: str,
        fn: Callable,
        args: tuple,
        kwargs: dict,
        on_done: Callable[[BackgroundTask], None] | None,
    ) -> None:
        """Worker: execute an arbitrary callable."""
        with self._lock:
            task = self._tasks.get(task_id)
        if not task:
            return

        tid = threading.get_ident()
        with self._lock:
            task.status = TaskStatus.RUNNING
            task.started = time.time()
            self._thread_to_task[tid] = task_id

        publish_status_changed(task)

        try:
            result = fn(*args, **kwargs)
            with self._lock:
                if task.status != TaskStatus.CANCELED:
                    task.status = TaskStatus.DONE
                    task.result = str(result) if result is not None else "Done."
        except Exception as e:
            with self._lock:
                if task.status != TaskStatus.CANCELED:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
            logger.error("Background task %s failed: %s", task_id, e)
        finally:
            with self._lock:
                task.finished = time.time()
                self._thread_to_task.pop(tid, None)
            publish_status_changed(task)
            if on_done:
                try:
                    on_done(task)
                except Exception as cb_err:
                    logger.error("Background on_done callback failed for %s: %s", task_id, cb_err)


# ── Singleton ─────────────────────────────────────────────────────────────────

_runner: BackgroundTaskRunner | None = None


def get_runner() -> BackgroundTaskRunner:
    """Return the global BackgroundTaskRunner instance."""
    global _runner
    if _runner is None:
        _runner = BackgroundTaskRunner()
    return _runner


def init_runner(
    on_done: Callable[[BackgroundTask], None] | None = None,
    max_workers: int | None = None,
) -> BackgroundTaskRunner:
    """Initialize (or reinitialize) the global runner. Called once at startup."""
    global _runner
    if _runner:
        _runner.shutdown(wait=False)
    _runner = BackgroundTaskRunner(max_workers=max_workers, on_done=on_done)
    return _runner
