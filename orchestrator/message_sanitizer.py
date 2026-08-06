"""
Message Sanitizer — pre-flight history guard before every LLM API call.

Pattern from hermes-agent/agent/message_sanitization.py.

Problems it fixes:
  1. close_interrupted_tool_sequence()
     An assistant message with tool_calls but no matching tool result
     messages causes a hard 400 on OpenAI/Anthropic APIs. This happens
     when a turn is interrupted (user cancels) mid-tool-execution.
     Fix: append a synthetic tool result for every dangling call.

  2. strip_orphaned_tool_results()
     A tool result message with a tool_call_id that has no matching
     assistant tool_calls message above it causes a 400.
     Fix: remove the orphaned tool result from history.

  3. repair_empty_assistant_turns()
     An assistant message with role="assistant" and content=None and
     no tool_calls is rejected by strict providers (DeepSeek, Mistral).
     Fix: replace content with a single space to satisfy the schema.

  4. enforce_alternating_roles()
     Two consecutive user messages (or two consecutive assistant messages)
     confuse some providers. Fix: merge consecutive same-role messages.

All functions operate on a COPY — the original list is never mutated.
sanitize_history() is the single entry point: runs all 4 passes in order.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def close_interrupted_tool_sequence(messages: list[dict]) -> list[dict]:
    """Append synthetic tool results for any dangling tool_calls.

    If an assistant message has tool_calls but one or more of those call IDs
    has no matching ``role=tool`` message immediately following, inject a
    synthetic result so the API never sees an unclosed tool sequence.

    Returns a new list; the input is not mutated.
    """
    result: list[dict] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        result.append(msg)

        if msg.get("role") != "assistant":
            i += 1
            continue

        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            i += 1
            continue

        # Collect the call IDs declared in this assistant message
        declared_ids: set[str] = set()
        for tc in tool_calls:
            if isinstance(tc, dict):
                tc_id = tc.get("id") or ""
                if tc_id:
                    declared_ids.add(tc_id)

        if not declared_ids:
            i += 1
            continue

        # Collect which IDs are answered by immediately-following tool messages
        answered_ids: set[str] = set()
        j = i + 1
        while j < len(messages) and messages[j].get("role") == "tool":
            tc_id = messages[j].get("tool_call_id") or ""
            if tc_id:
                answered_ids.add(tc_id)
            j += 1

        # Inject synthetic results for any unanswered calls
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            tc_id = tc.get("id") or ""
            func_name = (tc.get("function") or {}).get("name") or "unknown_tool"
            if tc_id and tc_id not in answered_ids:
                result.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": f"[Tool '{func_name}' was interrupted and did not complete.]",
                })
                logger.debug(
                    "sanitizer: injected synthetic result for dangling tool_call_id=%s (%s)",
                    tc_id, func_name,
                )

        i += 1

    return result


def strip_orphaned_tool_results(messages: list[dict]) -> list[dict]:
    """Remove tool result messages whose tool_call_id has no matching assistant call.

    An orphaned tool result (e.g. from a previous session that was partially
    replayed) causes a 400 on strict providers.

    Returns a new list; the input is not mutated.
    """
    # First pass: collect all tool_call IDs declared by assistant messages
    declared_ids: set[str] = set()
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in (msg.get("tool_calls") or []):
                if isinstance(tc, dict):
                    tc_id = tc.get("id") or ""
                    if tc_id:
                        declared_ids.add(tc_id)

    # Second pass: filter out tool results with no matching declaration
    result: list[dict] = []
    for msg in messages:
        if msg.get("role") == "tool":
            tc_id = msg.get("tool_call_id") or ""
            if tc_id and tc_id not in declared_ids:
                logger.debug(
                    "sanitizer: stripped orphaned tool result (tool_call_id=%s)", tc_id
                )
                continue  # drop it
        result.append(msg)

    return result


def repair_empty_assistant_turns(messages: list[dict]) -> list[dict]:
    """Replace assistant messages with null/empty content and no tool_calls.

    Strict providers (DeepSeek, Mistral) reject ``{"role": "assistant",
    "content": null}`` with a schema validation error. Replace with a
    single-space placeholder to satisfy the content requirement.

    Returns a new list; the input is not mutated.
    """
    result: list[dict] = []
    for msg in messages:
        if msg.get("role") == "assistant":
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            has_content = bool(content) if content is not None else False
            has_tool_calls = bool(tool_calls)

            if not has_content and not has_tool_calls:
                # Clone and patch content
                patched = {**msg, "content": " "}
                logger.debug("sanitizer: repaired empty assistant turn")
                result.append(patched)
                continue

        result.append(msg)

    return result


def enforce_alternating_roles(messages: list[dict]) -> list[dict]:
    """Merge consecutive same-role messages into one.

    Some providers error on two consecutive user messages or two consecutive
    assistant messages. Merges them by concatenating their content with a
    newline separator.

    System messages and tool messages are never merged.
    Returns a new list; the input is not mutated.
    """
    if not messages:
        return messages

    MERGEABLE = {"user", "assistant"}
    result: list[dict] = []

    for msg in messages:
        role = msg.get("role")
        if (
            result
            and role in MERGEABLE
            and result[-1].get("role") == role
            and not result[-1].get("tool_calls")
            and not msg.get("tool_calls")
        ):
            # Merge: append content to previous message
            prev = result[-1]
            prev_content = prev.get("content") or ""
            curr_content = msg.get("content") or ""
            merged = {**prev, "content": f"{prev_content}\n{curr_content}".strip()}
            result[-1] = merged
            logger.debug("sanitizer: merged consecutive %s messages", role)
        else:
            result.append(msg)

    return result


def sanitize_history(messages: list[dict]) -> list[dict]:
    """Run all sanitization passes on a message list.

    Passes (in order):
      1. close_interrupted_tool_sequence  — inject synthetic tool results
      2. strip_orphaned_tool_results      — remove dangling tool results
      3. repair_empty_assistant_turns     — patch null-content assistant msgs
      4. enforce_alternating_roles        — merge consecutive same-role msgs

    Returns a new list. The input is never mutated.
    Fails silently per-pass — a broken sanitizer never prevents the LLM call.
    """
    sanitized = list(messages)

    passes = [
        ("close_interrupted_tool_sequence", close_interrupted_tool_sequence),
        ("strip_orphaned_tool_results",     strip_orphaned_tool_results),
        ("repair_empty_assistant_turns",    repair_empty_assistant_turns),
        ("enforce_alternating_roles",       enforce_alternating_roles),
    ]

    for name, fn in passes:
        try:
            sanitized = fn(sanitized)
        except Exception as e:
            logger.warning("sanitizer pass '%s' failed (skipped): %s", name, e)

    return sanitized
