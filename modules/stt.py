"""
Speech-to-Text module — multi-backend with process isolation and fallback.

Architecture:
  - Uses the STTBackend ABC + Registry (mirroring TTSBackend pattern)
  - Runs transcription in an isolated subprocess (optional) so crashes don't
    take down the main application
  - Falls through configured backends automatically
  - Maintains the same public API as the original module

Crash sources eliminated:
  1. Subprocess crash → restart in <2s
  2. Backend failure  →  fallback chain
  3. Health pings     →  detects dead subprocess instantly
"""

from modules.stt_backends import IsolatedSTTRunner
import logging
import sys
import threading
import queue
from pathlib import Path

# Ensure project root is on sys.path
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

import config
from controller.state import state
import contextlib

logger = logging.getLogger(__name__)

# ── Backend system import (lazy to avoid import-order issues) ────────────
_STT_BACKENDS = None  # Populated on first use


def _load_backends():
    """Import and initialize the STT backend system."""
    global _STT_BACKENDS
    if _STT_BACKENDS is not None:
        return _STT_BACKENDS  # type: ignore[unreachable]
    from modules.stt_backends import (
        STTRegistry, IsolatedSTTRunner, IsolatedSTTConfig,
        STTResult, STTError,
    )
    _STT_BACKENDS = (STTRegistry, IsolatedSTTRunner, IsolatedSTTConfig, STTResult, STTError)
    return _STT_BACKENDS


# ====================================================================
# Public STT API — functions used by main.py / RaphaelController
# ====================================================================

# The shared queue for transcripts (consumed by the main loop's VAD poller)
transcript_queue: queue.Queue = queue.Queue(maxsize=32)

# Active state
_detector: BaseSpeechDetector | None = None
_running = False


class BaseSpeechDetector:
    """
    Unified base class that wraps both legacy (thread) and isolated
    (subprocess) STT modes.
    """

    def __init__(self):
        self.transcript_queue = transcript_queue
        self._running = False
        self._state_callback = None

    def set_state_callback(self, cb):
        """Register a callback fn(state_str) for UI state tracking."""
        self._state_callback = cb

    def start(self):
        """Override in subclass."""
        raise NotImplementedError

    def stop(self):
        """Override in subclass."""
        raise NotImplementedError

    @property
    def is_running(self):
        return self._running

    def run(self):
        """Duck-type compat with threading.Thread API — not used."""
        pass


class LegacyDetector(BaseSpeechDetector):
    """
    Uses the STTRegistry directly in-process (no subprocess).

    Simpler but crashes in the STT thread can still propagate.
    Used when STT_PROCESS_ISOLATION=False.
    """

    def __init__(self):
        super().__init__()
        self._backend_name = config.STT_BACKEND
        self._backend = None
        self._stop_event = threading.Event()

    def start(self) -> bool:
        """Start transcription using the configured backend.

        Returns:
            True if a backend started successfully, False otherwise.
        """
        STTRegistry, _IsolatedSTTRunner, _IsolatedSTTConfig, _STTResult, _STTError = _load_backends()

        # ── Check mic availability BEFORE trying any backend ──
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            has_input = any(d.get("max_input_channels", 0) > 0 for d in devices)
            if not has_input:
                logger.warning("No microphone input devices found — chat-only mode")
                return False
        except Exception as e:
            logger.debug("Mic check failed (%s) — proceeding anyway", e)

        preferred = config.STT_PREFERRED_BACKENDS
        if not preferred or preferred == [""]:
            preferred = [self._backend_name]

        logger.info("STT (legacy): preferred backends = %s", preferred)

        def on_transcript(text: str, is_final: bool):
            """Callback from backend — push to shared queue."""
            if not is_final:
                return  # Only final results
            if state.muted:
                return
            if state.tts_speaking:
                return  # Echo guard: don't transcribe our own voice
            if text:
                logger.debug("STT result: \"%s\"", text[:80])
                with contextlib.suppress(queue.Full):
                    self.transcript_queue.put_nowait(text)

        # Try each backend in order
        for name in preferred:
            instance = STTRegistry.get(name)
            if instance is None:
                logger.warning("STT backend '%s' not available", name)
                continue

            if not instance.health():
                logger.warning("STT backend '%s' unhealthy", name)
                continue

            try:
                if instance.supports_streaming:
                    # Wire state callback
                    if hasattr(instance, "set_state_callback") and self._state_callback:
                        instance.set_state_callback(self._state_callback)

                    started = instance.start_streaming(on_transcript)
                    if not started:
                        logger.warning("STT backend '%s' did not start (no mic?)", name)
                        continue
                    self._backend = instance
                    self._backend_name = name
                    self._running = True
                    logger.info("STT (legacy): started '%s'", name)
                    return True
                else:
                    logger.warning("STT backend '%s' doesn't support streaming, skipping", name)
            except Exception as e:
                logger.error("STT backend '%s' failed: %s", name, e)
                continue

        logger.error("STT (legacy): ALL backends failed — no speech input available")
        return False

    def stop(self):
        self._running = False
        if self._backend:
            try:
                self._backend.stop()
            except Exception as e:
                logger.debug("STT stop error: %s", e)
            self._backend = None

    def health(self) -> bool:
        if not self._running:
            return False
        if self._backend:
            try:
                return bool(self._backend.health())
            except Exception:
                pass
        return False


