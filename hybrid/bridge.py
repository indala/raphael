"""
C# hybrid bridge — communicates with RaphaelBridge.exe via JSON stdin/stdout subprocess.
Replaces the pythonnet-based bridge for .NET 10 compatibility.
"""

import atexit
import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Any
import contextlib

logger = logging.getLogger(__name__)

_BRIDGE_DIR = Path(__file__).resolve().parent / "bin" / "Bridge"
_BRIDGE_EXE = _BRIDGE_DIR / "RaphaelBridge.exe"

_process: subprocess.Popen | None = None
_write_lock = threading.Lock()
_state_lock = threading.Lock()
_next_id = 0
_available = False
_shutdown_active = False

_pending_events: dict[int, threading.Event] = {}
_pending_results: dict[int, tuple[Any, str | None]] = {}

_stdout_thread: threading.Thread | None = None
_stderr_thread: threading.Thread | None = None


# ── Typed Bridge Exception Hierarchy ─────────────────────────────────────────

class BridgeError(Exception):
    """Base exception for all hybrid bridge operations."""


class BridgeUnavailableError(BridgeError):
    """Raised when RaphaelBridge.exe is not found or fails to start."""


class BridgeTimeoutError(BridgeError):
    """Raised when a bridge method execution exceeds its timeout."""


class BridgeExecutionError(BridgeError):
    """Raised when the C# bridge returns an explicit execution error."""


def _stdout_reader():
    """Continuously read JSON responses from the bridge and multiplex to waiting callers."""
    global _process, _available
    proc = _process
    if proc is None or proc.stdout is None:
        return

    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue

            req_id = resp.get("id")
            if req_id is not None:
                with _state_lock:
                    err = resp.get("error")
                    res = resp.get("result")
                    _pending_results[req_id] = (res, err)
                    ev = _pending_events.get(req_id)
                    if ev is not None:
                        ev.set()
    except Exception as e:
        logger.debug("Bridge stdout reader exited: %s", e)
    finally:
        with _state_lock:
            _available = False
            # Unblock all pending callers on process termination
            for req_id, ev in list(_pending_events.items()):
                if req_id not in _pending_results:
                    _pending_results[req_id] = (None, "Bridge process terminated unexpectedly")
                ev.set()


def _drain_stderr():
    """Read and log bridge stderr (background thread)."""
    global _process
    proc = _process
    if proc is None or proc.stderr is None:
        return
    try:
        for line in proc.stderr:
            line = line.rstrip("\n\r")
            if not line:
                continue
            if "Windows App SDK" in line or "Microsoft.UI" in line or "DLL not found" in line:
                logger.warning(
                    "Bridge runtime missing: %s\n  Install Windows App SDK runtime:\n"
                    "  https://aka.ms/windowsappsdk/1.6/latest/windowsappruntimeinstaller-x64.exe",
                    line,
                )
            else:
                logger.debug("Bridge stderr: %s", line)
    except Exception:
        pass


