"""UI automation tools — mouse/keyboard/window control."""

from modules import clipboard as _clipboard
from modules import ui_control as _ui_control


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "ui_click",
                "description": "Click at the given screen coordinates by simulating a mouse click via the C# SendInput (Win32) bridge. Use when the user asks to click somewhere on their screen without a mouse.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {
                            "type": "integer",
                            "description": "X coordinate on the screen",
                        },
                        "y": {
                            "type": "integer",
                            "description": "Y coordinate on the screen",
                        },
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "Mouse button to click (default 'left')",
                        },
                    },
                    "required": ["x", "y"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_double_click",
                "description": "Double-click at screen coordinates using C# SendInput (Win32)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {
                            "type": "integer",
                            "description": "X coordinate on the screen",
                        },
                        "y": {
                            "type": "integer",
                            "description": "Y coordinate on the screen",
                        },
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "Mouse button (default 'left')",
                        },
                    },
                    "required": ["x", "y"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_smooth_move",
                "description": "Animate cursor smoothly to screen coordinates using C# SendInput (Win32). "
                               "Useful when a teleporting cursor would look suspicious or trigger anti-bot detection.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {
                            "type": "integer",
                            "description": "Target X coordinate",
                        },
                        "y": {
                            "type": "integer",
                            "description": "Target Y coordinate",
                        },
                        "duration_ms": {
                            "type": "integer",
                            "description": "Animation duration in milliseconds (default 200, min 50)",
                        },
                    },
                    "required": ["x", "y"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_drag",
                "description": "Drag from one point to another holding the specified mouse button using C# SendInput",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x1": {"type": "integer", "description": "Start X"},
                        "y1": {"type": "integer", "description": "Start Y"},
                        "x2": {"type": "integer", "description": "End X"},
                        "y2": {"type": "integer", "description": "End Y"},
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "Mouse button to hold (default 'left')",
                        },
                    },
                    "required": ["x1", "y1", "x2", "y2"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_scroll",
                "description": "Scroll the mouse wheel at the current cursor position via C# SendInput. "
                               "Positive clicks = scroll down, negative = scroll up.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "clicks": {
                            "type": "integer",
                            "description": "Number of wheel clicks (positive=down, negative=up, e.g. 3 to scroll down 3 notches)",
                        },
                    },
                    "required": ["clicks"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_scroll_at",
                "description": "Move to screen coordinates then scroll the mouse wheel via C# SendInput. "
                               "Positive clicks = scroll down, negative = scroll up.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer", "description": "X coordinate to move to"},
                        "y": {"type": "integer", "description": "Y coordinate to move to"},
                        "clicks": {
                            "type": "integer",
                            "description": "Number of wheel clicks (positive=down, negative=up)",
                        },
                    },
                    "required": ["x", "y", "clicks"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_move_relative",
                "description": "Move the cursor by a relative offset (dx, dy) from its current position using the C# SendInput (Win32) bridge. Use when the user wants to nudge the mouse a small amount rather than jump to an absolute position.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dx": {"type": "integer", "description": "Pixels to move right (negative = left)"},
                        "dy": {"type": "integer", "description": "Pixels to move down (negative = up)"},
                    },
                    "required": ["dx", "dy"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_mouse_down",
                "description": "Press and hold a mouse button (for advanced drag sequences) via C# SendInput. "
                               "Must be paired with ui_mouse_up to release.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "Mouse button to hold (default 'left')",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_mouse_up",
                "description": "Release a held mouse button via C# SendInput. Pair with ui_mouse_down.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "button": {
                            "type": "string",
                            "enum": ["left", "right", "middle"],
                            "description": "Mouse button to release (default 'left')",
                        },
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_type_text",
                "description": "Type text at the current cursor position using C# SendInput (Win32)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The text to type",
                        },
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_press_key",
                "description": "Press and release a SINGLE keyboard key (e.g. 'enter', 'tab', 'escape', 'space', 'backspace', 'delete', 'up', 'down'). "
                               "DO NOT use this for shortcut combinations (like Win+Shift+S, Ctrl+C, Alt+Tab) — ALWAYS use 'ui_hotkey' instead for combinations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Single key name (e.g., 'enter', 'tab', 'escape', 'space', 'backspace')",
                        },
                    },
                    "required": ["key"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_hotkey",
                "description": "Press a combination of keys SIMULTANEOUSLY (e.g. keyboard shortcuts). "
                               "Examples: ['win', 'shift', 's'] for Windows Snipping Tool screenshot, "
                               "['ctrl', 'c'] for copy, ['ctrl', 'v'] for paste, ['win', 'r'] for Run dialog, "
                               "['alt', 'tab'] for window switching. "
                               "ALWAYS use this instead of multiple ui_press_key calls when modifiers are involved.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Keys to press simultaneously (e.g. ['win', 'shift', 's'], ['ctrl', 'c'], ['alt', 'f4'])",
                        },
                    },
                    "required": ["keys"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_get_mouse_position",
                "description": "Get current mouse coordinates on the screen via C# SendInput",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_get_screen_size",
                "description": "Get the primary screen dimensions (width, height) in pixels via the C# bridge. Use when you need to compute coordinates or check the available screen area.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_focus_window",
                "description": "Bring a window to the foreground by matching a partial title string using the C# bridge. Use when the user asks to switch to or focus a specific application window.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial title of the window to focus",
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_enum_windows",
                "description": "List all visible windows with handle, title, PID, process name, screen rect, and whether the window is protected (belongs to Raphael's own process chain). Use this to discover what windows exist before acting on them.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_close_window",
                "description": "Safely close a window by title. Refuses to close protected windows (Raphael's own host, terminal, IDE, etc.). Uses WM_CLOSE for clean shutdown — NOT Alt+F4.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial or exact window title to close",
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_minimize_window",
                "description": "Minimize a window so it collapses to the taskbar. Provide a partial window title (for example the app name) to match. Useful when decluttering the desktop or before focusing another window.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial window title to minimize",
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_maximize_window",
                "description": "Maximize a window to fill the entire screen. Provide a partial window title (for example the app name) to match. Useful when the user wants a window expanded to full size.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial window title to maximize",
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_raphael_ui_state",
                "description": "Check Raphael's current UI presentation state — returns 'window' (main HUD window visible) or 'floating_icon' (minimized to floating minion icon).",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "show_raphael_window",
                "description": "Show Raphael's main HUD window and switch UI presentation state to 'window'.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "hide_raphael_window",
                "description": "Hide Raphael's main HUD window to floating minion icon mode and switch UI presentation state to 'floating_icon'.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_get_window_rect",
                "description": "Get a window's current on-screen position and size as left, top, right, bottom pixel coordinates. Provide a partial window title. Useful for computing click targets or verifying window layout.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial window title to inspect",
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_move_window",
                "description": "Move a window to a new on-screen position by matching a partial window title. Provide the target X and Y screen coordinates (top-left corner), the window's size is preserved. Useful for arranging windows on the monitor.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial window title to move",
                        },
                        "x": {
                            "type": "integer",
                            "description": "Target left coordinate",
                        },
                        "y": {
                            "type": "integer",
                            "description": "Target top coordinate",
                        },
                    },
                    "required": ["title", "x", "y"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_resize_window",
                "description": "Resize a window to a new width and height (in pixels) by matching a partial window title. The window's top-left position is preserved. Useful for setting windows to specific dimensions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial window title to resize",
                        },
                        "width": {
                            "type": "integer",
                            "description": "New width in pixels",
                        },
                        "height": {
                            "type": "integer",
                            "description": "New height in pixels",
                        },
                    },
                    "required": ["title", "width", "height"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_set_always_on_top",
                "description": "Pin a window to stay on top of all other windows (always-on-top) or release it, by matching a partial window title. Pass on_top true to pin it above everything, false to let it sit normally in the z-order.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial window title",
                        },
                        "on_top": {
                            "type": "boolean",
                            "description": "True to keep the window always on top, false to release",
                        },
                    },
                    "required": ["title", "on_top"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_set_window_opacity",
                "description": "Set a window's transparency to a value between 0.0 (fully invisible) and 1.0 (fully opaque), by matching a partial window title. Useful for semi-transparent overlays or previews. Uses the Win32 layered window API.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial window title",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Opacity from 0.0 (invisible) to 1.0 (opaque)",
                        },
                    },
                    "required": ["title", "opacity"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_hide_window",
                "description": "Hide a window by matching a partial title so it disappears from the desktop and taskbar, without closing it. The window keeps running in the background. Use ui_show_window to bring it back.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial window title to hide",
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_show_window",
                "description": "Show a previously hidden window by matching a partial title, restoring it to the desktop and taskbar. Pairs with ui_hide_window. No effect (and returns an error) if no matching window is found.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "Partial window title to show",
                        },
                    },
                    "required": ["title"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_get_monitors",
                "description": "Get information about all connected monitors: index, bounds, work area (excluding taskbar), and primary flag. Useful for understanding the physical screen layout before positioning windows or taking screenshots.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_get_system_state",
                "description": "Get current user and system state: idle time (seconds since last input), foreground process info (PID, name, executable, responding, memory), full-screen detection (whether foreground window fills its monitor), and power/battery status. Use this to check user activity before deciding whether to interrupt or proceed.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ui_get_explorer_selection",
                "description": "Get the active File Explorer window's current folder path and any selected files/folders. Uses Shell.Application COM to directly query the Explorer shell. Returns the folder path and a list of selected items with name, full path, and whether each is a folder. Returns an error message if no Explorer window is active.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_snapshot",
                "description": "Get a comprehensive snapshot of the current desktop state in a single call: monitor layout, system state (idle time, foreground process, full-screen, power), visible windows with protected flags, mouse position, active Explorer folder & selection, clipboard text and clipboard file list. Use this at the start of a desktop automation sequence and whenever the user interrupts or context may have changed — prefer a single snapshot over multiple individual calls.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "key_is_pressed",
                "description": "Check whether a specific keyboard key (for example shift, ctrl, alt, or any letter or number) is currently being held down right now using GetAsyncKeyState. Use when the user asks if a key is being pressed or to detect held modifier keys.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Key name to check, e.g. 'shift', 'ctrl', 'alt', 'a', 'enter'",
                        },
                    },
                    "required": ["key"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "caps_lock_state",
                "description": "Report whether Caps Lock is currently toggled on or off using GetKeyState. Use when the user asks whether Caps Lock is enabled, such as before typing or pasting text.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "num_lock_state",
                "description": "Report whether Num Lock is currently toggled on or off using GetKeyState. Use when the user asks whether Num Lock is enabled before typing numbers on the numeric keypad.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "monitor_get_dpi",
                "description": "Get the primary monitor's effective DPI scaling (dots per inch) on both the horizontal and vertical axes via the Windows shcore API. Use to reason about display scaling when computing pixel-perfect coordinates.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_brightness",
                "description": "Get the primary monitor's current brightness along with its minimum and maximum supported levels via the Windows dxva2 API. Use when the user asks how bright their display is or to report brightness alongside other settings.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_brightness",
                "description": "Set the primary monitor's brightness to a level between 0 and 100 percent using the Windows dxva2 API. Requires a display that supports DDC/CI brightness control such as external monitors or this laptop's panel.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "integer",
                            "description": "Target brightness from 0 (minimum) to 100 (maximum)",
                        },
                    },
                    "required": ["level"],
                },
            },
        },
    ]


