"""
Persistent long-term memory for Raphael.

**Storage Backend: SQLite + FTS5** (as of task #3 enhancement)
  - Unlimited memory size (no 2200-char cap)
  - Full-text search via SQLite FTS5 built-in
  - Thread-safe, WAL mode for concurrent access
  - Auto-migration from legacy JSON on first use

**Backward Compatibility**
  - All existing callers continue to work unchanged
  - load_memory() / save_memory() preserved
  - format_memory_for_prompt() unchanged

**New Capabilities**
  - search_memory(query) — semantic keyword search
  - No memory size limit (was 2200 chars total)
  - Thread-safe concurrent access

Stores categorized information in 6 categories:
  - user_memory: identity, preferences, profile
  - daily_task_memory: tasks, routines, deadlines
  - chat_memory: conversation highlights
  - feature_memory: tool settings, preferences
  - capability_memory: why tools exist, impact
  - planning_memory: successful execution plans
"""

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

import config

# ── Storage backend selection ────────────────────────────────────────────────
# SQLite is the default. JSON fallback is kept for environments where SQLite
# fails to initialize (rare, but possible in restricted environments).

_USE_SQLITE = True  # Set to False to force JSON fallback

try:
    from memory.sqlite_store import get_store as _get_sqlite_store
    _store = _get_sqlite_store()
    logger.info("Memory backend: SQLite + FTS5")
except Exception as e:
    logger.warning("SQLite backend unavailable (%s) — falling back to JSON", e)
    _USE_SQLITE = False
    _store = None


# ── Legacy JSON path (kept as fallback) ──────────────────────────────────────
MEMORY_PATH = config.ROAMING_DIR / "memory" / "long_term.json"


from threading import Lock

# --- Legacy JSON limits (only used when SQLite unavailable) ---
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200

# --- Read cache (used by JSON fallback path) ---
_cached_memory: dict | None = None
_cached_memory_time: float = 0.0
MEMORY_CACHE_TTL: float = 5.0  # seconds
_lock = Lock()


def _empty_memory() -> dict:
    """Return a skeleton with all six categories."""
    return {
        "user_memory":        {},
        "daily_task_memory":  {},
        "chat_memory":        {},
        "feature_memory":     {},
        "capability_memory":  {},
        "planning_memory":    {},
    }


def load_memory() -> dict:
    """Load memory from the active backend (SQLite or JSON fallback).
    
    Returns a nested dict matching the legacy format:
        {category: {key: {value: str, updated: str}}}
    """
    if _USE_SQLITE and _store is not None:
        try:
            return _store.load_all()
        except Exception as e:
            logger.error("SQLite load failed: %s — falling back to JSON", e)
    return _load_memory_json()


def save_memory(memory: dict) -> None:
    """Save memory to the active backend.
    
    Accepts a nested dict of the form:
        {category: {key: {value: str, updated: str}}} 
    and persists it. Used for bulk replacement (consolidation).
    """
    if _USE_SQLITE and _store is not None:
        try:
            _save_memory_sqlite(memory)
            return
        except Exception as e:
            logger.error("SQLite save failed: %s — falling back to JSON", e)
    _save_memory_json(memory)


def search_memory(query: str, category: str | None = None, limit: int = 20) -> list[dict]:
    """Search memory entries using FTS5 full-text search.
    
    NEW in SQLite backend — not available in JSON fallback.
    
    Args:
        query:    Natural language query string.
        category: Optional category filter.
        limit:    Maximum results.
        
    Returns:
        List of {category, key, value, updated, score} dicts.
    """
    if _USE_SQLITE and _store is not None:
        try:
            return _store.search(query, category=category, limit=limit)
        except Exception as e:
            logger.error("Memory search failed: %s", e)
    return []


def search_memory_hybrid(
    query: str, category: str | None = None, limit: int = 20, rrf_k: int = 60
) -> list[dict]:
    """Search memory entries using Native SIMD Vector + BM25 Hybrid Search.
    
    Combines FTS5 BM25 keyword matching with SIMD vector cosine similarity
    and Reciprocal Rank Fusion (RRF).
    """
    if _USE_SQLITE and _store is not None:
        try:
            return _store.hybrid_search(query, category=category, limit=limit, rrf_k=rrf_k)
        except Exception as e:
            logger.error("Hybrid memory search failed: %s", e)
    return []


