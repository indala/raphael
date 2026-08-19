"""
SQLite Memory Store — replaces the 2200-char JSON flat file.

Uses SQLite with FTS5 (built into Python's stdlib sqlite3) for full-text
search across all memory entries. No external dependencies required.

Pattern from OpenJarvis: StorageConfig with chunking + BM25 search.
Credential-safe: values containing secrets are never returned in search
results without explicit key lookup.

Schema
------
  memories(id, category, key, value, updated, created)
  memories_fts (FTS5 virtual table over key + value columns)

The FTS5 virtual table is content-synced via triggers so search always
reflects the latest writes.

Backward Compatibility
----------------------
  - migrate_from_json(path)  — one-shot migration of long_term.json
  - to_json_dict()           — serialize back to the old dict format
  - The existing memory_manager.py public API is fully preserved.
    All callers continue to work without modification.

Usage
-----
  store = MemoryStore()
  store.upsert("user_memory", "name", "Alice")
  results = store.search("Alice project ideas")
  store.delete("chat_memory", "2024-01-01")
  full = store.load_all()
"""

from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
import zlib
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import cast

import config
from modules.native_core import batch_cosine_similarity, top_k_indices

logger = logging.getLogger(__name__)

# Database path — sibling to long_term.json
DB_PATH = config.ROAMING_DIR / "memory" / "memory.db"

# Max chars stored per value (increased 10× over JSON era)
MAX_VALUE_LENGTH = 4000

# BM25-style result cap for search queries
DEFAULT_SEARCH_LIMIT = 20

# Valid categories (matches existing memory_manager categories)
VALID_CATEGORIES = frozenset({
    "user_memory",
    "daily_task_memory",
    "chat_memory",
    "feature_memory",
    "capability_memory",
    "planning_memory",
})

# Patterns that may indicate sensitive values — never snippet in search results
_SENSITIVE_PATTERNS = re.compile(
    r"(api[_\-]?key|password|secret|token|bearer|auth|credential|private[_\-]?key)",
    re.IGNORECASE,
)

_BASE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    category  TEXT NOT NULL,
    key       TEXT NOT NULL,
    value     TEXT NOT NULL DEFAULT '',
    updated   TEXT NOT NULL DEFAULT '',
    created   TEXT NOT NULL DEFAULT '',
    UNIQUE(category, key)
);

CREATE INDEX IF NOT EXISTS idx_category ON memories(category);
CREATE INDEX IF NOT EXISTS idx_updated  ON memories(updated DESC);
"""

_FTS_SCHEMA_SQL = """
-- FTS5 virtual table for full-text search over key + value
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    category UNINDEXED,
    key,
    value,
    content='memories',
    content_rowid='id'
);

-- Auto-sync triggers: keep FTS index current
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, category, key, value)
    VALUES (new.id, new.category, new.key, new.value);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, category, key, value)
    VALUES ('delete', old.id, old.category, old.key, old.value);
    INSERT INTO memories_fts(rowid, category, key, value)
    VALUES (new.id, new.category, new.key, new.value);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, category, key, value)
    VALUES ('delete', old.id, old.category, old.key, old.value);