def _coerce_int(value, name: str = "coordinate") -> int:
    """Coerce a value to int, tolerating models that emit numbers as strings.

    Raises ValueError with a clear message if the value can't be converted.
    """
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer, got bool")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer, got {value!r}") from None


def ui_click(x: int, y: int, button: str = "left") -> str:
    """Click at screen coordinates."""
    try:
        x, y = _coerce_int(x, "x"), _coerce_int(y, "y")
    except ValueError as e:
        return f"Failed to click: {e}. Provide integer screen coordinates."
    if _ui_control.click(x, y, button):
        return f"Clicked {button} button at ({x}, {y})."
    return f"Failed to click {button} button at ({x}, {y})."


def ui_double_click(x: int, y: int, button: str = "left") -> str:
    """Double-click at screen coordinates."""
    try:
        x, y = _coerce_int(x, "x"), _coerce_int(y, "y")
    except ValueError as e:
        return f"Failed to double-click: {e}. Provide integer screen coordinates."
    if _ui_control.double_click(x, y, button):
        return f"Double-clicked {button} button at ({x}, {y})."
    return f"Failed to double-click at ({x}, {y})."


def ui_smooth_move(x: int, y: int, duration_ms: int = 200) -> str:
    """Animate cursor smoothly to coordinates."""
    try:
        x, y, duration_ms = _coerce_int(x, "x"), _coerce_int(y, "y"), _coerce_int(duration_ms, "duration_ms")
    except ValueError as e:
        return f"Failed to move cursor: {e}."
    if _ui_control.smooth_move_to(x, y, duration_ms):
        return f"Smoothly moved cursor to ({x}, {y}) over {duration_ms}ms."
    return f"Failed to move cursor to ({x}, {y})."


