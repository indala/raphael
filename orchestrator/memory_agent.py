"""
Memory Agent — Dedicated librarian and organizer.
Handles semantic context retrieval before main LLM execution,
background memory updates after responses, and idle-time consolidation.
"""

import json
import logging
import time as _time
from datetime import datetime

from memory.memory_manager import load_memory, update_memory
from orchestrator.event_bus import MEMORY_UPDATED, EventBus

logger = logging.getLogger(__name__)

# ── Context cache ───────────────────────────────────────────────────
_context_cache: dict[str, tuple[str, float]] = {}
_CONTEXT_CACHE_TTL = 300.0  # seconds (5 min, was 30s)


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
    Read Phase: Fast keyword-based memory retrieval.
    No LLM calls — pure text matching against the memory database.
    """
    # Fast path: cache hit for a similar query within TTL
    cache_key = user_query.strip().lower()[:80]
    now = _time.monotonic()
    if cache_key in _context_cache:
        cached_result, cached_time = _context_cache[cache_key]
        if (now - cached_time) < _CONTEXT_CACHE_TTL:
            return cached_result

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
            if text.startswith("[Error calling LLM"):
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
                updates = json.loads(text)
                if isinstance(updates, dict) and updates:
                    update_memory(updates)
                    EventBus().publish(MEMORY_UPDATED, source="organizer", updates=list(updates.keys()))
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
            if text.startswith("[Error calling LLM"):
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
                consolidated = json.loads(text)
                if isinstance(consolidated, dict) and all(k in consolidated for k in ["user_memory", "daily_task_memory", "chat_memory", "feature_memory"]):
                    from memory.memory_manager import save_memory
                    save_memory(consolidated)
                    logger.info("Memory consolidation completed and saved successfully.")
    except Exception as e:
        logger.error("Memory consolidation failed: %s", e)