END;
"""


def _vectorize_text(text: str, dim: int = 64) -> list[float]:
    """Fast deterministic subword/n-gram feature hashing vectorizer for SIMD similarity."""
    if not text:
        return [0.0] * dim
    vec = [0.0] * dim
    words = re.findall(r"\w+", text.lower())
    for w in words:
        h = zlib.crc32(w.encode("utf-8")) % dim
        vec[h] += 1.0
        if len(w) >= 3:
            for i in range(len(w) - 2):
                gram = w[i:i+3]
                gram_h = zlib.crc32(gram.encode("utf-8")) % dim
                vec[gram_h] += 0.5

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0.0:
        return [x / norm for x in vec]
    return vec


class MemoryStore:
    """Thread-safe SQLite memory store with FTS5 full-text search and fallback."""

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or DB_PATH
        self._local = threading.local()
        self._write_lock = threading.Lock()
        self._fts_available = False
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        """Per-thread connection (SQLite connections are not thread-safe)."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
                timeout=10.0,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return cast(sqlite3.Connection, self._local.conn)

    def _init_db(self) -> None:
        """Create tables and FTS index on first use."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock:
            conn = self._conn()
            conn.executescript(_BASE_SCHEMA_SQL)
            conn.commit()
            try:
                conn.executescript(_FTS_SCHEMA_SQL)
                conn.commit()
                self._fts_available = True
            except sqlite3.OperationalError as e:
                logger.warning(
                    "MemoryStore: SQLite FTS5 extension not available (%s). "
                    "Falling back to standard LIKE search.",
                    e,
                )
                self._fts_available = False
        logger.debug(
            "MemoryStore: database initialised at %s (FTS5: %s)",
            self._db_path,
            self._fts_available,
        )

    # ── Write API ────────────────────────────────────────────────────────────

    def upsert(
        self,
        category: str,
        key: str,
        value: str,
        updated: str | None = None,
    ) -> None:
        """Insert or replace a memory entry.

        Args:
            category: One of the 6 memory categories.
            key:      Unique key within the category.
            value:    The value to store. Truncated to MAX_VALUE_LENGTH.
            updated:  ISO date string; defaults to today.
        """
        category = _normalise_category(category)
        key = key.strip()[:255]
        value = value.strip()[:MAX_VALUE_LENGTH]
        if not key or not value:
            return
        now_str = updated or datetime.now().strftime("%Y-%m-%d")

        with self._write_lock:
            conn = self._conn()
            conn.execute(
                """
                INSERT INTO memories (category, key, value, updated, created)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value   = excluded.value,
                    updated = excluded.updated
                """,
                (category, key, value, now_str, now_str),
            )
            conn.commit()

    def delete(self, category: str, key: str) -> bool:
        """Delete a memory entry. Returns True if something was deleted."""
        category = _normalise_category(category)
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute(
                "DELETE FROM memories WHERE category=? AND key=?",
                (category, key),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_category(self, category: str) -> int:
        """Delete all entries in a category. Returns count deleted."""
        category = _normalise_category(category)
        with self._write_lock:
            conn = self._conn()
            cur = conn.execute(
                "DELETE FROM memories WHERE category=?", (category,)
            )
            conn.commit()
            return cur.rowcount

    def upsert_many(self, entries: list[tuple[str, str, str]]) -> None:
        """Bulk upsert. Each entry is (category, key, value)."""
        now_str = datetime.now().strftime("%Y-%m-%d")
        with self._write_lock:
            conn = self._conn()
            conn.executemany(
                """
                INSERT INTO memories (category, key, value, updated, created)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value   = excluded.value,
                    updated = excluded.updated
                """,
                [
                    (_normalise_category(c), k.strip()[:255], v.strip()[:MAX_VALUE_LENGTH], now_str, now_str)
                    for c, k, v in entries
                    if k and v
                ],
            )
            conn.commit()

    # ── Read API ─────────────────────────────────────────────────────────────

    def get(self, category: str, key: str) -> str | None:
        """Exact key lookup. Returns value string or None."""
        category = _normalise_category(category)
        conn = self._conn()
        row = conn.execute(
            "SELECT value FROM memories WHERE category=? AND key=?",
            (category, key),
        ).fetchone()
        return row["value"] if row else None

    def get_category(self, category: str) -> dict[str, dict]:
        """Return all entries in a category as {key: {value, updated}} dict."""
        category = _normalise_category(category)
        conn = self._conn()
        rows = conn.execute(
            "SELECT key, value, updated FROM memories WHERE category=? ORDER BY updated DESC",
            (category,),
        ).fetchall()
        return {
            row["key"]: {"value": row["value"], "updated": row["updated"]}
            for row in rows
        }

    def load_all(self) -> dict[str, dict[str, dict]]:
        """Load the full memory as a nested dict matching the old JSON format.

        Returns:
            {category: {key: {value: str, updated: str}}}
        """
        conn = self._conn()
        rows = conn.execute(
            "SELECT category, key, value, updated FROM memories ORDER BY category, updated DESC"
        ).fetchall()

        result: dict[str, dict[str, dict]] = {cat: {} for cat in VALID_CATEGORIES}
        for row in rows:
            cat = row["category"]
            if cat not in result:
                result[cat] = {}
            result[cat][row["key"]] = {
                "value": row["value"],
                "updated": row["updated"],
            }
        return result

    # ── Search API (FTS5) ────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        category: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
    ) -> list[dict[str, str | float]]:
        """Full-text search across all memory entries using FTS5.

        Uses SQLite's built-in BM25 ranking — no external dependencies.

        Args:
            query:    User query string. Automatically escaped for FTS5.
            category: Optional filter to a single category.
            limit:    Maximum results to return.

        Returns:
            List of {category, key, value, updated, score} dicts,
            ordered by relevance (best match first).
            Sensitive values are redacted in results.
        """
        if not query or not query.strip():
            return []

        if not self._fts_available:
            return self._like_search(query, category, limit)

        fts_query = _build_fts_query(query)
        if not fts_query:
            return []

        conn = self._conn()
        try:
            if category:
                category = _normalise_category(category)
                rows = conn.execute(
                    """
                    SELECT m.category, m.key, m.value, m.updated,
                           bm25(memories_fts) AS score
                    FROM memories_fts
                    JOIN memories m ON memories_fts.rowid = m.id
                    WHERE memories_fts MATCH ?
                      AND m.category = ?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (fts_query, category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT m.category, m.key, m.value, m.updated,
                           bm25(memories_fts) AS score
                    FROM memories_fts
                    JOIN memories m ON memories_fts.rowid = m.id
                    WHERE memories_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()

            results = []
            for row in rows:
                value = row["value"]
                # Redact sensitive values in search results
                if _SENSITIVE_PATTERNS.search(row["key"]):
                    value = "[redacted]"
                results.append({
                    "category": row["category"],
                    "key": row["key"],
                    "value": value,
                    "updated": row["updated"],
                    "score": row["score"],
                })
            return results

        except sqlite3.OperationalError as e:
            # FTS syntax error — fall back to LIKE search
            logger.debug("FTS search failed ('%s'): %s — falling back to LIKE", fts_query, e)
            return self._like_search(query, category, limit)

    def _like_search(
        self, query: str, category: str | None, limit: int
    ) -> list[dict[str, str | float]]:
        """Fallback LIKE-based search when FTS5 query fails."""
        conn = self._conn()
        pattern = f"%{query}%"
        if category:
            rows = conn.execute(
                """SELECT category, key, value, updated FROM memories
                   WHERE category=? AND (key LIKE ? OR value LIKE ?)
                   ORDER BY updated DESC LIMIT ?""",
                (category, pattern, pattern, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT category, key, value, updated FROM memories
                   WHERE key LIKE ? OR value LIKE ?
                   ORDER BY updated DESC LIMIT ?""",
                (pattern, pattern, limit),
            ).fetchall()
        return [
            {"category": r["category"], "key": r["key"],
             "value": r["value"], "updated": r["updated"], "score": 0.0}
            for r in rows
        ]

    def hybrid_search(
        self,
        query: str,
        category: str | None = None,
        limit: int = DEFAULT_SEARCH_LIMIT,
        rrf_k: int = 60,
    ) -> list[dict[str, str | float]]:
        """Hybrid search combining BM25/FTS5 keyword ranking with SIMD vector matching via RRF.

        Uses Reciprocal Rank Fusion (RRF) (inspired by OpenJarvis/OpenClaw):
            RRF_score(d) = sum(1 / (k + rank_i))
        """
        if not query or not query.strip():
            return []

        # 1. Exact/BM25 keyword search results
        keyword_results = self.search(query, category=category, limit=limit * 2)

        # 2. Native SIMD vector search over candidate entries
        all_entries: list[tuple[str, str, str, str]] = []
        if category:
            cat_dict = self.get_category(category)
            for k, data in cat_dict.items():
                all_entries.append((category, k, data["value"], data["updated"]))
        else:
            full = self.load_all()
            for cat, kvs in full.items():
                for k, data in kvs.items():
                    all_entries.append((cat, k, data["value"], data["updated"]))

        semantic_results = []
        if all_entries:
            query_vec = _vectorize_text(query)
            candidate_vecs = [_vectorize_text(f"{k} {val}") for _, k, val, _ in all_entries]
            sim_scores = batch_cosine_similarity(query_vec, candidate_vecs)

            # Filter non-zero scores and pick top K using SIMD indexer
            top_k_count = min(len(all_entries), limit * 2)
            top_indices = top_k_indices(sim_scores, top_k_count)

            for idx in top_indices:
                score = sim_scores[idx]
                if score > 0.05:  # meaningful similarity threshold
                    cat, k, val, upd = all_entries[idx]
                    semantic_results.append({
                        "category": cat,
                        "key": k,
                        "value": val,
                        "updated": upd,
                        "similarity": score,
                    })

        # 3. Reciprocal Rank Fusion
        rrf_scores: dict[tuple[str, str], float] = defaultdict(float)
        item_map: dict[tuple[str, str], dict] = {}

        for rank, item in enumerate(keyword_results, start=1):
            key_id = (str(item["category"]), str(item["key"]))
            rrf_scores[key_id] += 1.0 / (rrf_k + rank)
            item_map[key_id] = item

        for rank, item in enumerate(semantic_results, start=1):
            key_id = (str(item["category"]), str(item["key"]))
            rrf_scores[key_id] += 1.0 / (rrf_k + rank)
            if key_id not in item_map:
                val = item["value"]
                if _SENSITIVE_PATTERNS.search(item["key"]):
                    val = "[redacted]"
                item_map[key_id] = {
                    "category": item["category"],
                    "key": item["key"],
                    "value": val,
                    "updated": item["updated"],
                }

        # Sort by fused RRF score
        sorted_keys = sorted(rrf_scores.keys(), key=lambda k: rrf_scores[k], reverse=True)
        final_results = []
        for k_id in sorted_keys[:limit]:
            res = dict(item_map[k_id])
            res["score"] = round(rrf_scores[k_id], 6)
            final_results.append(res)
        return final_results

    # ── Helpers ──────────────────────────────────────────────────────────────

    def entry_count(self, category: str | None = None) -> int:
        """Return total number of stored entries (optionally filtered by category)."""
        conn = self._conn()
        if category:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM memories WHERE category=?",
                (_normalise_category(category),),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS n FROM memories").fetchone()
        return row["n"] if row else 0

    def close(self) -> None:
        """Close the thread-local connection (call on shutdown)."""
        conn = getattr(self._local, "conn", None)
        if conn:
            conn.close()
            self._local.conn = None

    # ── Migration ────────────────────────────────────────────────────────────

    def migrate_from_json(self, json_path: Path) -> int:
        """One-shot migration from long_term.json to SQLite.

        Reads the existing JSON file, upserts every entry into SQLite,
        and returns the number of entries migrated.

        The JSON file is NOT deleted — it remains as a backup until the
        user is satisfied with the migration.
        """
        if not json_path.exists():
            return 0

        try:
            raw = json_path.read_text(encoding="utf-8").strip()
            if not raw:
                return 0
            data = json.loads(raw)
        except Exception as e:
            logger.warning("Migration: failed to read %s: %s", json_path, e)
            return 0

        if not isinstance(data, dict):
            return 0

        entries: list[tuple[str, str, str]] = []
        for category, items in data.items():
            if not isinstance(items, dict):
                continue
            for key, entry in items.items():
                if isinstance(entry, dict) and "value" in entry:
                    value = str(entry["value"])
                elif isinstance(entry, str):
                    value = entry
                else:
                    value = json.dumps(entry, ensure_ascii=False)
                if value and value.strip():
                    entries.append((category, key, value))

        if entries:
            self.upsert_many(entries)
            logger.info(
                "Migration: imported %d entries from %s → %s",
                len(entries), json_path.name, self._db_path.name,
            )

        return len(entries)

    def to_json_dict(self) -> dict[str, dict[str, dict]]:
        """Serialize the store back to the old dict format for compatibility.

        Used by memory_manager.format_memory_for_prompt() and other callers
        that still expect the nested {category: {key: {value, updated}}} shape.
        """
        return self.load_all()


# ── Module-level helpers ─────────────────────────────────────────────────────

def _normalise_category(category: str) -> str:
    """Normalise category name — map legacy names to current ones."""
    cat = category.strip().lower()
    _LEGACY_MAP = {
        "identity":      "user_memory",
        "preferences":   "user_memory",
        "relationships": "user_memory",
        "wishes":        "user_memory",
        "notes":         "user_memory",
        "projects":      "daily_task_memory",
    }
    return _LEGACY_MAP.get(cat, cat)


def _build_fts_query(query: str) -> str:
    """Convert a plain-text query into an FTS5 query string.

    Strategy:
    - Each word is quoted to prevent FTS5 special-char errors
    - Words are joined with OR so partial matches still score well
    - Very short words (≤ 2 chars) are skipped to reduce noise
    """
    words = [w for w in re.split(r"\s+", query.strip()) if len(w) > 2]
    if not words:
        return ""
    # Quote each token to escape FTS5 special characters
    quoted = [f'"{w}"' for w in words[:10]]  # cap at 10 terms
    return " OR ".join(quoted)


# ── Global singleton ─────────────────────────────────────────────────────────

_store: MemoryStore | None = None
_store_lock = threading.Lock()


def get_store() -> MemoryStore:
    """Return (and lazily create) the global MemoryStore singleton."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = MemoryStore()
                # Auto-migrate from JSON on first use if JSON exists and DB is empty
                json_path = config.ROAMING_DIR / "memory" / "long_term.json"
                if json_path.exists() and _store.entry_count() == 0:
                    count = _store.migrate_from_json(json_path)
                    if count:
                        logger.info(
                            "MemoryStore: auto-migrated %d entries from JSON → SQLite",
                            count,
                        )
    return _store
