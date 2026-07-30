"""
Streaming event types for the orchestrator.

Typed events that the orchestrator yields during process_message_stream(),
enabling the UI/controller to stream intermediate state in real time
instead of waiting for a final blocking result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

T = TypeVar("T")


@dataclass
class StreamEvent:
    """Base class for all streaming events."""
    type: str  # discriminator for easy isinstance-free matching
    timestamp: float = field(default_factory=lambda: __import__("time").time())


# ── Lifecycle ────────────────────────────────────────────────────

@dataclass
class ThinkingEvent(StreamEvent):
    """LLM is generating a response (no tool calls yet)."""
    type: str = "thinking"
    round: int = 0


@dataclass
class AssistantEvent(StreamEvent):
    """Text response from the LLM (final or intermediate)."""
    type: str = "assistant"
    content: str = ""
    reasoning_content: str | None = None
    round: int = 0
    is_final: bool = False


@dataclass
class TokenEvent(StreamEvent):
    """A single streaming token from the LLM."""
    type: str = "token"
    token: str = ""


@dataclass
class ReasoningTokenEvent(StreamEvent):
    """A single reasoning token from the LLM."""
    type: str = "reasoning_token"
    token: str = ""


# ── Tool Execution ───────────────────────────────────────────────

@dataclass
class ToolStartEvent(StreamEvent):
    """A tool call is about to be executed."""
    type: str = "tool_start"
    tool: str = ""
    args: dict = field(default_factory=dict)
    round: int = 0
    parallel_group: str = ""


@dataclass
class ToolResultEvent(StreamEvent):
    """A tool call completed successfully."""
    type: str = "tool_result"
    tool: str = ""
    result: str = ""
    duration_ms: float = 0.0
    round: int = 0
    truncated: bool = False


@dataclass
class ToolErrorEvent(StreamEvent):
    """A tool call failed."""
    type: str = "tool_error"
    tool: str = ""
    error: str = ""
    duration_ms: float = 0.0
    round: int = 0


# ── Progress ─────────────────────────────────────────────────────

@dataclass
class ProgressEvent(StreamEvent):
    """Round progress update."""
    type: str = "progress"
    round: int = 0
    total_rounds: int = 25
    tool_count: int = 0


@dataclass
class ToolLoopWarningEvent(StreamEvent):
    """Tool is looping (same tool + args called repeatedly)."""
    type: str = "tool_loop_warning"
    tool: str = ""
    warning: str = ""


# ── Task Outcome ─────────────────────────────────────────────────

@dataclass
class TaskCompleteEvent(StreamEvent):
    """Task completed successfully with final result."""
    type: str = "task_complete"
    task_id: str = ""
    result: str = ""


@dataclass
class TaskErrorEvent(StreamEvent):
    """Task failed or hit an error."""
    type: str = "task_error"
    task_id: str = ""
    error: str = ""


@dataclass
class InterruptedEvent(StreamEvent):
    """Task was cancelled by user interrupt."""
    type: str = "interrupted"
    task_id: str = ""


# ── Helpers ──────────────────────────────────────────────────────

def event_to_dict(event: StreamEvent) -> dict:
    """Serialize a StreamEvent to a plain dict (for logging/API)."""
    d = {"type": event.type, "timestamp": event.timestamp}
    for k, v in event.__dict__.items():
        if k not in ("type", "timestamp"):
            d[k] = v
    return d
