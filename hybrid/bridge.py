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
_lock = threading.Lock()
_next_id = 0
_available = False
_shutdown_active = False


def _start() -> bool:
    """Launch the bridge subprocess."""
    global _process, _available, _stderr_thread

    if _shutdown_active:
        return False

    if _process is not None and _process.poll() is None:
        return True  # Already running

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
            encoding="utf-8",   # Explicit UTF-8: prevents charmap errors on non-ASCII chars
            errors="replace",   # Fallback: replace any remaining un-encodable chars
            bufsize=1,          # Line-buffered
            creationflags=creationflags,
        )
        _available = True
        # Drain stderr in a background thread to prevent pipe deadlocks
        # and capture DLL-load errors gracefully.
        _stderr_thread = threading.Thread(
            target=_drain_stderr,
            daemon=True,
            name="bridge-stderr",
        )
        _stderr_thread.start()
        logger.info("Bridge subprocess started (PID %s)", _process.pid)
        return True
    except Exception as e:
        logger.error("Failed to start bridge: %s", e)
        _available = False
        return False


def _drain_stderr():
    """Read and log bridge stderr (background thread).

    Without this the stderr pipe fills → subprocess deadlock.
    Also captures DLL-not-found errors for diagnostics.
    """
    global _process
    if _process is None or _process.stderr is None:
        return
    try:
        for line in _process.stderr:
            line = line.rstrip("\n\r")
            if not line:
                continue
            # Check for known missing-runtime patterns
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


# Background thread for draining bridge stderr
_stderr_thread: threading.Thread | None = None


def _stop():
    """Terminate the bridge subprocess."""
    global _process, _available, _shutdown_active
    _shutdown_active = True
    if _process is not None:
        p = _process
        _process = None
        _available = False
        if p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                with contextlib.suppress(Exception):
                    p.kill()
        # Safely close all standard streams to prevent Errno 22 / traceback printout
        for stream in (p.stdin, p.stdout, p.stderr):
            if stream:
                with contextlib.suppress(Exception):
                    stream.close()
        logger.info("Bridge subprocess stopped")


atexit.register(_stop)


def _call(method: str, *args, timeout: float = 10.0) -> Any:
    """Send a JSON-RPC call to the bridge and return the result.

    Args:
        method: The bridge method name.
        *args: Positional arguments for the method.
        timeout: Maximum seconds to wait for a response (default 10s).
                 Prevents indefinite blocking if the C# process hangs.

    Raises:
        RuntimeError: If bridge is unavailable, process dies, or timeout.
        TimeoutError: If the C# process does not respond within `timeout` seconds.
    """
    global _next_id, _available, _process
    if _shutdown_active:
        raise RuntimeError("Bridge shutting down")
    if not _available and not _start():
        raise RuntimeError("Bridge not available")

    # Quick health check — if process is dead, mark unavailable and bail
    if _process is None or _process.poll() is not None:
        _available = False
        raise RuntimeError("Bridge process not running")

    with _lock:
        _next_id += 1
        req_id = _next_id
        request = {"id": req_id, "method": method, "args": list(args)}
        line = json.dumps(request, ensure_ascii=False)

        try:
            assert _process is not None and _process.stdin is not None
            _process.stdin.write(line + "\n")
            _process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            _available = False
            raise RuntimeError(f"Bridge pipe broken: {e}") from e

        # Read response with timeout (prevents hang on crashed C# process)
        response_line = _read_line_with_timeout(_process.stdout, timeout)
        if response_line is None:
            # Timed out — kill the process to unblock stale reader threads
            _available = False
            p = _process
            _process = None
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                with contextlib.suppress(Exception):
                    p.kill()
            logger.error("Bridge call '%s' timed out after %ss — process terminated", method, timeout)
            raise TimeoutError(
                f"Bridge call '{method}' timed out after {timeout}s — process restarted"
            )
        if not response_line:
            _available = False
            raise RuntimeError("Bridge process closed unexpectedly")

        try:
            resp = json.loads(response_line)
        except json.JSONDecodeError as e:
            _available = False
            raise RuntimeError(f"Bridge response invalid: {e}") from e

        if resp.get("error"):
            raise RuntimeError(resp["error"])
        return resp.get("result")


