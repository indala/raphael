"""
Structured Context Compressor — JSON-aware tool result truncation.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def compress_tool_result(
    result: Any,
    max_str_len: int = 500,
    max_list_items: int = 10,
) -> str:
    """Compress a tool result string or object using structure-preserving truncation.

    If input is JSON or a dict/list, long strings are trimmed and large arrays keep
    head/tail elements with a clear placeholder notice.
    If input is raw text, head and tail are preserved.
    """
    if result is None:
        return ""

    if not isinstance(result, str):
        try:
            return json.dumps(_compress_obj(result, max_str_len, max_list_items), ensure_ascii=False)
        except Exception:
            result = str(result)

    result_str = result.strip()
    if not result_str:
        return ""

    # Attempt JSON parsing first
    try:
        parsed = json.loads(result_str)
        compressed = _compress_obj(parsed, max_str_len, max_list_items)
        return json.dumps(compressed, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass

    # Non-JSON plain text fallback: keep head and tail if exceeds 2 * max_str_len
    if len(result_str) <= max_str_len * 2:
        return result_str

    truncated_count = len(result_str) - (max_str_len * 2)
    head = result_str[:max_str_len]
    tail = result_str[-max_str_len:]
    return f"{head}\n\n[... truncated {truncated_count} characters ...]\n\n{tail}"


def _compress_obj(obj: Any, max_str_len: int, max_list_items: int) -> Any:
    if isinstance(obj, str):
        if len(obj) > max_str_len:
            head = obj[: max_str_len // 2]
            tail = obj[-max_str_len // 2 :]
            omitted = len(obj) - max_str_len
            return f"{head} ... [truncated {omitted} chars] ... {tail}"
        return obj
    elif isinstance(obj, list):
        compressed_list = [_compress_obj(item, max_str_len, max_list_items) for item in obj]
        if len(compressed_list) > max_list_items:
            keep_head = max_list_items // 2
            keep_tail = max_list_items // 2
            omitted = len(compressed_list) - (keep_head + keep_tail)
            return (
                compressed_list[:keep_head]
                + [f"[... truncated {omitted} items ...]"]
                + compressed_list[-keep_tail:]
            )
        return compressed_list
    elif isinstance(obj, dict):
        return {
            str(k): _compress_obj(v, max_str_len, max_list_items)
            for k, v in obj.items()
        }
    else:
        return obj


class ContextCompressor:
    """Intelligent context compression for long-running conversations."""

    def __init__(
        self,
        threshold_percent: float = 0.8,
        protect_last_n: int = 6,
        protect_first_n: int = 3,
        min_history_for_compression: int = 12,
    ):
        self.threshold_percent = threshold_percent
        self.protect_last_n = protect_last_n
        self.protect_first_n = protect_first_n
        self.min_history_for_compression = min_history_for_compression

    def prune_tool_results_only(self, history: list[dict]) -> list[dict]:
        """Compress oversized tool results in history using structured JSON/text compression."""
        pruned = []
        for turn in history:
            if turn.get("role") == "tool" and "content" in turn:
                content = str(turn.get("content") or "")
                new_turn = dict(turn)
                new_turn["content"] = compress_tool_result(content)
                pruned.append(new_turn)
            else:
                pruned.append(turn)
        return pruned

    def should_compress(self, history: list[dict], max_history: int) -> bool:
        if len(history) < self.min_history_for_compression:
            return False
        return len(history) >= int(max_history * self.threshold_percent)

    def compress(self, history: list[dict], llm: Any, max_history: int) -> list[dict]:
        if not self.should_compress(history, max_history):
            return history
        if len(history) <= (self.protect_first_n + self.protect_last_n):
            return history

        head = history[: self.protect_first_n]
        middle = history[self.protect_first_n : -self.protect_last_n]
        tail = history[-self.protect_last_n :]

        summary_text = f"[System Summary: omitted {len(middle)} middle context turns]"
        summary_turn = {"role": "system", "content": summary_text}
        return head + [summary_turn] + tail

