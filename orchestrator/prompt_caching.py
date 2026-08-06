"""
Prompt Caching — Anthropic cache_control breakpoint injection.

Pattern from hermes-agent/agent/prompt_caching.py.

Anthropic supports prompt caching via ``cache_control: {"type": "ephemeral"}``
breakpoints in the messages list. When a breakpoint is set, Anthropic caches
all content UP TO that point in their infrastructure. On subsequent requests
with the same prefix, cached tokens cost ~10% of normal input token price,
reducing cost by up to 90% on long sessions.

Where breakpoints are placed:
  1. The system message (always, if present) — highest-value cache point since
     Raphael's system prompt is large and constant across turns.
  2. After the oldest N tool-result messages when the history is long — caches
     the "completed work" portion of a long agentic task.

Rules enforced:
  - Only injected when backend base_url contains "anthropic.com" OR the model
    name starts with "claude" AND the ANTHROPIC_PROMPT_CACHE flag is enabled.
  - Cache breakpoints are added to message content list-form; string content
    is promoted to list-form first so the structure is always valid.
  - Breakpoints on the last 3 messages are skipped (volatile tail).
  - At most MAX_BREAKPOINTS breakpoints per request.
  - strip_cache_control() removes all breakpoints (used before fallback to
    non-Anthropic backends to avoid sending unknown fields).

Opt-in: set ANTHROPIC_PROMPT_CACHE = true in settings.toml [general] section
or as an environment variable.
"""

from __future__ import annotations

import copy
import logging
import re

logger = logging.getLogger(__name__)

# Maximum cache breakpoints per request (Anthropic limit is 4)
MAX_BREAKPOINTS = 4

# Protect the last N messages from receiving a breakpoint (they change each turn)
PROTECT_TAIL = 3

# Minimum number of messages before caching is worth doing
MIN_MESSAGES_FOR_CACHING = 6

# Anthropic host patterns
_ANTHROPIC_HOST_RE = re.compile(r"anthropic\.com", re.IGNORECASE)
_CLAUDE_MODEL_RE   = re.compile(r"^claude", re.IGNORECASE)


# ── Eligibility ──────────────────────────────────────────────────────────────

def is_anthropic_backend(base_url: str, model: str) -> bool:
    """Return True if this request targets an Anthropic-compatible endpoint."""
    return bool(
        _ANTHROPIC_HOST_RE.search(base_url or "")
        or _CLAUDE_MODEL_RE.match(model or "")
    )


def cache_enabled() -> bool:
    """Return True if prompt caching is enabled via config."""
    try:
        import config
        return bool(getattr(config, "ANTHROPIC_PROMPT_CACHE", False))
    except Exception:
        return False


# ── Content helpers ───────────────────────────────────────────────────────────

def _to_content_list(content) -> list[dict]:
    """Promote string content to the list-of-blocks form Anthropic uses."""
    if content is None:
        return [{"type": "text", "text": ""}]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if isinstance(content, list):
        return list(content)
    return [{"type": "text", "text": str(content)}]


def _add_breakpoint(block: dict) -> dict:
    """Clone a content block and add cache_control to it."""
    b = dict(block)
    b["cache_control"] = {"type": "ephemeral"}
    return b


def _mark_message_cached(msg: dict) -> dict:
    """Clone a message, promoting its last content block to have cache_control."""
    m = dict(msg)
    blocks = _to_content_list(m.get("content"))
    if blocks:
        # Attach cache_control to the LAST block of this message
        new_blocks = list(blocks[:-1]) + [_add_breakpoint(blocks[-1])]
        m["content"] = new_blocks
    return m


def _has_breakpoint(msg: dict) -> bool:
    """Return True if a message already has a cache_control breakpoint."""
    content = msg.get("content")
    if not isinstance(content, list):
        return False
    for block in content:
        if isinstance(block, dict) and "cache_control" in block:
            return True
    return False


# ── Strip helpers (for non-Anthropic backends) ────────────────────────────────

def strip_cache_control(messages: list[dict]) -> list[dict]:
    """Remove all cache_control fields from messages.

    Called before sending to non-Anthropic backends (OpenAI, Ollama, etc.)
    to avoid sending unknown fields that cause validation errors.

    Returns a new list; the input is not mutated.
    """
    result = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            stripped_blocks = []
            for block in content:
                if isinstance(block, dict) and "cache_control" in block:
                    b = {k: v for k, v in block.items() if k != "cache_control"}
                    # Collapse single-text blocks back to a plain string
                    # only if it's the sole block (preserves multi-block structure)
                    stripped_blocks.append(b)
                else:
                    stripped_blocks.append(block)
            # Simplify: if the list is a single {"type":"text","text":"..."} block,
            # collapse back to a plain string for maximum provider compatibility
            if (
                len(stripped_blocks) == 1
                and isinstance(stripped_blocks[0], dict)
                and stripped_blocks[0].get("type") == "text"
                and set(stripped_blocks[0].keys()) == {"type", "text"}
            ):
                result.append({**msg, "content": stripped_blocks[0]["text"]})
            else:
                result.append({**msg, "content": stripped_blocks})
        else:
            result.append(msg)
    return result


# ── Main entry point ──────────────────────────────────────────────────────────

def build_prompt_cache_plan(
    messages: list[dict],
    base_url: str = "",
    model: str = "",
) -> list[dict]:
    """Inject cache_control breakpoints into messages for Anthropic caching.

    Strategy:
      1. System message — always the first breakpoint. Raphael's system prompt
         is large (~4k chars) and constant, making it the highest-value cache.
      2. Stable history tail boundary — place a breakpoint at
         ``len(messages) - PROTECT_TAIL - 1`` to cache completed work in long
         agentic tasks without touching the volatile recent turns.
      3. Never exceed MAX_BREAKPOINTS total.

    Returns a new messages list with breakpoints injected.
    If caching is disabled, not an Anthropic backend, or the history is too
    short, returns the original list unchanged (no copy overhead).
    """
    # Guard: only inject for Anthropic-compatible backends
    if not cache_enabled():
        return messages
    if not is_anthropic_backend(base_url, model):
        return messages
    if len(messages) < MIN_MESSAGES_FOR_CACHING:
        return messages

    result = list(messages)  # shallow copy — we replace specific items
    breakpoints_placed = 0

    # ── Breakpoint 1: system message ─────────────────────────────────────────
    if result and result[0].get("role") == "system" and not _has_breakpoint(result[0]):
        result[0] = _mark_message_cached(result[0])
        breakpoints_placed += 1
        logger.debug("prompt_cache: breakpoint on system message")

    # ── Breakpoint 2: stable history boundary ────────────────────────────────
    if breakpoints_placed < MAX_BREAKPOINTS:
        # Target: the message just before the protected tail
        boundary_idx = len(result) - PROTECT_TAIL - 1
        if boundary_idx > 0 and not _has_breakpoint(result[boundary_idx]):
            msg = result[boundary_idx]
            role = msg.get("role")
            # Only cache on user or tool messages (stable content)
            if role in ("user", "tool", "assistant") and msg.get("content"):
                result[boundary_idx] = _mark_message_cached(msg)
                breakpoints_placed += 1
                logger.debug(
                    "prompt_cache: breakpoint at history boundary idx=%d (role=%s)",
                    boundary_idx, role,
                )

    if breakpoints_placed:
        logger.debug("prompt_cache: %d breakpoint(s) placed for %s", breakpoints_placed, model)

    return result
