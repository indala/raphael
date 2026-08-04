"""Power and notification tools — system power control and desktop toasts.

All operations delegate to the C# hybrid bridge (PowerManager / ToastNotifier),
which is the single owner of the Windows API surface. Destructive power
operations (shutdown / reboot) require an explicit confirm flag.
"""

from modules import ui_control as _ui_control


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "power_sleep",
                "description": "Put the computer into sleep mode (suspend to RAM) immediately. The current session stays open and resumes where it left off when the user wakes the machine. Use when the user asks to sleep or suspend the computer.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "power_hibernate",
                "description": "Hibernate the computer (suspend to disk) immediately. The full memory state is written to disk so everything is restored on the next boot. Use when the user asks to hibernate or power the machine down while preserving the session.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "power_lock",
                "description": "Lock the workstation, showing the Windows lock screen and requiring the user's password or PIN to continue. Use when the user asks to lock the screen or secure the computer. Does not close any running programs.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "power_shutdown",
                "description": "Shut down the computer completely. DANGEROUS: this closes all programs and powers off the machine, so it MUST NOT be called without the user explicitly asking to shut down, and it requires confirm=true as a safety gate. Any other value is ignored.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirm": {
                            "type": "boolean",
                            "description": "Must be true to actually shut down; anything else is a no-op",
                        },
                    },
                    "required": ["confirm"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "power_reboot",
                "description": "Restart the computer. DANGEROUS: this closes all programs and reboots the machine, so it MUST NOT be called without the user explicitly asking for a restart, and it requires confirm=true as a safety gate. Any other value is ignored.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirm": {
                            "type": "boolean",
                            "description": "Must be true to actually reboot; anything else is a no-op",
                        },
                    },
                    "required": ["confirm"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "show_toast",
                "description": "Show a Windows desktop toast notification with the given title and message text. Toasts appear in the bottom-right notification area and slide away on their own. Use for short alerts, confirmations, or reminders without opening a window.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Toast title (short, e.g. 'Download complete')",
                        },
                        "message": {
                            "type": "string",
                            "description": "Toast body text with the details",
                        },
                    },
                    "required": ["title", "message"],
                },
            },
        },
    ]


def power_sleep() -> str:
    """Put the computer to sleep."""
    if _ui_control.power_sleep():
        return "Computer put to sleep."
    return "Failed to put the computer to sleep (C# bridge unavailable or call failed)."


def power_hibernate() -> str:
    """Hibernate the computer."""
    if _ui_control.power_hibernate():
        return "Computer hibernated."
    return "Failed to hibernate the computer (C# bridge unavailable or call failed)."


def power_lock() -> str:
    """Lock the workstation."""
    if _ui_control.power_lock():
        return "Workstation locked."
    return "Failed to lock the workstation (C# bridge unavailable or call failed)."


def power_shutdown(confirm: bool = False) -> str:
    """Shut down the computer. Requires confirm=True."""
    if not confirm:
        return "Refusing to shut down: confirm flag not set. Pass confirm=true only after the user explicitly asks to shut down the computer."
    if _ui_control.power_shutdown(True):
        return "Shutting down the computer."
    return "Failed to shut down the computer (C# bridge unavailable or call failed)."


def power_reboot(confirm: bool = False) -> str:
    """Restart the computer. Requires confirm=True."""
    if not confirm:
        return "Refusing to restart: confirm flag not set. Pass confirm=true only after the user explicitly asks to restart the computer."
    if _ui_control.power_reboot(True):
        return "Restarting the computer."
    return "Failed to restart the computer (C# bridge unavailable or call failed)."


def show_toast(title: str, message: str) -> str:
    """Show a desktop toast notification."""
    if _ui_control.toast_show(title, message):
        return f"Toast shown: '{title}' — {message}"
    return "Failed to show toast (C# bridge unavailable or call failed)."
