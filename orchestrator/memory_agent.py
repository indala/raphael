"""
Memory Agent — Dedicated librarian and organizer.
Handles semantic context retrieval before main LLM execution,
background memory updates after responses, and idle-time consolidation.
"""

import json
import logging
import re
import time as _time
from datetime import datetime

from memory.memory_manager import load_memory, update_memory
from orchestrator.event_bus import MEMORY_UPDATED, EventBus
from orchestrator.event_payloads import MemoryUpdatedPayload

logger = logging.getLogger(__name__)

# ── JSON Repair Helper ──────────────────────────────────────────────
def _repair_json(text: str) -> str:
    """
    Attempt to repair common malformed JSON issues from LLM output.
    Handles:
    - Unescaped quotes inside string values
    - Single quotes instead of double quotes
    - Common typos in JSON structure
    Returns repaired JSON string.
    """
    # Remove leading/trailing whitespace
    text = text.strip()

    # Replace common problematic patterns
    # 1. Fix single quotes to double quotes (but preserve escaped quotes)
    text = re.sub(r"'([^']*)'", r'"\1"', text)

    # 2. Fix unescaped double quotes inside values (basic approach)
    # This regex tries to fix malformed JSON by escaping unescaped quotes
    # in values (between : and , or })
    text = re.sub(r':\s*"([^"]*)"([^"]*)"', r': "\1\2"', text)

    # 3. Remove trailing commas before closing braces/brackets
    text = re.sub(r',(\s*[}\]])', r'\1', text)

    # 4. Fix missing colons in key-value pairs
    text = re.sub(r'("([^"]+)")\s+("[^"]*")', r'\1: \3', text)

    # 5. Fix null/true/false capitalization issues (JSON standard is lowercase)
    text = re.sub(r'\bNULL\b', 'null', text, flags=re.IGNORECASE)
    text = re.sub(r'\bTRUE\b', 'true', text, flags=re.IGNORECASE)
    text = re.sub(r'\bFALSE\b', 'false', text, flags=re.IGNORECASE)

    return text


# ── Context cache ───────────────────────────────────────────────────
_context_cache: dict[str, tuple[str, float]] = {}
_CONTEXT_CACHE_TTL = 300.0  # seconds (5 min)

