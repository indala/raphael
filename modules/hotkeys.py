"""
Global Hotkey Listener — System-wide keyboard shortcut registration for Windows.

Uses Win32 RegisterHotKey API via pywin32 to register global keyboard shortcuts
(e.g., Win+Shift+R or Alt+Space) that trigger even when Raphael is not in focus.
"""

import logging
import os
import sys
import threading
from collections.abc import Callable
import contextlib

logger = logging.getLogger(__name__)

_WIN32_AVAILABLE = False
if sys.platform == "win32":
    try:
        import win32api
        import win32con
        import win32gui
        _WIN32_AVAILABLE = True
    except ImportError:
        logger.debug("pywin32 not available — global hotkeys disabled")


class GlobalHotkeyListener:
    """Listens for global Windows keyboard shortcuts on a daemon thread."""

    HOTKEY_ID = 9001  # Unique ID for Raphael global hotkey

    def __init__(self, callback: Callable[[], None] | None = None, modifiers: int | None = None, vk_code: int | None = None):
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._running = False
        self._hwnd = None

        # Default modifier: MOD_WIN (0x0008) + MOD_SHIFT (0x0004) = Win+Shift
        # Default VK code: 'R' (0x52)
        if _WIN32_AVAILABLE:
            self._modifiers = modifiers if modifiers is not None else (win32con.MOD_WIN | win32con.MOD_SHIFT)
            self._vk_code = vk_code if vk_code is not None else 0x52  # 'R'
        else:
            self._modifiers = 0
            self._vk_code = 0

    def start(self) -> bool:
        """Start global hotkey listener thread.

        Returns True if registered successfully, False otherwise.
        """
        if not _WIN32_AVAILABLE:
            logger.info("Global hotkeys unavailable (pywin32 missing or non-Windows)")
            return False

        if self._running:
            return True

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="global-hotkey")
        self._thread.start()
        return True

    def stop(self):
        """Stop listening and unregister hotkey."""
        self._running = False
        if _WIN32_AVAILABLE and self._hwnd:
            with contextlib.suppress(Exception):  # type: ignore[unreachable]
                win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)
        self._hwnd = None

    def _loop(self):
        """Background thread loop for Win32 message pumping."""
        try:
            # Create hidden window for message processing
            wndclass = win32gui.WNDCLASS()
            wndclass.hInstance = win32api.GetModuleHandle(None)
            wndclass.lpszClassName = f"RaphaelHotkeyWnd_{os.getpid()}"
            wndclass.lpfnWndProc = self._wnd_proc

            reg_class = win32gui.RegisterClass(wndclass)
            self._hwnd = win32gui.CreateWindow(
                reg_class,
                "Raphael Hotkey Window",
                0, 0, 0, 0, 0,
                0, 0, wndclass.hInstance, None,
            )

            # Register hotkey with ID fallback (try 9001..9010)
            registered = False
            for hotkey_id in range(9001, 9011):
                res = win32gui.RegisterHotKey(
                    self._hwnd,
                    hotkey_id,
                    self._modifiers,
                    self._vk_code,
                )
                if res:
                    self.HOTKEY_ID = hotkey_id
                    registered = True
                    break

            if not registered:
                logger.warning("Failed to register global hotkey (Win+Shift+R) — key shortcut or ID in use")
                return

            logger.info("Global hotkey registered (Win+Shift+R) — press anytime to raise Raphael")

            # Pump Win32 messages
            win32gui.PumpMessages()
        except Exception as e:
            logger.debug("Global hotkey thread exit: %s", e)
        finally:
            if _WIN32_AVAILABLE and self._hwnd:
                with contextlib.suppress(Exception):  # type: ignore[unreachable]
                    win32gui.UnregisterHotKey(self._hwnd, self.HOTKEY_ID)
            self._running = False

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """Window procedure callback for WM_HOTKEY events."""
        if msg == win32con.WM_HOTKEY:
            if wparam == self.HOTKEY_ID:
                logger.info("Global hotkey triggered")
                if self._callback:
                    try:
                        self._callback()
                    except Exception as e:
                        logger.error("Hotkey callback error: %s", e)
            return 0
        elif msg == win32con.WM_DESTROY or msg == win32con.WM_CLOSE:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