def ui_drag(x1: int, y1: int, x2: int, y2: int, button: str = "left") -> str:
    """Drag from start to end coordinates holding button."""
    try:
        x1, y1 = _coerce_int(x1, "x1"), _coerce_int(y1, "y1")
        x2, y2 = _coerce_int(x2, "x2"), _coerce_int(y2, "y2")
    except ValueError as e:
        return f"Failed to drag: {e}."
    if _ui_control.drag(x1, y1, x2, y2, button):
        return f"Dragged {button} button from ({x1},{y1}) to ({x2},{y2})."
    return f"Failed to drag from ({x1},{y1}) to ({x2},{y2})."


def ui_scroll(clicks: int) -> str:
    """Scroll mouse wheel at current position."""
    try:
        clicks = _coerce_int(clicks, "clicks")
    except ValueError as e:
        return f"Failed to scroll: {e}."
    if _ui_control.scroll(clicks):
        direction = "down" if clicks > 0 else "up"
        return f"Scrolled {direction} {abs(clicks)} clicks."
    return "Failed to scroll."


def ui_scroll_at(x: int, y: int, clicks: int) -> str:
    """Move to coordinates then scroll mouse wheel."""
    try:
        x, y, clicks = _coerce_int(x, "x"), _coerce_int(y, "y"), _coerce_int(clicks, "clicks")
    except ValueError as e:
        return f"Failed to scroll at coordinate: {e}."
    if _ui_control.scroll_at(x, y, clicks):
        direction = "down" if clicks > 0 else "up"
        return f"Moved to ({x},{y}) and scrolled {direction} {abs(clicks)} clicks."
    return f"Failed to scroll at ({x},{y})."


