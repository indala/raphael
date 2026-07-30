"""
Task Manager — lifecycle state machine for Raphael tasks.

Mirrors OpenClaude's Task.ts pattern: tasks go through a strict state machine
(pending → running → completed/failed/killed), track progress steps, and
support sub-tasks for agent delegation.

Usage::

    task_id = TaskManager.create_task("Build a game", "main")
    TaskManager.start_task(task_id)
    TaskManager.add_step(task_id, "Created HTML", "write_file")
    TaskManager.complete_task(task_id, "Game built successfully")
    progress = TaskManager.build_progress_prompt(task_id)
"""

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar


class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


@dataclass
class TaskStep:
    """A single completed or planned step within a task."""
    id: str
    description: str
    tool_name: str
    status: str = "completed"  # "completed" | "failed" | "running"
    timestamp: float = field(default_factory=time.time)


@dataclass
class Task:
    """A task tracked by the TaskManager.

    Mirrors OpenClaude's TaskStateBase + type-specific fields.
    Each task has its own abort_signal for independent cancellation.
    """
    id: str
    type: str               # "main" | "sub_agent" | "background"
    status: TaskState
    goal: str
    steps: list[TaskStep] = field(default_factory=list)
    sub_task_ids: list[str] = field(default_factory=list)
    result: str | None = None
    error: str | None = None
    created: float = field(default_factory=time.time)
    completed: float | None = None
    abort_signal: threading.Event = field(default_factory=threading.Event)
    output_file: str = ""          # Path to persistent output file
    output_offset: int = 0         # Bytes already read (for resume)
    max_tokens: int | None = None   # Budget: max tokens for this task
    max_cost_usd: float | None = None  # Budget: max USD cost for this task
    tokens_used: int = 0           # Running token count
    cost_usd: float = 0.0          # Running cost estimate

    def is_cancelled(self) -> bool:
        """Check whether this task's abort signal has been set."""
        return self.abort_signal.is_set()

    def is_terminal(self) -> bool:
        """Check if this task is in a terminal state (can't be mutated further)."""
        return self.status in (TaskState.COMPLETED, TaskState.FAILED, TaskState.KILLED)


