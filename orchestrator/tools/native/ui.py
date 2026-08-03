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
                "description": "Press a keyboard key using C# SendInput (Win32). "
                               "Common keys: enter, tab, escape, space, backspace, delete, "
                               "shift, ctrl, alt, win (Windows key). "
                               "Arrow keys: up, down, left, right. "
                               "Function keys: f1 through f24. "
                               "Other: home, end, pgup, pgdn, insert, printscreen, numlock, scrolllock, capslock, apps/menu. "
                               "Numpad: numpad0-numpad9, add, subtract, multiply, divide, decimal, separator.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Key name (e.g., 'enter', 'tab', 'escape', 'space')",
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
                "description": "Press a combination of keys (hotkey) using C# SendInput (Win32). "
                               "Example: ['ctrl', 'c'] for copy, ['win', 'r'] for Run dialog, "
                               "['alt', 'tab'] for window switching. "
                               "Use 'win' for the Windows key, 'shift'/'ctrl'/'alt' for modifiers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Keys to press together (e.g. ['ctrl', 'c'], ['win', 'r'], ['alt', 'tab'])",
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
    ]


def ui_click(x: int, y: int, button: str = "left") -> str:
    """Click at screen coordinates."""
    if _ui_control.click(x, y, button):
        return f"Clicked {button} button at ({x}, {y})."
    return f"Failed to click {button} button at ({x}, {y})."


def ui_double_click(x: int, y: int, button: str = "left") -> str:
    """Double-click at screen coordinates."""
    if _ui_control.double_click(x, y, button):
        return f"Double-clicked {button} button at ({x}, {y})."
    return f"Failed to double-click at ({x}, {y})."


def ui_smooth_move(x: int, y: int, duration_ms: int = 200) -> str:
    """Animate cursor smoothly to coordinates."""
    if _ui_control.smooth_move_to(x, y, duration_ms):
        return f"Smoothly moved cursor to ({x}, {y}) over {duration_ms}ms."
    return f"Failed to move cursor to ({x}, {y})."


def ui_drag(x1: int, y1: int, x2: int, y2: int, button: str = "left") -> str:
    """Drag from start to end coordinates holding button."""
    if _ui_control.drag(x1, y1, x2, y2, button):
        return f"Dragged {button} button from ({x1},{y1}) to ({x2},{y2})."
    return f"Failed to drag from ({x1},{y1}) to ({x2},{y2})."


def ui_scroll(clicks: int) -> str:
    """Scroll mouse wheel at current position."""
    if _ui_control.scroll(clicks):
        direction = "down" if clicks > 0 else "up"
        return f"Scrolled {direction} {abs(clicks)} clicks."
    return "Failed to scroll."


def ui_scroll_at(x: int, y: int, clicks: int) -> str:
    """Move to coordinates then scroll mouse wheel."""
    if _ui_control.scroll_at(x, y, clicks):
        direction = "down" if clicks > 0 else "up"
        return f"Moved to ({x},{y}) and scrolled {direction} {abs(clicks)} clicks."
    return f"Failed to scroll at ({x},{y})."


def ui_move_relative(dx: int, dy: int) -> str:
    """Move cursor relative to current position."""
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


def ui_press_key(key: str) -> str:
    """Press a keyboard key (e.g. 'enter', 'tab', 'escape')."""
    if _ui_control.press_key(key):
        return f"Successfully pressed key: {key}."
    return f"Failed to press key: {key}."


def ui_hotkey(keys: list[str]) -> str:
    """Press a combination of keys (e.g. ['ctrl', 'c'])."""
    if _ui_control.hotkey(*keys):
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
