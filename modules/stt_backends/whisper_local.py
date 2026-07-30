"""
Local Offline Whisper STT Backend — faster-whisper implementation.

Provides 100% offline speech recognition using faster-whisper.
Supports GPU (CUDA) and CPU execution with model size selection (tiny, base, small, medium).
"""

import io
import logging
import threading

from .base import STTBackend, STTResult, StreamHandle, SetupError, STTError
from .registry import STTRegistry

logger = logging.getLogger(__name__)

_FASTER_WHISPER_AVAILABLE = None

def _check_faster_whisper() -> bool:
    global _FASTER_WHISPER_AVAILABLE
    if _FASTER_WHISPER_AVAILABLE is None:
        try:
            import faster_whisper
            _FASTER_WHISPER_AVAILABLE = True
        except ImportError:
            _FASTER_WHISPER_AVAILABLE = False
            logger.debug("faster-whisper package not installed — whisper_local backend disabled")
    return _FASTER_WHISPER_AVAILABLE


@STTRegistry.register("whisper_local")
class WhisperLocalBackend(STTBackend):
    """
    Local STT backend using faster-whisper for 100% offline speech recognition.

    Lazy loads the configured model (tiny, base, small, medium) on demand.
    Auto-detects CUDA / CPU computation device.
    """

    def __init__(self):
        self._model = None
        self._model_size = "base"
        self._device = "auto"
        self._compute_type = "default"
        self._lock = threading.Lock()
        self._state_callback = None
        self._running = False

    @property
    def name(self) -> str:
        return "whisper_local"

    def set_state_callback(self, cb):
        """Register a callback fn(state_str) for UI state tracking."""
        self._state_callback = cb

    def _ensure_model_loaded(self):
        """Lazy-load faster-whisper model."""
        if self._model is not None:
            return

        if not _check_faster_whisper():
            raise SetupError(
                tool="Whisper Local STT",
                hint="Install faster-whisper: pip install faster-whisper",
                backend=self.name,
            )

        with self._lock:
            if self._model is not None:
                return  # type: ignore[unreachable]

            import config
            self._model_size = getattr(config, "STT_WHISPER_LOCAL_MODEL", "base")
            device = getattr(config, "STT_WHISPER_DEVICE", "auto")

            logger.info("Loading local Whisper model '%s' (device=%s)...", self._model_size, device)
            try:
                import faster_whisper
                self._model = faster_whisper.WhisperModel(
                    self._model_size,
                    device=device,
                    compute_type="default",
                )
                logger.info("Local Whisper model '%s' loaded successfully", self._model_size)
            except Exception as e:
                logger.error("Failed to load local Whisper model '%s': %s", self._model_size, e)
                raise STTError(f"Model load failed: {e}", backend=self.name)

    # ── STTBackend interface ───────────────────────────────────────────

    def transcribe(self, audio: bytes) -> STTResult:
        """Transcribe PCM or WAV audio bytes using local Whisper."""
        try:
            self._ensure_model_loaded()
            assert self._model is not None
            audio_stream = io.BytesIO(audio)
            segments, info = self._model.transcribe(audio_stream, beam_size=5)
            text = " ".join([segment.text for segment in segments]).strip()
            duration_ms = getattr(info, "duration", 0.0) * 1000
            return STTResult(
                success=True,
                text=text,
                backend=self.name,
                duration_ms=duration_ms,
            )
        except SetupError as e:
            return STTResult(success=False, backend=self.name, error=str(e))
        except Exception as e:
            logger.error("Whisper local transcription error: %s", e)
            return STTResult(success=False, backend=self.name, error=str(e))

    @property
    def supports_streaming(self) -> bool:
        return _check_faster_whisper()

    def start_streaming(self, on_partial) -> StreamHandle:
        """Continuous audio processing callback streaming."""
        if not _check_faster_whisper():
            raise SetupError(
                tool="Whisper Local STT",
                hint="Install faster-whisper: pip install faster-whisper",
                backend=self.name,
            )
        try:
            self._ensure_model_loaded()
            self._running = True
            if self._state_callback:
                self._state_callback("IDLE")
            logger.info("Whisper local STT active")
            return StreamHandle(self)
        except Exception as e:
            logger.error("Failed to start Whisper local streaming: %s", e)
            on_partial("", True)
            return StreamHandle(self)

    def health(self) -> bool:
        return _check_faster_whisper()

    def stop(self):
        self._running = False

    def close(self):
        self.stop()
        self._model = None
