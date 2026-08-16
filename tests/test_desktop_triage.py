"""Unit tests for modules/desktop_triage.py."""

from __future__ import annotations

from modules.desktop_triage import NotificationTriageManager, TriagedNotification


def test_triage_classification():
    mgr = NotificationTriageManager()

    assert mgr.classify("Database Outage", "Server is down in production!") == "URGENT"
    assert mgr.classify("Code Review", "Please review PR #42 before 5pm") == "ACTION_REQUIRED"
    assert mgr.classify("Flash Sale", "Limited offer! Buy now for 50% discount!") == "SPAM"
    assert mgr.classify("Weather Update", "Rain expected this afternoon.") == "FYI"


def test_triage_ingestion_and_filtering():
    mgr = NotificationTriageManager()
    n1 = mgr.ingest("Security Alert", "Critical CPU temperature detected")
    n2 = mgr.ingest("System Notice", "Daily backup completed successfully")
    n3 = mgr.ingest("Team Standup", "Meeting in 10 minutes")

    assert n1.category == "URGENT"
    assert n2.category == "FYI"
    assert n3.category == "ACTION_REQUIRED"

    urgent = mgr.get_by_category("URGENT")
    assert len(urgent) == 1
    assert urgent[0].title == "Security Alert"


def test_generate_morning_briefing():
    mgr = NotificationTriageManager()
    mgr.ingest("Urgent Alarm", "Production API is down")
    mgr.ingest("GitHub", "Action required: review PR #101")

    briefing = mgr.generate_morning_briefing(user_name="Mohan", active_goals=["Deploy Raphael v2.0"])

    assert "Good morning, Mohan." in briefing["speech_text"]
    assert "urgent notification" in briefing["speech_text"]
    assert len(briefing["urgent_items"]) == 1
    assert len(briefing["action_items"]) == 1
    assert briefing["active_goals"] == ["Deploy Raphael v2.0"]
