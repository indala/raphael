"""Tests for the upgraded multiplexed C# Hybrid Bridge."""

import concurrent.futures
import time

from hybrid.bridge import (
    LazyBridge,
    is_available,
    list_methods,
    ping,
    version,
)


def test_bridge_liveness_and_introspection():
    """Verify ping, version, and list_methods endpoints."""
    if not is_available():
        return

    assert ping() is True, "Ping failed"
    ver = version()
    assert ver is not None, "Version returned None"
    assert "version" in ver
    assert ver["framework"] == ".NET 10"

    methods = list_methods()
    assert isinstance(methods, list)
    assert "ping" in methods
    assert "clipboard_has_text" in methods
    assert "system_snapshot" in methods


def test_concurrent_bridge_calls():
    """Verify that multiple concurrent threads can make calls through the bridge simultaneously."""
    if not is_available():
        return

    def worker(idx: int):
        ok, res = LazyBridge.call_checked("ping")
        assert ok and res == "pong"
        ok_clip, _ = LazyBridge.call_checked("clipboard_has_text")
        assert ok_clip is True
        return idx

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, i) for i in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.perf_counter() - start

    assert len(results) == 20
    # 20 concurrent calls (40 bridge requests) should complete in a fraction of a second
    assert elapsed < 3.0, f"Concurrent execution took too long: {elapsed:.2f}s"
