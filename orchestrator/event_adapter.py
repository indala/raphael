"""
Single-emitter adapter for the streaming event path.

Wraps the ``StreamEvent`` generator produced by
:meth:`RaphaelOrchestrator.process_message_events` so that each yielded
event is ALSO published as a typed ``EventBus`` payload — making the stream
the *single emitter* for request-path outcomes.

Before this module, the streaming path both yielded a ``StreamEvent`` **and**
published the corresponding ``EventBus`` event inline (see the deleted
publishes in ``orchestrator/core.py``). This adapter removes that duplication:
a tool result is now translated to ``TOOL_EXECUTED`` in exactly one place.
"""

from __future__ import annotations

from collections.abc import Generator

from orchestrator.event_bus import (
    TASK_COMPLETED,
    TOOL_EXECUTED,
    TOOL_FAILED,
    EventBus,
)
from orchestrator.event_payloads import (
    TaskCompletedPayload,
    ToolExecutedPayload,
)
from orchestrator.events import (
    StreamEvent,
    TaskCompleteEvent,
    TaskErrorEvent,
    ToolErrorEvent,
    ToolResultEvent,
)

# Results longer than this are truncated to match the historical payload shape.
_MAX_RESULT = 200


def _translate(ev: StreamEvent) -> None:
    """Publish a typed EventBus payload for a single stream event."""
    bus = EventBus()

    if isinstance(ev, ToolResultEvent):
        bus.publish_typed(
            TOOL_EXECUTED,
            ToolExecutedPayload(
                agent=ev.agent,
                tool=ev.tool,
                args=ev.args,
                result=ev.result[:_MAX_RESULT],
                round=ev.round,
            ),
        )
    elif isinstance(ev, ToolErrorEvent):
        bus.publish_typed(
            TOOL_FAILED,
            ToolExecutedPayload(
                agent=ev.agent,
                tool=ev.tool,
                args=ev.args,
                result=ev.error[:_MAX_RESULT],
                round=ev.round,
            ),
        )
    elif isinstance(ev, TaskCompleteEvent):
        # Proactive ("background") completions were historically not published
        # on the bus — preserve that behavior.
        if not ev.proactive:
            bus.publish_typed(
                TASK_COMPLETED,
                TaskCompletedPayload(response=ev.result[:_MAX_RESULT]),
            )
    elif isinstance(ev, TaskErrorEvent):
        bus.publish_typed(
            TASK_COMPLETED,
            TaskCompletedPayload(response=ev.error[:_MAX_RESULT]),
        )


def stream_with_events(events: Generator[StreamEvent]) -> Generator[StreamEvent]:
    """Yield each stream event, publishing its typed EventBus counterpart after.

    Publish-after-``yield`` preserves the historical tool ordering (the bus
    event arrives after the UI has observed the stream event) and exactly
    matches the background-task status chain.
    """
    for ev in events:
        yield ev
        _translate(ev)
