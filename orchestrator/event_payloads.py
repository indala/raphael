"""
Typed event payloads for Raphael's EventBus.

Each event name in :mod:`orchestrator.event_bus` maps to a ``@dataclass``
payload here. Publishing through ``EventBus.publish_typed(event_name, payload)``
serializes the payload via :meth:`EventPayload.to_dict` (which drops ``None``
fields) so the existing ``(name, dict)`` subscriber contract is unchanged.

There are **no event-name constants defined here** — the registry keys are the
actual constant objects imported from ``orchestrator.event_bus``, so a single
event name never diverges between the two modules. ``from_dict`` is tolerant of
missing and unknown keys so consumers can hydrate a payload from a partial dict
without crashing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, cast

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
)


class EventPayload:
    """Base class for all typed event payloads."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict, dropping ``None`` fields.

        Mirrors the key sets of the legacy ``EventBus.publish(name, **data)``
        call sites so subscribers observe identical data.
        """
        return {k: v for k, v in asdict(cast(Any, self)).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventPayload:
        """Build a payload from a dict, ignoring unknown and missing keys."""
        cls_type = cast(type[Any], cls)
        known = {f.name: data[f.name] for f in fields(cls_type) if f.name in data}
        return cls(**known)


@dataclass
class ToolExecutedPayload(EventPayload):
    """Payload for ``TOOL_EXECUTED`` / ``TOOL_FAILED``."""

    agent: str
    tool: str
    args: dict[str, Any]
    result: str
    round: int


@dataclass
class ToolRegistryChangedPayload(EventPayload):
    """Payload for ``TOOL_CREATED`` / ``TOOL_OPTIMIZED`` / ``TOOL_ARCHIVED``."""

    name: str
    file: str | None = None
    old_ms: float | None = None
    new_ms: float | None = None


@dataclass
class TaskStatusChangedPayload(EventPayload):
    """Payload for ``TASK_STATUS_CHANGED`` — mirrors ``BackgroundTask.to_dict()``."""

    task_id: str
    label: str
    tool_name: str
    status: str
    result: str | None = None
    error: str | None = None
    elapsed: float | None = None
    current_action: str | None = None


@dataclass
class TaskFinishedPayload(EventPayload):
    """Payload for ``TASK_FINISHED``."""

    task_id: str
    label: str
    status: str
    summary: str = ""
    error: str | None = None


@dataclass
class TaskCompletedPayload(EventPayload):
    """Payload for ``TASK_COMPLETED``.

    A union of the three shapes published today: the core request path
    (``user_input`` / ``response``), agent delegation (``from_agent`` /
    ``agent`` / ``query`` / ``result``), and workflow completion (``workflow`` /
    ``steps`` / ``results``). ``to_dict`` drops ``None`` fields, so only the
    keys relevant to the publisher's shape are emitted.
    """

    user_input: str | None = None
    response: str | None = None
    error: str | None = None
    task_id: str | None = None
    # delegation shape
    from_agent: str | None = None
    agent: str | None = None
    query: str | None = None
    result: str | None = None
    # workflow shape
    workflow: str | None = None
    steps: int | None = None
    results: list[Any] | None = None


@dataclass
class AgentDelegatedPayload(EventPayload):
    """Payload for ``AGENT_DELEGATED``."""

    from_agent: str
    to_agent: str
    query: str
    depth: int


@dataclass
class MemoryUpdatedPayload(EventPayload):
    """Payload for ``MEMORY_UPDATED``."""

    source: str
    updates: list[str]


# ── Registry ──────────────────────────────────────────────────────────────

EVENT_PAYLOAD: dict[str, type[EventPayload]] = {
    TOOL_EXECUTED: ToolExecutedPayload,
    TOOL_FAILED: ToolExecutedPayload,
    TOOL_CREATED: ToolRegistryChangedPayload,
    TOOL_OPTIMIZED: ToolRegistryChangedPayload,
    TOOL_ARCHIVED: ToolRegistryChangedPayload,
    TASK_STATUS_CHANGED: TaskStatusChangedPayload,
    TASK_FINISHED: TaskFinishedPayload,
    TASK_COMPLETED: TaskCompletedPayload,
    AGENT_DELEGATED: AgentDelegatedPayload,
    MEMORY_UPDATED: MemoryUpdatedPayload,
}