def ui_move_relative(dx: int, dy: int) -> str:
    """Move cursor relative to current position."""
    try:
        dx, dy = _coerce_int(dx, "dx"), _coerce_int(dy, "dy")
    except ValueError as e:
        return f"Failed to move cursor: {e}."
    if _ui_control.move_relative(dx, dy):
        return f"Moved cursor by ({dx:+d}, {dy:+d})."
    return f"Failed to move cursor by ({dx}, {dy})."


def ui_mouse_down(button: str = "left") -> str:
    """Press and hold a mouse button."""
    if _ui_control.mouse_down(button):
        return f"Pressed and holding {button} button."
    return f"Failed to press {button} button."


def ui_mouse_up(button: str = "left") -> str:
    """Release a held mouse button."""
    if _ui_control.mouse_up(button):
        return f"Released {button} button."
    return f"Failed to release {button} button."


def ui_type_text(text: str) -> str:
    """Type text at the current cursor position."""
    if _ui_control.type_text(text):
        return "Successfully typed text."
    return "Failed to type text."


_KEY_ALIASES = {
    "windows": "win",
    "win_key": "win",
    "super": "win",
    "cmd": "win",
    "command": "win",
    "control": "ctrl",
    "escape": "esc",
    "return": "enter",
    "prtscr": "printscreen",
    "prtsc": "printscreen",
}


def _normalize_key(k: str) -> str:
    k = k.strip().lower()
    return _KEY_ALIASES.get(k, k)


