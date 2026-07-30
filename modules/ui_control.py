"""
UI Control module.
Mouse/keyboard automation and window management.
Uses C# User32 bridge for window ops and C# SendInput for all cursor/keyboard input.
"""

import logging
import os

import pygetwindow as gw
import time
import contextlib

logger = logging.getLogger(__name__)

# Optional C# hybrid bridge — all cursor/keyboard ops REQUIRE this
try:
    from hybrid.bridge import CWindowManager as CsWin, CInputSimulator as CsInput, CMonitorInfo as CsMon, CSystemState as CsState, CExplorerHelper as CsExplorer, is_available
    _CS_OK = is_available()
    _CS_WIN = _CS_OK
    _CS_INPUT = _CS_OK
except ImportError:
    _CS_WIN = False
    _CS_INPUT = False


def click(x: int, y: int, button: str = "left") -> bool:
    """Click at screen coordinates via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot click")
        return False
    try:
        CsInput.ClickAt(x, y, button)
        return True
    except Exception as e:
        logger.error("C# ClickAt failed: %s", e)
        return False


def double_click(x: int, y: int, button: str = "left") -> bool:
    """Double-click at coordinates via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot double-click")
        return False
    try:
        CsInput.DoubleClickAt(x, y, button)
        return True
    except Exception as e:
        logger.error("C# DoubleClickAt failed: %s", e)
        return False


def smooth_move_to(x: int, y: int, duration_ms: int = 200) -> bool:
    """Animate cursor smoothly to coordinates via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot move")
        return False
    try:
        CsInput.SmoothMoveTo(x, y, duration_ms)
        return True
    except Exception as e:
        logger.error("C# SmoothMoveTo failed: %s", e)
        return False


def drag(x1: int, y1: int, x2: int, y2: int, button: str = "left") -> bool:
    """Drag from (x1,y1) to (x2,y2) holding button via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot drag")
        return False
    try:
        CsInput.Drag(x1, y1, x2, y2, button)
        return True
    except Exception as e:
        logger.error("C# Drag failed: %s", e)
        return False


def scroll(clicks: int) -> bool:
    """Scroll mouse wheel (positive = down, negative = up) via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot scroll")
        return False
    try:
        CsInput.Scroll(clicks)
        return True
    except Exception as e:
        logger.error("C# Scroll failed: %s", e)
        return False


def scroll_at(x: int, y: int, clicks: int) -> bool:
    """Move to (x,y) then scroll via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot scroll")
        return False
    try:
        CsInput.ScrollAt(x, y, clicks)
        return True
    except Exception as e:
        logger.error("C# ScrollAt failed: %s", e)
        return False


def move_relative(dx: int, dy: int) -> bool:
    """Move cursor relative to current position via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot move")
        return False
    try:
        CsInput.MoveRelative(dx, dy)
        return True
    except Exception as e:
        logger.error("C# MoveRelative failed: %s", e)
        return False


def mouse_down(button: str = "left") -> bool:
    """Press and hold a mouse button via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available")
        return False
    try:
        CsInput.MouseDown(button)
        return True
    except Exception as e:
        logger.error("C# MouseDown failed: %s", e)
        return False


def mouse_up(button: str = "left") -> bool:
    """Release a held mouse button via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available")
        return False
    try:
        CsInput.MouseUp(button)
        return True
    except Exception as e:
        logger.error("C# MouseUp failed: %s", e)
        return False


def type_text(text: str) -> bool:
    """Type text at the current cursor position via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot type")
        return False
    try:
        CsInput.TypeText(text)
        return True
    except Exception as e:
        logger.error("C# TypeText failed: %s", e)
        return False


def press_key(key: str) -> bool:
    """Press and release a keyboard key via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot press key")
        return False
    try:
        CsInput.TapKey(key)
        return True
    except Exception as e:
        logger.error("C# TapKey failed: %s", e)
        return False


def hotkey(*keys: str) -> bool:
    """Press a combination of keys via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available — cannot send hotkey")
        return False
    try:
        CsInput.Hotkey("+".join(keys).lower())
        return True
    except Exception as e:
        logger.error("C# Hotkey failed: %s", e)
        return False


def get_window(title: str):
    """Find a window by title (partial match). Uses C# User32 bridge if available."""
    if _CS_WIN:
        try:
            hwnd = CsWin.FindWindow(title)
            if hwnd and hwnd != 0:
                return hwnd  # Return raw handle for C# bridge methods
            return None
        except Exception:
            pass
    windows = gw.getWindowsWithTitle(title)
    return windows[0] if windows else None


