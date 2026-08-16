"""Unit tests for hybrid search in memory/sqlite_store.py."""

from __future__ import annotations

from pathlib import Path
from memory.sqlite_store import MemoryStore


def test_hybrid_search_rrf(tmp_path: Path):
    db_file = tmp_path / "test_hybrid.db"
    store = MemoryStore(db_file)

    # Insert entries
    store.upsert("user_memory", "editor_theme", "Visual Studio Code Dark+ neon cyber")
    store.upsert("user_memory", "ui_pref", "Aesthetic minimalist dark user interface")
    store.upsert("feature_memory", "fast_search", "Full-text BM25 index with high performance")

    # Search with hybrid query matching semantic concepts and exact keywords
    results = store.hybrid_search("dark neon theme", category="user_memory")

    assert len(results) > 0
    assert results[0]["key"] == "editor_theme"
    assert "score" in results[0]
    assert results[0]["score"] > 0.0


def test_hybrid_search_empty_and_sensitive(tmp_path: Path):
    db_file = tmp_path / "test_hybrid_sec.db"
    store = MemoryStore(db_file)

    store.upsert("user_memory", "api_key", "secret-token-xyz-12345")
    assert store.hybrid_search("") == []

    res = store.hybrid_search("token api key")
    assert len(res) == 1
    assert res[0]["value"] == "[redacted]"