def ui_press_key(key: str | None = None, keys: list[str] | str | None = None, **kwargs) -> str:
    """Press a single keyboard key (e.g. 'enter', 'tab', 'escape', 'space')."""
    # Defensive handling if caller passed 'keys' parameter
    if key is None and keys is not None:
        if isinstance(keys, list) and len(keys) == 1:
            key = keys[0]
        elif isinstance(keys, list):
            return ui_hotkey(keys)
        else:
            key = str(keys)

    if not key:
        return "Error: key parameter is required for ui_press_key."

    # Handle mouse actions if mistakenly passed to ui_press_key
    if key.lower().startswith("mouse_"):
        if "down" in key.lower():
            btn = "right" if "right" in key.lower() else "left"
            if _ui_control.mouse_down(btn):
                return f"Pressed and holding mouse {btn} button."
        elif "up" in key.lower():
            btn = "right" if "right" in key.lower() else "left"
            if _ui_control.mouse_up(btn):
                return f"Released mouse {btn} button."
        elif "move" in key.lower():
            x = kwargs.get("x", 0)
            y = kwargs.get("y", 0)
            if _ui_control.move_to(int(x), int(y)):
                return f"Moved mouse to ({x}, {y})."
        return f"Error: '{key}' is a mouse action. Use mouse tools (ui_click, ui_drag, ui_mouse_down, ui_mouse_up)."

    # If the LLM passed a shortcut string (e.g., "win+shift+s" or "win shift s"), auto-route to ui_hotkey
    if any(sep in key for sep in ("+", "-", " ")):
        parts = [k.strip() for k in key.replace("+", " ").replace("-", " ").split() if k.strip()]
        if len(parts) > 1:
            return ui_hotkey(parts)

    norm_key = _normalize_key(key)
    if _ui_control.press_key(norm_key):
        return f"Successfully pressed key: {key}."
    return f"Failed to press key: {key}."


def ui_hotkey(keys: list[str]) -> str:
    """Press a combination of keys simultaneously (e.g. ['win', 'shift', 's'], ['ctrl', 'c'])."""
    if isinstance(keys, str):
        keys = [k.strip() for k in keys.replace("+", " ").replace("-", " ").split() if k.strip()]
    norm_keys = [_normalize_key(k) for k in keys]
    if _ui_control.hotkey(*norm_keys):
        return f"Successfully executed hotkey combination: {keys}."
    return f"Failed to execute hotkey combination: {keys}."


def ui_focus_window(title: str) -> str:
    """Bring a window to the foreground by partial title match."""
    if _ui_control.focus_window(title):
        return f"Focused window matching title: '{title}'."
    return f"Failed to find or focus window matching title: '{title}'."


def ui_get_mouse_position() -> str:
    """Get current mouse coordinates."""
    pos = _ui_control.get_mouse_position()
    if pos is None:
        return "Failed to get mouse position (C# bridge unavailable)."
    return f"Current mouse position: X={pos[0]}, Y={pos[1]}"


def ui_get_screen_size() -> str:
    """Get screen dimensions."""
    size = _ui_control.get_screen_size()
    if size is None:
        return "Failed to get screen size (C# bridge unavailable)."
    return f"Screen size: {size[0]}x{size[1]}"


def ui_enum_windows() -> str:
    """List all visible windows with full details."""
    windows = _ui_control.enum_windows()
    if not windows:
        return "No visible windows found."
    lines = [f"Found {len(windows)} visible window(s):"]
    for w in windows:
        title = w.get("title", "")
        proc = w.get("process_name", "")
        handle = w.get("handle", 0)
        pid = w.get("pid", 0)
        fg = w.get("is_foreground", False)
        prot = w.get("protected", False)
        rect = f"{w.get('rect_left', 0)},{w.get('rect_top', 0)} {w.get('rect_right', 0)}x{w.get('rect_bottom', 0)}"
        flags = " | ".join(filter(None, [
            "foreground" if fg else "",
            "PROTECTED" if prot else "",
        ]))
        lines.append(f"  [{int(handle):#x}] \"{title}\"  pid={pid}  proc={proc}  rect={rect}  {flags}")
    return "\n".join(lines)


