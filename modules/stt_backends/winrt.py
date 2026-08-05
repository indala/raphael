"""
WinRT STT Backend — Windows.Media.SpeechRecognition continuous dictation.

Uses the modern Windows speech engine (same as Windows Voice Access) for
always-listening dictation. Extracted into STTBackend ABC with:
  - Crash isolation via dedicated event loop + thread
  - Proper task cleanup to prevent "Task was destroyed" errors
  - Graceful handling of SpeechRuntime.exe failures
"""

import asyncio
import datetime
import logging
import threading
import time

from .base import STTBackend, STTResult, SetupError
from .registry import STTRegistry
import contextlib

logger = logging.getLogger(__name__)

# WinRT projections are imported lazily via _load_winrt() — never at module
# level. Loading WinRT's native DLLs before onnxruntime breaks onnxruntime's
# DLL initialization on Windows (ERROR_DLL_INIT_FAILED), which silently
# degrades the silero VAD gate to the energy fallback. These globals are
# bound by _load_winrt() on first successful import.
_WINRT_AVAILABLE = False

SpeechRecognizer = None
SpeechRecognitionResultStatus = None
SpeechRecognizerState = None
SpeechRecognitionTopicConstraint = None
SpeechRecognitionScenario = None


def _load_winrt() -> bool:
    """Import WinRT projections on first use; report whether they work.

    onnxruntime is imported first so it is always resident before WinRT's
    native DLLs enter the process — the ordering that avoids the DLL init
    conflict regardless of which code path triggers this loader.
    """
    global _WINRT_AVAILABLE
    global SpeechRecognizer, SpeechRecognitionResultStatus
    global SpeechRecognizerState, SpeechRecognitionTopicConstraint, SpeechRecognitionScenario
    if _WINRT_AVAILABLE:
        return True
    try:
        import onnxruntime  # noqa: F401 — must precede WinRT native DLLs
    except ImportError:
        pass  # onnxruntime absent → nothing to conflict with later
    try:
        import winrt.windows.foundation.collections  # noqa: F401 — pre-import IVector proxy
        from winrt.windows.media.speechrecognition import (
            SpeechRecognizer,
            SpeechRecognitionResultStatus,
            SpeechRecognizerState,
            SpeechRecognitionTopicConstraint,
            SpeechRecognitionScenario,
        )
        _WINRT_AVAILABLE = True
    except ImportError:
        logger.debug("winrt package not available — WinRT STT backend disabled")
    return _WINRT_AVAILABLE

# Known Windows speech-engine HRESULT codes (as signed 32-bit).
_WINERR_INTERNAL_SPEECH = -2147199584  # "Internal Speech Error" — typically when running elevated
_WINERR_PRIVACY_POLICY = -2147199735   # online speech recognition privacy policy not accepted


def _is_elevated() -> bool:
    """True if this process runs with Administrator privileges.

    Windows' speech engine (SpeechRuntime.exe) often fails to create a
    recognizer from an elevated integrity level, surfacing as
    ``Internal Speech Error``. Detection lets us warn the user instead of
    silently producing a dead STT.
    """
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


