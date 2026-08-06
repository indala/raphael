"""
Context Compressor — intelligent conversation history summarization.

Pattern from hermes-agent + openclaude: when history exceeds a threshold,
compress old turns into a summary rather than truncating. Preserves context
about goals, decisions, and key facts while drastically reducing token count.

Features:
- Head/tail protection: never compress the N newest turns
- Smart boundary detection: compress at natural conversation breaks
- Auto-compaction trigger at configurable percentage of context window
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.core import LLMClient

logger = logging.getLogger(__name__)


class ContextCompressor:
    """Compresses conversation history to stay within context limits."""

    def __init__(
        self,
        threshold_percent: float = 0.8,
        protect_last_n: int = 6,
        protect_first_n: int = 3,
        min_history_for_compression: int = 20,
    ):
        """Initialize the compressor with thresholds.

        Args:
            threshold_percent: Trigger compression at this % of max history (0.8 = 80%)
            protect_last_n: Always preserve the N most recent turns
            protect_first_n: Always preserve the N oldest turns (context setup)
            min_history_for_compression: Don't compress unless history exceeds this
        """
        self.threshold_percent = threshold_percent
        self.protect_last_n = protect_last_n
        self.protect_first_n = protect_first_n
        self.min_history_for_compression = min_history_for_compression

    def should_compress(self, history: list[dict], max_history: int) -> bool:
        """Check if history should be compressed.

        Returns True if history length exceeds threshold_percent of max_history
        and has at least min_history_for_compression turns.
        """
        if len(history) < self.min_history_for_compression:
            return False
        threshold = int(max_history * self.threshold_percent)
        return len(history) > threshold

    def compress(
        self, history: list[dict], llm: "LLMClient", max_history: int
    ) -> list[dict]:
        """Compress old conversation turns into a summary.

        Preserves:
        - First N turns (context setup, system messages)
        - Last N turns (recent conversation)

        Compresses:
        - Everything in between → single summary message

        Returns the compressed history list.
        """
        if not self.should_compress(history, max_history):
            return history

        # Calculate compression boundary
        protect_head = min(self.protect_first_n, len(history) // 3)
        protect_tail = min(self.protect_last_n, len(history) // 3)

        if protect_head + protect_tail >= len(history):
            # Not enough to compress
            return history

        head = history[:protect_head]
        to_compress = history[protect_head : -protect_tail]
        tail = history[-protect_tail:]

        if not to_compress:
            return history

        # Build summary prompt from turns to compress
        compact_text = self._format_for_summary(to_compress)

        try:
            summary = llm.chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a conversation summarizer. Summarize the following "
                            "conversation history concisely. Focus on:\n"
                            "- User goals and requests\n"
                            "- Decisions made\n"
                            "- Files modified or created\n"
                            "- Tools used\n"
                            "- Key facts established\n\n"
                            "Keep the summary under 250 words. Be specific about what was accomplished."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Summarize this conversation:\n\n{compact_text}",
                    },
                ],
                tools=None,
                reason="history_compression",
            )
            summary_text = summary.content if summary and hasattr(summary, "content") else ""
            if not summary_text or summary_text.strip().startswith("[Error calling LLM"):
                raise ValueError("LLM compression failed")
        except Exception as e:
            logger.warning("Compression failed: %s — falling back to truncation", e)
            # Fallback: simple truncation keeping head + tail
            return head + tail

        # Insert compressed summary between head and tail
        compressed_message = {
            "role": "system",
            "content": f"[Compressed History]: {summary_text[:600]}",
        }

        compressed_history = head + [compressed_message] + tail

        logger.info(
            "Compressed history: %d turns → %d turns (saved ~%d turns)",
            len(history),
            len(compressed_history),
            len(to_compress),
        )

        return compressed_history

    def _format_for_summary(self, turns: list[dict]) -> str:
        """Format conversation turns for LLM summarization.

        Includes role, content preview, and tool calls.
        Truncates long content to keep summary prompt manageable.
        """
        lines = []
        for turn in turns:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            tool_calls = turn.get("tool_calls", [])

            # Truncate long content
            if isinstance(content, str) and len(content) > 300:
                content = content[:300] + "..."

            line = f"[{role}] {content}"
            lines.append(line)

            # Add tool call info
            if tool_calls:
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        func_name = tc.get("function", {}).get("name", "?")
                        lines.append(f"  → tool: {func_name}")

        return "\n".join(lines)

    def prune_tool_results_only(self, history: list[dict], max_chars: int = 5000) -> list[dict]:
        """Cheap deterministic trim: truncate oversized tool results.

        Pattern from hermes-agent: before expensive LLM compression, try
        a quick pass that just trims tool results to a reasonable size.
        This often buys enough space to defer compression.

        Returns modified history (does not mutate original).
        """
        pruned = []
        for turn in history:
            if turn.get("role") == "tool":
                content = turn.get("content", "")
                if isinstance(content, str) and len(content) > max_chars:
                    pruned_turn = dict(turn)
                    pruned_turn["content"] = content[:max_chars] + "\n...[truncated]"
                    pruned.append(pruned_turn)
                else:
                    pruned.append(turn)
            else:
                pruned.append(turn)
        return pruned


# Global singleton
_compressor = ContextCompressor()


def should_compress(history: list[dict], max_history: int) -> bool:
    """Check if history should be compressed (global singleton)."""
    return _compressor.should_compress(history, max_history)


def compress_history(
    history: list[dict], llm: "LLMClient", max_history: int
) -> list[dict]:
    """Compress history (global singleton)."""
    return _compressor.compress(history, llm, max_history)


def prune_tool_results(history: list[dict], max_chars: int = 5000) -> list[dict]:
    """Prune oversized tool results (global singleton)."""
    return _compressor.prune_tool_results(history, max_chars)
