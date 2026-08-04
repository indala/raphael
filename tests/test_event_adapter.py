"""Tests for the single-emitter stream adapter.

Verifies that iterating a stream through ``stream_with_events`` publishes
the typed ``EventBus`` counterparts for tool results/errors and task
outcomes, and that proactive completions are NOT published (historical
behavior preserved).
"""

from orchestrator.event_adapter import stream_with_events
from orchestrator.event_bus import (
    TASK_COMPLETED,
    TOOL_EXECUTED,
    TOOL_FAILED,
    EventBus,
)
from orchestrator.events import (
    TaskCompleteEvent,
    TaskErrorEvent,
    ThinkingEvent,
    ToolErrorEvent,
    ToolResultEvent,
)


def setup_function():
    """Clear all subscribers before each test."""
    EventBus().clear()


def collect(events):
    """Iterate a stream, returning (yielded, bus events)."""
    bus = EventBus()
    yielded = []
    received = []

    def handler(event, data):
        received.append((event, data))

    bus.subscribe("*", handler)
    for ev in stream_with_events(events):
        yielded.append(ev)
    return yielded, received


def test_tool_result_publishes_tool_executed():
    """A ToolResultEvent yields through and publishes TOOL_EXECUTED."""
    yielded, received = collect([
        ToolResultEvent(
            tool="get_weather", result="sunny", round=2, agent="raphael",
            args={"city": "Paris"},
        ),
    ])
    assert len(yielded) == 1
    assert len(received) == 1
    event, data = received[0]
    assert event == TOOL_EXECUTED
    assert data == {
        "agent": "raphael",
        "tool": "get_weather",
        "args": {"city": "Paris"},
        "result": "sunny",
        "round": 2,
    }


def test_tool_error_publishes_tool_failed():
    """A ToolErrorEvent publishes TOOL_FAILED, not TOOL_EXECUTED."""
    _, received = collect([
        ToolErrorEvent(
            tool="search", error="Error: timeout", round=1, agent="raphael",
            args={"q": "x"},
        ),
    ])
    assert received[0][0] == TOOL_FAILED
    assert received[0][1]["result"] == "Error: timeout"


def test_task_complete_publishes_task_completed():
    """A non-proactive TaskCompleteEvent publishes TASK_COMPLETED."""
    _, received = collect([
        TaskCompleteEvent(task_id="t1", result="hello"),
    ])
    assert received[0][0] == TASK_COMPLETED
    assert received[0][1] == {"response": "hello"}


def test_task_complete_proactive_not_published():
    """A proactive completion preserves legacy behavior: no bus event."""
    yielded, received = collect([
        TaskCompleteEvent(task_id="t1", result="background done", proactive=True),
    ])
    assert len(yielded) == 1
    assert received == []


def test_task_error_publishes_task_completed_with_error():
    """A TaskErrorEvent publishes TASK_COMPLETED with the error text."""
    _, received = collect([
        TaskErrorEvent(task_id="t1", error="boom"),
    ])
    assert received[0][0] == TASK_COMPLETED
    assert received[0][1] == {"response": "boom"}


def test_unrelated_events_pass_through_silently():
    """Events with no bus counterpart (e.g. ThinkingEvent) yield only."""
    yielded, received = collect([
        ThinkingEvent(),
        ToolResultEvent(tool="t", result="ok", round=0),
    ])
    assert len(yielded) == 2
    assert [ev.type for ev in yielded] == ["thinking", "tool_result"]
    assert len(received) == 1  # only the tool result
    assert received[0][0] == TOOL_EXECUTED


def test_result_truncated_to_200():
    """Long results are truncated to match the historical payload shape."""
    long = "x" * 500
    _, received = collect([
        ToolResultEvent(tool="t", result=long, round=0),
    ])
    assert len(received[0][1]["result"]) == 200
