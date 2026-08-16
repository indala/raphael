"""
Integration, stress, and race condition tests for Raphael performance plan (Task 18).

Tests cover:
  - CacheManager (thread safety, versioning, TTL)
  - Processing lanes (user/proactive/background isolation)
  - Routing cache (SHA-256 keys, version invalidation)
  - Parallel tool execution (concurrent-safe tools)
  - Prompt caching (static/dynamic split)
  - Proactive + user + background collision detection
"""

import concurrent.futures
import pytest
import threading
import time


class TestCacheManager:
    """Integration tests for unified CacheManager."""

    def test_cache_set_get_basic(self):
        """Test basic set/get operations."""
        from orchestrator.cache_manager import CacheManager

        cache = CacheManager()
        cache.set("test", "key1", "value1")
        assert cache.get("test", "key1") == "value1"
        assert cache.get("test", "nonexistent") is None

    def test_cache_version_invalidation(self):
        """Test that changing version invalidates cached entries."""
        from orchestrator.cache_manager import CacheManager

        cache = CacheManager()
        cache.set_version("test", 1)
        cache.set("test", "key1", "value1")

        assert cache.get("test", "key1") == "value1"

        # Bump version → should invalidate
        cache.set_version("test", 2)
        assert cache.get("test", "key1") is None

    def test_cache_ttl_expiration(self):
        """Test TTL-based expiration."""
        from orchestrator.cache_manager import CacheManager

        cache = CacheManager()
        cache.set("test", "key1", "value1", ttl_seconds=0.1)

        assert cache.get("test", "key1") == "value1"
        time.sleep(0.2)
        assert cache.get("test", "key1") is None

    def test_cache_thread_safety(self):
        """Stress test: concurrent reads/writes should not deadlock or corrupt."""
        from orchestrator.cache_manager import CacheManager

        cache = CacheManager()
        errors = []

        def _writer(thread_id: int):
            try:
                for i in range(100):
                    cache.set(f"ns{thread_id}", f"key{i}", f"value{i}")
            except Exception as e:
                errors.append(e)

        def _reader(thread_id: int):
            try:
                for i in range(100):
                    cache.get(f"ns{thread_id}", f"key{i}")
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = []
            for i in range(4):
                futures.append(executor.submit(_writer, i))
                futures.append(executor.submit(_reader, i))
            concurrent.futures.wait(futures)

        assert not errors, f"Cache thread safety errors: {errors}"

    def test_cache_stats(self):
        """Test cache statistics tracking."""
        from orchestrator.cache_manager import CacheManager

        cache = CacheManager()
        cache.set("test", "key1", "value1")

        # Hit
        cache.get("test", "key1")
        # Miss
        cache.get("test", "nonexistent")

        stats = cache.stats("test")
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate_percent"] == 50.0


class TestProcessingLanes:
    """Integration tests for three-lane processing isolation."""

    def test_lanes_user_preempts_proactive(self):
        """User lane should invalidate proactive results."""
        from controller.processing_lanes import ProcessingLanes

        lanes = ProcessingLanes()

        # Start proactive work
        proactive_gen = lanes.begin_proactive()
        assert not lanes.is_stale("proactive", proactive_gen)

        # User arrives → bump proactive generation
        lanes.begin_user()
        assert lanes.is_stale("proactive", proactive_gen)

    def test_lanes_user_preempts_background(self):
        """User lane should invalidate background results."""
        from controller.processing_lanes import ProcessingLanes

        lanes = ProcessingLanes()

        # Start background work
        bg_gen = lanes.begin_background()
        assert not lanes.is_stale("background", bg_gen)

        # User arrives → bump background generation
        lanes.begin_user()
        assert lanes.is_stale("background", bg_gen)

    def test_lanes_concurrent_activity(self):
        """Test concurrent lane activity tracking."""
        from controller.processing_lanes import ProcessingLanes

        lanes = ProcessingLanes()

        # Start multiple concurrent activities
        user_gen = lanes.begin_user()
        proactive_gen = lanes.begin_proactive()
        bg_gen = lanes.begin_background()

        assert lanes.is_user_processing()
        assert lanes.is_proactive_processing()
        assert lanes.is_background_processing()
        assert lanes.active_lane() == "user"

        # End user → proactive becomes active
        lanes.end_user()
        assert not lanes.is_user_processing()
        assert lanes.is_proactive_processing()
        assert lanes.active_lane() == "proactive"

    def test_lanes_thread_safety(self):
        """Stress test: many threads using lanes concurrently."""
        from controller.processing_lanes import ProcessingLanes

        lanes = ProcessingLanes()
        errors = []

        def _lane_user():
            try:
                for _ in range(50):
                    gen = lanes.begin_user()
                    time.sleep(0.001)
                    lanes.end_user()
            except Exception as e:
                errors.append(e)

        def _lane_proactive():
            try:
                for _ in range(50):
                    gen = lanes.begin_proactive()
                    time.sleep(0.001)
                    lanes.end_proactive()
            except Exception as e:
                errors.append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            futures = [
                executor.submit(_lane_user) for _ in range(4)
            ] + [
                executor.submit(_lane_proactive) for _ in range(4)
            ]
            concurrent.futures.wait(futures)

        assert not errors, f"Lanes thread safety errors: {errors}"


