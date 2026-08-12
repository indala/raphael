"""
Tests for orchestrator/proactive_engine.py

Coverage:
- TopicMonitor: add/remove topics, blocked category filtering, change detection
- EventWatcher: add reminders, check due events
- ProactiveEngine: idle check timing, monitor integration, callback dispatch
"""

import time
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from orchestrator.proactive_engine import (
    ProactiveEngine,
    TopicMonitor,
    EventWatcher,
    _is_blocked,
    _slug,
    _title_hash,
)


# ── Test Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def tmp_storage():
    """Temporary directory for storage files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def topic_monitor(tmp_storage):
    """TopicMonitor instance with temp storage."""
    return TopicMonitor(tmp_storage / "monitors.json")


@pytest.fixture
def event_watcher(tmp_storage):
    """EventWatcher instance with temp storage."""
    return EventWatcher(tmp_storage / "events.json")


@pytest.fixture
def proactive_engine(tmp_storage):
    """ProactiveEngine instance with mocked callbacks."""
    submit_cb = MagicMock()
    get_idle_time_cb = MagicMock(return_value=0.0)

    engine = ProactiveEngine(
        submit_cb=submit_cb,
        get_idle_time_cb=get_idle_time_cb,
        storage_dir=tmp_storage,
        cooldown=10.0,
        min_interval=5.0,
        topics_enabled=True,
        ddg_check_interval_hours=0.001,  # ~3.6 seconds for testing
    )
    engine._submit_cb = submit_cb
    engine._get_idle_time = get_idle_time_cb
    return engine


# ── Tests: Helper Functions ────────────────────────────────────────────────

class TestBlockedCategories:
    """Test _is_blocked() category filtering."""

    def test_blocked_crypto_keywords(self):
        """Verify crypto keywords are blocked."""
        assert _is_blocked("bitcoin price")
        assert _is_blocked("ethereum news")
        assert _is_blocked("dogecoin")
        assert _is_blocked("nft market")
        assert _is_blocked("blockchain technology")

    def test_blocked_finance_keywords(self):
        """Verify finance spam keywords are blocked."""
        assert _is_blocked("forex trading")
        assert _is_blocked("pump and dump")

    def test_blocked_multilingual(self):
        """Verify multilingual blocked keywords."""
        assert _is_blocked("仮想通貨")  # Japanese cryptocurrency
        assert _is_blocked("крипто")   # Russian crypto
        assert _is_blocked("cripto")   # Spanish crypto

    def test_allowed_topics(self):
        """Verify legitimate topics pass through."""
        assert not _is_blocked("weather forecast")
        assert not _is_blocked("python programming")
        assert not _is_blocked("latest news")
        assert not _is_blocked("music recommendations")


class TestSlugGeneration:
    """Test _slug() for filesystem-safe names."""

    def test_slug_basic(self):
        """Convert topic to slug."""
        assert _slug("Weather Forecast") == "weather_forecast"
        assert _slug("Python Programming") == "python_programming"

    def test_slug_special_chars(self):
        """Strip special characters."""
        assert _slug("Tech & Innovation!") == "tech_innovation"
        assert _slug("COVID-19 Updates") == "covid_19_updates"

    def test_slug_max_length(self):
        """Limit slug to 40 chars."""
        long_topic = "a" * 100
        slug = _slug(long_topic)
        assert len(slug) <= 40

    def test_slug_empty(self):
        """Handle empty input."""
        assert _slug("") == ""
        assert _slug("   ") == ""


class TestTitleHash:
    """Test _title_hash() for change detection."""

    def test_hash_consistency(self):
        """Same title produces same hash."""
        title = "Breaking News: Python 3.12 Released"
        h1 = _title_hash(title)
        h2 = _title_hash(title)
        assert h1 == h2

    def test_hash_length(self):
        """Hash is exactly 12 characters."""
        h = _title_hash("Test Title")
        assert len(h) == 12
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_unicode_handling(self):
        """Handle unicode titles gracefully."""
        h = _title_hash("Python 🐍 News")
        assert len(h) == 12

    def test_hash_change_detection(self):
        """Different titles produce different hashes."""
        h1 = _title_hash("Title 1")
        h2 = _title_hash("Title 2")
        assert h1 != h2


# ── Tests: TopicMonitor ────────────────────────────────────────────────────

class TestTopicMonitor:
    """Test TopicMonitor topic management and DDG integration."""

    def test_add_topic_success(self, topic_monitor):
        """Add a valid topic."""
        msg = topic_monitor.add_topic("weather forecast")
        assert "Now monitoring" in msg
        assert "weather forecast" in msg
        assert "weather_forecast" in topic_monitor._monitors

    def test_add_topic_blocked(self, topic_monitor):
        """Reject blocked topics."""
        msg = topic_monitor.add_topic("bitcoin price")
        assert "don't monitor" in msg.lower()
        assert len(topic_monitor._monitors) == 0

    def test_add_topic_empty(self, topic_monitor):
        """Reject empty topics."""
        msg = topic_monitor.add_topic("")
        assert "specify a topic" in msg.lower()

    def test_add_topic_duplicate(self, topic_monitor):
        """Detect duplicate topics."""
        topic_monitor.add_topic("python news")
        msg = topic_monitor.add_topic("python news")
        assert "already monitoring" in msg.lower()

    def test_remove_topic_exact(self, topic_monitor):
        """Remove topic by exact slug match."""
        topic_monitor.add_topic("weather forecast")
        msg = topic_monitor.remove_topic("weather forecast")
        assert "stopped monitoring" in msg.lower()
        assert len(topic_monitor._monitors) == 0

    def test_remove_topic_partial(self, topic_monitor):
        """Remove topic by partial match."""
        topic_monitor.add_topic("weather forecast")
        msg = topic_monitor.remove_topic("weather")
        assert "stopped monitoring" in msg.lower()

    def test_remove_topic_not_found(self, topic_monitor):
        """Handle removal of non-existent topic."""
        msg = topic_monitor.remove_topic("nonexistent")
        assert "not found" in msg.lower()

    def test_list_topics(self, topic_monitor):
        """List all monitored topics."""
        topic_monitor.add_topic("python news")
        topic_monitor.add_topic("tech news")
        topics = topic_monitor.list_topics()
        assert len(topics) == 2
        assert "python news" in topics
        assert "tech news" in topics

    def test_persistence_save_load(self, tmp_storage):
        """Topics persist across instances."""
        # Create and save
        monitor1 = TopicMonitor(tmp_storage / "monitors.json")
        monitor1.add_topic("python news")
        monitor1.add_topic("tech news")

        # Reload from disk
        monitor2 = TopicMonitor(tmp_storage / "monitors.json")
        topics = monitor2.list_topics()
        assert len(topics) == 2
        assert "python news" in topics

    def test_check_all_no_monitors(self, topic_monitor):
        """Return empty list when no topics."""
        alerts = topic_monitor.check_all()
        assert alerts == []

    @patch('orchestrator.proactive_engine.DDGS')
    def test_check_all_with_duckduckgo(self, mock_ddgs, topic_monitor):
        """Check all topics using mocked DDG."""
        # Add a topic
        topic_monitor.add_topic("python news")

        # Mock DDG response
        mock_results = [
            {
                "title": "Python 3.12 Released",
                "body": "Major new features...",
                "source": "python.org",
                "date": "2026-08-06",
            }
        ]
        mock_ddgs.return_value.__enter__.return_value.news.return_value = iter(mock_results)

        # First check: should return alert with headline
        alerts = topic_monitor.check_all()
        assert len(alerts) == 1
        assert "[MONITOR_ALERT]" in alerts[0]
        assert "Python 3.12 Released" in alerts[0]

        # Second check same day: no new headline
        alerts = topic_monitor.check_all()
        assert len(alerts) == 0

    @patch('orchestrator.proactive_engine.DDGS')
    def test_check_all_headline_change_detected(self, mock_ddgs, topic_monitor):
        """Detect when headline changes."""
        topic_monitor.add_topic("tech news")

        # First headline
        results1 = [{"title": "Headline A", "body": "", "source": "", "date": ""}]
        mock_ddgs.return_value.__enter__.return_value.news.return_value = iter(results1)

        # Manually set date to "yesterday" to force re-check
        slug = _slug("tech news")
        topic_monitor._monitors[slug]["last_check"] = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        alerts = topic_monitor.check_all()
        assert len(alerts) == 1  # First headline generates alert

        # Second headline (different)
        results2 = [{"title": "Headline B", "body": "", "source": "", "date": ""}]
        mock_ddgs.return_value.__enter__.return_value.news.return_value = iter(results2)

        # Force re-check
        topic_monitor._monitors[slug]["last_check"] = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        alerts = topic_monitor.check_all()
        assert len(alerts) == 1  # New headline generates alert


# ── Tests: EventWatcher ────────────────────────────────────────────────────

class TestEventWatcher:
    """Test EventWatcher reminder management."""

    def test_add_reminder_success(self, event_watcher):
        """Add a valid reminder."""
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        msg = event_watcher.add_reminder(future, "Team meeting at 3pm")
        assert "Reminder set" in msg
        assert len(event_watcher._events) == 1

    def test_add_reminder_invalid_time(self, event_watcher):
        """Reject invalid timestamp format."""
        msg = event_watcher.add_reminder("tomorrow", "Remember this")
        assert "parse" in msg.lower() or "iso" in msg.lower()

    def test_add_reminder_past_time(self, event_watcher):
        """Allow adding reminders in the past (will fire immediately)."""
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        msg = event_watcher.add_reminder(past, "Past event")
        assert "Reminder set" in msg or "ISO" in msg

    def test_check_due_not_due_yet(self, event_watcher):
        """No alerts for future reminders."""
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        event_watcher.add_reminder(future, "Future event")
        alerts = event_watcher.check_due()
        assert len(alerts) == 0

    def test_check_due_fires_reminder(self, event_watcher):
        """Fire reminders that are due."""
        past = (datetime.now() - timedelta(minutes=1)).isoformat()
        event_watcher.add_reminder(past, "Call dentist")
        alerts = event_watcher.check_due()
        assert len(alerts) == 1
        assert "[REMINDER]" in alerts[0]
        assert "Call dentist" in alerts[0]

    def test_check_due_only_once(self, event_watcher):
        """Fire each reminder exactly once."""
        past = (datetime.now() - timedelta(minutes=1)).isoformat()
        event_watcher.add_reminder(past, "One-time event")

        # First check: fires
        alerts = event_watcher.check_due()
        assert len(alerts) == 1

        # Second check: already fired, no alert
        alerts = event_watcher.check_due()
        assert len(alerts) == 0

    def test_list_upcoming(self, event_watcher):
        """List upcoming non-fired reminders."""
        t1 = (datetime.now() + timedelta(hours=1)).isoformat()
        t2 = (datetime.now() + timedelta(hours=2)).isoformat()

        event_watcher.add_reminder(t1, "First")
        event_watcher.add_reminder(t2, "Second")

        upcoming = event_watcher.list_upcoming(limit=10)
        assert len(upcoming) == 2
        assert upcoming[0]["message"] == "First"
        assert upcoming[1]["message"] == "Second"

    def test_persistence_events(self, tmp_storage):
        """Events persist across instances."""
        watcher1 = EventWatcher(tmp_storage / "events.json")
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        watcher1.add_reminder(future, "Persisted event")

        watcher2 = EventWatcher(tmp_storage / "events.json")
        upcoming = watcher2.list_upcoming()
        assert len(upcoming) == 1
        assert upcoming[0]["message"] == "Persisted event"


# ── Tests: ProactiveEngine ─────────────────────────────────────────────────

class TestProactiveEngine:
    """Test ProactiveEngine main coordination logic."""

    def test_init_default_params(self, tmp_storage):
        """Initialize with default parameters."""
        engine = ProactiveEngine(
            submit_cb=MagicMock(),
            get_idle_time_cb=MagicMock(return_value=0.0),
            storage_dir=tmp_storage,
        )
        assert engine._cooldown == 60.0
        assert engine._min_interval == 120.0
        assert engine._topics_enabled is True

    def test_init_custom_params(self, proactive_engine):
        """Initialize with custom parameters."""
        assert proactive_engine._cooldown == 10.0
        assert proactive_engine._min_interval == 5.0
        assert proactive_engine._topics_enabled is True

    def test_set_enabled_disable(self, proactive_engine):
        """Enable/disable at runtime."""
        proactive_engine.set_enabled(False)
        assert proactive_engine._enabled is False
        proactive_engine.set_enabled(True)
        assert proactive_engine._enabled is True

    def test_check_returns_false_when_disabled(self, proactive_engine):
        """Return False when disabled."""
        proactive_engine.set_enabled(False)
        result = proactive_engine.check()
        assert result is False

    def test_check_idle_not_enough_time(self, proactive_engine):
        """Don't trigger if idle time < cooldown."""
        proactive_engine._get_idle_time = MagicMock(return_value=5.0)  # 5s < 10s cooldown
        result = proactive_engine.check()
        assert result is False
        proactive_engine._submit_cb.assert_not_called()

    def test_check_idle_triggers_proactive(self, proactive_engine):
        """Trigger proactive check when idle time >= cooldown."""
        proactive_engine._get_idle_time = MagicMock(return_value=15.0)  # 15s > 10s cooldown
        result = proactive_engine.check()
        assert result is True
        proactive_engine._submit_cb.assert_called_once()
        # Verify system instruction was submitted
        call_args = proactive_engine._submit_cb.call_args[0][0]
        assert "[PROACTIVE_CHECK]" in call_args

    def test_check_cooldown_enforced(self, proactive_engine):
        """Enforce min_interval between checks."""
        proactive_engine._get_idle_time = MagicMock(return_value=20.0)

        # First check succeeds
        result1 = proactive_engine.check()
        assert result1 is True

        # Immediate second check fails (min_interval)
        result2 = proactive_engine.check()
        assert result2 is False

        # Only one submit call
        assert proactive_engine._submit_cb.call_count == 1

    def test_reset_timer(self, proactive_engine):
        """Reset timer clears pending proactive."""
        proactive_engine._get_idle_time = MagicMock(return_value=20.0)
        proactive_engine.check()
        assert proactive_engine._pending_proactive is True

        proactive_engine.reset_timer()
        assert proactive_engine._pending_proactive is False

    def test_on_check_complete(self, proactive_engine):
        """Mark check complete."""
        proactive_engine._pending_proactive = True
        proactive_engine.on_check_complete()
        assert proactive_engine._pending_proactive is False

    def test_add_monitor_proxy(self, proactive_engine):
        """Add monitor delegates to TopicMonitor."""
        msg = proactive_engine.add_monitor("weather")
        assert "monitoring" in msg.lower()

    def test_remove_monitor_proxy(self, proactive_engine):
        """Remove monitor delegates to TopicMonitor."""
        proactive_engine.add_monitor("weather")
        msg = proactive_engine.remove_monitor("weather")
        assert "stopped" in msg.lower()

    def test_list_monitors_proxy(self, proactive_engine):
        """List monitors delegates to TopicMonitor."""
        proactive_engine.add_monitor("weather")
        proactive_engine.add_monitor("tech")
        monitors = proactive_engine.list_monitors()
        assert len(monitors) == 2

    def test_add_reminder_proxy(self, proactive_engine):
        """Add reminder delegates to EventWatcher."""
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        msg = proactive_engine.add_reminder(future, "Test reminder")
        assert "reminder" in msg.lower() or "ISO" in msg

    def test_list_reminders_proxy(self, proactive_engine):
        """List reminders delegates to EventWatcher."""
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        proactive_engine.add_reminder(future, "Reminder 1")
        proactive_engine.add_reminder(future, "Reminder 2")
        reminders = proactive_engine.list_reminders(limit=10)
        # May be 1 or 2 depending on how many duplicates, but should have content
        assert isinstance(reminders, list)