def _save_memory_sqlite(memory: dict) -> None:
    """Bulk-write all categories to SQLite — used by consolidation."""
    assert _store is not None
    for category, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                value = str(entry["value"])
                updated = entry.get("updated", "")
            elif isinstance(entry, str):
                value = entry
                updated = ""
            else:
                continue
            if value and value.strip():
                _store.upsert(category, key, value, updated=updated or None)


# ── JSON fallback implementations ────────────────────────────────────────────

def _load_memory_json() -> dict:
    """Load memory from JSON file (fallback when SQLite unavailable)."""
    import time as _time
    global _cached_memory, _cached_memory_time

    now = _time.monotonic()
    if _cached_memory is not None and (now - _cached_memory_time) < MEMORY_CACHE_TTL:
        return _cached_memory

    if not MEMORY_PATH.exists():
        _cached_memory = _empty_memory()
        _cached_memory_time = now
        return _cached_memory

    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                old_keys = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
                if any(key in data for key in old_keys):
                    data = _migrate_legacy_memory_unlocked(data)
                base = _empty_memory()
                for cat_key in base:
                    if cat_key not in data:
                        data[cat_key] = {}
                _cached_memory = data
                _cached_memory_time = now
                return data
            _cached_memory = _empty_memory()
            _cached_memory_time = now
            return _cached_memory
        except Exception as e:
            logger.error("JSON load error: %s", e)
            _cached_memory = _empty_memory()
            _cached_memory_time = now
            return _cached_memory


def _save_memory_json(memory: dict) -> None:
    """Save memory to JSON file (fallback)."""
    import time as _time
    global _cached_memory, _cached_memory_time
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    _cached_memory = memory
    _cached_memory_time = _time.monotonic()


# ──────────────────────────────────────────────
#  Internal helpers
# ──────────────────────────────────────────────


def _all_entries(memory: dict) -> list[tuple]:
    """Flatten memory to (category, key, entry) triples."""
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


def _trim_to_limit(memory: dict) -> dict:
    """Evict oldest entries when JSON exceeds MEMORY_MAX_CHARS."""
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        logger.info("Trimmed %s/%s", cat, key)
    return memory


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "..."
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    """Deep-merge ``updates`` into ``target``. Returns True if anything changed."""
    changed = False
    for key, value in updates.items():
        if value is None or (isinstance(value, dict) and "value" in value and value["value"] is None):
            if key in target:
                del target[key]
                changed = True
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val = _truncate_value(
                str(value["value"] if isinstance(value, dict) else value)
            )
            entry = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


# ──────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────


def update_memory(memory_update: dict) -> dict:
    """Apply a partial update and persist. Returns the full memory dict.
    
    SQLite path: upserts individual entries directly (fast, no full reload).
    JSON path: loads full dict, merges, saves.
    """
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()

    if _USE_SQLITE and _store is not None:
        try:
            # Fast path: upsert each changed entry directly
            changed = False
            for category, items in memory_update.items():
                if not isinstance(items, dict):
                    continue
                for key, entry in items.items():
                    if isinstance(entry, dict) and "value" in entry:
                        value = entry["value"]
                    elif isinstance(entry, str):
                        value = entry
                    elif entry is None:
                        # Explicit delete
                        _store.delete(category, key)
                        changed = True
                        continue
                    else:
                        value = json.dumps(entry, ensure_ascii=False)

                    if value and str(value).strip():
                        _store.upsert(category, key, str(value)[:MAX_VALUE_LENGTH])
                        changed = True

            if changed:
                try:
                    from orchestrator.memory_agent import _invalidate_context_cache
                    _invalidate_context_cache()
                except ImportError:
                    pass
                logger.info("Saved (SQLite): %s", list(memory_update.keys()))
            return load_memory()
        except Exception as e:
            logger.error("SQLite update failed: %s — falling back to JSON", e)

    # JSON fallback
    memory = _load_memory_json()
    if _recursive_update(memory, memory_update):
        _save_memory_json(memory)
        try:
            from orchestrator.memory_agent import _invalidate_context_cache
            _invalidate_context_cache()
        except ImportError:
            pass
        logger.info("Saved (JSON): %s", list(memory_update.keys()))
    return memory


