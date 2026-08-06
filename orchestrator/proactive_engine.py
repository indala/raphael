"""
Proactive Engine — idle-time check-in system for Raphael.

Enhanced version with topic monitoring, DDG news checking, and event watching.
Architecture inspired by Mark-XLVII's background monitor pattern.

Features:
  - Idle monitor using existing _last_interaction_time
  - Topic monitoring with DDG news + hash-based change detection
  - Event/reminder watching for time-based alerts
  - Blocked category filtering (crypto/finance/spam)
"""

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# System prompt appended when running a proactive check
PROACTIVE_SYSTEM_INSTRUCTION = (
    "\n\n[PROACTIVE_CHECK] The user has been idle for a while. "
    "If you have something useful to say, respond with 1-2 sentences maximum. "
    "Otherwise respond with '__noop__' to stay silent. "
    "Do NOT use any tools. This is a READ-ONLY check. "
    "Topics: idle reminders, system alerts, time-based suggestions."
)

# ── Blocked categories (never monitor regardless of what user says) ────────────

_BLOCKED_CATEGORIES = {
    # Cryptocurrency / blockchain (various languages)
    "bitcoin", "ethereum", "dogecoin", "solana", "binance", "coinbase",
    "nft", "blockchain", "defi", "altcoin", "memecoin", "coin", "token",
    "crypto", "kripto", "cripto", "krypto", "крипто", "仮想通貨", "暗号資産",
    "cryptocurrency", "web3",
    # Finance spam
    "forex", "trading", "pump", "dump", "moonshot",
    # Adult/gambling
    "casino", "gambling", "poker", "betting",
}


def _is_blocked(topic: str) -> bool:
    """Check if a topic contains blocked keywords."""
    t = topic.lower()
    return any(word in t for word in _BLOCKED_CATEGORIES)


# ── Slug / hash helpers ────────────────────────────────────────────────────────

def _slug(topic: str) -> str:
    """Convert topic to safe filesystem slug."""
    return re.sub(r"[^a-z0-9]+", "_", topic.lower().strip())[:40].strip("_")


def _title_hash(title: str) -> str:
    """Generate hash for headline change detection."""
    return hashlib.md5(title.encode("utf-8", errors="ignore")).hexdigest()[:12]


# ── Topic Monitor ──────────────────────────────────────────────────────────────