@STTRegistry.register("winrt")
class WinRTBackend(STTBackend):
    """
    STT backend using Windows.Media.SpeechRecognition (WinRT).

    Always-listening dictation on a daemon thread with its own asyncio loop.
    Transcripts delivered via ``on_partial(text, is_final)`` callback.

    Engine crashes are caught and reported — never propagate as segfaults.
    """

    @property
    def name(self) -> str:
        return "winrt"

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event: asyncio.Event | None = None
        self._running = False
        self._state_callback = None
        self._recognizer = None  # Keep reference to prevent GC
        self._session = None     # Keep reference to prevent GC
        # Init handshake — start_streaming() must NOT claim success until the
        # recognizer is actually live, otherwise the fallback chain (groq,
        # whisper_local) never gets a chance when WinRT cannot start (e.g.
        # elevated-process "Internal Speech Error").
        self._init_done = threading.Event()
        self._init_success = False
        self._init_error = ""

    def set_state_callback(self, cb):
        """Register a callback fn(state_str) for UI state tracking."""
        self._state_callback = cb

    # ── STTBackend interface ───────────────────────────────────────────

    def transcribe(self, audio: bytes) -> STTResult:
        return STTResult(
            success=False, backend=self.name,
            error="WinRT backend does not support batch transcription; use start_streaming()",
        )

    @property
    def supports_streaming(self) -> bool:
        return _load_winrt()

    def start_streaming(self, on_partial):
        """Start continuous dictation on a background thread.

        Blocks briefly (up to 8s) on an init handshake so this method only
        returns ``True`` once the recognizer is genuinely listening. On any
        init failure it returns ``False`` so the caller's fallback chain
        (groq, whisper_local) can take over instead of a silently dead winrt.
        """
        if not _load_winrt():
            raise SetupError(
                tool="WinRT STT",
                hint="Install winrt: pip install winrt-runtime "
                     "winrt-Windows.Foundation winrt-Windows.Foundation.Collections "
                     "winrt-Windows.Media.SpeechRecognition",
                backend=self.name,
            )

        if _is_elevated():
            logger.warning(
                "Raphael is running as Administrator. Windows speech recognition "
                "often fails in elevated processes ('Internal Speech Error'). If "
                "WinRT STT cannot start, relaunch without 'Run as administrator' "
                "or rely on the groq/whisper_local fallback."
            )

        self._stop_event = asyncio.Event()
        self._init_done = threading.Event()
        self._init_success = False
        self._init_error = ""
        self._thread = threading.Thread(
            target=self._run_loop, args=(on_partial,),
            daemon=True, name="stt-winrt",
        )
        self._thread.start()

        # Wait for the background thread to reach "listening" (or fail). The
        # recognizer is created inside that thread, so without this wait we'd
        # return success before the recognizer exists.
        if not self._init_done.wait(timeout=8.0):
            self._init_error = self._init_error or "timed out waiting for WinRT recognizer init"
            logger.error("WinRT STT init timed out: %s", self._init_error)
            return False
        if not self._init_success:
            logger.error("WinRT STT failed to start: %s", self._init_error)
            return False
        return True

    def health(self) -> bool:
        if not _load_winrt():
            return False
        return not (self._thread and not self._thread.is_alive())

    def stop(self):
        """Stop dictation and shut down the event loop."""
        self._running = False
        if self._loop and self._stop_event:
            with contextlib.suppress(Exception):
                self._loop.call_soon_threadsafe(self._stop_event.set)

    def close(self):
        self.stop()

    # ── Internal: asyncio loop in background thread ─────────────────────

    def _run_loop(self, on_partial):
        """Background thread entry point."""
        self._running = True
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._async_run(on_partial))
        except Exception as e:
            logger.exception("WinRT STT loop crashed: %s", e)
            self._init_success = False
            self._init_error = self._init_error or f"loop crashed: {e}"
            self._init_done.set()
        finally:
            # Clean up pending tasks to avoid "Task was destroyed" errors
            try:
                pending = asyncio.all_tasks(self._loop)
                if pending:
                    for t in pending:
                        t.cancel()
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            with contextlib.suppress(Exception):
                self._loop.close()
            self._loop = None
            self._running = False

    async def _async_run(self, on_partial):
        """Async coroutine: create recognizer, compile grammar, run."""
        if self._stop_event is None:
            self._stop_event = asyncio.Event()

        # Create recognizer — store as instance var to prevent GC
        try:
            recognizer = SpeechRecognizer()
            self._recognizer = recognizer
        except Exception as e:
            winerr = getattr(e, "winerror", None)
            logger.error("Failed to create SpeechRecognizer: %s", e)
            if winerr == _WINERR_INTERNAL_SPEECH:
                logger.error(
                    "WinRT: 'Internal Speech Error' usually means Raphael is running "
                    "as Administrator — relaunch without 'Run as administrator'."
                )
            logger.error("Enable microphone access in Windows Privacy settings.")
            self._init_success = False
            self._init_error = f"SpeechRecognizer() failed: {e}"
            self._init_done.set()
            on_partial("", True)  # Signal error
            return

        # Add dictation constraint
        constraint = SpeechRecognitionTopicConstraint(
            SpeechRecognitionScenario.DICTATION, "dictation"
        )
        recognizer.constraints.append(constraint)

        # ── Fix the built-in silence timeout ────────────────────────
        # SpeechRecognizer.Timeouts (plural!) exposes:
        #   initial_silence_timeout  — wait for speech to START (default 5s)
        #   end_silence_timeout      — pause after speech before finalizing (default 0.5s)
        #   babble_timeout           — noise the recognizer treats as speech
        # These take datetime.timedelta. The old code set
        # `recognizer.timeout.speech_recognition_timeout = 0`, which
        # (a) used the wrong attribute name (Timeout vs Timeouts) and
        # (b) referenced a property that doesn't exist — so the default
        # 5s wait-for-speech timeout always fired, ending every session
        # with TIMEOUT_EXCEEDED after ~5s of silence and missing wake words.
        #
        # Fix: extend the initial silence window to "wait indefinitely".
        # We deliberately leave end_silence_timeout at its default — that
        # value is what finalizes an utterance after the user stops
        # speaking; zeroing it can prevent commands from finalizing.
        try:
            _timeouts = recognizer.timeouts
            _timeouts.initial_silence_timeout = datetime.timedelta(0)
            logger.debug("WinRT initial silence timeout disabled (wait indefinitely)")
        except Exception as e:
            logger.debug("Could not set silence timeout: %s", e)

        # ── Event handlers ──────────────────────────────────────────

        def on_result_generated(sender, args):
            """Fired on each recognized utterance."""
            try:
                result = args.result
                if result.status == SpeechRecognitionResultStatus.SUCCESS:
                    text = result.text.strip()
                    if text and self._running:
                        logger.info("WinRT heard: \"%s\"", text[:80])
                        on_partial(text, True)
                else:
                    logger.debug("WinRT result status: %s", result.status)
            except Exception as e:
                logger.warning("WinRT result callback error: %s", e)

        def on_state_changed(sender, args):
            """Fired on recognizer state transitions."""
            state_name = getattr(sender.state, "name", str(sender.state))
            logger.debug("WinRT state: %s", state_name)
            if self._state_callback:
                try:
                    state = sender.state
                    mapping = {
                        SpeechRecognizerState.IDLE: "IDLE",
                        SpeechRecognizerState.CAPTURING: "SPEECHING",
                        SpeechRecognizerState.PROCESSING: "PROCESSING",
                    }
                    self._state_callback(mapping.get(state, "IDLE"))
                except Exception as e:
                    logger.debug("WinRT state callback error: %s", e)

        # Session restart with exponential backoff
        _restart_delay = 0.5
        _restart_attempts = 0
        _max_restart_attempts = 10
        _session_start_time = time.time()

        async def restart_session():
            nonlocal _restart_delay, _restart_attempts, _session_start_time
            duration = time.time() - _session_start_time
            if duration < 2.0:
                _restart_attempts += 1
                _restart_delay = min(_restart_delay * 2, 10.0)
                logger.warning(
                    "WinRT session ended quickly (%.2fs) — restart attempt %d/%d (delay %.1fs)",
                    duration, _restart_attempts, _max_restart_attempts, _restart_delay
                )
            else:
                _restart_delay = 0.5
                _restart_attempts = 0

            await asyncio.sleep(_restart_delay)
            if not self._running:
                return

            if _restart_attempts >= _max_restart_attempts:
                logger.error("Max restart attempts reached for WinRT STT — stopping")
                self._running = False
                return

            try:
                # Deliberately do NOT call stop_async() here. This coroutine
                # runs in response to on_completed — the session has already
                # ended. Calling stop_async() on an ended session emits a
                # spurious USER_CANCELED completion that re-triggers
                # on_completed, producing a self-perpetuating restart loop.
                # Just start a fresh session directly.
                await session.start_async()
                _session_start_time = time.time()
                logger.info("WinRT session restarted (back in listening mode)")
            except Exception as e:
                _restart_attempts += 1
                logger.error("WinRT restart %d failed: %s", _restart_attempts, e)
                if _restart_attempts >= _max_restart_attempts:
                    logger.error("Max restart attempts — stopping WinRT STT")
                    self._running = False
                    return
                _restart_delay = min(_restart_delay * 2, 30.0)

        def on_completed(sender, args):
            """Session ended — log status and restart if still running."""
            status_code = getattr(args, "status", None)
            status_name = getattr(status_code, "name", str(status_code)) if status_code is not None else "unknown"
            duration = time.time() - _session_start_time

            # USER_CANCELED is emitted in two cases:
            #   (a) our own stop_async() on clean shutdown — self-inflicted, not
            #       running, no restart needed, no alarm.
            #   (b) the OS speech engine interrupting an ACTIVE session, e.g. on
            #       audio-focus/routing changes or mic contention. This is a
            #       normal, recoverable interrupt — restart and keep listening.
            if status_name == "USER_CANCELED" and not self._running:
                logger.debug("WinRT session stopped cleanly (status: USER_CANCELED)")
                return
            if status_name == "USER_CANCELED" and self._running:
                logger.info(
                    "WinRT session interrupted by the system (%.2fs) — auto-restarting",
                    duration,
                )
            else:
                logger.warning(
                    "WinRT session ended (%.2fs) — status: %s",
                    duration, status_name,
                )
            if self._running and self._loop and self._loop.is_running():
                with contextlib.suppress(RuntimeError):
                    asyncio.run_coroutine_threadsafe(restart_session(), self._loop)

        # Wire events
        session = recognizer.continuous_recognition_session
        self._session = session  # Keep reference to prevent GC
        state_token = recognizer.add_state_changed(on_state_changed)
        result_token = session.add_result_generated(on_result_generated)
        completed_token = session.add_completed(on_completed)

        # Compile grammar
        logger.info("WinRT: Compiling dictation grammar...")
        try:
            status = (await recognizer.compile_constraints_async()).status
        except Exception as e:
            logger.error("WinRT grammar compilation failed: %s", e)
            self._init_success = False
            self._init_error = f"grammar compilation failed: {e}"
            self._init_done.set()
            on_partial("", True)
            return

        if status != SpeechRecognitionResultStatus.SUCCESS:
            logger.error("WinRT grammar compilation failed: %s", status)
            self._init_success = False
            self._init_error = f"grammar compilation status: {status}"
            self._init_done.set()
            on_partial("", True)
            return

        # Start recognition
        try:
            await session.start_async()
            _session_start_time = time.time()
        except OSError as e:
            winerr = getattr(e, "winerror", None)
            if winerr == _WINERR_PRIVACY_POLICY:
                logger.error("WinRT: Online speech recognition privacy policy not accepted.")
                logger.error("Settings → Privacy & security → Speech → ON")
            else:
                logger.error("WinRT start failed: %s", e)
            self._init_success = False
            self._init_error = f"session.start_async() failed: {e}"
            self._init_done.set()
            on_partial("", True)
            return
        except Exception as e:
            logger.error("WinRT start failed: %s", e)
            self._init_success = False
            self._init_error = f"session.start_async() failed: {e}"
            self._init_done.set()
            on_partial("", True)
            return

        logger.info("WinRT STT active — speak anytime")
        self._init_success = True
        self._init_error = ""
        self._init_done.set()
        self._running = True

        # Keep alive until stop
        await self._stop_event.wait()

        # ── Clean shutdown ──────────────────────────────────────────
        with contextlib.suppress(Exception):
            await session.stop_async()
        try:
            recognizer.remove_state_changed(state_token)
            session.remove_result_generated(result_token)
            session.remove_completed(completed_token)
        except Exception as e:
            logger.debug("WinRT handler cleanup: %s", e)
        self._recognizer = None
        self._session = None
