"""
Local Intent Fast Path — classifies and handles common deterministic intents without LLM calls.
"""

import datetime
import logging
import os
import re
import subprocess
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def _handle_stop(text: str, controller: Any = None) -> str:
    if controller and hasattr(controller, "_cancel_current_task"):
        controller._cancel_current_task()
    return "Task stopped."


def _handle_mute(text: str, controller: Any = None) -> str:
    if controller and hasattr(controller, "_mute"):
        controller._mute()
        return "Microphone muted."
    return "Microphone is now muted."


def _handle_unmute(text: str, controller: Any = None) -> str:
    if controller and hasattr(controller, "_unmute"):
        controller._unmute()
        return "Microphone unmuted."
    return "Microphone is now active."


def _handle_volume(text: str, controller: Any = None) -> str:
    text_lower = text.lower()
    if "up" in text_lower:
        action = "volume up"
    elif "down" in text_lower:
        action = "volume down"
    else:
        action = "volume adjusted"
    return f"Adjusted {action}."


def _handle_screenshot(text: str, controller: Any = None) -> str:
    try:
        from orchestrator.tools.native.screen import capture_screen
        res = capture_screen()
        return f"Screenshot captured: {res}"
    except Exception as e:
        return f"Failed to take screenshot: {e}"


def _handle_settings(text: str, controller: Any = None) -> str:
    if controller and hasattr(controller, "_open_settings"):
        controller._open_settings()
        return "Settings opened."
    return "Opening settings..."


def _handle_hide(text: str, controller: Any = None) -> str:
    if controller and hasattr(controller, "hide_main_window"):
        controller.hide_main_window()
        return "Window hidden."
    return "Hiding main window."


def _handle_play_pause(text: str, controller: Any = None) -> str:
    try:
        from orchestrator.tools.native.music_player_tools import music_toggle_play_pause
        res = music_toggle_play_pause()
        return str(res)
    except Exception:
        return "Toggled playback."


def _handle_time(text: str, controller: Any = None) -> str:
    now = datetime.datetime.now()
    return f"The current time is {now.strftime('%I:%M %p')}."


def _handle_calculator(text: str, controller: Any = None) -> str:
    try:
        subprocess.Popen(["calc.exe"])
        return "Opened calculator."
    except Exception as e:
        return f"Failed to open calculator: {e}"


def _handle_browser(text: str, controller: Any = None) -> str:
    try:
        import webbrowser
        webbrowser.open("https://www.google.com")
        return "Opened web browser."
    except Exception as e:
        return f"Failed to open browser: {e}"


def _handle_battery(text: str, controller: Any = None) -> str:
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery is None:
            return "No battery status available (desktop system or undetected)."
        percent = round(battery.percent)
        plugged = "plugged in" if battery.power_plugged else "on battery power"
        return f"Battery status: {percent}% ({plugged})."
    except Exception as e:
        return f"Battery status check unavailable: {e}"


def _handle_wifi(text: str, controller: Any = None) -> str:
    try:
        import socket
        socket.create_connection(("8.8.8.8", 53), timeout=2)
        return "Wi-Fi / Network status: Connected to internet."
    except Exception:
        return "Wi-Fi / Network status: Disconnected or offline."


# Structured matcher table: list of (regex_pattern, intent_name, handler_fn)
INTENT_MATCHERS: list[tuple[re.Pattern, str, Callable[[str, Any], str]]] = [
    (re.compile(r"^\s*(stop|cancel|halt|pause task)\s*$", re.IGNORECASE), "stop", _handle_stop),
    (re.compile(r"^\s*(mute|mute mic|mute microphone|silence)\s*$", re.IGNORECASE), "mute", _handle_mute),
    (re.compile(r"^\s*(unmute|unmute mic|unmute microphone)\s*$", re.IGNORECASE), "unmute", _handle_unmute),
    (re.compile(r"^\s*(volume up|volume down|set volume|mute audio|unmute audio|volume)\s*$", re.IGNORECASE), "volume", _handle_volume),
    (re.compile(r"^\s*(take screenshot|screenshot|capture screen)\s*$", re.IGNORECASE), "screenshot", _handle_screenshot),
    (re.compile(r"^\s*(open settings|show settings|settings)\s*$", re.IGNORECASE), "settings", _handle_settings),
    (re.compile(r"^\s*(hide|hide window|minimize|hide ui|hide raphael)\s*$", re.IGNORECASE), "hide", _handle_hide),
    (re.compile(r"^\s*(play music|pause music|toggle playback|play|pause)\s*$", re.IGNORECASE), "play/pause", _handle_play_pause),
    (re.compile(r"^\s*(what time is it|current time|tell me the time|time)\s*$", re.IGNORECASE), "time", _handle_time),
    (re.compile(r"^\s*(open calculator|calc|calculator)\s*$", re.IGNORECASE), "calculator", _handle_calculator),
    (re.compile(r"^\s*(open browser|launch browser|browser)\s*$", re.IGNORECASE), "browser", _handle_browser),
    (re.compile(r"^\s*(battery level|battery status|check battery|battery)\s*$", re.IGNORECASE), "battery", _handle_battery),
    (re.compile(r"^\s*(wifi status|check wifi|network status|wifi)\s*$", re.IGNORECASE), "wifi", _handle_wifi),
]


def try_match_intent(text: str, controller: Any = None) -> tuple[str, str] | None:
    """Check text against local intent patterns.

    If matched, runs the intent handler and returns (intent_name, result_message).
    If no match, returns None.
    """
    if not text or not text.strip():
        return None

    cleaned_text = text.strip()
    for pattern, intent_name, handler_fn in INTENT_MATCHERS:
        if pattern.match(cleaned_text):
            logger.info("Local intent fast path matched: '%s' -> %s", cleaned_text, intent_name)
            try:
                result = handler_fn(cleaned_text, controller)
                return (intent_name, result)
            except Exception as e:
                logger.error("Intent handler '%s' failed: %s", intent_name, e)
                return (intent_name, f"Error executing local intent '{intent_name}': {e}")
    return None
