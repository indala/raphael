"""
Tests for cron/scheduler.py and cron/jobs.py

Coverage:
- Schedule parsing (intervals, cron, timestamps)
- Job CRUD operations
- Due job detection
- Ticker execution
- File locking (Windows-compatible)
- State tracking and concurrency
"""

import json
import threading
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from cron import jobs as cron_jobs
from cron import scheduler as cron_scheduler
from cron.jobs import (
    add_job,
    remove_job,
    get_job,
    list_jobs,
    update_job,
    get_due_jobs,
    parse_schedule,
    mark_job_run,
    disable_job,
    enable_job,
    clear_all_jobs,
    get_job_status,
)


# ── Test Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_jobs():
    """Clean up all jobs before and after each test."""
    clear_all_jobs()
    yield
    clear_all_jobs()


# ── Tests: Schedule Parsing ────────────────────────────────────────────────

class TestScheduleParsing:
    """Test parse_schedule() for all supported formats."""

    def test_parse_minutes(self):
        """Parse relative minutes: '30m'."""
        result = parse_schedule("30m")
        assert result["kind"] == "once"
        assert result["value"] == 30
        assert result["unit"] == "m"
        assert "next_run" in result

    def test_parse_hours(self):
        """Parse relative hours: '2h'."""
        result = parse_schedule("2h")
        assert result["kind"] == "once"
        assert result["value"] == 2
        assert result["unit"] == "h"

    def test_parse_days(self):
        """Parse relative days: '1d'."""
        result = parse_schedule("1d")
        assert result["kind"] == "once"
        assert result["value"] == 1
        assert result["unit"] == "d"

    def test_parse_interval_minutes(self):
        """Parse recurring interval: 'every 30m'."""
        result = parse_schedule("every 30m")
        assert result["kind"] == "interval"
        assert result["value"] == 30
        assert result["unit"] == "m"

    def test_parse_interval_hours(self):
        """Parse recurring hours: 'every 2h'."""
        result = parse_schedule("every 2h")
        assert result["kind"] == "interval"
        assert result["value"] == 2
        assert result["unit"] == "h"

    def test_parse_interval_days(self):
        """Parse recurring days: 'every 1d'."""
        result = parse_schedule("every 1d")
        assert result["kind"] == "interval"
        assert result["value"] == 1
        assert result["unit"] == "d"

    def test_parse_iso_timestamp(self):
        """Parse ISO timestamp: '2026-08-07T14:00'."""
        ts = "2026-08-07T14:00"
        result = parse_schedule(ts)
        assert result["kind"] == "once"
        assert result["value"] == ts

    def test_parse_iso_timestamp_with_z(self):
        """Parse ISO timestamp with Z suffix."""
        ts = "2026-08-07T14:00Z"
        result = parse_schedule(ts)
        assert result["kind"] == "once"

    def test_parse_cron_expression(self):
        """Parse cron expression (if croniter available)."""
        result = parse_schedule("0 9 * * *")
        # croniter may not be installed; accept either result
        assert result["kind"] in ["cron", "unsupported"]

    def test_parse_invalid_schedule(self):
        """Reject invalid schedule strings."""
        result = parse_schedule("invalid")
        assert result["kind"] == "unsupported"
        assert "error" in result

    def test_parse_empty_string(self):
        """Reject empty schedule."""
        result = parse_schedule("")
        assert result["kind"] == "unsupported"

    def test_parse_whitespace_handling(self):
        """Handle leading/trailing whitespace."""
        result = parse_schedule("  30m  ")
        assert result["kind"] == "once"
        assert result["value"] == 30

    def test_parse_case_insensitive(self):
        """Parse schedule case-insensitively."""
        result1 = parse_schedule("30m")
        result2 = parse_schedule("30M")
        assert result1["kind"] == result2["kind"]
        assert result1["value"] == result2["value"]


# ── Tests: Job CRUD ────────────────────────────────────────────────────────

