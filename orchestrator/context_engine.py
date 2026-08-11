"""
ContextEngine ABC — pluggable context selection and compression.

Pattern from hermes-agent's ContextEngine abstract base class.

Decouples three orthogonal concerns:
  1. select_context()   — which history/memory to include BEFORE a request
  2. on_turn_complete() — post-turn observation (routing, indexing, learning)
  3. compress()         — when to summarize and how

Any class implementing ContextEngine can be registered via
RaphaelOrchestrator.set_context_engine() and will be called automatically
from the message processing loop.

Built-in implementation: DefaultContextEngine
  - Uses ContextCompressor for compression
  - Uses memory_agent.get_relevant_context() for pre-request selection
  - Applies token budget capping on included history

Custom implementations can add:
  - Vector search (FAISS/BM25) for retrieval-augmented context
  - Per-turn indexing for later retrieval
  - Dynamic compression thresholds per-model
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.core import LLMClient

logger = logging.getLogger(__name__)


class ContextEngine(ABC):
    """Abstract base for context selection, observation, and compression.

    Implementations are called by RaphaelOrchestrator at key points
    in the message processing loop.
    """

    @abstractmethod
    def select_context(
        self,
        user_query: str,
        history: list[dict],
        max_history: int,
    ) -> list[dict]:
        """Select which history turns to include in the next LLM request.

        Called BEFORE the LLM call. Implementations can:
        - Filter irrelevant turns
        - Re-rank by relevance to the current query
        - Cap total token budget
        - Inject retrieved memory chunks

        Args:
            user_query:  The current user message.
            history:     Full conversation history list.
            max_history: Configured MAX_HISTORY ceiling.

        Returns:
            A (possibly filtered/trimmed) history list to pass to the LLM.
        """
        ...

    @abstractmethod
    def on_turn_complete(
        self,
        user_query: str,
        assistant_response: str,
        history: list[dict],
    ) -> None:
        """Observe a completed turn for indexing, routing, or learning.

        Called AFTER the LLM produces its final text response.
        Runs in the main thread — keep it fast or spawn a background task.

        Args:
            user_query:          The user's message that triggered this turn.
            assistant_response:  The final assistant text (not tool calls).
            history:             Full conversation history after this turn.
        """
        ...

    @abstractmethod
    def compress(
        self,
        history: list[dict],
        llm: LLMClient,
        max_history: int,
    ) -> list[dict]:
        """Compress conversation history when it exceeds the context budget.

        Called when history length exceeds the threshold. Implementations
        should preserve semantic meaning while reducing token count.

        Args:
            history:     Current conversation history.
            llm:         LLMClient for summarization calls.
            max_history: Configured MAX_HISTORY ceiling.

        Returns:
            Compressed history list.
        """
        ...


class DefaultContextEngine(ContextEngine):
    """Production context engine — compression + keyword-based selection.

    Wraps ContextCompressor for compression logic and memory_agent for
    pre-request keyword retrieval. This is Raphael's default engine.
    """

    def __init__(
        self,
        threshold_percent: float = 0.8,
        protect_last_n: int = 6,
        protect_first_n: int = 3,
        min_history_for_compression: int = 12,
        max_history_tokens: int = 8000,
    ):
        from orchestrator.context_compressor import ContextCompressor

        self._compressor = ContextCompressor(
            threshold_percent=threshold_percent,
            protect_last_n=protect_last_n,
            protect_first_n=protect_first_n,
            min_history_for_compression=min_history_for_compression,
        )
        self._max_history_tokens = max_history_tokens
        self._turn_count = 0

    def select_context(
        self,
        user_query: str,
        history: list[dict],
        max_history: int,
    ) -> list[dict]:
        """Return history capped to a rough token budget.

        Preserves the most recent turns and the first turn (system context).
        Cheap enough to run every request — no LLM call needed.
        """
        if not history:
            return history

        # Step 1: prune oversized tool results (free, deterministic)
        history = self._compressor.prune_tool_results_only(history)

        # Step 2: cap by rough character budget (4 chars ≈ 1 token)
        char_budget = self._max_history_tokens * 4
        total_chars = sum(len(str(m.get("content") or "")) for m in history)

        if total_chars <= char_budget:
            return list(history)

        # Keep first turn (system context) + most recent turns within budget
        first = history[:1] if history else []
        rest = history[1:]

        kept: list[dict] = []
        used = sum(len(str(m.get("content") or "")) for m in first)

        for turn in reversed(rest):
            turn_chars = len(str(turn.get("content") or ""))
            if used + turn_chars > char_budget:
                break
            kept.insert(0, turn)
            used += turn_chars

        result = first + kept
        if len(result) < len(history):
            logger.debug(
                "select_context: trimmed %d→%d turns (budget %d chars)",
                len(history), len(result), char_budget,
            )
        return result

    def on_turn_complete(
        self,
        user_query: str,
        assistant_response: str,
        history: list[dict],
    ) -> None:
        """Track turn count. Subclasses can override for indexing/learning."""
        self._turn_count += 1

    def compress(
        self,
        history: list[dict],
        llm: LLMClient,
        max_history: int,
    ) -> list[dict]:
        """Delegate to ContextCompressor (two-phase: prune then LLM summarize)."""
        # Phase 1: cheap prune
        history = self._compressor.prune_tool_results_only(history)

        # Phase 2: LLM compression if still over threshold
        if self._compressor.should_compress(history, max_history):
            history = self._compressor.compress(history, llm, max_history)

        return list(history)


# ── Global default engine ─────────────────────────────────────

_default_engine: ContextEngine | None = None


def get_default_engine() -> ContextEngine:
    """Return (and lazily create) the global default context engine."""
    global _default_engine
    if _default_engine is None:
        _default_engine = DefaultContextEngine()
    return _default_engine


def set_default_engine(engine: ContextEngine) -> None:
    """Replace the global default engine with a custom implementation."""
    global _default_engine
    logger.info("ContextEngine replaced with %s", type(engine).__name__)
    _default_engine = engine