def _start() -> bool:
    """Launch the bridge subprocess and start background I/O threads."""
    global _process, _available, _stderr_thread, _stdout_thread, _shutdown_active

    if _shutdown_active:
        return False

    with _state_lock:
        if _process is not None and _process.poll() is None:
            return True

        if not _BRIDGE_EXE.exists():
            logger.warning("Bridge EXE not found: %s", _BRIDGE_EXE)
            return False

        try:
            import os
            creationflags = 0
            if os.name == "nt":
                creationflags = 0x08000000  # CREATE_NO_WINDOW

            _process = subprocess.Popen(
                [str(_BRIDGE_EXE)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            _available = True

            _stderr_thread = threading.Thread(
                target=_drain_stderr,
                daemon=True,
                name="bridge-stderr",
            )
            _stderr_thread.start()

            _stdout_thread = threading.Thread(
                target=_stdout_reader,
                daemon=True,
                name="bridge-stdout",
            )
            _stdout_thread.start()

            logger.info("Bridge subprocess started (PID %s) with concurrent multiplexing", _process.pid)
            return True
        except Exception as e:
            logger.error("Failed to start bridge: %s", e)
            _available = False
            return False


def _stop():
    """Terminate the bridge subprocess and unblock waiting threads."""
    global _process, _available, _shutdown_active
    _shutdown_active = True
    with _state_lock:
        _available = False
        p = _process
        _process = None

    if p is not None:
        if p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                with contextlib.suppress(Exception):
                    p.kill()
        for stream in (p.stdin, p.stdout, p.stderr):
            if stream:
                with contextlib.suppress(Exception):
                    stream.close()
        logger.info("Bridge subprocess stopped")


atexit.register(_stop)


def restart() -> bool:
    """Explicitly restart the bridge process (used for auto-recovery)."""
    global _shutdown_active
    _stop()
    _shutdown_active = False
    return _start()


def is_available() -> bool:
    """Return True if the bridge is currently running or can be launched."""
    if _shutdown_active:
        return False
    if _process is not None and _process.poll() is None:
        return True
    return _BRIDGE_EXE.exists()


def _call(method: str, *args, timeout: float = 10.0) -> Any:
    """Send a multiplexed JSON-RPC call to the bridge and return the result.

    Concurrent requests are multiplexed without holding a global serialization lock.
    """
    global _next_id, _available, _process
    if _shutdown_active:
        raise BridgeUnavailableError("Bridge shutting down")
    if not _available and not _start():
        raise BridgeUnavailableError("Bridge not available")

    proc = _process
    if proc is None or proc.poll() is not None:
        _available = False
        raise BridgeUnavailableError("Bridge process not running")

    ev = threading.Event()
    with _state_lock:
        _next_id += 1
        req_id = _next_id
        _pending_events[req_id] = ev

    request = {"id": req_id, "method": method, "args": list(args)}
    line = json.dumps(request, ensure_ascii=False)

    try:
        with _write_lock:
            if proc.stdin is None or proc.poll() is not None:
                raise BridgeUnavailableError("Bridge stdin not open")
            proc.stdin.write(line + "\n")
            proc.stdin.flush()
    except (BrokenPipeError, OSError) as e:
        with _state_lock:
            _available = False
            _pending_events.pop(req_id, None)
            _pending_results.pop(req_id, None)
        raise BridgeUnavailableError(f"Bridge pipe broken: {e}") from e

    signaled = ev.wait(timeout=timeout)

    with _state_lock:
        _pending_events.pop(req_id, None)
        result_entry = _pending_results.pop(req_id, None)

    if not signaled:
        logger.warning("Bridge call '%s' (id=%s) timed out after %ss", method, req_id, timeout)
        raise BridgeTimeoutError(f"Bridge call '{method}' timed out after {timeout}s")

    if result_entry is None:
        raise BridgeExecutionError("No response received from bridge")

    result, err = result_entry
    if err:
        raise BridgeExecutionError(err)
    return result


def ping(timeout: float = 10.0) -> bool:
    """Ping the bridge to verify liveness and fast round-trip response."""
    try:
        res = _call("ping", timeout=timeout)
        return res == "pong"
    except Exception:
        return False


def version(timeout: float = 10.0) -> dict[str, Any] | None:
    """Return bridge runtime version and environment metadata."""
    try:
        return _call("version", timeout=timeout)
    except Exception:
        return None


def list_methods(timeout: float = 10.0) -> list[str] | None:
    """Query all methods supported by the active bridge executable."""
    try:
        return _call("list_methods", timeout=timeout)
    except Exception:
        return None


# ── Lazy bridge wrappers (fail silently to fall back to Python) ──


class LazyBridge:
    """Wraps bridge calls with graceful fallback."""

    @staticmethod
    def call(method: str, *args) -> Any | None:
        """Call the bridge and return its result, or ``None`` on failure.

        Retained for backward compatibility: callers that only read a truthy
        result cannot tell a successful void call (result None) apart from a
        genuine failure. Prefer :meth:`call_checked` when the outcome matters.
        """
        ok, result = LazyBridge.call_checked(method, *args)
        return result if ok else None

    @staticmethod
    def call_checked(method: str, *args) -> tuple[bool, Any]:
        """Call the bridge and return ``(success, result_or_error_message)``.

        Unlike :meth:`call`, this lets callers distinguish a genuine failure
        (False, error message) from a successful void command (True, None).
        It never raises — a bridge outage surfaces as ``(False, msg)`` so the
        upstream tool can report it to the LLM instead of pretending success.
        """
        if _shutdown_active:
            return False, "Bridge is shutting down"
        try:
            return True, _call(method, *args)
        except Exception as e:
            if _shutdown_active:
                return False, "Bridge is shutting down"
            # During normal shutdown, the bridge process is terminated
            # which causes pipe reads to fail with empty responses.
            # These are expected and should not be logged as errors.
            msg = str(e)
            if "Bridge process closed unexpectedly" in msg or "Bridge pipe broken" in msg:
                logger.debug("%s: %s (shutdown expected)", method, e)
            elif "(interrupted)" not in msg:
                logger.error("%s failed: %s", method, e)
            return False, msg or repr(e)


# ── Public API (mirrors old pythonnet-based exports) ──


class CInputSimulator:
    """Input simulation via the C# bridge.

    Each command reports its true outcome: ``False`` plus a logged reason when
    the bridge call failed, so callers can surface failures to the LLM instead
    of the old behavior of returning ``True`` unconditionally.
    """

    @staticmethod
    def MoveTo(x: int, y: int) -> bool:
        ok, _err = LazyBridge.call_checked("input_move_to", x, y)
        return ok

    @staticmethod
    def Click(button: str = "left") -> bool:
        ok, _err = LazyBridge.call_checked("input_click", button)
        return ok

    @staticmethod
    def ClickAt(x: int, y: int, button: str = "left") -> bool:
        ok, _err = LazyBridge.call_checked("input_click_at", x, y, button)
        return ok

    @staticmethod
    def GetCursorPosition():
        ok, r = LazyBridge.call_checked("input_get_cursor")
        return (r["x"], r["y"]) if ok and r else (0, 0)

    @staticmethod
    def TypeText(text: str) -> bool:
        ok, _err = LazyBridge.call_checked("input_type_text", text)
        return ok

    @staticmethod
    def PressKey(key: str) -> bool:
        ok, _err = LazyBridge.call_checked("input_press_key", key)
        return ok

    @staticmethod
    def ReleaseKey(key: str) -> bool:
        ok, _err = LazyBridge.call_checked("input_release_key", key)
        return ok

    @staticmethod
    def TapKey(key: str) -> bool:
        ok, _err = LazyBridge.call_checked("input_tap_key", key)
        return ok

    @staticmethod
    def Hotkey(keys: str) -> bool:
        ok, _err = LazyBridge.call_checked("input_hotkey", keys)
        return ok

    # ── Mouse Enhancements ──

    @staticmethod
    def DoubleClick(button: str = "left") -> bool:
        ok, _err = LazyBridge.call_checked("input_double_click", button)
        return ok

    @staticmethod
    def DoubleClickAt(x: int, y: int, button: str = "left") -> bool:
        ok, _err = LazyBridge.call_checked("input_double_click_at", x, y, button)
        return ok

    @staticmethod
    def SmoothMoveTo(x: int, y: int, duration_ms: int = 200) -> bool:
        ok, _err = LazyBridge.call_checked("input_smooth_move_to", x, y, duration_ms)
        return ok

    @staticmethod
    def Drag(x1: int, y1: int, x2: int, y2: int, button: str = "left") -> bool:
        ok, _err = LazyBridge.call_checked("input_drag", x1, y1, x2, y2, button)
        return ok

    @staticmethod
    def Scroll(clicks: int) -> bool:
        ok, _err = LazyBridge.call_checked("input_scroll", clicks)
        return ok

    @staticmethod
    def ScrollAt(x: int, y: int, clicks: int) -> bool:
        ok, _err = LazyBridge.call_checked("input_scroll_at", x, y, clicks)
        return ok

    @staticmethod
    def MoveRelative(dx: int, dy: int) -> bool:
        ok, _err = LazyBridge.call_checked("input_move_relative", dx, dy)
        return ok

    @staticmethod
    def MouseDown(button: str = "left") -> bool:
        ok, _err = LazyBridge.call_checked("input_mouse_down", button)
        return ok

    @staticmethod
    def MouseUp(button: str = "left") -> bool:
        ok, _err = LazyBridge.call_checked("input_mouse_up", button)
        return ok

    @staticmethod
    def GetScreenSize():
        ok, r = LazyBridge.call_checked("input_get_screen_size")
        return (r["width"], r["height"]) if ok and r else (0, 0)


class CScreenCapture:
    @staticmethod
    def CapturePrimaryScreen() -> bytes | None:
        import base64
        r = LazyBridge.call("capture_primary")
        return base64.b64decode(r) if r else None

    @staticmethod
    def CaptureMonitor(index: int) -> bytes | None:
        import base64
        r = LazyBridge.call("capture_monitor", index)
        return base64.b64decode(r) if r else None

    @staticmethod
    def GetScreenSize():
        r = LazyBridge.call("screen_size")
        return (r["width"], r["height"]) if r else (0, 0)


class CTtsEngine:
    @staticmethod
    def Speak(text: str):
        LazyBridge.call("tts_speak", text)

    @staticmethod
    def SpeakAsync(text: str):
        LazyBridge.call("tts_speak_async", text)

    @staticmethod
    def Stop():
        LazyBridge.call("tts_stop")

    @property
    def IsSpeaking(self) -> bool:
        r = LazyBridge.call("tts_is_speaking")
        return bool(r) if r is not None else False

    @IsSpeaking.setter
    def IsSpeaking(self, value): ...

    @staticmethod
    def SetRate(rate: int):
        LazyBridge.call("tts_set_rate", rate)

    @staticmethod
    def SetVolume(volume: int):
        LazyBridge.call("tts_set_volume", volume)

    @staticmethod
    def SetVoice(name: str):
        LazyBridge.call("tts_set_voice", name)

    @staticmethod
    def GetVoices() -> list:
        r = LazyBridge.call("tts_get_voices")
        return list(r) if r else []


class CSystemMonitor:
    @staticmethod
    def GetSnapshot() -> dict | None:
        return LazyBridge.call("system_snapshot")


class CWindowManager:
    @staticmethod
    def FindWindow(title: str) -> int | None:
        return LazyBridge.call("window_find", title)

    @staticmethod
    def FocusWindow(title: str) -> bool | None:
        return LazyBridge.call("window_focus", title)

    @staticmethod
    def GetActiveWindowTitle() -> str | None:
        return LazyBridge.call("window_get_active_title")

    @staticmethod
    def GetAllWindowTitles() -> list:
        r = LazyBridge.call("window_get_all_titles")
        return list(r) if r else []

    @staticmethod
    def GetAllWindows() -> list[dict]:
        """Get all visible windows with handle, title, pid, process_name, foreground, rect."""
        r = LazyBridge.call("window_get_all")
        return list(r) if r else []

    @staticmethod
    def CloseWindow(title: str) -> bool:
        """Send WM_CLOSE to a window by title."""
        r = LazyBridge.call("window_close", title)
        return bool(r)

    @staticmethod
    def MinimizeWindow(title: str) -> bool | None:
        return LazyBridge.call("window_minimize", title)

    @staticmethod
    def MaximizeWindow(title: str) -> bool | None:
        return LazyBridge.call("window_maximize", title)

    @staticmethod
    def GetWindowRect(title: str) -> tuple | None:
        r = LazyBridge.call("window_get_rect", title)
        return (r["left"], r["top"], r["right"], r["bottom"]) if r else None

    @staticmethod
    def MoveWindow(title: str, x: int, y: int) -> bool | None:
        """Move a window by title to (x, y), preserving its size."""
        return LazyBridge.call("window_move", title, x, y)

    @staticmethod
    def ResizeWindow(title: str, width: int, height: int) -> bool | None:
        """Resize a window by title to (width, height), preserving its position."""
        return LazyBridge.call("window_resize", title, width, height)

    @staticmethod
    def SetAlwaysOnTop(title: str, on_top: bool) -> bool | None:
        """Pin a window to the top of the z-order or release it."""
        return LazyBridge.call("window_set_always_on_top", title, on_top)

    @staticmethod
    def SetOpacity(title: str, opacity: float) -> bool | None:
        """Set a window's opacity to a value in [0, 1]."""
        return LazyBridge.call("window_set_opacity", title, opacity)

    @staticmethod
    def HideWindow(title: str) -> bool | None:
        """Hide a window by title."""
        return LazyBridge.call("window_hide", title)

    @staticmethod
    def ShowWindow(title: str) -> bool | None:
        """Show a previously hidden window by title."""
        return LazyBridge.call("window_show", title)

    @staticmethod
    def GetActiveWindowElements(max_depth: int = 3) -> list[dict] | None:
        """Inspect UI Automation element tree of the active window (buttons, inputs, labels).

        Returns:
            List of element dicts {'name': str, 'control_type': str, 'rect': dict, 'enabled': bool} or None.
        """
        return LazyBridge.call("window_get_elements", max_depth)


class CPowerManager:
    """System power control via the C# PowerManager (PowrProf/User32)."""

    @staticmethod
    def Sleep() -> bool | None:
        return LazyBridge.call("power_sleep")

    @staticmethod
    def Hibernate() -> bool | None:
        return LazyBridge.call("power_hibernate")

    @staticmethod
    def Lock() -> bool | None:
        return LazyBridge.call("power_lock")

    @staticmethod
    def Shutdown(confirm: bool = False) -> bool | None:
        return LazyBridge.call("power_shutdown", confirm)

    @staticmethod
    def Reboot(confirm: bool = False) -> bool | None:
        return LazyBridge.call("power_reboot", confirm)


class CToastNotifier:
    """Desktop toast notifications via the C# ToastNotifier (WinRT)."""

    @staticmethod
    def Show(title: str, message: str) -> bool | None:
        return LazyBridge.call("toast_show", title, message)


class CServiceManager:
    """Windows service enumeration and control via the C# ServiceHelper (WMI)."""

    @staticmethod
    def List() -> list[dict] | None:
        return LazyBridge.call("service_list")

    @staticmethod
    def Start(name: str) -> str | None:
        """Start a service. Returns None on success or an error message."""
        return LazyBridge.call("service_start", name)

    @staticmethod
    def Stop(name: str) -> str | None:
        """Stop a service. Returns None on success or an error message."""
        return LazyBridge.call("service_stop", name)


class CProcessHelper:
    """Process lifecycle control via the C# ProcessHelper (System.Diagnostics)."""

    @staticmethod
    def Kill(pid: int) -> str | None:
        """Kill a process by PID. Returns None on success or an error message."""
        return LazyBridge.call("process_kill", pid)

    @staticmethod
    def Wait(pid: int, timeout_ms: int = 30000) -> dict | None:
        """Wait for a process to exit; returns {'exited': bool, 'error': str | None}."""
        return LazyBridge.call("process_wait", pid, timeout_ms)


class CShortcutHelper:
    """Create .lnk shortcuts via the C# ShortcutHelper (WScript.Shell COM)."""

    @staticmethod
    def Create(link_path: str, target: str, arguments: str = "", working_dir: str = "", description: str = "") -> str | None:
        """Create a shortcut. Returns None on success or an error message."""
        return LazyBridge.call("shortcut_create", link_path, target, arguments, working_dir, description)


class CRecycleBin:
    """Recycle Bin query and empty via the C# RecycleBin (Shell32)."""

    @staticmethod
    def Get() -> dict | None:
        """Query item count and size. Returns {'hr', 'item_count', 'size_bytes'}."""
        return LazyBridge.call("recycle_bin_get")

    @staticmethod
    def Empty(confirm: bool = False) -> dict | None:
        """Empty the recycle bin; no-op unless confirm=True."""
        return LazyBridge.call("recycle_bin_empty", confirm)


class CKeyboardState:
    """Keyboard key-state queries via the C# KeyboardState (User32)."""

    @staticmethod
    def IsPressed(key: str) -> dict | None:
        """Whether a key is currently held. Returns {'pressed', 'error'}."""
        return LazyBridge.call("key_is_pressed", key)

    @staticmethod
    def CapsLock() -> bool | None:
        return LazyBridge.call("key_caps_lock")

    @staticmethod
    def NumLock() -> bool | None:
        return LazyBridge.call("key_num_lock")


class CDisplayBrightness:
    """Monitor DPI and brightness via the C# DisplayBrightness (shcore/dxva2)."""

    @staticmethod
    def GetDpi() -> dict | None:
        """Primary-monitor DPI. Returns {'dpi_x', 'dpi_y'} or {'error'}."""
        return LazyBridge.call("monitor_get_dpi")

    @staticmethod
    def GetBrightness() -> dict | None:
        """Current brightness range. Returns {'min', 'current', 'max'} or {'error'}."""
        return LazyBridge.call("brightness_get")

    @staticmethod
    def SetBrightness(level: int) -> dict | None:
        """Set brightness to 0-100. Returns {'level'} or {'error'}."""
        return LazyBridge.call("brightness_set", level)


class CEnvVarHelper:
    """User environment variable read/write via the C# EnvVarHelper (BCL)."""

    @staticmethod
    def Get(name: str) -> str | None:
        return LazyBridge.call("env_get", name)

    @staticmethod
    def Set(name: str, value: str) -> str | None:
        """Set a user env var; empty value deletes it. Returns None on success."""
        return LazyBridge.call("env_set", name, value)


class CClipboardHelper:
    @staticmethod
    def GetText() -> str | None:
        return LazyBridge.call("clipboard_paste_text")

    @staticmethod
    def SetText(text: str) -> bool | None:
        return LazyBridge.call("clipboard_copy_text", text)

    @staticmethod
    def HasText() -> bool | None:
        return LazyBridge.call("clipboard_has_text")

    @staticmethod
    def Clear() -> bool | None:
        return LazyBridge.call("clipboard_clear")

    @staticmethod
    def CopyImage(base64_dib: str) -> bool | None:
        """Copy a DIB bitmap (base64-encoded, BMP header stripped) to clipboard."""
        return LazyBridge.call("clipboard_copy_image", base64_dib)

    @staticmethod
    def HasImage() -> bool | None:
        return LazyBridge.call("clipboard_has_image")

    @staticmethod
    def GetFileDropList() -> list[str] | None:
        """Get list of file paths from clipboard (CF_HDROP)."""
        return LazyBridge.call("clipboard_get_file_list")

    @staticmethod
    def HasFiles() -> bool | None:
        """Check if clipboard contains file drop list."""
        return LazyBridge.call("clipboard_has_files")


class CAudioPlayer:
    @staticmethod
    def PlayMp3(file_path: str):
        """Play an MP3 file synchronously via MCI."""
        LazyBridge.call("audio_play_mp3", file_path)

    @staticmethod
    def StopAll():
        """Stop all MCI playback."""
        LazyBridge.call("audio_stop_all")


class CRegistryHelper:
    @staticmethod
    def GetDefaultBrowserProgId() -> str | None:
        return LazyBridge.call("registry_get_browser_progid")

    @staticmethod
    def ReadCurrentUser(sub_key: str, value_name: str) -> str | None:
        return LazyBridge.call("registry_read_current_user", sub_key, value_name)

    @staticmethod
    def ReadLocalMachine(sub_key: str, value_name: str) -> str | None:
        return LazyBridge.call("registry_read_local_machine", sub_key, value_name)


class CShellHelper:
    @staticmethod
    def Open(path: str) -> bool | None:
        """Open a file/URL with its associated application."""
        return LazyBridge.call("shell_open", path)

    @staticmethod
    def Launch(app_name: str) -> bool | None:
        """Launch a Windows application by name."""
        return LazyBridge.call("shell_launch", app_name)


class CHybridInfo:
    @staticmethod
    def SelfTest() -> bool | None:
        return LazyBridge.call("self_test")


class CMonitorInfo:
    """Monitor information via DisplayHelper."""

    @staticmethod
    def GetAllMonitors() -> list[dict] | None:
        """Get all monitors with bounds, work area, and primary flag."""
        r = LazyBridge.call("monitors_get_all")
        return list(r) if r else []


class CSystemState:
    """User/system state via StateHelper."""

    @staticmethod
    def GetSnapshot() -> dict | None:
        """Get combined snapshot: idle time, foreground process, full-screen, power."""
        return LazyBridge.call("system_state_get")


class CExplorerHelper:
    """Shell.Application COM helper for Explorer window state."""

    @staticmethod
    def GetActiveExplorerSelection() -> dict | None:
        """Get active Explorer window's folder path and selected items."""
        return LazyBridge.call("explorer_get_selection")

    @staticmethod
    def GetAllExplorerSelections() -> list[dict]:
        """Get all open Explorer windows' folder paths and selections."""
        r = LazyBridge.call("explorer_get_all_selections")
        return list(r) if r else []


class CAudioDeviceState:
    """Audio device state via pycaw (Core Audio API wrapper).

    Falls back to direct pycaw calls since the C# Core Audio COM interop
    has compatibility issues on newer Windows builds.
    """

    @staticmethod
    def GetAudioState() -> dict | None:
        """Return dict with playback and recording state (muted + volume)."""
        try:
            from pycaw.pycaw import AudioUtilities

            info = {"playback": None, "recording": None}

            # Speakers
            try:
                spk = AudioUtilities.GetSpeakers()
                if spk and spk.EndpointVolume:
                    vol = spk.EndpointVolume
                    info["playback"] = {  # type: ignore[assignment]
                        "muted": bool(vol.GetMute()),
                        "volume_percent": int(vol.GetMasterVolumeLevelScalar() * 100),
                    }
            except Exception as ex:
                logger.debug("Audio playback query failed: %s", ex)

            # Microphone
            try:
                mic = AudioUtilities.GetMicrophone()
                if mic:
                    from comtypes import CLSCTX_ALL, POINTER, cast
                    from pycaw.pycaw import IAudioEndpointVolume

                    mic_vol = mic.Activate(
                        IAudioEndpointVolume._iid_, CLSCTX_ALL, None
                    )
                    mic_vol = cast(mic_vol, POINTER(IAudioEndpointVolume))
                    info["recording"] = {  # type: ignore[assignment]
                        "muted": bool(mic_vol.GetMute()),
                        "volume_percent": int(
                            mic_vol.GetMasterVolumeLevelScalar() * 100
                        ),
                    }
            except Exception as ex:
                logger.debug("Audio recording query failed: %s", ex)

            return info
        except ImportError:
            logger.warning("pycaw not installed — cannot query audio state")
            return None
        except Exception as ex:
            logger.error("Audio state query failed: %s", ex)
            return None