class TestJobCRUD:
    """Test job creation, reading, updating, deletion."""

    def test_add_job_simple(self):
        """Add a basic job."""
        job = add_job(
            prompt="Check weather",
            schedule="30m",
            name="Weather Check"
        )
        assert job["id"]
        assert job["prompt"] == "Check weather"
        assert job["name"] == "Weather Check"
        assert job["enabled"] is True

    def test_add_job_with_description(self):
        """Add job with optional description."""
        job = add_job(
            prompt="Send report",
            schedule="every 1d",
            name="Daily Report",
            description="Generate and send daily report"
        )
        assert job["description"] == "Generate and send daily report"

    def test_add_job_disabled(self):
        """Add job in disabled state."""
        job = add_job(
            prompt="Disabled task",
            schedule="30m",
            enabled=False
        )
        assert job["enabled"] is False

    def test_add_job_persists(self):
        """Jobs persist across instances."""
        job1 = add_job(prompt="Task 1", schedule="30m")
        job_id = job1["id"]

        job2 = get_job(job_id)
        assert job2 is not None
        assert job2["prompt"] == "Task 1"

    def test_get_job_not_found(self):
        """Return None for non-existent job."""
        result = get_job("nonexistent_id")
        assert result is None

    def test_remove_job(self):
        """Remove a job."""
        job = add_job(prompt="Task", schedule="30m")
        job_id = job["id"]

        removed = remove_job(job_id)
        assert removed is True
        assert get_job(job_id) is None

    def test_remove_nonexistent_job(self):
        """Removing non-existent job returns False."""
        removed = remove_job("nonexistent")
        assert removed is False

    def test_list_jobs_empty(self):
        """List returns empty list when no jobs."""
        jobs = list_jobs()
        assert jobs == []

    def test_list_jobs_multiple(self):
        """List all jobs."""
        add_job(prompt="Task 1", schedule="30m")
        add_job(prompt="Task 2", schedule="1h")
        add_job(prompt="Task 3", schedule="1d")

        jobs = list_jobs()
        assert len(jobs) == 3

    def test_list_jobs_enabled_only(self):
        """Filter to enabled jobs only."""
        add_job(prompt="Enabled 1", schedule="30m", enabled=True)
        add_job(prompt="Disabled", schedule="30m", enabled=False)
        add_job(prompt="Enabled 2", schedule="30m", enabled=True)

        enabled = list_jobs(enabled_only=True)
        assert len(enabled) == 2
        assert all(j["enabled"] for j in enabled)

    def test_update_job_name(self):
        """Update job name."""
        job = add_job(prompt="Task", schedule="30m", name="Old Name")
        updated = update_job(job["id"], name="New Name")
        assert updated["name"] == "New Name"

    def test_update_job_schedule(self):
        """Update job schedule."""
        job = add_job(prompt="Task", schedule="30m")
        updated = update_job(job["id"], schedule="1h")
        assert updated["schedule_format"] == "1h"
        assert updated["schedule"]["kind"] == "once"
        assert updated["schedule"]["value"] == 1
        assert updated["schedule"]["unit"] == "h"

    def test_update_nonexistent_job(self):
        """Updating non-existent job returns None."""
        result = update_job("nonexistent", name="New Name")
        assert result is None

    def test_disable_enable_job(self):
        """Disable and re-enable a job."""
        job = add_job(prompt="Task", schedule="30m", enabled=True)
        job_id = job["id"]

        assert disable_job(job_id) is True
        assert get_job(job_id)["enabled"] is False

        assert enable_job(job_id) is True
        assert get_job(job_id)["enabled"] is True


# ── Tests: Due Job Detection ───────────────────────────────────────────────

class TestDueJobDetection:
    """Test get_due_jobs() and job lifecycle."""

    def test_no_due_jobs_empty(self):
        """No due jobs when list is empty."""
        due = get_due_jobs()
        assert due == []

    def test_no_due_jobs_future(self):
        """Future jobs are not due."""
        future = (datetime.now() + timedelta(hours=1)).isoformat()
        add_job(prompt="Future task", schedule=future)

        due = get_due_jobs()
        assert len(due) == 0

    def test_due_job_past_timestamp(self):
        """Jobs with past timestamps are due."""
        past = (datetime.now() - timedelta(minutes=5)).isoformat()
        job = add_job(prompt="Past task", schedule=past)

        due = get_due_jobs()
        assert len(due) >= 1
        # Find our job in the due list
        found = any(j["id"] == job["id"] for j in due)
        assert found

    def test_due_job_grace_window(self):
        """Jobs just over due time (within grace window) are due."""
        # 2 seconds ago
        past = (datetime.now() - timedelta(seconds=2)).isoformat()
        job = add_job(prompt="Grace window task", schedule=past)

        # Grace window is 5 seconds by default
        due = get_due_jobs(grace_window_seconds=5.0)
        found = any(j["id"] == job["id"] for j in due)
        assert found

    def test_skip_disabled_jobs(self):
        """Disabled jobs are not returned as due."""
        past = (datetime.now() - timedelta(minutes=1)).isoformat()
        job = add_job(prompt="Disabled task", schedule=past, enabled=False)

        due = get_due_jobs()
        found = any(j["id"] == job["id"] for j in due)
        assert not found

    def test_mark_job_run_once(self):
        """Mark one-time job as run (no next_run)."""
        job = add_job(prompt="One-time", schedule="30m")
        job_id = job["id"]

        mark_job_run(job_id, success=True)

        updated = get_job(job_id)
        assert updated["run_count"] == 1
        assert updated["last_run"] is not None
        assert updated["next_run"] is None  # One-time jobs don't recur

    def test_mark_job_run_interval(self):
        """Mark recurring job as run (calculates next_run)."""
        job = add_job(prompt="Recurring", schedule="every 30m")
        job_id = job["id"]

        mark_job_run(job_id, success=True)

        updated = get_job(job_id)
        assert updated["run_count"] == 1
        assert updated["next_run"] is not None
        # Next run should be ~30 minutes from now
        next_run = datetime.fromisoformat(updated["next_run"])
        now = datetime.now()
        delta = (next_run - now).total_seconds()
        assert 1200 < delta < 1900  # Between 20-30 minutes

    def test_mark_job_run_with_error(self):
        """Mark failed job run."""
        job = add_job(prompt="Task", schedule="30m")
        job_id = job["id"]

        mark_job_run(job_id, success=False, error="Database connection failed")

        updated = get_job(job_id)
        assert updated["last_error"] == "Database connection failed"

    def test_job_status(self):
        """Get job status snapshot."""
        job = add_job(prompt="Task", schedule="30m", name="Status Check")
        job_id = job["id"]

        status = get_job_status(job_id)
        assert status["id"] == job_id
        assert status["name"] == "Status Check"
        assert status["enabled"] is True
        assert status["run_count"] == 0