def ui_close_window(title: str) -> str:
    """Safely close a window by title. Refuses if protected."""
    from modules.ui_control import close_window as _close_window
    from modules.ui_control import is_protected_window as _is_protected
    if _is_protected(title):
        return f"Error: Refusing to close '{title}' — it is a protected window (part of Raphael's process chain)."
    if _close_window(title):
        return f"Closed window '{title}'."
    return f"Failed to close window '{title}'."


def ui_minimize_window(title: str) -> str:
    """Minimize a window by partial title match."""
    if _ui_control.minimize_window(title):
        return f"Minimized window matching title: '{title}'."
    return f"Failed to minimize window matching title: '{title}'."


def ui_maximize_window(title: str) -> str:
    """Maximize a window by partial title match."""
    if _ui_control.maximize_window(title):
        return f"Maximized window matching title: '{title}'."
    return f"Failed to maximize window matching title: '{title}'."


def ui_get_window_rect(title: str) -> str:
    """Get a window's position and size by partial title match."""
    rect = _ui_control.get_window_rect(title)
    if not rect:
        return f"Failed to get rect for window matching title: '{title}'."
    return (
        f"Window rect for '{title}': left={rect['left']} top={rect['top']} "
        f"right={rect['right']} bottom={rect['bottom']} "
        f"(width={rect['right'] - rect['left']}, height={rect['bottom'] - rect['top']})"
    )


def ui_move_window(title: str, x: int, y: int) -> str:
    """Move a window to a new screen position (x, y), preserving its size."""
    if _ui_control.move_window(title, x, y):
        return f"Moved window '{title}' to ({x}, {y})."
    return f"Failed to move window matching title: '{title}' to ({x}, {y})."


def ui_resize_window(title: str, width: int, height: int) -> str:
    """Resize a window to (width, height), preserving its position."""
    if _ui_control.resize_window(title, width, height):
        return f"Resized window '{title}' to {width}x{height}."
    return f"Failed to resize window matching title: '{title}' to {width}x{height}."


def ui_set_always_on_top(title: str, on_top: bool) -> str:
    """Pin a window to the top of the z-order or release it."""
    if _ui_control.set_always_on_top(title, on_top):
        state = "always-on-top" if on_top else "back to normal"
        return f"Set window '{title}' to {state}."
    return f"Failed to set always-on-top flag on window matching title: '{title}'."


def ui_set_window_opacity(title: str, opacity: float) -> str:
    """Set a window's opacity to a value in [0, 1]."""
    if _ui_control.set_window_opacity(title, opacity):
        return f"Set window '{title}' opacity to {opacity:.2f}."
    return f"Failed to set opacity on window matching title: '{title}'."


def ui_hide_window(title: str) -> str:
    """Hide a window by partial title match."""
    if _ui_control.hide_window(title):
        return f"Hidden window matching title: '{title}'."
    return f"Failed to hide window matching title: '{title}'."


def ui_show_window(title: str) -> str:
    """Show a previously hidden window by partial title match."""
    if _ui_control.show_window(title):
        return f"Shown window matching title: '{title}'."
    return f"Failed to show window matching title: '{title}'."


def ui_get_monitors() -> str:
    """Get information about all connected monitors."""
    monitors = _ui_control.get_monitors()
    if not monitors:
        return "No monitors detected."
    lines = [f"Found {len(monitors)} monitor(s):"]
    for m in monitors:
        primary = " (PRIMARY)" if m.get("is_primary") else ""
        lines.append(
            f"  Monitor {m['index']}{primary}: "
            f"bounds=({m['left']},{m['top']})-({m['right']},{m['bottom']}) "
            f"work=({m['work_left']},{m['work_top']})-({m['work_right']},{m['work_bottom']})"
        )
    return "\n".join(lines)