# ── Credential redaction ────────────────────────────────────────────
# Pattern from hermes-agent/agent/context_engine.py sanitize_memory_context().
# Applied to ALL memory before it enters the system prompt — prevents
# API keys, passwords, tokens stored in memory from leaking to LLM backends.
_REDACT_PATTERN = re.compile(
    r"""
    (?:
        # Key=value formats: api_key=sk-..., password: hunter2, token="abc"
        (?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|auth[_\-]?token
          |bearer[_\-]?token|private[_\-]?key|client[_\-]?secret
          |password|passwd|credentials?|api[_\-]?secret)
        \s*[=:]\s*
        (?P<val1>[^\s,;\"\']{6,})
    )
    |
    (?:
        # Standalone secrets: sk-..., ghp_..., xoxb-..., AIza..., AKIA...
        \b(?:sk|pk|rk|dk)-[A-Za-z0-9\-_]{16,}
        |\bghp_[A-Za-z0-9]{36,}
        |\bxoxb-[A-Za-z0-9\-]{40,}
        |\bAIza[A-Za-z0-9\-_]{35,}
        |\bAKIA[A-Z0-9]{16}
        |\beyJ[A-Za-z0-9_\-]{20,}\.eyJ[A-Za-z0-9_\-]{20,}  # JWT
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Cap on memory context injected into the system prompt
_MEMORY_CONTEXT_MAX_CHARS = 6_000
_MEMORY_CONTEXT_HEAD_CHARS = 4_000
_MEMORY_CONTEXT_TAIL_CHARS = 1_500
_MEMORY_CONTEXT_TRUNCATION_MARKER = "\n...[memory context truncated for length]...\n"


def sanitize_memory_context(text: str) -> str:
    """Scrub credentials from memory context before system prompt injection.

    Replaces detected secrets with ``[REDACTED]``. Also truncates text that
    exceeds _MEMORY_CONTEXT_MAX_CHARS to avoid bloating the context window.

    Pattern from hermes-agent/agent/context_engine.py sanitize_memory_context().
    """
    if not text:
        return text

    # Step 1: redact credentials
    def _replace(m: re.Match) -> str:
        full = m.group(0)
        val = m.group("val1")
        if val:
            return full.replace(val, "[REDACTED]")
        return "[REDACTED]"

    sanitized = _REDACT_PATTERN.sub(_replace, text)

    # Step 2: truncate if over max
    if len(sanitized) <= _MEMORY_CONTEXT_MAX_CHARS:
        return sanitized

    return (
        sanitized[:_MEMORY_CONTEXT_HEAD_CHARS]
        + _MEMORY_CONTEXT_TRUNCATION_MARKER
        + sanitized[-_MEMORY_CONTEXT_TAIL_CHARS:]
    )


def _invalidate_context_cache() -> None:
    """Clear the context cache (called when memory is written)."""
    _context_cache.clear()


def _keyword_match(query: str, text: str) -> bool:
    """Fast keyword overlap check — no LLM needed."""
    query_lower = query.lower()
    # Extract meaningful keywords (skip very short words)
    keywords = {w for w in query_lower.split() if len(w) > 3}
    if not keywords:
        return True  # short query = always relevant
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def get_relevant_context(user_query: str) -> str:
    """
    Read Phase: Memory retrieval using SQLite FTS5 search when available,
    falling back to keyword matching against the JSON store.
    
    SQLite path: uses FTS5 BM25 ranking for relevance.
    JSON path: keyword overlap matching (original behaviour).
    """
    # Fast path: cache hit within TTL
    cache_key = user_query.strip().lower()[:80]
    now = _time.monotonic()
    if cache_key in _context_cache:
        cached_result, cached_time = _context_cache[cache_key]
        if (now - cached_time) < _CONTEXT_CACHE_TTL:
            return cached_result

    # ── SQLite FTS5 path ─────────────────────────────────────────
    try:
        from memory.memory_manager import search_memory, load_memory

        memory = load_memory()
        user_mem = memory.get("user_memory", {})

        # 1. Always include core profile fields
        core_lines = []
        core_fields = ["name", "job", "motto", "city"]
        for field in core_fields:
            entry = user_mem.get(field)
            if entry:
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    core_lines.append(f"{field.title()}: {val}")

        # 2. FTS5 search for relevant entries
        search_results = search_memory(user_query, limit=15)
        match_lines = []
        seen_keys: set[str] = set(core_fields)
        for result in search_results:
            key = result["key"]
            if key in seen_keys:
                continue
            seen_keys.add(key)
            cat = result["category"]
            val = result["value"]
            if not val or val == "[redacted]":
                continue
            prefix = "" if cat == "user_memory" else f"[{cat}] "
            match_lines.append(f"{prefix}{key}: {val}")

        # 3. Combine
        lines = []
        if core_lines:
            lines.append("Core User Profile:")
            for line in core_lines:
                lines.append(f"  - {line}")
        if match_lines:
            if lines:
                lines.append("")
            lines.append("Relevant Context / Saved Details:")
            for line in match_lines:
                lines.append(f"  - {line}")

        if not lines:
            _context_cache[cache_key] = ("", now)
            return ""

        header = "[WHAT YOU KNOW ABOUT THE USER -- use naturally, never recite like a list]\n"
        result_text = header + "\n".join(lines) + "\n"
        result_text = sanitize_memory_context(result_text)
        _context_cache[cache_key] = (result_text, now)
        return result_text

    except Exception as e:
        logger.debug("FTS context retrieval failed: %s — falling back to keyword", e)

    # ── Keyword fallback ─────────────────────────────────────────
    return _get_relevant_context_keyword(user_query, cache_key, now)


def _get_relevant_context_keyword(user_query: str, cache_key: str, now: float) -> str:
    """Original keyword-based context retrieval (fallback)."""
    from memory.memory_manager import load_memory
    memory = load_memory()
    if not memory:
        _context_cache[cache_key] = ("", now)
        return ""

    # 1. Core Profile (always include)
    user_mem = memory.get("user_memory", {})
    core_lines = []
    core_fields = ["name", "job", "motto", "city"]
    for field in core_fields:
        entry = user_mem.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                core_lines.append(f"{field.title()}: {val}")

    # 2. Keyword-match against all memory categories
    match_lines = []
    for cat, items in memory.items():
        if cat == "user_memory":
            # Check extra profile fields beyond core
            for k, v in items.items():
                if k not in core_fields:
                    val = v.get("value") if isinstance(v, dict) else v
                    if val and isinstance(val, str) and (_keyword_match(user_query, val) or _keyword_match(user_query, k)):
                        match_lines.append(f"{k}: {val}")
        elif isinstance(items, dict):
            for k, v in items.items():
                val = v.get("value") if isinstance(v, dict) else v
                if isinstance(val, str) and (_keyword_match(user_query, val) or _keyword_match(user_query, k)):
                    match_lines.append(f"[{cat}] {k}: {val}")
                elif isinstance(val, (list, dict)):
                    text = json.dumps(val)
                    if _keyword_match(user_query, text) or _keyword_match(user_query, k):
                        match_lines.append(f"[{cat}] {k}: {json.dumps(val, ensure_ascii=False)[:200]}")

    # 3. Combine
    lines = []
    if core_lines:
        lines.append("Core User Profile:")
        for line in core_lines:
            lines.append(f"  - {line}")

    if match_lines:
        if lines:
            lines.append("")
        lines.append("Relevant Context / Saved Details:")
        for line in match_lines:
            lines.append(f"  - {line}")

    if not lines:
        _context_cache[cache_key] = ("", now)
        return ""

    header = "[WHAT YOU KNOW ABOUT THE USER -- use naturally, never recite like a list]\n"
    result = header + "\n".join(lines) + "\n"
    result = sanitize_memory_context(result)
    _context_cache[cache_key] = (result, now)
    return result


def run_memory_agent(user_text: str, assistant_text: str) -> None:
    """
    Write Phase: Background organizer that extracts new facts, preferences,
    or tasks from the latest turn and structures/persists them.
    """
    if not user_text or not assistant_text:
        return

    try:
        from orchestrator.core import LLMClient
        client = LLMClient()

        system_prompt = (
            "You are Raphael's Memory Organizer. Your job is to extract user facts, preferences, "
            "tasks, or settings from the latest conversation turn, and organize them.\n\n"
            f"Today's date is {datetime.now().strftime('%Y-%m-%d')}.\n\n"
            "Look for details belonging to these categories:\n"
            "- user_memory: name, job, motto, city, bio, preferences, relationships, wishes, plans, wants, general notes, etc.\n"
            "- daily_task_memory: active tasks, startup routines, deadlines, todo list items, etc.\n"
            "- feature_memory: settings, custom triggers, tool configurations, speaker/TTS rate preferences, visual settings, etc.\n\n"
            "Analyze this turn:\n"
            f"User: {user_text}\n"
            f"Assistant: {assistant_text}\n\n"
            "Instructions:\n"
            "1. Output a JSON object mapping category -> key -> value. Example:\n"
            f"   {{\n"
            f"     \"user_memory\": {{\"favorite_color\": \"blue\"}},\n"
            f"     \"daily_task_memory\": {{\"finish_bridge\": \"due by Friday\"}},\n"
            f"     \"chat_memory\": {{\"{datetime.now().strftime('%Y-%m-%d')}\": \"Discussed portfolio analytics and stock market\"}}\n"
            f"   }}\n"
            f"2. Also extract a brief summary of the current conversation turn into `chat_memory` "
            f"under today's date ({datetime.now().strftime('%Y-%m-%d')}) as key.\n"
            "3. If the user explicitly asked to forget a fact, task, or setting, set the value of that key to null (e.g. \"favorite_color\": null).\n"
            "4. If no new facts or changes were shared, output ONLY a chat_memory entry for the current turn.\n"
            "5. IMPORTANT: Output ONLY valid JSON. Do not include markdown code blocks, intro, or explanation."
        )

        messages = [{"role": "system", "content": system_prompt}]
        resp = client.chat(messages, None, reason="memory_organizer")
        if resp and resp.content:  # type: ignore[union-attr]
            text = resp.content.strip()  # type: ignore[union-attr]
            if text.startswith("[Error calling LLM") or text.startswith("💳 ") or text.startswith("❌ "):
                logger.error("Memory Organizer background thread failed: %s", text)
                return
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            if text:
                try:
                    updates = json.loads(text)
                except json.JSONDecodeError as json_err:
                    # JSON parsing failed — attempt to repair common issues
                    logger.warning("Memory Organizer JSON parse failed (%s) — attempting repair", json_err)
                    # Try basic repairs: fix common quote issues
                    repaired = _repair_json(text)
                    try:
                        updates = json.loads(repaired)
                    except json.JSONDecodeError as repair_err:
                        logger.error(
                            "Memory Organizer JSON repair failed: original=%s, repaired=%s",
                            json_err, repair_err
                        )
                        return

                if isinstance(updates, dict) and updates:
                    update_memory(updates)
                    EventBus().publish_typed(
                        MEMORY_UPDATED,
                        MemoryUpdatedPayload(source="organizer", updates=list(updates.keys())),
                    )
                    logger.info("Memory Organizer successfully saved background updates: %s", list(updates.keys()))
                    # Signal that memory needs consolidation (throttled to once per 5 min)
                    from controller.state import state
                    now = datetime.now()
                    last = getattr(state, '_last_consolidation_hint', None)
                    if last is None or (now - last).total_seconds() > 300:
                        state.memory_needs_consolidation = True
                        state._last_consolidation_hint = now  # type: ignore[attr-defined]
    except Exception as e:
        logger.error("Memory Organizer background thread failed: %s", e)


def consolidate_memory(history: list[dict]) -> None:
    """
    Idle Consolidation Phase: Reviews current memory database and the recent conversation history
    to organize all categories, structure tool/feature preferences, merge/reorganize chat logs,
    and remove duplicate or obsolete entries.
    """
    memory = load_memory()
    if not memory:
        return

    # Extract history text
    history_lines = []
    for turn in history:
        role = turn.get("role", "user")
        content = turn.get("content", "")
        if content and content != "(interrupted)":
            history_lines.append(f"{role.title()}: {content}")
    history_text = "\n".join(history_lines)

    try:
        from orchestrator.core import LLMClient
        client = LLMClient()

        system_prompt = (
            "You are Raphael's Memory Consolidation Agent—a highly organized personal assistant.\n"
            f"Today's date is {datetime.now().strftime('%Y-%m-%d')}.\n"
            "Your job is to review the current memory database and the conversation history of the recent session. "
            "You must optimize, clean, and reorganize the database according to these rules:\n\n"
            "1. Categories structure:\n"
            "   - `user_memory`: general facts, profile, preferences, wishes, relationships.\n"
            "   - `daily_task_memory`: active tasks, startup routines, deadlines, todo lists.\n"
            "   - `chat_memory`: chronological highlights and summaries of recent and past sessions.\n"
            "   - `feature_memory`: structured preferences, default apps, custom triggers/states, or settings for tools.\n\n"
            "2. Tasks:\n"
            "   - Review the recent session history: if the user completed any tasks in `daily_task_memory`, remove them.\n"
            "   - Summarize the key takeaways and topics discussed in this recent session and append them to `chat_memory` chronologically. Merge with or clean up old/outdated summaries in `chat_memory` to avoid redundant logs.\n"
            "   - Reorganize and clean up `user_memory` and `feature_memory` to make them clean, structured, and free of duplicates or contradictions.\n"
            "   - Format all values as clean, concise descriptions.\n\n"
            "Here is the current memory database:\n"
            f"{json.dumps(memory, indent=2)}\n\n"
            "Here is the recent session's conversation history:\n"
            f"{history_text}\n\n"
            "Instructions:\n"
            "1. Output the FULL updated and consolidated memory database in JSON format. It must have the 4 keys: user_memory, daily_task_memory, chat_memory, feature_memory.\n"
            "2. Preserve any existing memory fields that are still valid and were not contradicted/completed.\n"
            "3. IMPORTANT: Output ONLY the valid JSON object. Do not include markdown code blocks, intro, or explanation."
        )

        messages = [{"role": "system", "content": system_prompt}]
        resp = client.chat(messages, None, reason="memory_organizer")
        if resp and resp.content:  # type: ignore[union-attr]
            text = resp.content.strip()  # type: ignore[union-attr]
            if text.startswith("[Error calling LLM") or text.startswith("💳 ") or text.startswith("❌ "):
                logger.error("Memory consolidation failed: %s", text)
                return
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            if text:
                try:
                    consolidated = json.loads(text)
                except json.JSONDecodeError as json_err:
                    # JSON parsing failed — attempt to repair common issues
                    logger.warning("Memory consolidation JSON parse failed (%s) — attempting repair", json_err)
                    # Try basic repairs: fix common quote issues
                    repaired = _repair_json(text)
                    try:
                        consolidated = json.loads(repaired)
                    except json.JSONDecodeError as repair_err:
                        logger.error(
                            "Memory consolidation JSON repair failed: original=%s, repaired=%s",
                            json_err, repair_err
                        )
                        return

                if isinstance(consolidated, dict) and all(k in consolidated for k in ["user_memory", "daily_task_memory", "chat_memory", "feature_memory"]):
                    from memory.memory_manager import save_memory
                    save_memory(consolidated)
                    logger.info("Memory consolidation completed and saved successfully.")
    except Exception as e:
        logger.error("Memory consolidation failed: %s", e)
