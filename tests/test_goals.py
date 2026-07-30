"""Tests for the Goal Manager."""


import config

# Clean up test goals file before each test
_GOALS_FILE = config.ROAMING_DIR / "goals" / "goals.json"


def setup_function():
    if _GOALS_FILE.exists():
        _GOALS_FILE.unlink()


def teardown_function():
    if _GOALS_FILE.exists():
        _GOALS_FILE.unlink()


def test_create_goal():
    """Creating a goal should succeed and persist."""
    from goals import GoalManager
    mgr = GoalManager()
    err = mgr.create("Test Goal", "A test goal", priority="high")
    assert err == ""
    goal = mgr.get("Test Goal")
    assert goal is not None
    assert goal.name == "Test Goal"
    assert goal.description == "A test goal"
    assert goal.priority == "high"
    assert goal.status == "active"
    assert goal.progress == 0


def test_create_goal_empty_name():
    """Empty name should return an error."""
    from goals import GoalManager
    mgr = GoalManager()
    err = mgr.create("")
    assert err != ""


def test_create_goal_duplicate():
    """Duplicate name should return an error."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Dup Goal")
    err = mgr.create("Dup Goal")
    assert err != ""
    assert "already exists" in err


def test_create_goal_with_sub_tasks():
    """Goal with sub-tasks should show progress."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Learn Python", sub_tasks=["Basics", "OOP", "Libraries"])
    goal = mgr.get("Learn Python")
    assert len(goal.sub_tasks) == 3  # type: ignore[union-attr]
    assert all(not s["completed"] for s in goal.sub_tasks)  # type: ignore[union-attr]
    assert goal.progress == 0  # type: ignore[union-attr]


def test_list_goals():
    """list() should return all goals sorted by priority."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Low Priority", priority="low")
    mgr.create("High Priority", priority="high")
    mgr.create("Medium Priority", priority="medium")
    goals = mgr.list()
    assert len(goals) == 3
    assert goals[0].name == "High Priority"


def test_list_goals_filtered():
    """list(status='completed') should only return completed goals."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Active Goal")
    mgr.create("Done Goal")
    mgr.update("Done Goal", status="completed")
    goals = mgr.list(status="completed")
    assert len(goals) == 1
    assert goals[0].name == "Done Goal"


def test_update_goal_toggle_sub_task():
    """Toggle a sub-task should update progress."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Build App", sub_tasks=["Frontend", "Backend", "Deploy"])
    err = mgr.update("Build App", sub_task="Frontend")
    assert err == ""
    goal = mgr.get("Build App")
    assert goal.sub_tasks[0]["completed"] is True  # type: ignore[union-attr]
    assert goal.sub_tasks[1]["completed"] is False  # type: ignore[union-attr]
    assert goal.progress == 33  # type: ignore[union-attr]  # 1/3


def test_update_goal_status_completed():
    """Setting status to completed should mark all sub-tasks done and progress=100."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Write Book", sub_tasks=["Outline", "Draft", "Edit"])
    mgr.update("Write Book", status="completed")
    goal = mgr.get("Write Book")
    assert goal.status == "completed"  # type: ignore[union-attr]
    assert goal.progress == 100  # type: ignore[union-attr]
    assert all(s["completed"] for s in goal.sub_tasks)  # type: ignore[union-attr]


def test_archive_goal():
    """Archiving a goal should change its status."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Old Project")
    err = mgr.archive("Old Project")
    assert err == ""
    goal = mgr.get("Old Project")
    assert goal.status == "archived"  # type: ignore[union-attr]


def test_delete_goal():
    """Deleting a goal should remove it permanently."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Temp Goal")
    mgr.delete("Temp Goal")
    assert mgr.get("Temp Goal") is None


def test_summary_empty():
    """Summary of no goals should return a message."""
    from goals import GoalManager
    mgr = GoalManager()
    summary = mgr.summary()
    assert "No goals" in summary


def test_summary_with_goals():
    """Summary should include active goals with progress bars."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Test Goal", priority="high")
    summary = mgr.summary()
    assert "Test Goal" in summary
    assert "high" in summary
    assert "0%" in summary


def test_goal_progress_no_sub_tasks():
    """Goal without sub-tasks should have 0% progress when active."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Simple Goal")
    assert mgr.get("Simple Goal").progress == 0  # type: ignore[union-attr]


def test_goal_progress_full():
    """All sub-tasks completed should give 100%."""
    from goals import GoalManager
    mgr = GoalManager()
    mgr.create("Full Goal", sub_tasks=["A", "B"])
    mgr.update("Full Goal", sub_task="A")
    mgr.update("Full Goal", sub_task="B")
    assert mgr.get("Full Goal").progress == 100  # type: ignore[union-attr]


def test_tool_create_goal():
    """Tool function create_goal should return success message."""
    from orchestrator.tools.native.goals import create_goal
    result = create_goal("Tool Goal", "Created via tool")
    assert "created" in result.lower()
    from goals import GoalManager
    assert GoalManager().get("Tool Goal") is not None


def test_tool_list_goals():
    """Tool function list_goals should return formatted output."""
    from orchestrator.tools.native.goals import create_goal, list_goals
    create_goal("List Goal")
    result = list_goals()
    assert "List Goal" in result


def test_tool_update_goal():
    """Tool function update_goal should return success message."""
    from orchestrator.tools.native.goals import create_goal, update_goal
    create_goal("Update Goal")
    result = update_goal("Update Goal", status="completed")
    assert "updated" in result.lower()


def test_tool_archive_goal():
    """Tool function archive_goal should return success message."""
    from orchestrator.tools.native.goals import create_goal, archive_goal
    create_goal("Archive Goal")
    result = archive_goal("Archive Goal")
    assert "archived" in result.lower()