def focus_window(title: str) -> bool:
    """Bring a window to the foreground. Uses C# User32 bridge if available."""
    if _CS_WIN:
        try:
            return CsWin.FocusWindow(title)  # type: ignore[return-value]
        except Exception:
            pass
    try:
        win = get_window(title)
        if win:
            win.activate()
            time.sleep(0.3)
            return True
        return False
    except Exception as e:
        logger.error("Focus window failed: %s", e)
        return False


def get_mouse_position() -> tuple | None:
    """Get current mouse coordinates via C# SendInput."""
    if not _CS_INPUT:
        logger.error("C# bridge not available")
        return None
    try:
        return CsInput.GetCursorPosition()  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("C# GetCursorPosition failed: %s", e)
        return None


def get_screen_size() -> tuple | None:
    """Get screen dimensions (width, height) via C# bridge."""
    if not _CS_INPUT:
        logger.error("C# bridge not available")
        return None
    try:
        return CsInput.GetScreenSize()  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("C# GetScreenSize failed: %s", e)
        return None


def _get_protected_pids() -> set[int]:
    """Get PIDs of Raphael's own process chain (self + parent + host)."""
    pids = set()
    with contextlib.suppress(AttributeError):
        pids.add(os.getpid())
    try:
        import psutil
        p = psutil.Process(os.getpid())
        while p is not None:
            pids.add(p.pid)
            try:
                p = p.parent()
            except (psutil.NoSuchProcess, PermissionError):
                break
    except ImportError:
        pass
    return pids


def _get_protected_process_names() -> set[str]:
    """Process names that should never be closed/killed by automation."""
    return {"python", "python3", "python3.14", "pythonw", "py",
            "antigravity", "code", "cursor", "windsurf",
            "cmd", "powershell", "pwsh", "windowsterminal", "wt"}


def enum_windows() -> list[dict]:
    """Enumerate all visible windows with handle, title, pid, process_name, rect, and protected flag."""
    protected_pids = _get_protected_pids()
    protected_names = _get_protected_process_names()

    if _CS_WIN:
        try:
            windows = CsWin.GetAllWindows()
            for w in windows:
                proc = (w.get("process_name") or "").lower()
                w["protected"] = w.get("pid") in protected_pids or proc in protected_names
            return windows
        except Exception as e:
            logger.warning("C# GetAllWindows failed: %s, falling back to pygetwindow", e)

    # Pure Python fallback
    result = []
    for w in gw.getAllWindows():
        title = w.title.strip()
        if not title:
            continue
        proc_name = ""
        try:
            import psutil
            # pygetwindow doesn't expose PID, try via hWnd
        except ImportError:
            pass
        result.append({
            "title": title,
            "handle": getattr(w, "_hWnd", 0),
            "pid": 0,
            "process_name": proc_name,
            "is_foreground": w.isActive,
            "rect_left": w.left, "rect_top": w.top,
            "rect_right": w.right, "rect_bottom": w.bottom,
            "protected": proc_name.lower() in protected_names,
        })
    return result


def close_window(title: str) -> bool:
    """Close a window by title using WM_CLOSE via C# bridge. Returns True if successful."""
    if _CS_WIN:
        try:
            return bool(CsWin.CloseWindow(title))
        except Exception as e:
            logger.warning("C# CloseWindow failed: %s", e)
    return False


def is_protected_window(title: str) -> bool:
    """Check if a window title matches a protected process."""
    windows = enum_windows()
    for w in windows:
        wt = w.get("title", "")
        if not wt:
            continue
        if title.lower() in wt.lower() or wt.lower() in title.lower():
            return w.get("protected", False)  # type: ignore[no-any-return]
    return False


def get_monitors() -> list[dict]:
    """Get all monitor info via C# DisplayHelper bridge."""
    if _CS_WIN:
        try:
            monitors = CsMon.GetAllMonitors()
            if monitors:
                return monitors
        except Exception as e:
            logger.warning("C# GetAllMonitors failed: %s", e)
    return []


def get_user_state() -> dict:
    """Get combined user/system state: idle time, foreground process, full-screen, power."""
    if _CS_WIN:
        try:
            state = CsState.GetSnapshot()
            if state:
                return state
        except Exception as e:
            logger.warning("C# GetSnapshot failed: %s", e)
    return {"idle_seconds": 0, "foreground_process": None, "full_screen": False, "power": {}}


def get_explorer_selection() -> dict | None:
    """Get the active Explorer window's folder path and selected files via Shell.Application COM."""
    if _CS_WIN:
        try:
            return CsExplorer.GetActiveExplorerSelection()
        except Exception as e:
            logger.warning("C# GetActiveExplorerSelection failed: %s", e)
    return None