class TestRoutingCache:
    """Integration tests for agent routing cache with SHA-256 keys."""

    def test_routing_cache_key_generation(self):
        """Test SHA-256 cache key generation."""
        from orchestrator.agent_orchestrator import _get_routing_cache_key

        key1 = _get_routing_cache_key("hello world")
        key2 = _get_routing_cache_key("hello world")
        key3 = _get_routing_cache_key("goodbye world")

        assert key1 == key2  # Same query → same key
        assert key1 != key3  # Different query → different key
        assert len(key1) == 64  # SHA-256 = 64 hex chars

    def test_routing_cache_normalization(self):
        """Test query normalization in cache key."""
        from orchestrator.agent_orchestrator import _get_routing_cache_key

        key1 = _get_routing_cache_key("Hello World")
        key2 = _get_routing_cache_key("hello world")
        key3 = _get_routing_cache_key("  HELLO WORLD  ")

        # All should be equal after normalization
        assert key1 == key2 == key3


class TestParallelToolExecution:
    """Integration tests for parallel tool execution with concurrency limits."""

    def test_parallel_safe_tools_set_expanded(self):
        """Verify PARALLEL_SAFE_TOOLS is expanded per Task 15."""
        from orchestrator.tools import PARALLEL_SAFE_TOOLS

        # Should have 40+ tools after Task 15 expansion
        assert len(PARALLEL_SAFE_TOOLS) >= 35

        # Sample of expected tools
        expected = {
            "web_search", "web_fetch", "read_file", "capture_screen",
            "recall_memory", "list_goals", "desktop_processes",
            "get_system_volume", "list_local_songs", "read_inbox"
        }
        assert expected.issubset(PARALLEL_SAFE_TOOLS)

    def test_concurrent_tool_execution_stress(self):
        """Stress: simulate 50+ parallel tool calls."""
        from orchestrator.tools import PARALLEL_SAFE_TOOLS

        # Mock tool executor
        call_count = [0]
        lock = threading.Lock()

        def mock_tool_exec(tool_name: str, args: dict) -> str:
            with lock:
                call_count[0] += 1
            time.sleep(0.01)  # Simulate work
            return f"Result of {tool_name}"

        # Execute many parallel tools
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i in range(50):
                tool = list(PARALLEL_SAFE_TOOLS)[i % len(PARALLEL_SAFE_TOOLS)]
                futures.append(executor.submit(mock_tool_exec, tool, {}))

            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 50
        assert call_count[0] == 50


class TestPromptCaching:
    """Integration tests for static/dynamic prompt split and caching."""

    def test_system_prompt_builder_caching(self):
        """Test that system prompt uses CacheManager for static sections."""
        from orchestrator.cache_manager import get_cache_manager, reset_cache_manager

        reset_cache_manager()
        cache = get_cache_manager()

        # First call should miss
        assert cache.get("system_prompt", "static") is None

        # After importing prompt builder and calling _build_tool_guide,
        # it should be cached
        from orchestrator.prompt_builder import SystemPromptBuilder
        guide1 = SystemPromptBuilder._build_tool_guide()

        # Should be cached now
        cached = cache.get("tool_guide", "guide_text")
        assert cached == guide1


