"""Tests for Native SIMD Vector + BM25 Hybrid Memory Retrieval."""

import time

from memory.memory_manager import search_memory_hybrid
from memory.sqlite_store import _vectorize_text, get_store


def test_vectorize_text():
    """Verify vectorizer produces normalized 64-dim float vectors."""
    vec = _vectorize_text("Python asyncio architecture and SIMD acceleration")
    assert len(vec) == 64
    # Check L2 normalized magnitude
    norm = sum(x * x for x in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-4

    empty_vec = _vectorize_text("")
    assert len(empty_vec) == 64
    assert all(x == 0.0 for x in empty_vec)


def test_hybrid_search_end_to_end():
    """Verify hybrid search returns relevant memories for keywords and semantic queries."""
    store = get_store()

    # Seed sample test memories
    store.upsert("user_memory", "favorite_editor", "Visual Studio Code with Python and Rust extensions")
    store.upsert("daily_task_memory", "morning_standup", "Daily team sync at 10 AM on Google Meet")
    store.upsert("feature_memory", "tts_engine", "Edge TTS with high quality neural voices")

    # 1. Search via store.hybrid_search
    results = store.hybrid_search("Visual Studio Code Rust", limit=5)
    assert len(results) > 0
    assert any("favorite_editor" in r["key"] for r in results)

    # 2. Search via memory_manager.search_memory_hybrid
    mgr_results = search_memory_hybrid("standup team sync", limit=5)
    assert len(mgr_results) > 0
    assert any("morning_standup" in r["key"] for r in mgr_results)


def test_hybrid_search_latency():
    """Verify hybrid search executes in sub-50ms."""
    store = get_store()
    # Populate 50 test records if not already populated
    for i in range(50):
        store.upsert("planning_memory", f"perf_plan_{i}", f"Automated workflow step {i} with database indexing")

    start_t = time.perf_counter()
    results = store.hybrid_search("workflow database indexing", limit=10)
    elapsed_ms = (time.perf_counter() - start_t) * 1000.0

    assert len(results) > 0
    assert elapsed_ms < 50.0  # Fast execution benchmark