# ── Tests: Scheduler Execution ─────────────────────────────────────────────

class TestSchedulerExecution:
    """Test tick(), job execution, and background threads."""

    def test_tick_no_jobs(self):
        """Tick with no jobs executes nothing."""
        executed = cron_scheduler.tick(verbose=False)
        assert executed == 0

    def test_tick_executes_due_jobs(self):
        """Tick executes all due jobs."""
        # Create 3 past jobs
        for i in range(3):
            past = (datetime.now() - timedelta(minutes=1)).isoformat()
            add_job(prompt=f"Task {i}", schedule=past)

        # Mock run_job to avoid actual LLM calls
        with patch("cron.scheduler.run_job_background") as mock_run:
            mock_run.return_value = None
            executed = cron_scheduler.tick(verbose=False, sync=True)

        assert executed == 3

    def test_ticker_thread_lifecycle(self):
        """Start and stop ticker thread."""
        assert not cron_scheduler.is_ticker_running()

        # Start ticker
        result = cron_scheduler.start_ticker_thread(interval=2, verbose=False)
        assert result is True
        time.sleep(0.1)
        assert cron_scheduler.is_ticker_running()

        # Stop ticker
        result = cron_scheduler.stop_ticker_thread(timeout=5.0)
        assert result is True
        time.sleep(0.1)
        assert not cron_scheduler.is_ticker_running()

    def test_ticker_already_running(self):
        """Starting ticker when already running returns False."""
        cron_scheduler.start_ticker_thread(interval=2)
        time.sleep(0.1)

        result = cron_scheduler.start_ticker_thread(interval=2)
        assert result is False

        # Cleanup
        cron_scheduler.stop_ticker_thread()

    def test_ticker_stops_gracefully(self):
        """Ticker stops within timeout."""
        cron_scheduler.start_ticker_thread(interval=60)  # Long interval
        time.sleep(0.1)

        start = time.time()
        result = cron_scheduler.stop_ticker_thread(timeout=2.0)
        elapsed = time.time() - start

        assert result is True
        assert elapsed < 2.5  # Should stop quickly

    def test_running_jobs_tracking(self):
        """Track running jobs in state."""
        running = cron_scheduler.get_running_jobs()
        assert isinstance(running, list)
        assert len(running) == 0

    def test_scheduler_status(self):
        """Get overall scheduler status."""
        status = cron_scheduler.get_scheduler_status()
        assert "ticker_running" in status
        assert "running_jobs" in status
        assert "last_heartbeat" in status

    def test_heartbeat_recording(self):
        """Record and retrieve heartbeat."""
        cron_scheduler._record_ticker_heartbeat()
        heartbeat = cron_scheduler.get_ticker_heartbeat()

        assert heartbeat is not None
        assert "timestamp" in heartbeat
        assert "running_jobs" in heartbeat

    def test_ticker_health_check(self):
        """Check if ticker is healthy (recent heartbeat)."""
        cron_scheduler._record_ticker_heartbeat()

        assert cron_scheduler.is_ticker_healthy(max_age_seconds=10.0) is True
        assert cron_scheduler.is_ticker_healthy(max_age_seconds=0.0) is False


# ── Tests: File Locking (Windows Compatibility) ────────────────────────────

