"""Tests for typed event payloads and ``EventBus.publish_typed``.

Verifies the ``EventPayload`` dataclasses round-trip through
``to_dict``/``from_dict``, that ``None`` fields are dropped during
serialization, and that ``publish_typed`` validates the event↔payload
mapping (warning, never raising) before delegating to ``publish``.
"""

from orchestrator.event_bus import (
    AGENT_DELEGATED,
    MEMORY_UPDATED,
    TASK_COMPLETED,
    TASK_FINISHED,
    TASK_STATUS_CHANGED,
    TOOL_ARCHIVED,
    TOOL_CREATED,
    TOOL_EXECUTED,
    TOOL_FAILED,
    TOOL_OPTIMIZED,
    EventBus,
)
from orchestrator.event_payloads import (
    EVENT_PAYLOAD,
    AgentDelegatedPayload,
    MemoryUpdatedPayload,
    TaskCompletedPayload,
    TaskFinishedPayload,
    TaskStatusChangedPayload,
    ToolExecutedPayload,
    ToolRegistryChangedPayload,
)


def setup_function():
    """Clear all subscribers before each test."""
    EventBus().clear()


# ── Payload round-trips ──────────────────────────────────────────────────


def test_registry_maps_every_event():
    """Every typed event constant has a registered payload class."""
    for name in (
        TOOL_EXECUTED,
        TOOL_FAILED,
        TOOL_CREATED,
        TOOL_OPTIMIZED,
        TOOL_ARCHIVED,
        TASK_STATUS_CHANGED,
        TASK_FINISHED,
        TASK_COMPLETED,
        AGENT_DELEGATED,
        MEMORY_UPDATED,
    ):
        assert name in EVENT_PAYLOAD, f"no payload registered for {name}"


def test_tool_executed_roundtrip():
    payload = ToolExecutedPayload(
        agent="raphael", tool="get_weather", args={"city": "Paris"},
        result="sunny", round=3,
    )
    data = payload.to_dict()
    assert data["agent"] == "raphael"
    assert data["round"] == 3
    rebuilt = ToolExecutedPayload.from_dict(data)
    assert rebuilt == payload


def test_tool_registry_changed_drops_none():
    payload = ToolRegistryChangedPayload(name="my_tool")
    data = payload.to_dict()
    assert data == {"name": "my_tool"}
    assert "file" not in data
    assert "old_ms" not in data
    # Unknown/missing keys tolerated
    rebuilt = ToolRegistryChangedPayload.from_dict({"name": "my_tool", "bogus": 1})
    assert rebuilt.name == "my_tool"


def test_task_status_changed_mirrors_background_task_keys():
    payload = TaskStatusChangedPayload(
        task_id="abc123", label="web search", tool_name="web_search",
        status="done", result="found it", elapsed=1.2,
    )
    data = payload.to_dict()
    assert data == {
        "task_id": "abc123",
        "label": "web search",
        "tool_name": "web_search",
        "status": "done",
        "result": "found it",
        "elapsed": 1.2,
    }
    assert "error" not in data
    assert "current_action" not in data


def test_task_finished_roundtrip():
    payload = TaskFinishedPayload(task_id="t1", label="task", status="done", summary="ok")
    data = payload.to_dict()
    rebuilt = TaskFinishedPayload.from_dict(data)
    assert rebuilt == payload


def test_task_completed_union_shapes():
    # core request-path shape
    core = TaskCompletedPayload(user_input="hi", response="hello")
    assert core.to_dict() == {"user_input": "hi", "response": "hello"}
    # delegation shape
    delegation = TaskCompletedPayload(from_agent="raphael", agent="coder", query="q", result="r")
    assert delegation.to_dict() == {
        "from_agent": "raphael", "agent": "coder", "query": "q", "result": "r",
    }
    # workflow shape
    workflow = TaskCompletedPayload(workflow="wf", steps=2, results=[{"a": 1}])
    assert workflow.to_dict() == {"workflow": "wf", "steps": 2, "results": [{"a": 1}]}


def test_agent_delegated_and_memory_updated():
    d = AgentDelegatedPayload(from_agent="raphael", to_agent="researcher", query="q", depth=1)
    assert AgentDelegatedPayload.from_dict(d.to_dict()) == d
    m = MemoryUpdatedPayload(source="organizer", updates=["note"])
    assert MemoryUpdatedPayload.from_dict(m.to_dict()) == m


# ── publish_typed validation ─────────────────────────────────────────────


def test_publish_typed_dispatches_correct_keys():
    """A subscriber sees the exact keys a typed payload serializes to."""
    bus = EventBus()
    received = []

    def handler(event, data):
        received.append((event, data))

    bus.subscribe(TOOL_EXECUTED, handler)
    bus.publish_typed(
        TOOL_EXECUTED,
        ToolExecutedPayload(agent="raphael", tool="get_weather", args={}, result="sunny", round=1),
    )
    assert len(received) == 1
    event, data = received[0]
    assert event == TOOL_EXECUTED
    assert data == {
        "agent": "raphael", "tool": "get_weather", "args": {},
        "result": "sunny", "round": 1,
    }


def test_publish_typed_warns_on_unregistered_event():
    """An event with no payload in the registry logs a warning, not a raise."""
    bus = EventBus()
    received = []

    def handler(event, _data):
        received.append(event)

    bus.subscribe("*", handler)
    # No payload registered for this string event name
    bus.publish_typed("no.such.event", MemoryUpdatedPayload(source="x", updates=[]))
    assert received == []


def test_publish_typed_warns_on_type_mismatch():
    """Publishing the wrong payload class for an event warns and drops."""
    bus = EventBus()
    received = []

    def handler(event, _data):
        received.append(event)

    bus.subscribe(TOOL_CREATED, handler)
    # TOOL_CREATED expects ToolRegistryChangedPayload, not ToolExecutedPayload
    bus.publish_typed(
        TOOL_CREATED,
        ToolExecutedPayload(agent="raphael", tool="x", args={}, result="", round=0),
    )
    assert received == []
