"""Tests for the Workflow system."""

from workflows import save_workflow, load_workflow, list_workflows, delete_workflow
from workflows.executor import interpolate, interpolate_args


def teardown_function():
    """Clean up test workflow files."""
    for name in ("test_workflow", "test_workflow_save", "test_params"):
        delete_workflow(name)


def _sample_workflow(name="test_workflow"):
    return {
        "name": name,
        "description": "Test workflow",
        "parameters": [
            {"name": "name", "type": "string", "description": "A name"},
        ],
        "steps": [
            {"tool": "say", "args": {"text": "Hello {{name}}!"}, "label": "Greet"},
            {"tool": "get_time", "args": {}, "label": "Get time"},
        ],
        "required_tools": ["say", "get_time"],
    }


def test_interpolate():
    """{{param}} placeholders should be replaced with values."""
    assert interpolate("Hello {{name}}!", {"name": "World"}) == "Hello World!"
    assert interpolate("No placeholders", {"x": "y"}) == "No placeholders"
    assert interpolate("{{a}}-{{b}}", {"a": "1", "b": "2"}) == "1-2"


def test_interpolate_missing():
    """Missing params should leave placeholder intact."""
    assert interpolate("Hello {{name}}!", {}) == "Hello {{name}}!"


def test_interpolate_args():
    """Dict interpolation should work recursively."""
    args = {"greeting": "Hi {{name}}!", "nested": {"msg": "Bye {{name}}"}}
    result = interpolate_args(args, {"name": "Alice"})
    assert result["greeting"] == "Hi Alice!"
    assert result["nested"]["msg"] == "Bye Alice"


def test_save_and_load():
    """Save and load a workflow."""
    wf = _sample_workflow("test_workflow_save")
    err = save_workflow(wf)
    assert err == ""

    loaded = load_workflow("test_workflow_save")
    assert loaded is not None
    assert loaded["name"] == "test_workflow_save"
    assert len(loaded["steps"]) == 2


def test_save_validates_name():
    """Saving a workflow without a name should return an error."""
    err = save_workflow({"description": "no name"})
    assert "name" in err


def test_save_validates_steps():
    """Saving a workflow without steps should return an error."""
    err = save_workflow({"name": "x", "description": "y"})
    assert "step" in err.lower()


def test_list_workflows():
    """list_workflows should return saved workflows."""
    save_workflow(_sample_workflow("test_workflow_save"))
    workflows = list_workflows()
    names = [w["name"] for w in workflows]
    assert "test_workflow_save" in names


def test_delete_workflow():
    """Deleted workflow should not appear in listings."""
    save_workflow(_sample_workflow("test_workflow_save"))
    delete_workflow("test_workflow_save")
    loaded = load_workflow("test_workflow_save")
    assert loaded is None


def test_load_nonexistent():
    """Loading a nonexistent workflow should return None."""
    assert load_workflow("nonexistent_workflow") is None


def test_execute_workflow_basic():
    """execute_workflow with parameter interpolation should run steps."""
    from workflows.executor import execute_workflow
    save_workflow({
        "name": "test_params",
        "description": "Test params",
        "parameters": [{"name": "greeting", "type": "string"}],
        "steps": [
            {"tool": "get_agent_performance", "args": {}, "label": "Get perf"},
        ],
        "required_tools": ["get_agent_performance"],
    })
    result = execute_workflow("test_params")
    assert "test_params" in result
    assert "Get perf" in result