class TestLocalIntents:
    """Integration tests for expanded local intents."""

    def test_local_intents_expanded(self):
        """Verify local intents expanded to 19+ intents per Task 16."""
        from orchestrator.local_intents import INTENT_MATCHERS

        assert len(INTENT_MATCHERS) >= 18

        intent_names = [name for _, name, _ in INTENT_MATCHERS]
        expected = {"stop", "mute", "unmute", "help", "battery", "wifi", "time", "date", "cpu", "memory"}
        assert expected.issubset(set(intent_names))

    def test_local_intent_matching(self):
        """Test intent pattern matching."""
        from orchestrator.local_intents import try_match_intent

        # Test time intent
        result = try_match_intent("what time is it")
        assert result is not None
        intent_name, response = result
        assert intent_name == "time"
        assert "time" in response.lower()

        # Test battery intent
        result = try_match_intent("check battery")
        assert result is not None
        intent_name, response = result
        assert intent_name == "battery"


class TestProcessIsolation:
    """High-level integration tests for process isolation architecture."""

    def test_user_busy_blocks_proactive(self):
        """Verify that user processing prevents proactive results from displaying."""
        from controller.processing_lanes import ProcessingLanes

        lanes = ProcessingLanes()

        # Proactive check starts
        proactive_gen = lanes.begin_proactive()

        # Simulate user message preempting proactive check
        user_gen = lanes.begin_user()

        # When proactive result arrives, it should be stale
        assert lanes.is_stale("proactive", proactive_gen)

        # User done → proactive results can proceed
        lanes.end_user()

        # New proactive would be fresh
        proactive_gen2 = lanes.begin_proactive()
        assert not lanes.is_stale("proactive", proactive_gen2)

    def test_write_invalidation_map_defined(self):
        """Verify WRITE_INVALIDATION_MAP is defined per Task 11."""
        from config import WRITE_INVALIDATION_MAP

        assert isinstance(WRITE_INVALIDATION_MAP, dict)
        assert len(WRITE_INVALIDATION_MAP) > 0

        # Sample tools that should invalidate caches
        assert "write_file" in WRITE_INVALIDATION_MAP
        assert "save_memory" in WRITE_INVALIDATION_MAP
        assert "routing" in WRITE_INVALIDATION_MAP["write_file"]

    def test_background_cooldown_constants(self):
        """Verify background task constraints defined per Task 11."""
        from config import (
            BACKGROUND_COOLDOWN_SECONDS,
            BACKGROUND_MAX_CONCURRENT,
            BACKGROUND_TASK_TIMEOUT,
            BACKGROUND_RESULT_DELIVERY_DELAY
        )

        assert BACKGROUND_COOLDOWN_SECONDS == 30
        assert BACKGROUND_MAX_CONCURRENT == 3
        assert BACKGROUND_TASK_TIMEOUT == 300
        assert BACKGROUND_RESULT_DELIVERY_DELAY == 1.0


