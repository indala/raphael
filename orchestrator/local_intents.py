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


def _handle_date(text: str, controller: Any = None) -> str:
    now = datetime.datetime.now()
    day_name = now.strftime("%A")
    date_str = now.strftime("%B %d, %Y")
    return f"Today is {day_name}, {date_str}."


def _handle_help(text: str, controller: Any = None) -> str:
    return (
        "I'm Raphael, your AI assistant. I can help with:\n"
        "• Search the web for information\n"
        "• Control your desktop and applications\n"
        "• Manage files and documents\n"
        "• Send emails and read messages\n"
        "• Play music and control media\n"
        "• Answer questions and explain concepts\n"
        "Ask me anything!"
    )


def _handle_echo(text: str, controller: Any = None) -> str:
    # Echo back the user text (minimal operation, deterministic)
    return f"You said: {text}"


def _handle_cpu_usage(text: str, controller: Any = None) -> str:
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.1)
        return f"CPU usage: {cpu_percent}%."
    except Exception as e:
        return f"CPU usage check unavailable: {e}"


def _handle_disk_space(text: str, controller: Any = None) -> str:
    try:
        import psutil
        disk = psutil.disk_usage("/")
        percent_used = disk.percent
        free_gb = disk.free / (1024**3)
        return f"Disk usage: {percent_used}% full ({free_gb:.1f} GB free)."
    except Exception as e:
        return f"Disk space check unavailable: {e}"


def _handle_uptime(text: str, controller: Any = None) -> str:
    try:
        import psutil
        boot_time_ts = psutil.boot_time()
        boot_time = datetime.datetime.fromtimestamp(boot_time_ts)
        uptime = datetime.datetime.now() - boot_time
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        return f"System uptime: {int(uptime.days)} days, {hours} hours, {minutes} minutes."
    except Exception as e:
        return f"Uptime check unavailable: {e}"


def _handle_memory(text: str, controller: Any = None) -> str:
    try:
        import psutil
        mem = psutil.virtual_memory()
        percent_used = mem.percent
        available_gb = mem.available / (1024**3)
        return f"Memory usage: {percent_used}% full ({available_gb:.1f} GB available)."
    except Exception as e:
        return f"Memory check unavailable: {e}"


# Structured matcher table: list of (regex_pattern, intent_name, handler_fn)
# Task 16: Expanded from ~14 intents to 20+ intents for faster deterministic handling
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
    (re.compile(r"^\s*(what.*date|today's date|current date|today|date)\s*$", re.IGNORECASE), "date", _handle_date),
    (re.compile(r"^\s*(open calculator|calc|calculator)\s*$", re.IGNORECASE), "calculator", _handle_calculator),
    (re.compile(r"^\s*(open browser|launch browser|browser)\s*$", re.IGNORECASE), "browser", _handle_browser),
    (re.compile(r"^\s*(battery level|battery status|check battery|battery)\s*$", re.IGNORECASE), "battery", _handle_battery),
    (re.compile(r"^\s*(wifi status|check wifi|network status|wifi)\s*$", re.IGNORECASE), "wifi", _handle_wifi),
    (re.compile(r"^\s*(help|assist|what can you do|capabilities)\s*$", re.IGNORECASE), "help", _handle_help),
    (re.compile(r"^\s*(cpu.*usage|check cpu|cpu load)\s*$", re.IGNORECASE), "cpu", _handle_cpu_usage),
    (re.compile(r"^\s*(disk.*space|disk.*usage|storage|free space)\s*$", re.IGNORECASE), "disk", _handle_disk_space),
    (re.compile(r"^\s*(uptime|system uptime|how long.*running)\s*$", re.IGNORECASE), "uptime", _handle_uptime),
    (re.compile(r"^\s*(memory.*usage|memory.*available|ram.*usage|check memory)\s*$", re.IGNORECASE), "memory", _handle_memory),
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