def _read_line_with_timeout(stream, timeout: float) -> str | None:
    """Read a line from a text stream with timeout. Returns None on timeout."""
    import queue as _queue

    result_queue: _queue.Queue = _queue.Queue(maxsize=1)
    read_thread = threading.Thread(
        target=lambda: result_queue.put(stream.readline() if stream else ""),
        daemon=True,
    )
    read_thread.start()
    read_thread.join(timeout=timeout)
    if read_thread.is_alive():
        return None  # Timeout — caller should handle
    try:
        return result_queue.get_nowait()  # type: ignore[no-any-return]
    except _queue.Empty:
        return ""


# ── Lazy bridge wrappers (fail silently to fall back to Python) ──


class LazyBridge:
    """Wraps bridge calls with graceful fallback."""

    @staticmethod
    def call(method: str, *args) -> Any | None:
        if _shutdown_active:
            return None
        try:
            return _call(method, *args)
        except Exception as e:
            if _shutdown_active:
                return None  # type: ignore[unreachable]
            # During normal shutdown, the bridge process is terminated
            # which causes pipe reads to fail with empty responses.
            # These are expected and should not be logged as errors.
            msg = str(e)
            if "Bridge process closed unexpectedly" in msg or "Bridge pipe broken" in msg:
                logger.debug("%s: %s (shutdown expected)", method, e)
            elif "(interrupted)" not in msg:
                logger.error("%s failed: %s", method, e)
            return None


# ── Public API (mirrors old pythonnet-based exports) ──


class CInputSimulator:
    @staticmethod
    def MoveTo(x: int, y: int) -> bool:
        LazyBridge.call("input_move_to", x, y)
        return True

    @staticmethod
    def Click(button: str = "left") -> bool:
        LazyBridge.call("input_click", button)
        return True

    @staticmethod
    def ClickAt(x: int, y: int, button: str = "left") -> bool:
        LazyBridge.call("input_click_at", x, y, button)
        return True

    @staticmethod
    def GetCursorPosition():
        r = LazyBridge.call("input_get_cursor")
        return (r["x"], r["y"]) if r else (0, 0)

    @staticmethod
    def TypeText(text: str) -> bool:
        LazyBridge.call("input_type_text", text)
        return True

    @staticmethod
    def PressKey(key: str) -> bool:
        LazyBridge.call("input_press_key", key)
        return True

    @staticmethod
    def ReleaseKey(key: str) -> bool:
        LazyBridge.call("input_release_key", key)
        return True

    @staticmethod
    def TapKey(key: str) -> bool:
        LazyBridge.call("input_tap_key", key)
        return True

    @staticmethod
    def Hotkey(keys: str) -> bool:
        LazyBridge.call("input_hotkey", keys)
        return True

    # ── Mouse Enhancements ──

    @staticmethod
    def DoubleClick(button: str = "left") -> bool:
        LazyBridge.call("input_double_click", button)
        return True

    @staticmethod
    def DoubleClickAt(x: int, y: int, button: str = "left") -> bool:
        LazyBridge.call("input_double_click_at", x, y, button)
        return True

    @staticmethod
    def SmoothMoveTo(x: int, y: int, duration_ms: int = 200) -> bool:
        LazyBridge.call("input_smooth_move_to", x, y, duration_ms)
        return True

    @staticmethod
    def Drag(x1: int, y1: int, x2: int, y2: int, button: str = "left") -> bool:
        LazyBridge.call("input_drag", x1, y1, x2, y2, button)
        return True

    @staticmethod
    def Scroll(clicks: int) -> bool:
        LazyBridge.call("input_scroll", clicks)
        return True

    @staticmethod
    def ScrollAt(x: int, y: int, clicks: int) -> bool:
        LazyBridge.call("input_scroll_at", x, y, clicks)
        return True

    @staticmethod
    def MoveRelative(dx: int, dy: int) -> bool:
        LazyBridge.call("input_move_relative", dx, dy)
        return True

    @staticmethod
    def MouseDown(button: str = "left") -> bool:
        LazyBridge.call("input_mouse_down", button)
        return True

    @staticmethod
    def MouseUp(button: str = "left") -> bool:
        LazyBridge.call("input_mouse_up", button)
        return True

    @staticmethod
    def GetScreenSize():
        r = LazyBridge.call("input_get_screen_size")
        return (r["width"], r["height"]) if r else (0, 0)


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


class CHybridInfo:  # type: ignore[no-redef]
    @staticmethod
    def SelfTest() -> bool | None:
        return LazyBridge.call("self_test")


def is_available() -> bool:
    """Check if the bridge is available and working."""
    if not _BRIDGE_EXE.exists():
        return False
    try:
        result = CHybridInfo.SelfTest()
        return bool(result)
    except Exception:
        return False