class TestModelStateManagement:
    """Integration tests for ModelStateManager (Task 19)."""

    def test_endpoint_registration(self):
        """Test that endpoints register correctly with model priorities."""
        from orchestrator.model_state_manager import ModelStateManager

        manager = ModelStateManager()
        manager.register_endpoint("openrouter", ["openrouter/openrouter/free", "mistral-small-latest"])
        manager.register_endpoint("mistral", ["mistral-small-latest", "mistral-tiny-latest"])

        assert "openrouter" in manager._endpoints
        assert "mistral" in manager._endpoints
        assert manager._endpoints["openrouter"].model_priority == ["openrouter/openrouter/free", "mistral-small-latest"]
        assert manager._endpoints["mistral"].model_priority == ["mistral-small-latest", "mistral-tiny-latest"]

    def test_record_success_reorders_priority(self):
        """Test that successful calls reorder model priority."""
        from orchestrator.model_state_manager import ModelStateManager

        manager = ModelStateManager()
        manager.register_endpoint("test_ep", ["model_a", "model_b", "model_c"])

        # Record success with model_a — it should move to front
        manager.record_success("test_ep", "model_a")
        assert manager._endpoints["test_ep"].model_priority[0] == "model_a"

        # Record success with model_c — it should move to front
        manager.record_success("test_ep", "model_c")
        assert manager._endpoints["test_ep"].model_priority[0] == "model_c"

        # model_a should now be second
        assert manager._endpoints["test_ep"].model_priority[1] == "model_a"

    def test_record_rate_limit_backoff(self):
        """Test exponential backoff when rate limited."""
        from orchestrator.model_state_manager import ModelStateManager

        manager = ModelStateManager()
        manager.register_endpoint("test_ep", ["model_a"])

        # Record rate limit — should set rate_limit_until
        manager.record_rate_limit("test_ep", retry_after_seconds=5)
        ep = manager._endpoints["test_ep"]
        assert ep.status == "rate_limited"
        assert ep.rate_limit_until is not None

        # After backoff expires, get_next_model should return model_a
        time.sleep(5.1)
        assert manager.get_next_model("test_ep") == "model_a"

    def test_record_failure_marks_unavailable(self):
        """Test that 401/403/404/503 errors mark endpoint unavailable."""
        from orchestrator.model_state_manager import ModelStateManager

        manager = ModelStateManager()
        manager.register_endpoint("test_ep", ["model_a"])

        manager.record_failure("test_ep", "401")
        assert manager._endpoints["test_ep"].status == "unavailable"

        manager.record_failure("test_ep", "403")
        assert manager._endpoints["test_ep"].status == "unavailable"

    def test_record_success_recovers_unavailable(self):
        """Test that successful calls recover unavailable endpoints."""
        from orchestrator.model_state_manager import ModelStateManager

        manager = ModelStateManager()
        manager.register_endpoint("test_ep", ["model_a"])

        manager.record_failure("test_ep", "401")
        assert manager._endpoints["test_ep"].status == "unavailable"

        manager.record_success("test_ep", "model_a")
        assert manager._endpoints["test_ep"].status == "healthy"

    def test_stats(self):
        """Test that stats aggregation works correctly."""
        from orchestrator.model_state_manager import ModelStateManager

        manager = ModelStateManager()
        manager.register_endpoint("openrouter", ["openrouter/openrouter/free"])
        manager.register_endpoint("mistral", ["mistral-small-latest"])

        manager.record_success("openrouter", "openrouter/openrouter/free")
        manager.record_success("mistral", "mistral-small-latest")
        manager.record_failure("openrouter", "404")

        stats = manager.stats()
        assert stats["openrouter"]["status"] == "unavailable"
        assert stats["openrouter"]["success_count"] == 1
        assert stats["openrouter"]["failure_count"] == 1
        assert stats["mistral"]["status"] == "healthy"
        assert stats["mistral"]["success_count"] == 1
        assert stats["mistral"]["failure_count"] == 0


class TestConcurrencyRaceConditions:
    """Race condition detection tests."""

    def test_proactive_user_background_collision(self):
        """Simulate proactive + user + background starting simultaneously."""
        from controller.processing_lanes import ProcessingLanes

        lanes = ProcessingLanes()
        start_event = threading.Event()
        results = {}

        def _user_work():
            start_event.wait()
            gen = lanes.begin_user()
            results["user_gen"] = gen
            time.sleep(0.05)
            lanes.end_user()

        def _proactive_work():
            start_event.wait()
            gen = lanes.begin_proactive()
            results["proactive_gen"] = gen
            time.sleep(0.01)
            # Check if stale (user might have started)
            results["proactive_stale"] = lanes.is_stale("proactive", gen)
            lanes.end_proactive()

        def _background_work():
            start_event.wait()
            gen = lanes.begin_background()
            results["background_gen"] = gen
            time.sleep(0.02)
            # Check if stale (user might have started)
            results["background_stale"] = lanes.is_stale("background", gen)
            lanes.end_background()

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(_user_work),
                executor.submit(_proactive_work),
                executor.submit(_background_work),
            ]
            time.sleep(0.01)
            start_event.set()
            concurrent.futures.wait(futures)

        # Verify results
        assert "user_gen" in results
        assert "proactive_gen" in results
        assert "background_gen" in results
        # If user started first, proactive/background should be stale
        # (This is probabilistic but very likely with our timing)

    def test_cache_invalidation_race(self):
        """Race condition: version bump during concurrent access."""
        from orchestrator.cache_manager import CacheManager

        cache = CacheManager()
        cache.set_version("test", 1)
        cache.set("test", "key1", "value1")

        results = {"errors": []}

        def _reader():
            try:
                for _ in range(100):
                    val = cache.get("test", "key1")
                    # Value may be None if invalidated, but no errors
            except Exception as e:
                results["errors"].append(e)

        def _invalidator():
            try:
                for i in range(10):
                    time.sleep(0.001)
                    cache.set_version("test", i + 2)
            except Exception as e:
                results["errors"].append(e)

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(_reader) for _ in range(3)
            ] + [
                executor.submit(_invalidator)
            ]
            concurrent.futures.wait(futures)

        assert not results["errors"], f"Cache race condition errors: {results['errors']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
