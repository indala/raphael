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

    def __init__(
        self,
        callback: Callable[[], None] | None = None,
        modifiers: int | None = None,
        vk_code: int | None = None,
        additional_hotkeys: list[dict] | None = None,
    ):
        self._callback = callback
        self._thread: threading.Thread | None = None
        self._running = False
        self._hwnd = None
        self._registered_ids: list[int] = []
        self._hotkey_callbacks: dict[int, Callable[[], None]] = {}

        self._hotkey_specs: list[dict] = []
        if _WIN32_AVAILABLE:
            main_mods = modifiers if modifiers is not None else (win32con.MOD_WIN | win32con.MOD_SHIFT)
            main_vk = vk_code if vk_code is not None else 0x52  # 'R'
            self._hotkey_specs.append({
                "id": 9001,
                "mods": main_mods,
                "vk": main_vk,
                "cb": callback,
                "name": "Win+Shift+R (Main Window)",
            })

            if additional_hotkeys:
                for idx, hk in enumerate(additional_hotkeys, start=9002):
                    self._hotkey_specs.append({
                        "id": hk.get("id", idx),
                        "mods": hk.get("mods", win32con.MOD_CONTROL),
                        "vk": hk.get("vk", 0x49),
                        "cb": hk.get("callback"),
                        "name": hk.get("name", f"Hotkey {idx}"),
                    })

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

            for spec in self._hotkey_specs:
                hid = spec["id"]
                mods = spec["mods"]
                vk = spec["vk"]
                cb = spec["cb"]
                res = win32gui.RegisterHotKey(self._hwnd, hid, mods, vk)
                if res:
                    self._registered_ids.append(hid)
                    if cb:
                        self._hotkey_callbacks[hid] = cb
                    logger.info("Global hotkey registered: %s (id=%d)", spec["name"], hid)
                else:
                    logger.debug("Failed to register global hotkey: %s", spec["name"])

            # Pump Win32 messages
            win32gui.PumpMessages()
        except Exception as e:
            logger.debug("Global hotkey thread exit: %s", e)
        finally:
            if _WIN32_AVAILABLE and self._hwnd:
                for hid in self._registered_ids:
                    with contextlib.suppress(Exception):
                        win32gui.UnregisterHotKey(self._hwnd, hid)
            self._running = False

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        """Window procedure callback for WM_HOTKEY events."""
        if msg == win32con.WM_HOTKEY:
            hid = wparam
            cb = self._hotkey_callbacks.get(hid)
            if cb:
                try:
                    cb()
                except Exception as e:
                    logger.error("Hotkey callback error: %s", e)
            return 0
        elif msg == win32con.WM_DESTROY or msg == win32con.WM_CLOSE:
            win32gui.PostQuitMessage(0)
            return 0
        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)
