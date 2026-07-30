"""
Goal Manager — persistent goal tracking with JSON storage.

Manages long-term goals with priorities, deadlines, sub-task tracking,
and auto-calculated progress percentages.
"""

import json
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

import config

_GOALS_FILE = config.ROAMING_DIR / "goals" / "goals.json"
_lock = threading.RLock()


@dataclass
class SubTask:
    name: str
    completed: bool = False


@dataclass
class Goal:
    name: str
    description: str = ""
    status: str = "active"  # active | completed | archived
    priority: str = "medium"  # high | medium | low
    deadline: str | None = None  # ISO date string
    created_at: str = field(default_factory=lambda: datetime.now().isoformat()[:19])
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat()[:19])
    sub_tasks: list = field(default_factory=list)  # list of {"name": str, "completed": bool}

    @property
    def progress(self) -> int:
        """Auto-calculated progress percentage based on sub-tasks."""
        if self.status == "completed":
            return 100
        if not self.sub_tasks:
            return 0
        completed = sum(1 for s in self.sub_tasks if s.get("completed"))
        return int(completed / len(self.sub_tasks) * 100)


class GoalManager:
    """Thread-safe goal manager with JSON file persistence."""

    def __init__(self) -> None:
        self._goals: dict[str, Goal] = {}
        self._load()

    # ── Persistence ─────────────────────────────────────────────

    def _load(self):
        """Load goals from JSON file."""
        with _lock:
            if not _GOALS_FILE.exists():
                self._goals = {}
                return
            try:
                content = _GOALS_FILE.read_text(encoding="utf-8").strip()
                if not content:
                    self._goals = {}
                    return
                data = json.loads(content)
                self._goals = {}
                for name, g in data.items():
                    g.setdefault("sub_tasks", [])
                    g.setdefault("status", "active")
                    self._goals[name] = Goal(**g)
                logger.debug("Loaded %d goals from %s", len(self._goals), _GOALS_FILE)
            except Exception as e:
                logger.error("Failed to load goals: %s", e)
                self._goals = {}

    def _save(self):
        """Save goals to JSON file."""
        with _lock:
            try:
                _GOALS_FILE.parent.mkdir(parents=True, exist_ok=True)
                data = {name: asdict(g) for name, g in self._goals.items()}
                _GOALS_FILE.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
            except Exception as e:
                logger.error("Failed to save goals: %s", e)

    # ── CRUD ────────────────────────────────────────────────────

    def create(self, name: str, description: str = "",
               priority: str = "medium",
               deadline: str | None = None,
               sub_tasks: list[str] | None = None) -> str:
        """Create a new goal. Returns error string or empty string on success."""
        with _lock:
            if not name or not name.strip():
                return "Goal name is required."

            name = name.strip()
            if name in self._goals:
                return f"Goal '{name}' already exists."

            now = datetime.now().isoformat()[:19]
            tasks = [{"name": s.strip(), "completed": False} for s in (sub_tasks or []) if s.strip()]
            self._goals[name] = Goal(
                name=name,
                description=description.strip(),
                priority=priority.lower() if priority in ("high", "medium", "low") else "medium",
                deadline=deadline,
                created_at=now,
                updated_at=now,
                sub_tasks=tasks,
            )
            self._save()
            return ""

    def list(self, status: str | None = None) -> list[Goal]:
        """List goals, optionally filtered by status."""
        with _lock:
            goals = list(self._goals.values())
        if status:
            goals = [g for g in goals if g.status == status]
        return sorted(goals, key=lambda g: {"high": 0, "medium": 1, "low": 2}.get(g.priority, 1))

    def get(self, name: str) -> Goal | None:
        """Get a single goal by name."""
        with _lock:
            return self._goals.get(name)

    def update(self, name: str, **kwargs) -> str:
        """Update goal fields. Returns error string or empty string on success.

        Supported kwargs: description, priority, deadline, status.
        To toggle a sub-task: sub_task="SubTask Name"
        """
        with _lock:
            goal = self._goals.get(name)
            if not goal:
                return f"Goal '{name}' not found."

            changed = False
            now = datetime.now().isoformat()[:19]

            for key, value in kwargs.items():
                if key == "description":
                    goal.description = value.strip()
                    changed = True
                elif key == "priority" and value in ("high", "medium", "low"):
                    goal.priority = value
                    changed = True
                elif key == "deadline":
                    goal.deadline = value
                    changed = True
                elif key == "status" and value in ("active", "completed", "archived"):
                    goal.status = value
                    if value == "completed":
                        for s in goal.sub_tasks:
                            s["completed"] = True
                    changed = True
                elif key == "sub_task":
                    # Toggle a sub-task's completed status
                    for s in goal.sub_tasks:
                        if s["name"] == value:
                            s["completed"] = not s["completed"]
                            changed = True
                            break
                    else:
                        return f"Sub-task '{value}' not found in goal '{name}'."

            if changed:
                goal.updated_at = now
                self._save()
            return ""

    def archive(self, name: str) -> str:
        """Archive a goal. Returns error string or empty string on success."""
        return self.update(name, status="archived")

    def delete(self, name: str) -> str:
        """Permanently delete a goal."""
        with _lock:
            if name not in self._goals:
                return f"Goal '{name}' not found."
            del self._goals[name]
            self._save()
            return ""

    def summary(self) -> str:
        """Return a formatted summary of all goals."""
        with _lock:
            goals = list(self._goals.values())

        if not goals:
            return "No goals set."

        active = [g for g in goals if g.status == "active"]
        completed = [g for g in goals if g.status == "completed"]
        [g for g in goals if g.status == "archived"]

        lines = [f"**Goals Summary** ({len(active)} active, {len(completed)} completed)"]
        for g in active:
            progress = g.progress
            pbar = "█" * (progress // 10) + "░" * (10 - progress // 10)
            deadline = f"  Due: {g.deadline}" if g.deadline else ""
            lines.append(
                f"\n**{g.name}** [{g.priority}] {pbar} {progress}%{deadline}"
            )
            if g.description:
                lines.append(f"  _{g.description}_")
            if g.sub_tasks:
                for s in g.sub_tasks:
                    check = "✅" if s["completed"] else "☐"
                    lines.append(f"  {check} {s['name']}")
        return "\n".join(lines)