def format_memory_for_prompt(memory: dict | None) -> str:
    """Render memory as a plain-text block for injecting into the system prompt."""
    if not memory:
        return ""

    lines = []

    # 1. User Memory (profile, preferences, wishes, etc.)
    user_mem = memory.get("user_memory", {})
    if user_mem:
        lines.append("User Profile & Preferences:")
        id_fields = ["name", "job", "motto", "city", "age", "birthday", "language"]
        for field in id_fields:
            entry = user_mem.get(field)
            if entry:
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"  - {field.title()}: {val}")
        for key, entry in user_mem.items():
            if key in id_fields:
                continue
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    # 2. Daily Task Memory
    task_mem = memory.get("daily_task_memory", {})
    if task_mem:
        if lines:
            lines.append("")
        lines.append("Daily Tasks & Goals:")
        if isinstance(task_mem, dict):
            for key, entry in task_mem.items():
                if key.startswith("_"):
                    continue
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"  - {key.replace('_', ' ').title()}: {val}")
        elif isinstance(task_mem, list):
            for item in task_mem:
                desc = item.get("task", item.get("description", ""))
                if desc:
                    lines.append(f"  - {desc}")

    # 3. Chat Memory (Summaries of past sessions)
    chat_mem = memory.get("chat_memory", {})
    if chat_mem:
        if lines:
            lines.append("")
        lines.append("Conversation Highlights & History:")
        if isinstance(chat_mem, dict):
            for key, entry in chat_mem.items():
                val = entry.get("value") if isinstance(entry, dict) else entry
                if val:
                    lines.append(f"  - {key}: {val}")
        elif isinstance(chat_mem, list):
            for item in chat_mem:
                date = item.get("date", "")
                summary = item.get("summary", "")
                if summary:
                    prefix = f"{date}: " if date else ""
                    lines.append(f"  - {prefix}{summary}")

    # 4. Feature Memory (Tool preferences, settings)
    feat_mem = memory.get("feature_memory", {})
    if feat_mem:
        if lines:
            lines.append("")
        lines.append("Tool & Feature Preferences:")
        for key, entry in feat_mem.items():
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    # 5. Capability Memory (why tools/skills exist, impact)
    cap_mem = memory.get("capability_memory", {})
    if cap_mem:
        if lines:
            lines.append("")
        lines.append("Capabilities & Tools:")
        for key, entry in cap_mem.items():
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val[:200]}")

    # 6. Planning Memory (successful execution plans)
    plan_mem = memory.get("planning_memory", {})
    if plan_mem:
        if lines:
            lines.append("")
        lines.append("Known Execution Plans:")
        for key, entry in plan_mem.items():
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {str(val)[:200]}")

    if not lines:
        return ""

    header = "[WHAT YOU KNOW ABOUT THIS PERSON -- use naturally, never recite like a list]\n"
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "..."

    return result + "\n"


def remember(key: str, value: str, category: str = "user_memory") -> str:
    """Quick single-entry save. Returns confirmation string."""
    valid = {"user_memory", "daily_task_memory", "chat_memory", "feature_memory", "capability_memory", "planning_memory"}
    if category not in valid:
        category = "user_memory"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "user_memory") -> str:
    """Delete a single key from a category. Returns confirmation."""
    valid = {"user_memory", "daily_task_memory", "chat_memory", "feature_memory", "capability_memory", "planning_memory"}
    if category not in valid:
        category = "user_memory"
    memory = load_memory()
    cat = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget  # alias


# ──────────────────────────────────────────────
#  Planning Memory
# ──────────────────────────────────────────────


def save_plan(
    task_name: str,
    steps: list[str],
    tools_used: list[str],
    agent: str = "personal",
    success_rate: float = 1.0,
) -> str:
    """Record a successful execution plan for reuse.

    Args:
        task_name: What the plan accomplishes (e.g. "generate_invoice").
        steps: Ordered list of high-level steps.
        tools_used: Tools involved in the plan.
        agent: Which agent executed it.
        success_rate: Historical success rate (0.0-1.0).

    Returns:
        Confirmation string.
    """
    import json
    value = json.dumps({
        "steps": steps,
        "tools_used": tools_used,
        "agent": agent,
        "success_rate": success_rate,
        "last_executed": datetime.now().isoformat(),
    })
    return remember(task_name, value, "planning_memory")