class TestFileLocking:
    """Test cross-process file locking (msvcrt/fcntl)."""

    def test_jobs_lock_context_manager(self):
        """Jobs lock can be acquired and released."""
        # This should not raise an error
        with cron_jobs._jobs_lock():
            jobs = cron_jobs._load_jobs()
            assert isinstance(jobs, dict)

    def test_concurrent_job_writes(self):
        """Multiple threads writing jobs concurrently."""
        results = []

        def add_job_thread(i):
            try:
                job = add_job(prompt=f"Task {i}", schedule="30m")
                results.append(job["id"])
            except Exception as e:
                results.append(f"error:{e}")

        threads = [threading.Thread(target=add_job_thread, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All jobs should be added successfully (no corrupt state)
        assert len(results) == 5
        all_jobs = list_jobs()
        assert len(all_jobs) == 5

    def test_atomic_file_writes(self):
        """Job file writes are atomic (no partial writes)."""
        # Add a job
        job1 = add_job(prompt="Task 1", schedule="30m")

        # Load jobs file directly
        jobs_path = cron_jobs._get_jobs_path()
        content = jobs_path.read_text(encoding="utf-8")
        data = json.loads(content)

        # File should be valid JSON (not truncated)
        assert isinstance(data, dict)
        assert len(data) >= 1


# ── Tests: Edge Cases and Error Handling ───────────────────────────────────

class TestEdgeCases:
    """Test edge cases and error scenarios."""

    def test_corrupted_jobs_file(self):
        """Handle corrupted jobs.json gracefully."""
        jobs_path = cron_jobs._get_jobs_path()
        jobs_path.write_text("{ invalid json }", encoding="utf-8")

        # Should load as empty, not crash
        jobs = cron_jobs._load_jobs()
        assert jobs == {}

    def test_add_job_invalid_schedule(self):
        """Reject jobs with invalid schedules."""
        with pytest.raises(ValueError):
            add_job(prompt="Task", schedule="invalid_schedule")

    def test_clear_all_jobs(self):
        """Clear all jobs."""
        add_job(prompt="Task 1", schedule="30m")
        add_job(prompt="Task 2", schedule="30m")

        count = clear_all_jobs()
        assert count == 2
        assert list_jobs() == []

    def test_very_long_prompt(self):
        """Handle very long job prompts."""
        long_prompt = "Task description " * 100
        job = add_job(prompt=long_prompt, schedule="30m")

        retrieved = get_job(job["id"])
        assert retrieved["prompt"] == long_prompt

    def test_unicode_in_job_fields(self):
        """Handle unicode in job prompts and names."""
        job = add_job(
            prompt="Check 天気 (weather) 🌤️",
            schedule="30m",
            name="日本語テスト"
        )

        retrieved = get_job(job["id"])
        assert "天気" in retrieved["prompt"]
        assert "テスト" in retrieved["name"]

    def test_special_characters_in_schedule(self):
        """Handle special characters in job names."""
        job = add_job(
            prompt="Task",
            schedule="30m",
            name="Job & Task (Special) [1/2]"
        )

        retrieved = get_job(job["id"])
        assert retrieved["name"] == "Job & Task (Special) [1/2]"

    def test_job_run_count_increment(self):
        """Run count increments correctly."""
        job = add_job(prompt="Task", schedule="every 1h")
        job_id = job["id"]

        assert get_job(job_id)["run_count"] == 0

        mark_job_run(job_id, success=True)
        assert get_job(job_id)["run_count"] == 1

        mark_job_run(job_id, success=True)
        assert get_job(job_id)["run_count"] == 2


# ── Integration Tests ──────────────────────────────────────────────────────

class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_job_lifecycle(self):
        """Complete job lifecycle: create → schedule → run → complete."""
        # Create job
        job = add_job(
            prompt="Integration test task",
            schedule="every 30m",
            name="Test Job"
        )
        job_id = job["id"]

        # Verify job is scheduled
        assert get_job(job_id) is not None
        assert get_job(job_id)["enabled"] is True

        # Mark as run
        mark_job_run(job_id, success=True)

        # Verify run count incremented
        updated = get_job(job_id)
        assert updated["run_count"] == 1
        assert updated["next_run"] is not None

        # Disable and verify
        disable_job(job_id)
        assert get_job(job_id)["enabled"] is False

        # Re-enable and remove
        enable_job(job_id)
        assert remove_job(job_id) is True
        assert get_job(job_id) is None

    def test_multiple_jobs_various_schedules(self):
        """Create and manage multiple jobs with different schedules."""
        job1 = add_job(prompt="Every 30 minutes", schedule="every 30m")
        job2 = add_job(prompt="Every 2 hours", schedule="every 2h")
        job3 = add_job(prompt="Once in 1 day", schedule="1d")

        future = (datetime.now() + timedelta(days=7)).isoformat()
        job4 = add_job(prompt="Weekly report", schedule=future)

        # Verify all jobs exist
        all_jobs = list_jobs()
        assert len(all_jobs) >= 4

        # Verify schedule types are preserved
        assert get_job(job1["id"])["schedule"]["kind"] == "interval"
        assert get_job(job3["id"])["schedule"]["kind"] == "once"
        assert get_job(job4["id"])["schedule"]["kind"] == "once"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
