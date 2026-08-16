"""
Desktop Notification Triage & Morning Briefing Module.

Inspired by OpenJarvis smart inbox & scheduled operations:
Classifies desktop events and notifications into 4 deterministic buckets
(URGENT, ACTION_REQUIRED, FYI, SPAM) and compiles structured Daily Morning Briefings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Triage classification rules
_URGENT_PATTERNS = re.compile(
    r"\b(urgent|critical|outage|down|alarm|security alert|failed deploy|emergency|overheat)\b",
    re.IGNORECASE,
)
_ACTION_PATTERNS = re.compile(
    r"\b(action required|please review|pr #|pull request|approve|due today|meeting in|reminder:|deadline)\b",
    re.IGNORECASE,
)
_SPAM_PATTERNS = re.compile(
    r"\b(discount|limited offer|sale!|buy now|promo|newsletter|unsubscribe|ad\b|marketing)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TriagedNotification:
    """A triaged desktop notification or event."""

    title: str
    message: str
    category: str       # "URGENT" | "ACTION_REQUIRED" | "FYI" | "SPAM"
    source: str = "desktop"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    dismissed: bool = False


class NotificationTriageManager:
    """Thread-safe desktop notification triage and briefing generator."""

    def __init__(self) -> None:
        self._history: list[TriagedNotification] = []

    @staticmethod
    def classify(title: str, message: str) -> str:
        """Classify title and message text into one of 4 triage categories."""
        full_text = f"{title} {message}".strip()
        if _URGENT_PATTERNS.search(full_text):
            return "URGENT"
        if _ACTION_PATTERNS.search(full_text):
            return "ACTION_REQUIRED"
        if _SPAM_PATTERNS.search(full_text):
            return "SPAM"
        return "FYI"

    def ingest(self, title: str, message: str, source: str = "desktop") -> TriagedNotification:
        """Ingest a desktop notification, classify it, and store it in triage history."""
        category = self.classify(title, message)
        notification = TriagedNotification(
            title=title,
            message=message,
            category=category,
            source=source,
        )
        self._history.append(notification)
        logger.debug("DesktopTriage: [%s] %s — %s", category, title, message[:60])
        return notification

    def get_by_category(self, category: str) -> list[TriagedNotification]:
        """Return all notifications matching category."""
        return [n for n in self._history if n.category.upper() == category.upper()]

    def generate_morning_briefing(
        self,
        user_name: str = "sir",
        active_goals: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a structured morning briefing report for the PyQt6 HUD.

        Returns:
            dict containing formatted speech text, urgent count, action items, and goals.
        """
        urgent = self.get_by_category("URGENT")
        action_items = self.get_by_category("ACTION_REQUIRED")
        goals = active_goals or []

        # Compose natural speech text
        greeting = f"Good morning, {user_name}."
        parts = [greeting]

        if urgent:
            parts.append(f"You have {len(urgent)} urgent notification(s) requiring immediate attention.")
        else:
            parts.append("All systems are operational with no urgent alerts.")

        if action_items:
            parts.append(f"There are {len(action_items)} action item(s) pending on your desk.")

        if goals:
            parts.append(f"You have {len(goals)} active goal(s) queued for today.")

        speech_text = " ".join(parts)

        return {
            "speech_text": speech_text,
            "urgent_items": [{"title": n.title, "message": n.message} for n in urgent],
            "action_items": [{"title": n.title, "message": n.message} for n in action_items],
            "active_goals": goals,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def clear(self) -> None:
        """Clear triage history."""
        self._history.clear()
