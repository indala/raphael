"""
Background Self-Improvement Reviewer — learns from every turn automatically.

Pattern from hermes-agent/agent/background_review.py.

After every conversation turn, spawns a silent daemon thread that re-reads
the last exchange and asks two focused questions:
  1. Did the user reveal something worth remembering? (memory)
  2. Did the user correct Raphael's behavior? (behavioral rule)

Unlike the broad memory organizer (which extracts facts for long-term memory),
the reviewer specifically hunts for BEHAVIORAL SIGNALS — corrections, style
preferences, workflow adjustments — and writes them to agent_evolution.json
via the existing process_correction() / record_interaction() pipeline.

Key design decisions (from hermes-agent's production experience):
  - Runs on a separate daemon thread — NEVER blocks the main response path
  - Tool-whitelist limited to memory writes only (no browsing, no commands)
  - Uses a CHEAP/FAST model when available (configured via REVIEWER_MODEL)
  - Silently skips trivial turns (greetings, single words, tool-only turns)
  - Surfaces a one-line summary in the UI log only when something was saved
  - Persistence-isolated: never touches conversation history or task state

Configuration (settings.toml [general]):
  background_reviewer_enabled = true    # on by default
  background_reviewer_model   = ""      # empty = use same model as main LLM
  background_reviewer_min_turn_chars = 60  # skip very short turns
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

# ── Skip heuristics ──────────────────────────────────────────────────────────
# Turn pairs below MIN_CHARS are skipped (greetings, acks, single commands)
_MIN_TURN_CHARS = 60

# Keywords that signal a behavioral correction in the user message
_CORRECTION_SIGNALS = re.compile(
    r"\b(wrong|incorrect|mistake|error|stop|don'?t|shouldn'?t|never|always|"
    r"why did you|you said|that'?s not|please don'?t|actually|"
    r"remember to|from now on|in the future|next time|instead)\b",
    re.IGNORECASE,
)

# Keywords in assistant response that signal the assistant acknowledged a correction
_APOLOGY_SIGNALS = re.compile(
    r"\b(apologize|apologies|sorry|my mistake|my bad|you'?re right|"
    r"i see|got it|understood|noted|i'?ll remember|i'?ll keep that)\b",
    re.IGNORECASE,
)

# ── Review prompt ─────────────────────────────────────────────────────────────
_REVIEW_PROMPT = (
    "Review this conversation exchange and determine if Raphael should learn anything.\n\n"
    "Focus on TWO things only:\n"
    "1. BEHAVIORAL CORRECTION — Did the user correct how Raphael responded, "
    "its style, format, approach, or workflow? Examples: 'stop using bullet points', "
    "'don\\'t open the browser for simple questions', 'always confirm before deleting'.\n"
    "2. USER FACT — Did the user reveal a durable personal fact, preference, or goal "
    "that should be remembered across sessions?\n\n"
    "Exchange:\n"
    "User: {user_text}\n"
    "Raphael: {assistant_text}\n\n"
    "Output a JSON object with this exact structure:\n"
    "{{\n"
    '  "behavioral_correction": {{\n'
    '    "found": true/false,\n'
    '    "rule": "<specific behavioral instruction, empty if not found>",\n'
    '    "condition": "<when this applies, empty if not found>"\n'
    "  }},\n"
    '  "user_fact": {{\n'
    '    "found": true/false,\n'
    '    "key": "<memory key, empty if not found>",\n'
    '    "value": "<memory value, empty if not found>",\n'
    '    "category": "<user_memory|feature_memory|daily_task_memory>"\n'
    "  }}\n"
    "}}\n\n"
    "IMPORTANT: Only output the JSON. No explanation. "
    "If nothing was learned, set both found fields to false.\n"
    "Do NOT invent corrections that weren\\'t clearly expressed by the user."
)


def _should_review(user_text: str, assistant_text: str) -> bool:
    """Quick pre-filter: skip trivial turns to avoid wasting LLM calls."""
    # Too short to contain meaningful signal
    combined = (user_text or "") + (assistant_text or "")
    if len(combined) < _MIN_TURN_CHARS:
        return False

    # Looks like a correction OR the assistant acknowledged one
    has_correction_signal = bool(_CORRECTION_SIGNALS.search(user_text or ""))
    has_apology_signal    = bool(_APOLOGY_SIGNALS.search(assistant_text or ""))

    # Always review when correction signals present
    if has_correction_signal or has_apology_signal:
        return True

    # Also review longer turns (>200 chars) where facts might be revealed
    return len(combined) > 200


def _get_reviewer_llm():
    """Get the LLM client for the review pass — prefer cheap model if configured."""
    import config
    reviewer_model = getattr(config, "BACKGROUND_REVIEWER_MODEL", "").strip()

    from orchestrator.core import LLMClient
    if reviewer_model:
        # Try to split "backend/model" shorthand
        if "/" in reviewer_model:
            backend, _, model = reviewer_model.partition("/")
            return LLMClient(backend=backend.strip(), model=model.strip())
        # Just a model name — use current backend
        return LLMClient(model=reviewer_model)

    return LLMClient()


def _run_review(
    user_text: str,
    assistant_text: str,
    on_learned: Callable[[str], None] | None = None,
) -> None:
    """Worker executed in the daemon thread.

    Calls the LLM with a focused prompt, parses the result, and writes any
    findings to the appropriate memory store. Calls on_learned(summary) if
    something was saved, for UI notification.
    """
    try:
        prompt = _REVIEW_PROMPT.format(
            user_text=user_text[:600],
            assistant_text=assistant_text[:600],
        )
        messages = [{"role": "user", "content": prompt}]

        client = _get_reviewer_llm()
        resp = client.chat(messages, tools=None, reason="background_review")

        if not resp or not resp.content:
            return

        text = resp.content.strip()

        # Strip markdown fences
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        if not text or text.startswith("{") is False:
            return

        result = json.loads(text)
        learned_items: list[str] = []

        # ── Process behavioral correction ──────────────────────────────
        correction = result.get("behavioral_correction", {})
        if isinstance(correction, dict) and correction.get("found"):
            rule      = (correction.get("rule", "") or "").strip()
            condition = (correction.get("condition", "") or "").strip()
            if rule:
                try:
                    from memory.agent_memory import process_correction
                    process_correction("raphael", condition or user_text[:200], rule)
                    learned_items.append(f"behavior: {rule[:80]}")
                    logger.info("Background reviewer saved behavioral rule: %s", rule[:80])
                except Exception as e:
                    logger.debug("Reviewer: failed to save correction: %s", e)

        # ── Process user fact ──────────────────────────────────────────
        user_fact = result.get("user_fact", {})
        if isinstance(user_fact, dict) and user_fact.get("found"):
            key      = (user_fact.get("key", "") or "").strip()
            value    = (user_fact.get("value", "") or "").strip()
            category = (user_fact.get("category", "user_memory") or "user_memory").strip()
            if key and value:
                valid_cats = {"user_memory", "feature_memory", "daily_task_memory"}
                if category not in valid_cats:
                    category = "user_memory"
                try:
                    from memory.memory_manager import update_memory
                    update_memory({category: {key: {"value": value}}})
                    learned_items.append(f"memory: {key}={value[:60]}")
                    logger.info("Background reviewer saved fact: %s/%s", category, key)
                except Exception as e:
                    logger.debug("Reviewer: failed to save fact: %s", e)

        # ── Notify UI if something was learned ─────────────────────────
        if learned_items and on_learned:
            summary = " · ".join(learned_items)
            try:
                on_learned(f"💾 Learned: {summary}")
            except Exception:
                pass

    except json.JSONDecodeError:
        logger.debug("Background reviewer: LLM returned non-JSON output")
    except Exception as e:
        logger.debug("Background reviewer failed: %s", e)


def spawn_background_review(
    user_text: str,
    assistant_text: str,
    on_learned: Callable[[str], None] | None = None,
) -> threading.Thread | None:
    """Spawn a daemon thread to review the last turn for learning opportunities.

    Args:
        user_text:      The user's message from this turn.
        assistant_text: Raphael's response from this turn.
        on_learned:     Optional callback called with a summary string when
                        something is saved. Use to show a UI notification.

    Returns:
        The spawned thread, or None if review was skipped.
    """
    import config
    if not getattr(config, "BACKGROUND_REVIEWER_ENABLED", True):
        return None

    if not _should_review(user_text, assistant_text):
        logger.debug("Background reviewer: skipped (turn too short or no signal)")
        return None

    t = threading.Thread(
        target=_run_review,
        args=(user_text, assistant_text, on_learned),
        daemon=True,
        name="bg_reviewer",
    )
    t.start()
    logger.debug("Background reviewer: spawned for turn")
    return t