class IsolatedDetector(BaseSpeechDetector):
    """
    Runs STT in a subprocess with crash detection + auto-restart.
    IsolatedSTTRunner detects death via health pings and restarts.
    """

    def __init__(self):
        super().__init__()
        self._runner: IsolatedSTTRunner | None = None
        self._stop_event = threading.Event()

    def start(self):
        """Launch the isolated STT subprocess."""
        _STTRegistry, IsolatedSTTRunner, IsolatedSTTConfig, _STTResult, _STTError = _load_backends()

        # ── Check mic availability BEFORE starting subprocess ──
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            has_input = any(
                d.get("max_input_channels", 0) > 0 for d in devices if isinstance(d, dict)
            )
            if not has_input:
                logger.warning("No microphone input devices found — chat-only mode")
                return False
        except Exception as e:
            logger.debug("Mic check failed (%s) — proceeding anyway", e)

        preferred = tuple(
            p.strip()
            for p in config.STT_PREFERRED_BACKENDS
            if p.strip()
        )
        if not preferred:
            preferred = ("moonshine",)

        cfg = IsolatedSTTConfig(preferred_backends=preferred)
        self._runner = IsolatedSTTRunner(cfg)

        def on_transcript(text: str, is_final: bool):
            """Callback from subprocess — push to shared queue."""
            if not is_final:
                return
            if state.muted:
                return
            if state.tts_speaking:
                return  # Echo guard: don't transcribe our own voice
            if text:
                with contextlib.suppress(queue.Full):
                    self.transcript_queue.put_nowait(text)

        self._runner.start(on_transcript)
        self._running = True
        logger.info("STT (isolated): subprocess started with backends=%s", preferred)
        return True

    def stop(self):
        self._running = False
        if self._runner:
            try:
                self._runner.stop()
            except Exception as e:
                logger.debug("STT isolated stop error: %s", e)
            self._runner = None


# ====================================================================
# Factory — create the right detector based on config
# ====================================================================

def create_detector():
    """
    Create an STT detector based on config.

    Returns a duck-typed object (transcript_queue, start(), stop(), etc.).
    """

    # Pre-warm: import all backends so they register
    STTRegistry, _IsolatedSTTRunner, _IsolatedSTTConfig, _STTResult, _STTError = _load_backends()

    process_isolation = getattr(config, "STT_PROCESS_ISOLATION", True)
    logger.info("STT: process_isolation=%s", process_isolation)

    # ── VAD gate (Rhasspy-style wake→VAD→ASR) ──
    # Default on: the mic is gated by a voice-activity detector instead of
    # streaming continuously.
    if getattr(config, "STT_USE_VAD_GATE", True):
        try:
            from modules.voice_pipeline import GatedDetector

            gated = GatedDetector()
            if gated.available():
                logger.info("STT: using VAD-gated pipeline (batch=%s)", gated._batch_backends)
                return gated
            logger.warning("STT: VAD gate unavailable (no batch backend) — streaming fallback")
        except Exception as e:
            logger.warning("STT: VAD gate init failed (%s) — streaming fallback", e)

    if process_isolation:
        return IsolatedDetector()
    else:
        return LegacyDetector()


# ====================================================================
# Convenience functions (same API as original module)
# ====================================================================

def transcribe_mic(timeout: float = 10.0) -> str:
    """
    One-shot microphone transcription.

    Captures audio from the microphone and transcribes it using the
    configured backend chain. Returns empty string on failure.

    Compatible with the original convenience API.
    """
    STTRegistry, _IsolatedSTTRunner, _IsolatedSTTConfig, _STTResult, _STTError = _load_backends()

    # Capture audio from mic using sounddevice
    try:
        import sounddevice as sd

        logger.info("STT: recording from mic for %.1f seconds...", timeout)
        audio = sd.rec(int(timeout * 16000), samplerate=16000, channels=1, dtype="int16")
        sd.wait()
        audio_bytes = audio[:, 0].tobytes()
    except Exception as e:
        logger.error("STT mic capture failed: %s", e)
        return ""

    # Try each preferred backend
    preferred = getattr(config, "STT_PREFERRED_BACKENDS", None)
    if isinstance(preferred, list) and preferred:
        result = STTRegistry.transcribe_with_fallback(audio_bytes, preferred=preferred)
    else:
        result = STTRegistry.transcribe_with_fallback(audio_bytes)

    if result.success:
        return str(result.text)

    logger.warning("STT transcribe_mic failed: %s", result.error)
    return ""


def transcribe_file(path: str) -> str:
    """
    Transcribe an audio file using the configured backend.

    Args:
        path: Path to audio file (.wav, .mp3, .m4a, etc.)

    Returns:
        Transcribed text, or empty string on failure.
    """
    STTRegistry, _IsolatedSTTRunner, _IsolatedSTTConfig, _STTResult, _STTError = _load_backends()

    try:
        audio_bytes = Path(path).read_bytes()
    except Exception as e:
        logger.error("STT transcribe_file: cannot read '%s': %s", path, e)
        return ""

    preferred = getattr(config, "STT_PREFERRED_BACKENDS", None)
    if isinstance(preferred, list) and preferred:
        result = STTRegistry.transcribe_with_fallback(audio_bytes, preferred=preferred)
    else:
        result = STTRegistry.transcribe_with_fallback(audio_bytes)

    if result.success:
        return str(result.text)
    return ""