# ──────────────────────────────────────────────
#  Capability Memory
# ──────────────────────────────────────────────


def save_capability(
    name: str,
    reason_created: str = "",
    created_by: str = "tool_manager",
    created_from: str = "conversation",
    created_after: int = 0,
    confidence: float = 0.0,
    related_agents: list | None = None,
    usage_count: int = 0,
    success_rate: float = 1.0,
    optimization_history: list | None = None,
) -> str:
    """Record a capability entry — why a tool was created and its history.

    Args:
        name: Tool or capability name.
        reason_created: Why this was built (user need, observed pattern).
        created_by: What created it ("tool_manager", "user", "observation").
        created_from: Source context ("conversation", "observation", "manual").
        created_after: Conversation turn index when created (0 if unknown).
        confidence: LLM confidence in this capability (0.0-1.0).
        related_agents: Agent names that use this capability.
        usage_count: How many times it's been called.
        success_rate: Ratio of successful vs total calls (0.0-1.0).
        optimization_history: List of version optimization records.

    Returns:
        Confirmation string.
    """
    import json
    value = json.dumps({
        "reason_created": reason_created,
        "created_by": created_by,
        "created_from": created_from,
        "created_after": created_after,
        "confidence": confidence,
        "related_agents": related_agents or [],
        "usage_count": usage_count,
        "success_rate": success_rate,
        "optimization_history": optimization_history or [],
    })
    return remember(name, value, "capability_memory")


def flush_all_except_user_memory() -> str:
    """Clear all memory categories except 'user_memory'."""
    memory = load_memory()
    for cat_key in list(memory.keys()):
        if cat_key != "user_memory":
            memory[cat_key] = {}
    save_memory(memory)
    return "Successfully cleared all memory categories except your personal user profile information."


def delete_memory_key(category: str, key: str) -> str:
    """Delete a specific key from a memory category."""
    memory = load_memory()
    if category in memory and key in memory[category]:
        del memory[category][key]
        save_memory(memory)
        return f"Successfully deleted key '{key}' from category '{category}'."
    return f"Key '{key}' not found in category '{category}'."


# ──────────────────────────────────────────────
#  Consumed session summaries (Mark-XLVII pattern)
#  A short "where we left off" note written at session end and
#  surfaced once (then deleted) so it never repeats in a briefing.
# ──────────────────────────────────────────────

SESSION_SUMMARIES_PATH = config.ROAMING_DIR / "memory" / "session_summaries.json"
MAX_SESSION_SUMMARIES = 3


def save_session_summary(summary: str) -> None:
    """Record a 1-2 sentence session summary; keep only the newest MAX_SESSION_SUMMARIES."""
    if not summary or not summary.strip():
        return
    # Read-modify-write is fully inside _lock so concurrent writers never
    # clobber each other's appends.
    with _lock:
        try:
            summaries = _load_session_summaries()
            summaries.append(
                {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "summary": summary.strip()}
            )
            # Keep the most recent entries (oldest first, so pop from the end gives newest).
            summaries = summaries[-MAX_SESSION_SUMMARIES:]
            SESSION_SUMMARIES_PATH.parent.mkdir(parents=True, exist_ok=True)
            SESSION_SUMMARIES_PATH.write_text(
                json.dumps(summaries, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save session summary: %s", e)


def pop_last_session() -> str | None:
    """Return the newest session summary AND delete it, so it never repeats.

    Mirrors Mark-XLVII's ``pop_last_session`` (return-and-consume). Returns
    None when there is nothing to surface.
    """
    # Read-modify-write is fully inside _lock so a concurrent save can never
    # interleave between the read and the delete.
    with _lock:
        try:
            summaries = _load_session_summaries()
            if not summaries:
                return None
            newest = summaries[-1]  # newest is last
            SESSION_SUMMARIES_PATH.write_text(
                json.dumps(summaries[:-1], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return newest.get("summary")
        except Exception as e:
            logger.error("Failed to consume session summary: %s", e)
            return None


def _load_session_summaries() -> list[dict]:
    """Thread-safe read of the session summaries store (returns [] on any error)."""
    try:
        content = SESSION_SUMMARIES_PATH.read_text(encoding="utf-8").strip()
        if not content:
            return []
        data = json.loads(content)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