def ui_get_system_state() -> str:
    """Get current user and system state."""
    state = _ui_control.get_user_state()
    lines = [f"Idle: {state.get('idle_seconds', 0):.0f}s"]

    fg = state.get("foreground_process")
    if fg:
        lines.append(
            f"Foreground: pid={fg['pid']} name={fg['process_name']} "
            f"exe={fg.get('executable_path', '')} "
            f"responding={fg['responding']} mem={fg['memory_bytes'] / 1024 / 1024:.0f}MB"
        )
    else:
        lines.append("Foreground: (none)")

    lines.append(f"Full-screen: {state.get('full_screen', False)}")

    power = state.get("power") or {}
    if power:
        lines.append(
            f"Battery: {power.get('battery_remaining', '?')}% "
            f"charging={power.get('power_line_status', '?')} "
            f"status={power.get('battery_charge_status', '?')} "
            f"remaining={power.get('battery_life_seconds', -1)}s"
        )
    else:
        lines.append("Power: (unknown)")

    return "\n".join(lines)


def ui_get_explorer_selection() -> str:
    """Get the active File Explorer window's folder path and selected items."""
    sel = _ui_control.get_explorer_selection()
    if not sel:
        return "No active Explorer window with a filesystem folder found."
    folder = sel.get("folder_path", "")
    selected = sel.get("selected")
    lines = [f"Explorer folder: {folder}"]
    if selected and len(selected) > 0:
        lines.append(f"Selected ({len(selected)} item(s)):")
        for item in selected:
            tag = " [FOLDER]" if item.get("is_folder") else ""
            lines.append(f"  • {item['name']}{tag}  ({item.get('path', '')})")
    else:
        lines.append("(no selection)")
    return "\n".join(lines)


def desktop_snapshot() -> str:
    """Comprehensive desktop state snapshot: monitors, system state, windows, explorer, clipboard."""
    parts = []

    # ── Monitors ──
    try:
        monitors = _ui_control.get_monitors()
        if monitors:
            mon_lines = [f"Monitors ({len(monitors)}):"]
            for m in monitors:
                primary = " (PRIMARY)" if m.get("is_primary") else ""
                mon_lines.append(
                    f"  {m['index']}{primary}: "
                    f"bounds=({m['left']},{m['top']})-({m['right']},{m['bottom']})"
                )
            parts.append("\n".join(mon_lines))
    except Exception as e:
        parts.append(f"Monitors: (error: {e})")

    # ── System state ──
    try:
        state = _ui_control.get_user_state()
        state_lines = [
            f"Idle: {state.get('idle_seconds', 0):.0f}s",
        ]
        fg = state.get("foreground_process")
        if fg:
            state_lines.append(
                f"Foreground: pid={fg['pid']} name={fg['process_name']} "
                f"exe={fg.get('executable_path', '')} "
                f"responding={fg['responding']} mem={fg['memory_bytes'] / 1024 / 1024:.0f}MB"
            )
        else:
            state_lines.append("Foreground: (none)")
        state_lines.append(f"Full-screen: {state.get('full_screen', False)}")
        power = state.get("power") or {}
        if power:
            state_lines.append(
                f"Battery: {power.get('battery_remaining', '?')}% "
                f"charging={power.get('power_line_status', '?')}"
            )
        parts.append("\n".join(state_lines))
    except Exception as e:
        parts.append(f"System state: (error: {e})")

    # ── Mouse position ──
    try:
        pos = _ui_control.get_mouse_position()
        if pos is not None:
            parts.append(f"Mouse: X={pos[0]}, Y={pos[1]}")
        else:
            parts.append("Mouse: (unavailable)")
    except Exception as e:
        parts.append(f"Mouse: (error: {e})")

    # ── Visible windows ──
    try:
        windows = _ui_control.enum_windows()
        if windows:
            win_lines = [f"Visible windows ({len(windows)}):"]
            for w in windows:
                title = w.get("title", "")
                proc = w.get("process_name", "")
                prot = " PROTECTED" if w.get("protected") else ""
                fg = " [fg]" if w.get("is_foreground") else ""
                win_lines.append(f"  [{w.get('handle', 0):#x}] \"{title}\"  {proc}{fg}{prot}")
            parts.append("\n".join(win_lines))
        else:
            parts.append("Visible windows: (none)")
    except Exception as e:
        parts.append(f"Windows: (error: {e})")

    # ── Explorer selection ──
    try:
        sel = _ui_control.get_explorer_selection()
        if sel:
            folder = sel.get("folder_path", "")
            selected = sel.get("selected")
            exp_lines = [f"Explorer: {folder}"]
            if selected:
                for item in selected:
                    tag = " [FOLDER]" if item.get("is_folder") else ""
                    exp_lines.append(f"  • {item['name']}{tag}")
            parts.append("\n".join(exp_lines))
        else:
            parts.append("Explorer: (no active folder window)")
    except Exception as e:
        parts.append(f"Explorer: (error: {e})")

    # ── Clipboard text ──
    try:
        text = _clipboard.paste_text()
        if text:
            parts.append(f"Clipboard text: \"{text[:200]}{'...' if len(text) > 200 else ''}\"")
        else:
            parts.append("Clipboard text: (empty)")
    except Exception as e:
        parts.append(f"Clipboard text: (error: {e})")

    # ── Clipboard files ──
    try:
        files = _clipboard.get_file_list()
        if files:
            parts.append(f"Clipboard files ({len(files)}):\n" + "\n".join(f"  • {f}" for f in files))
        else:
            parts.append("Clipboard files: (none)")
    except Exception as e:
        parts.append(f"Clipboard files: (error: {e})")

    return "\n\n".join(parts)


