"""
Persistent long-term memory for Raphael.

Stores categorized information (identity, preferences, projects, relationships,
wishes, notes) in a single JSON file with automatic trimming to keep within limits.
Thread-safe for concurrent read/write.
"""

import json
import logging
import time as _time
from datetime import datetime
from threading import Lock

logger = logging.getLogger(__name__)


import config

# --- Path resolution ---
MEMORY_PATH = config.ROAMING_DIR / "memory" / "long_term.json"

_lock = Lock()

# --- Limits ---
MAX_VALUE_LENGTH = 380        # per-entry value truncation
MEMORY_MAX_CHARS = 2200       # total JSON size before trimming

# --- Read cache ---
_cached_memory: dict | None = None
_cached_memory_time: float = 0.0
MEMORY_CACHE_TTL: float = 5.0  # seconds


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


def _migrate_legacy_memory_unlocked(data: dict) -> dict:
    """Migrate legacy 6-category memory structure to the new layout without acquiring lock (since it's already held)."""
    new_data = _empty_memory()

    def copy_cat(old_cat, new_cat):
        for k, v in data.get(old_cat, {}).items():
            if isinstance(v, dict) and "value" in v:
                new_data[new_cat][k] = v
            else:
                new_data[new_cat][k] = {
                    "value": str(v),
                    "updated": datetime.now().strftime("%Y-%m-%d")
                }

    copy_cat("identity", "user_memory")
    copy_cat("preferences", "user_memory")
    copy_cat("relationships", "user_memory")
    copy_cat("wishes", "user_memory")
    copy_cat("notes", "user_memory")

    copy_cat("projects", "daily_task_memory")

    try:
        new_data = _trim_to_limit(new_data)
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(
            json.dumps(new_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Migrated legacy memory to new 4-category layout.")
    except Exception as e:
        logger.error("Failed to write migrated memory: %s", e)

    return new_data


# ──────────────────────────────────────────────
#  Read / Write
# ──────────────────────────────────────────────


def load_memory() -> dict:
    """Load memory from disk (cached, invalidated on save). Returns empty skeleton on any error."""
    global _cached_memory, _cached_memory_time

    # Serve from cache if still fresh
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
                # Check for legacy categories
                old_keys = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
                if any(key in data for key in old_keys):
                    data = _migrate_legacy_memory_unlocked(data)

                base = _empty_memory()
                for cat_key in base:
                    if cat_key not in data:
                        data[cat_key] = {}
                    elif isinstance(data[cat_key], list):
                        # Convert list-format categories to the expected dict envelope
                        lst = data[cat_key]
                        data[cat_key] = {}
                        for i, item in enumerate(lst):
                            if isinstance(item, dict):
                                item_key = item.get("task") or item.get("date") or f"entry_{i}"
                                item_val = item.get("description") or item.get("summary") or str(item)
                                data[cat_key][item_key] = {"value": item_val, "updated": item.get("date", "")}
                            else:
                                data[cat_key][f"entry_{i}"] = {"value": str(item), "updated": ""}
                    elif isinstance(data[cat_key], dict):
                        # Normalise any plain-value entries (not wrapped in {value, updated})
                        # Only apply to leaf entries (not nested dicts like app_paths)
                        cat = data[cat_key]
                        for k, v in list(cat.items()):
                            if not isinstance(v, dict) or "value" not in v:
                                # Skip nested dicts (sub-categories like app_paths)
                                if isinstance(v, dict) and any(isinstance(x, dict) for x in v.values()):
                                    continue
                                cat[k] = {"value": str(v), "updated": ""}
                _cached_memory = data
                _cached_memory_time = now
                return data
            _cached_memory = _empty_memory()
            _cached_memory_time = now
            return _cached_memory
        except Exception as e:
            logger.error("Load error: %s", e)
            _cached_memory = _empty_memory()
            _cached_memory_time = now
            return _cached_memory


def save_memory(memory: dict) -> None:
    """Trim memory to size limit and atomically write to disk.

    Invalidates the in-memory read cache so the next load_memory() call
    reads the fresh data from disk.
    """
    global _cached_memory, _cached_memory_time
    if not isinstance(memory, dict):
        return  # type: ignore[unreachable]
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
    """Apply a partial update and persist. Returns the full memory dict."""
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        # Invalidate the memory-agent context cache so next read picks up fresh data
        try:
            from orchestrator.memory_agent import _invalidate_context_cache
            _invalidate_context_cache()
        except ImportError:
            pass
        logger.info("Saved: %s", list(memory_update.keys()))
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


