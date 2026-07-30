"""Tests for the Event Bus pub/sub system."""

import threading
from orchestrator.event_bus import (
    EventBus, TOOL_EXECUTED, TOOL_FAILED, TOOL_CREATED, TOOL_OPTIMIZED,
    TOOL_ARCHIVED, MEMORY_UPDATED, AGENT_DELEGATED, TASK_COMPLETED,
)


def setup_function():
    """Clear all subscribers before each test."""
    EventBus().clear()


def test_subscribe_and_publish():
    """Basic subscribe + publish should call the handler."""
    bus = EventBus()
    received = []

    def handler(event, data):
        received.append((event, data))

    bus.subscribe(TOOL_EXECUTED, handler)
    bus.publish(TOOL_EXECUTED, tool="get_weather", latency_ms=42)

    assert len(received) == 1
    assert received[0][0] == TOOL_EXECUTED
    assert received[0][1]["tool"] == "get_weather"
    assert received[0][1]["latency_ms"] == 42


def test_multiple_subscribers():
    """Multiple handlers for the same event all get called."""
    bus = EventBus()
    results = []

    def handler_a(event, data):
        results.append("a")

    def handler_b(event, data):
        results.append("b")

    bus.subscribe(TOOL_EXECUTED, handler_a)
    bus.subscribe(TOOL_EXECUTED, handler_b)
    bus.publish(TOOL_EXECUTED, tool="test")

    assert sorted(results) == ["a", "b"]


def test_unsubscribe():
    """After unsubscribe, handler should not be called."""
    bus = EventBus()
    results = []

    def handler(event, data):
        results.append("called")

    bus.subscribe(TOOL_EXECUTED, handler)
    bus.unsubscribe(TOOL_EXECUTED, handler)
    bus.publish(TOOL_EXECUTED, tool="test")

    assert len(results) == 0


def test_different_events():
    """Handler only receives events it subscribed to."""
    bus = EventBus()
    received = []

    def handler(event, data):
        received.append(event)

    bus.subscribe(TOOL_CREATED, handler)
    bus.publish(TOOL_EXECUTED, tool="x")
    bus.publish(TOOL_CREATED, name="my_tool")
    bus.publish(TOOL_ARCHIVED, name="old_tool")

    assert received == [TOOL_CREATED]


def test_wildcard_subscriber():
    """Handler subscribed to '*' receives all events."""
    bus = EventBus()
    received = []

    def handler(event, data):
        received.append(event)

    bus.subscribe("*", handler)
    bus.publish(TOOL_EXECUTED, tool="x")
    bus.publish(TOOL_CREATED, name="y")
    bus.publish(MEMORY_UPDATED, source="test")

    assert len(received) == 3
    assert TOOL_EXECUTED in received
    assert TOOL_CREATED in received
    assert MEMORY_UPDATED in received


def test_handler_exception_does_not_block():
    """An exception in one handler should not prevent others from running."""
    bus = EventBus()
    results = []

    def failing_handler(event, data):
        raise RuntimeError("oops")

    def good_handler(event, data):
        results.append("ok")

    bus.subscribe(TOOL_EXECUTED, failing_handler)
    bus.subscribe(TOOL_EXECUTED, good_handler)
    bus.publish(TOOL_EXECUTED, tool="test")

    assert results == ["ok"]


def test_thread_safety():
    """Concurrent publish/subscribe operations should not crash or lose events."""
    bus = EventBus()
    results = []
    lock = threading.Lock()

    def handler(event, data):
        with lock:
            results.append(data.get("i"))

    bus.subscribe(TOOL_EXECUTED, handler)

    def publisher(start, count):
        for i in range(start, start + count):
            bus.publish(TOOL_EXECUTED, i=i)

    threads = [
        threading.Thread(target=publisher, args=(0, 50)),
        threading.Thread(target=publisher, args=(50, 50)),
        threading.Thread(target=publisher, args=(100, 50)),
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 150
    assert set(results) == set(range(150))


def test_singleton_behavior():
    """EventBus() always returns the same instance."""
    a = EventBus()
    b = EventBus()
    assert a is b
    assert a._subscribers is b._subscribers


def test_subscriber_count():
    """subscriber_count returns total registrations."""
    bus = EventBus()
    assert bus.subscriber_count == 0

    def h1(e, d): pass
    def h2(e, d): pass

    bus.subscribe(TOOL_EXECUTED, h1)
    bus.subscribe(TOOL_CREATED, h2)
    assert bus.subscriber_count == 2

    bus.subscribe(TOOL_EXECUTED, h2)
    assert bus.subscriber_count == 3

    bus.unsubscribe(TOOL_EXECUTED, h1)
    assert bus.subscriber_count == 2

    bus.clear()
    assert bus.subscriber_count == 0


def test_system_startup_and_shutdown_events():
    """Event constants should be valid publishable names."""
    bus = EventBus()
    received = []

    def handler(event, data):
        received.append(event)

    bus.subscribe("*", handler)
    bus.publish("system.startup", ts=123)
    bus.publish("system.shutdown", ts=456)

    assert "system.startup" in received
    assert "system.shutdown" in received


def test_event_constant_values():
    """Verify all event name constants are non-empty strings."""
    constants = [
        TOOL_EXECUTED, TOOL_FAILED, TOOL_CREATED, TOOL_OPTIMIZED, TOOL_ARCHIVED,
        MEMORY_UPDATED, AGENT_DELEGATED, TASK_COMPLETED,
    ]
    for c in constants:
        assert isinstance(c, str) and len(c) > 0
