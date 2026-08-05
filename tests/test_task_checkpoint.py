"""
Tests for TaskManager durable-execution checkpointing (LangGraph borrow).

Verifies that task state is persisted on every transition and that
recover_interrupted() repairs mid-flight tasks after a simulated restart.
"""

import pytest

from orchestrator.task_manager import TaskManager, TaskState


@pytest.fixture(autouse=True)
def isolated_tasks(monkeypatch, tmp_path):
    """Point the checkpoint at a temp file and reset in-memory state per test."""
    monkeypatch.setattr(TaskManager, "TASK_CHECKPOINT_FILE", tmp_path / "tasks.json")
    TaskManager._tasks = {}
    TaskManager._current_task_id = None
    yield
    TaskManager._tasks = {}
    TaskManager._current_task_id = None


def _simulate_restart():
    """Wipe in-memory state to mimic a process crash/restart."""
    TaskManager._tasks = {}
    TaskManager._current_task_id = None


def test_completed_task_survives_restart():
    tid = TaskManager.create_task("Write a report")
    TaskManager.start_task(tid)
    TaskManager.add_step(tid, "Gathered data", "web_search")
    TaskManager.complete_task(tid, result="Done")

    assert TaskManager.TASK_CHECKPOINT_FILE.exists(), "checkpoint must be written"

    _simulate_restart()
    assert TaskManager.get_task(tid) is None

    recovered = TaskManager.recover_interrupted()
    assert recovered == 1

    task = TaskManager.get_task(tid)
    assert task is not None
    assert task.status == TaskState.COMPLETED
    assert task.result == "Done"
    assert len(task.steps) == 1
    assert task.steps[0].tool_name == "web_search"


def test_running_task_is_repaired_as_failed():
    running = TaskManager.create_task("Long-running work")
    TaskManager.start_task(running)
    done = TaskManager.create_task("Already finished")
    TaskManager.complete_task(done, result="ok")

    _simulate_restart()
    TaskManager.recover_interrupted()

    run = TaskManager.get_task(running)
    assert run is not None
    assert run.status == TaskState.FAILED
    assert "Interrupted" in (run.error or "")

    # Terminal tasks preserved verbatim
    d = TaskManager.get_task(done)
    assert d is not None and d.status == TaskState.COMPLETED


def test_recover_with_no_checkpoint_returns_zero():
    assert TaskManager.recover_interrupted() == 0


def test_recover_with_non_dict_checkpoint_is_safe(tmp_path):
    """Valid JSON that is not a dict must not raise AttributeError (crash guard)."""
    TaskManager.TASK_CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    TaskManager.TASK_CHECKPOINT_FILE.write_text('[1, 2, 3]', encoding="utf-8")
    assert TaskManager.recover_interrupted() == 0
    assert TaskManager._tasks == {}


def test_usage_and_budget_are_persisted():
    tid = TaskManager.create_task("Budgeted task")
    TaskManager.start_task(tid)
    TaskManager.set_budget(tid, max_tokens=500)
    TaskManager.record_usage(tid, tokens=120, cost=0.01)

    _simulate_restart()
    TaskManager.recover_interrupted()

    task = TaskManager.get_task(tid)
    assert task is not None
    assert task.tokens_used == 120
    assert task.cost_usd == 0.01
    assert task.max_tokens == 500


def test_cancelled_task_persists_as_killed():
    tid = TaskManager.create_task("Cancellable task")
    TaskManager.start_task(tid)
    TaskManager.cancel_task(tid)

    _simulate_restart()
    TaskManager.recover_interrupted()

    task = TaskManager.get_task(tid)
    assert task is not None and task.status == TaskState.KILLED


def test_clear_completed_updates_checkpoint():
    a = TaskManager.create_task("One")
    TaskManager.complete_task(a, result="x")
    b = TaskManager.create_task("Two")
    TaskManager.start_task(b)

    TaskManager.clear_completed()
    assert TaskManager.get_task(a) is None

    _simulate_restart()
    TaskManager.recover_interrupted()

    assert TaskManager.get_task(a) is None
    # The surviving non-terminal task was repaired to FAILED, not lost
    task = TaskManager.get_task(b)
    assert task is not None
    assert task.status == TaskState.FAILED