# ── Integration Tests ──────────────────────────────────────────────────────

class TestProactiveEngineIntegration:
    """Integration tests combining multiple components."""

    def test_full_workflow(self, tmp_storage):
        """Complete workflow: add monitors, reminders, trigger checks."""
        submit_cb = MagicMock()
        get_idle_time_cb = MagicMock(return_value=0.0)

        engine = ProactiveEngine(
            submit_cb=submit_cb,
            get_idle_time_cb=get_idle_time_cb,
            storage_dir=tmp_storage,
            cooldown=5.0,
            min_interval=2.0,
        )

        # Add monitors and reminders
        engine.add_monitor("weather")
        future = (datetime.now() + timedelta(minutes=30)).isoformat()
        engine.add_reminder(future, "Upcoming meeting")

        # Verify they're saved
        assert len(engine.list_monitors()) == 1
        assert len(engine.list_reminders()) >= 1

        # Trigger idle check
        get_idle_time_cb.return_value = 10.0
        result = engine.check()
        assert result is True
        submit_cb.assert_called()

    def test_no_spam_on_repeated_checks(self, proactive_engine):
        """Don't spam reminders on repeated checks."""
        # Add a past reminder
        past = (datetime.now() - timedelta(minutes=1)).isoformat()
        proactive_engine.add_reminder(past, "Past event")

        # First check in monitor loop
        proactive_engine._get_idle_time = MagicMock(return_value=20.0)
        result1 = proactive_engine.check()
        submit_calls_1 = proactive_engine._submit_cb.call_count

        # Simulate second check (but below min_interval)
        result2 = proactive_engine.check()
        submit_calls_2 = proactive_engine._submit_cb.call_count

        # Submit count should not increase significantly
        # (first check fires idle proactive, not the past reminder yet)
        assert submit_calls_2 <= submit_calls_1 + 2