class TaskManager:
    """Singleton task lifecycle manager.

    Thread-safe — uses a lock for all state mutations.
    Tasks are stored in a class-level dict so they survive across
    conversation rounds and sub-agent boundaries.
    """

    _lock = threading.Lock()
    _tasks: ClassVar[dict[str, Task]] = {}
    _current_task_id: str | None = None
    TASK_OUTPUT_DIR = Path("task_outputs")

    # Prefix map for readable task IDs (mirrors OpenClaude's prefix scheme)
    TASK_ID_PREFIXES: ClassVar[dict[str, str]] = {"main": "m", "sub_agent": "a", "background": "b", "workflow": "w"}

    # ── Lifecycle ────────────────────────────────────────────────

    TERMINAL_STATES = frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.KILLED})

    @classmethod
    def _assert_not_terminal(cls, task_id: str) -> bool:
        """Quick-guard: return False if the task is in a terminal state.

        Skips the lock for the read (single-word status enum comparison is atomic
        in CPython). Callers must still acquire ``cls._lock`` for compound mutations.
        """
        task = cls._tasks.get(task_id)
        return bool(task and task.status not in cls.TERMINAL_STATES)

    @classmethod
    def create_task(cls, goal: str, task_type: str = "main") -> str:
        """Create a new task in PENDING state. Returns the task ID."""
        task_id = f"{cls.TASK_ID_PREFIXES.get(task_type, 't')}_{uuid.uuid4().hex[:8]}"
        # Initialize output file path for persistent task output
        output_path = cls._ensure_output_dir() / f"{task_id}.log"
        task = Task(
            id=task_id,
            type=task_type,
            status=TaskState.PENDING,
            goal=goal[:300],
            output_file=str(output_path),
        )
        with cls._lock:
            cls._tasks[task_id] = task
            if task_type == "main":
                cls._current_task_id = task_id
        return task_id

    @classmethod
    def start_task(cls, task_id: str) -> bool:
        """Transition a task from PENDING → RUNNING. Returns True if successful."""
        task = cls._get(task_id)
        if not task or task.status != TaskState.PENDING:
            return False
        with cls._lock:
            task.status = TaskState.RUNNING
        return True

    @classmethod
    def complete_task(cls, task_id: str, result: str = "") -> bool:
        """Transition a task to COMPLETED. Returns True if successful."""
        task = cls._get(task_id)
        if not task or task.status not in (TaskState.RUNNING, TaskState.PENDING):
            return False
        with cls._lock:
            task.status = TaskState.COMPLETED
            task.completed = time.time()
            task.result = result
        return True

    @classmethod
    def fail_task(cls, task_id: str, error: str) -> bool:
        """Transition a task to FAILED. Returns True if successful."""
        task = cls._get(task_id)
        if not task or task.status not in (TaskState.RUNNING, TaskState.PENDING):
            return False
        with cls._lock:
            task.status = TaskState.FAILED
            task.completed = time.time()
            task.error = error
        return True

    @classmethod
    def kill_task(cls, task_id: str) -> bool:
        """Transition a task to KILLED. Returns True if successful."""
        task = cls._get(task_id)
        if not task or task.status not in (TaskState.RUNNING, TaskState.PENDING):
            return False
        with cls._lock:
            task.status = TaskState.KILLED
            task.completed = time.time()
        return True

    # ── Steps ────────────────────────────────────────────────────

    @classmethod
    def set_budget(cls, task_id: str, max_tokens: int | None = None,
                   max_cost_usd: float | None = None) -> bool:
        """Set token/USD budget limits on a task. Returns True if successful."""
        task = cls._get(task_id)
        if not task:
            return False
        task.max_tokens = max_tokens
        task.max_cost_usd = max_cost_usd
        return True

    @classmethod
    def record_usage(cls, task_id: str, tokens: int = 0, cost: float = 0.0) -> bool:
        """Record token/cost usage for a task. Returns True if task existed."""
        task = cls._get(task_id)
        if not task:
            return False
        task.tokens_used += tokens
        task.cost_usd += cost
        return True

    @classmethod
    def budget_exceeded(cls, task_id: str) -> str | None:
        """Check if the task has exceeded its budget.

        Returns an error message string if over budget, None otherwise.
        Checks token budget first, then cost budget.
        """
        task = cls._get(task_id)
        if not task:
            return None
        if task.max_tokens is not None and task.tokens_used > task.max_tokens:
            return (
                f"Budget exceeded: used {task.tokens_used:,} tokens "
                f"(limit {task.max_tokens:,})"
            )
        if task.max_cost_usd is not None and task.cost_usd > task.max_cost_usd:
            return (
                f"Budget exceeded: cost ${task.cost_usd:.4f} "
                f"(limit ${task.max_cost_usd:.4f})"
            )
        return None

    @classmethod
    def add_step(cls, task_id: str, description: str, tool_name: str,
                 status: str = "completed") -> str | None:
        """Record a completed step. Returns the step ID or None."""
        task = cls._get(task_id)
        if not task or not cls._assert_not_terminal(task_id):
            return None
        step = TaskStep(
            id=f"s_{uuid.uuid4().hex[:6]}",
            description=description[:200],
            tool_name=tool_name,
            status=status,
        )
        with cls._lock:
            task.steps.append(step)
        return step.id

    @classmethod
    def add_step_from_tool_call(cls, task_id: str, tool_name: str,
                                 arguments: dict) -> str | None:
        """Convenience: add a step from tool name + args (auto-generates description)."""
        desc = cls._summarize_args(tool_name, arguments)
        return cls.add_step(task_id, desc, tool_name)

    # ── Query ────────────────────────────────────────────────────

    @classmethod
    def get_task(cls, task_id: str) -> Task | None:
        with cls._lock:
            task = cls._tasks.get(task_id)
            return task

    @classmethod
    def get_current_task(cls) -> Task | None:
        with cls._lock:
            tid = cls._current_task_id
            return cls._tasks.get(tid) if tid else None

    @classmethod
    def list_tasks(cls, status: TaskState | None = None) -> list[dict]:
        """Return tasks as plain dicts (safe for JSON serialization)."""
        with cls._lock:
            tasks = list(cls._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return [
            {
                "id": t.id,
                "type": t.type,
                "status": t.status.value,
                "goal": t.goal[:100],
                "steps": len(t.steps),
                "sub_tasks": len(t.sub_task_ids),
                "created": t.created,
                "completed": t.completed,
            }
            for t in sorted(tasks, key=lambda x: x.created, reverse=True)
        ]

    @classmethod
    def clear_completed(cls) -> int:
        """Remove all completed/failed/killed tasks. Returns count removed."""
        with cls._lock:
            terminal = {TaskState.COMPLETED, TaskState.FAILED, TaskState.KILLED}
            before = len(cls._tasks)
            cls._tasks = {
                tid: t for tid, t in cls._tasks.items()
                if t.status not in terminal
            }
            return before - len(cls._tasks)

    # ── Output Persistence (disk-backed task output) ─────────────

    @classmethod
    def _ensure_output_dir(cls) -> Path:
        """Create the task output directory if needed. Returns the Path."""
        cls.TASK_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return cls.TASK_OUTPUT_DIR

    @classmethod
    def write_output(cls, task_id: str, text: str) -> bool:
        """Append text to the task's persistent output file.

        Appends atomically (opens, writes, closes). Thread-safe because
        each append operation is an atomic write to the OS.
        Returns True if the task exists and was written to.
        """
        task = cls._get(task_id)
        if not task or not task.output_file:
            return False
        try:
            with open(task.output_file, "a", encoding="utf-8") as f:
                f.write(text)
                if not text.endswith("\n"):
                    f.write("\n")
            return True
        except OSError:
            return False

    @classmethod
    def read_output(cls, task_id: str) -> str:
        """Read the full output file for a task. Returns empty string on error."""
        task = cls._get(task_id)
        if not task or not task.output_file:
            return ""
        try:
            # If there's a stored offset, skip already-consumed bytes
            offset = task.output_offset
            with open(task.output_file, encoding="utf-8") as f:
                f.seek(offset)
                content = f.read()
                task.output_offset = f.tell()
            return content
        except OSError:
            return ""

    # ── Cancellation (per-task AbortController) ──────────────────

    @classmethod
    def cancel_task(cls, task_id: str) -> bool:
        """Set the abort signal on a task and transition to KILLED.

        Also cascades to all sub-tasks. Returns True if the task existed.
        Thread-safe via abort_signal (Event) + lock for state transition.
        """
        task = cls._get(task_id)
        if not task:
            return False

        # Signal the abort — this is checked in hot loops without the lock
        task.abort_signal.set()

        # Kill the state under lock
        with cls._lock:
            if task.status in (TaskState.RUNNING, TaskState.PENDING):
                task.status = TaskState.KILLED
                task.completed = time.time()

        # Cascade to sub-tasks
        for sub_id in list(task.sub_task_ids):
            cls.cancel_task(sub_id)

        return True

    @classmethod
    def is_cancelled(cls, task_id: str) -> bool:
        """Check whether a task has been cancelled (abort signal set).

        Lightweight check suitable for hot loops — reads the thread-safe Event
        without acquiring the class lock.
        """
        task = cls._get(task_id)
        return bool(task and task.abort_signal.is_set())

    @classmethod
    def get_main_task_id(cls) -> str | None:
        """Get the current main (top-level) task ID."""
        with cls._lock:
            return cls._current_task_id

    # ── Progress Prompt (replaces static _build_task_context) ────

    @classmethod
    def build_progress_prompt(cls, task_id: str) -> str:
        """Build a TASK PROGRESS section for the system prompt.

        Mirrors what I already built in RaphaelOrchestrator._build_task_context
        but sources data from the TaskManager store. Returns '' if no progress.
        """
        task = cls.get_task(task_id)
        if not task or not task.steps:
            return ""

        completed = [s for s in task.steps if s.status == "completed"]
        if not completed:
            return ""

        steps_text = "\n".join(
            f"  \u2713 {s.description}" for s in completed[-10:]
        )
        return (
            "=== TASK PROGRESS ===\n"
            f"Task: {task.id}  |  Goal: {task.goal[:150]}\n"
            "Completed steps:\n"
            f"{steps_text}\n\n"
            "IMPORTANT RULES:\n"
            "\u2022 Do NOT repeat any completed step \u2014 they are already done.\n"
            "\u2022 If all planned steps are done, respond with your final answer text "
            "\u2014 do NOT call more tools.\n"
            "\u2022 Only call a tool if you need to do something new that is NOT already completed."
        )

    # ── Internals ────────────────────────────────────────────────

    @classmethod
    def _get(cls, task_id: str) -> Task | None:
        with cls._lock:
            return cls._tasks.get(task_id)

    @staticmethod
    def _summarize_args(tool_name: str, args: dict) -> str:
        """Human-readable step description from tool args."""
        if "file_path" in args:
            fname = str(args["file_path"]).split("/")[-1].split("\\")[-1]
            return f"{tool_name}(file={fname})"
        elif "command" in args:
            cmd = str(args["command"])[:60]
            return f"{tool_name}(cmd={cmd})"
        elif "url" in args:
            return f"{tool_name}(url={args['url'][:60]})"
        elif "app_name" in args:
            return f"{tool_name}(app={args['app_name']})"
        elif "content" in args:
            preview = str(args["content"])[:40].replace("\n", " ")
            return f"{tool_name}(content={preview})"
        else:
            first = next(iter(args.values()), "")
            return f"{tool_name}({str(first)[:40]})"