class TopicMonitor:
    """
    DDG news checking with hash-based change detection.
    
    Pattern from Mark-XLVII/actions/background_monitor.py:
    - Check each topic once per day
    - Hash-based change detection (only alert on new headlines)
    - Blocked category filtering
    """

    def __init__(self, storage_path: Path):
        """
        Args:
            storage_path: JSON file path for monitor persistence
                         (e.g., _user_settings/proactive_monitors.json)
        """
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._monitors: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load monitors from disk."""
        if not self.storage_path.exists():
            self._monitors = {}
            return
        
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._monitors = data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("Failed to load topic monitors: %s", e)
            self._monitors = {}

    def _save(self) -> None:
        """Save monitors to disk (atomic write)."""
        try:
            # Atomic write pattern: write to temp, then replace
            temp_path = self.storage_path.with_suffix(".tmp")
            temp_path.write_text(
                json.dumps(self._monitors, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            temp_path.replace(self.storage_path)
        except Exception as e:
            logger.error("Failed to save topic monitors: %s", e)

    def add_topic(self, topic: str) -> str:
        """Add a topic to monitor.
        
        Returns:
            Success/error message
        """
        topic = topic.strip()
        if not topic:
            return "Please specify a topic to monitor."
        
        if _is_blocked(topic):
            return "I don't monitor crypto, finance, or spam topics."
        
        slug = _slug(topic)
        if slug in self._monitors:
            return f"Already monitoring: {self._monitors[slug]['topic']}"
        
        self._monitors[slug] = {
            "topic": topic,
            "added": datetime.now().strftime("%Y-%m-%d"),
            "last_check": "",
            "last_hash": "",
        }
        self._save()
        logger.info("Added topic monitor: %s", topic)
        return f"Now monitoring: {topic}"

    def remove_topic(self, topic: str) -> str:
        """Remove a topic from monitoring.
        
        Returns:
            Success/error message
        """
        topic_lower = topic.strip().lower()
        
        # Exact slug match first
        slug = _slug(topic)
        if slug in self._monitors:
            label = self._monitors.pop(slug)["topic"]
            self._save()
            logger.info("Removed topic monitor: %s", label)
            return f"Stopped monitoring: {label}"
        
        # Partial match fallback
        for key, val in list(self._monitors.items()):
            if topic_lower in val.get("topic", "").lower():
                label = self._monitors.pop(key)["topic"]
                self._save()
                logger.info("Removed topic monitor: %s", label)
                return f"Stopped monitoring: {label}"
        
        return f"Not found in monitored topics: {topic}"

    def list_topics(self) -> list[str]:
        """Get list of all monitored topics."""
        return [v.get("topic", k) for k, v in self._monitors.items()]

    def check_all(self) -> list[str]:
        """
        Run all pending topic checks (once per day per topic).
        
        Returns:
            List of [MONITOR_ALERT] strings (empty if nothing new)
        """
        if not self._monitors:
            return []
        
        # Import DDG here to avoid circular imports
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.warning("duckduckgo_search not installed, topic monitoring disabled")
            return []

        today = datetime.now().strftime("%Y-%m-%d")
        alerts = []
        changed = False

        for slug, data in self._monitors.items():
            # Skip if already checked today
            if data.get("last_check") == today:
                continue

            topic = data.get("topic", slug)
            try:
                # DDG news search (max 5 results)
                with DDGS() as ddgs:
                    results = list(ddgs.news(topic, max_results=5))
                
                if not results:
                    self._monitors[slug]["last_check"] = today
                    changed = True
                    continue

                # Get top headline
                top = results[0]
                title = top.get("title", "").strip()
                if not title:
                    continue

                # Check if headline changed
                h = _title_hash(title)
                self._monitors[slug]["last_check"] = today
                changed = True

                if h == data.get("last_hash"):
                    # Same headline as last check — no alert
                    continue

                # New headline detected
                self._monitors[slug]["last_hash"] = h

                # Build alert message
                snippet = top.get("body", "")[:150]
                source = top.get("source", "")
                date = top.get("date", "")
                
                parts = [f"[MONITOR_ALERT] {topic}", f"Headline: {title}"]
                if snippet:
                    parts.append(f"Summary: {snippet}")
                if source:
                    parts.append(f"Source: {source}")
                if date:
                    parts.append(f"Date: {date}")
                
                alert = "\n".join(parts)
                alerts.append(alert)
                logger.info("New headline for '%s': %s", topic, title[:60])

            except Exception as e:
                logger.warning("Check failed for topic '%s': %s", topic, e)
                # Still mark as checked to avoid hammering on errors
                self._monitors[slug]["last_check"] = today
                changed = True

        if changed:
            self._save()

        return alerts


# ── Event Watcher ──────────────────────────────────────────────────────────────

class EventWatcher:
    """
    Time-based reminders and event tracking.
    
    Simple implementation for MVP:
    - Stores reminders with timestamp
    - Checks for due reminders on each proactive check
    """

    def __init__(self, storage_path: Path):
        """
        Args:
            storage_path: JSON file path for event persistence
        """
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._events: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load events from disk."""
        if not self.storage_path.exists():
            self._events = {}
            return
        
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
            self._events = data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning("Failed to load events: %s", e)
            self._events = {}

    def _save(self) -> None:
        """Save events to disk (atomic write)."""
        try:
            temp_path = self.storage_path.with_suffix(".tmp")
            temp_path.write_text(
                json.dumps(self._events, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            temp_path.replace(self.storage_path)
        except Exception as e:
            logger.error("Failed to save events: %s", e)

    def add_reminder(self, when: str, message: str) -> str:
        """Add a time-based reminder.
        
        Args:
            when: ISO timestamp or relative time (e.g., "2026-08-07T14:00")
            message: Reminder text
            
        Returns:
            Success/error message
        """
        try:
            # Parse timestamp
            if "T" in when:
                due_dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
            else:
                # Try to parse relative time (simplified)
                return "Please provide ISO timestamp (YYYY-MM-DDTHH:MM)"
            
            event_id = hashlib.md5(
                f"{when}{message}".encode("utf-8")
            ).hexdigest()[:12]
            
            self._events[event_id] = {
                "due_at": due_dt.isoformat(),
                "message": message,
                "created": datetime.now().isoformat(),
                "fired": False,
            }
            self._save()
            logger.info("Added reminder: %s at %s", message[:30], when)
            return f"Reminder set for {due_dt.strftime('%Y-%m-%d %H:%M')}"
        
        except Exception as e:
            return f"Failed to parse time: {e}"

    def check_due(self) -> list[str]:
        """
        Check for due reminders.
        
        Returns:
            List of [REMINDER] alert strings
        """
        now = datetime.now()
        alerts = []
        changed = False

        for event_id, data in list(self._events.items()):
            if data.get("fired"):
                continue
            
            try:
                due_dt = datetime.fromisoformat(data["due_at"])
                if due_dt <= now:
                    # Reminder is due
                    message = data.get("message", "Reminder")
                    alerts.append(f"[REMINDER] {message}")
                    self._events[event_id]["fired"] = True
                    changed = True
                    logger.info("Fired reminder: %s", message[:30])
            except Exception as e:
                logger.warning("Failed to check event %s: %s", event_id, e)

        if changed:
            self._save()

        return alerts

    def list_upcoming(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get list of upcoming (not fired) reminders."""
        upcoming = [
            {
                "id": k,
                "due_at": v["due_at"],
                "message": v["message"],
            }
            for k, v in self._events.items()
            if not v.get("fired")
        ]
        # Sort by due_at
        upcoming.sort(key=lambda x: x["due_at"])
        return upcoming[:limit]


# ── Main ProactiveEngine ───────────────────────────────────────────────────────

class ProactiveEngine:
    """
    Manages proactive check-in timing and integration.
    
    Enhanced with:
    - Topic monitoring (DDG news)
    - Event watching (reminders)
    - Configurable check intervals
    """

    def __init__(
        self,
        submit_cb: Callable[[str], None],
        get_idle_time_cb: Callable[[], float],
        storage_dir: Path,
        cooldown: float = 60.0,
        min_interval: float = 120.0,
        topics_enabled: bool = True,
        ddg_check_interval_hours: float = 24.0,
    ):
        """
        Args:
            submit_cb: Called with text to submit to LLM.
            get_idle_time_cb: Returns seconds since last user interaction.
            storage_dir: Directory for persistent storage (monitors, events).
            cooldown: Minimum idle seconds before first proactive check.
            min_interval: Minimum seconds between consecutive checks.
            topics_enabled: Enable topic monitoring.
            ddg_check_interval_hours: Hours between DDG topic checks.
        """
        self._submit_cb = submit_cb
        self._get_idle_time = get_idle_time_cb
        self._cooldown = cooldown
        self._min_interval = min_interval
        self._topics_enabled = topics_enabled
        self._ddg_check_interval = ddg_check_interval_hours * 3600  # Convert to seconds
        
        self._last_check_time = 0.0
        self._last_topic_check_time = 0.0
        self._enabled = True
        self._pending_proactive = False
        
        # Initialize subsystems
        storage_dir.mkdir(parents=True, exist_ok=True)
        self.topic_monitor = TopicMonitor(storage_dir / "proactive_monitors.json")
        self.event_watcher = EventWatcher(storage_dir / "proactive_events.json")

    # ── Public API ─────────────────────────────────────────────────────

    def set_enabled(self, enabled: bool):
        """Enable or disable proactive checks at runtime."""
        self._enabled = enabled

    def reset_timer(self):
        """Called after user interaction — resets the idle counter."""
        self._pending_proactive = False

    def check(self) -> bool:
        """
        Called from the main poll loop (every 50ms).
        
        Checks for:
        1. Idle-based proactive check
        2. Topic monitor alerts (daily)
        3. Event reminders (continuous)
        
        Returns:
            True if a proactive check was triggered this cycle.
        """
        if not self._enabled:
            return False

        triggered = False

        # 1. Check for idle-based proactive check
        if self._check_idle_proactive():
            triggered = True

        # 2. Check for topic monitor alerts (if enabled)
        if self._topics_enabled:
            self._check_topic_monitors()

        # 3. Check for event reminders
        self._check_event_reminders()

        return triggered

    def _check_idle_proactive(self) -> bool:
        """Check if idle proactive check should fire."""
        if self._pending_proactive:
            return False

        idle_time = self._get_idle_time()
        now = time.time()

        # Check cooldown and min interval
        if idle_time < self._cooldown:
            return False

        if (now - self._last_check_time) < self._min_interval:
            return False

        # Trigger proactive check
        self._pending_proactive = True
        self._last_check_time = now

        logger.debug("Proactive check triggered (idle: %.0fs)", idle_time)
        self._submit_cb(PROACTIVE_SYSTEM_INSTRUCTION)
        return True

    def _check_topic_monitors(self) -> None:
        """Check topic monitors (rate-limited by ddg_check_interval)."""
        now = time.time()
        if (now - self._last_topic_check_time) < self._ddg_check_interval:
            return

        self._last_topic_check_time = now
        
        try:
            alerts = self.topic_monitor.check_all()
            for alert in alerts:
                # Submit each alert as a proactive check
                self._submit_cb(alert)
                logger.info("Topic alert: %s", alert[:100])
        except Exception as e:
            logger.error("Topic monitor check failed: %s", e)

    def _check_event_reminders(self) -> None:
        """Check for due event reminders."""
        try:
            alerts = self.event_watcher.check_due()
            for alert in alerts:
                # Submit each reminder as a proactive check
                self._submit_cb(alert)
                logger.info("Reminder fired: %s", alert[:100])
        except Exception as e:
            logger.error("Event watcher check failed: %s", e)

    def on_check_complete(self):
        """Called after the proactive check result is processed."""
        self._pending_proactive = False

    # ── Topic Monitor Interface ────────────────────────────────────────

    def add_monitor(self, topic: str) -> str:
        """Add a topic to monitor (proxies to TopicMonitor)."""
        return self.topic_monitor.add_topic(topic)

    def remove_monitor(self, topic: str) -> str:
        """Remove a topic from monitoring."""
        return self.topic_monitor.remove_topic(topic)

    def list_monitors(self) -> list[str]:
        """List all monitored topics."""
        return self.topic_monitor.list_topics()

    # ── Event Watcher Interface ────────────────────────────────────────

    def add_reminder(self, when: str, message: str) -> str:
        """Add a time-based reminder."""
        return self.event_watcher.add_reminder(when, message)

    def list_reminders(self, limit: int = 10) -> list[dict[str, Any]]:
        """List upcoming reminders."""
        return self.event_watcher.list_upcoming(limit)