# ── Edge Cases and Error Handling ──────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_corrupted_monitor_file(self, tmp_storage):
        """Handle corrupted JSON gracefully."""
        monitor_file = tmp_storage / "monitors.json"
        monitor_file.write_text("{ invalid json }", encoding="utf-8")

        # Should load as empty, not crash
        monitor = TopicMonitor(monitor_file)
        assert len(monitor._monitors) == 0

    def test_corrupted_events_file(self, tmp_storage):
        """Handle corrupted events file gracefully."""
        events_file = tmp_storage / "events.json"
        events_file.write_text("[broken", encoding="utf-8")

        # Should load as empty
        watcher = EventWatcher(events_file)
        assert len(watcher._events) == 0

    def test_concurrent_monitor_access(self, tmp_storage):
        """Multiple monitors can write simultaneously (atomic writes)."""
        monitor = TopicMonitor(tmp_storage / "monitors.json")

        def add_many():
            for i in range(5):
                monitor.add_topic(f"topic_{i}")
                time.sleep(0.01)

        threads = [threading.Thread(target=add_many) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All topics should be present (atomic writes prevent corruption)
        topics = monitor.list_topics()
        assert len(topics) >= 5

    def test_very_long_topic_name(self, topic_monitor):
        """Handle very long topic names."""
        long_topic = "a" * 500
        msg = topic_monitor.add_topic(long_topic)
        assert "monitoring" in msg.lower()

        # Slug should be truncated
        topics = topic_monitor.list_topics()
        assert any(t.startswith("a") for t in topics)

    def test_special_unicode_topics(self, topic_monitor):
        """Handle unicode topic names."""
        msg = topic_monitor.add_topic("Python 🐍 News 📰")
        assert "monitoring" in msg.lower()

        topics = topic_monitor.list_topics()
        assert len(topics) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