def key_is_pressed(key: str) -> str:
    """Check whether a keyboard key is currently held down."""
    if _ui_control.key_is_pressed(key):
        return f"Key '{key}' is currently pressed."
    return f"Key '{key}' is not pressed."


def caps_lock_state() -> str:
    """Report whether Caps Lock is toggled on or off."""
    state = "ON" if _ui_control.caps_lock_state() else "OFF"
    return f"Caps Lock is {state}."


def num_lock_state() -> str:
    """Report whether Num Lock is toggled on or off."""
    state = "ON" if _ui_control.num_lock_state() else "OFF"
    return f"Num Lock is {state}."


def monitor_get_dpi() -> str:
    """Get the primary monitor's effective DPI."""
    dpi = _ui_control.monitor_get_dpi()
    if not dpi:
        return "Failed to get monitor DPI (C# bridge unavailable)."
    if "error" in dpi:
        return f"Failed to get monitor DPI: {dpi['error']}"
    return f"Primary monitor DPI: {dpi.get('dpi_x')} x {dpi.get('dpi_y')}"


def get_brightness() -> str:
    """Get the primary monitor's current brightness."""
    b = _ui_control.get_brightness()
    if not b:
        return "Failed to get monitor brightness (C# bridge unavailable)."
    if "error" in b:
        return f"Failed to get monitor brightness: {b['error']}"
    return f"Brightness: {b.get('current')}% (range {b.get('min')}-{b.get('max')})"


def set_brightness(level: int) -> str:
    """Set the primary monitor's brightness to a level in [0, 100]."""
    result = _ui_control.set_brightness(level)
    if not result:
        return "Failed to set monitor brightness (C# bridge unavailable)."
    if "error" in result:
        return f"Failed to set brightness: {result['error']}"
    return f"Brightness set to {level}%."


def get_raphael_ui_state() -> str:
    """Check Raphael's current UI presentation state ('window' or 'floating_icon')."""
    from controller.raphael_controller import get_controller_instance
    ctrl = get_controller_instance()
    if ctrl is not None:
        state_mode = ctrl.get_ui_state()
        return f"Raphael UI is currently in '{state_mode}' state."
    return "Raphael UI is in 'window' state."


def show_raphael_window() -> str:
    """Show Raphael's main HUD window."""
    from controller.raphael_controller import get_controller_instance
    ctrl = get_controller_instance()
    if ctrl is not None:
        ctrl.show_main_window()
        return "Raphael main HUD window is now visible (WINDOW state)."
    return "Raphael controller not running."


def hide_raphael_window() -> str:
    """Hide Raphael's main HUD window to floating minion icon mode."""
    from controller.raphael_controller import get_controller_instance
    ctrl = get_controller_instance()
    if ctrl is not None:
        ctrl.hide_main_window()
        return "Raphael main HUD window hidden (FLOATING_ICON state)."
    return "Raphael controller not running."
