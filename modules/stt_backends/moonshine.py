"""
Local Offline Moonshine STT Backend — useful-sensors-moonshine implementation.

Provides ultra-fast, low-latency ASR using Useful Sensors Moonshine models (moonshine/tiny, moonshine/base).
Designed for real-time edge/CPU speech recognition with zero Admin elevation crashes and minimal memory usage.
"""

import io
import logging
import threading
import wave
import contextlib

from .base import STTBackend, STTResult, StreamHandle, SetupError, STTError
from .registry import STTRegistry

logger = logging.getLogger(__name__)

_MOONSHINE_AVAILABLE = None


def _check_moonshine() -> bool:
    global _MOONSHINE_AVAILABLE
    if _MOONSHINE_AVAILABLE is None:
        try:
            import moonshine  # useful-sensors-moonshine package
            _MOONSHINE_AVAILABLE = True
        except ImportError:
            try:
                import moonshine_onnx  # fallback ONNX moonshine
                _MOONSHINE_AVAILABLE = True
            except ImportError:
                _MOONSHINE_AVAILABLE = False
                logger.debug("moonshine / useful-sensors-moonshine package not installed — moonshine backend disabled")
    return _MOONSHINE_AVAILABLE


@STTRegistry.register("moonshine")
class MoonshineBackend(STTBackend):
    """
    Local STT backend using Moonshine for fast offline speech recognition.

    Lazy loads the configured model (moonshine/tiny, moonshine/base) on demand.
    Optimized for high-speed CPU inference.
    """

    def __init__(self):
        self._model = None
        self._model_name = "moonshine/tiny"
        self._lock = threading.Lock()
        self._state_callback = None
        self._running = False
        self._stream = None

    @property
    def name(self) -> str:
        return "moonshine"

    def set_state_callback(self, cb):
        """Register a callback fn(state_str) for UI state tracking."""
        self._state_callback = cb

    def prewarm(self):
        """Pre-warm model in background thread to eliminate first-call load lag."""
        try:
            self._ensure_model_loaded()
        except Exception as e:
            logger.debug("Moonshine prewarm error: %s", e)

    def _ensure_model_loaded(self):
        """Lazy-load Moonshine model."""
        if self._model is not None:
            return

        if not _check_moonshine():
            raise SetupError(
                tool="Moonshine STT",
                hint="Install useful-sensors-moonshine: pip install useful-sensors-moonshine",
                backend=self.name,
            )

        with self._lock:
            if self._model is not None:
                return

            import config
            self._model_name = getattr(config, "STT_MOONSHINE_MODEL", "moonshine/tiny")
            logger.info("Loading local Moonshine model '%s'...", self._model_name)
            try:
                import moonshine
                self._model = moonshine
                logger.info("Local Moonshine model '%s' ready", self._model_name)
            except Exception as e:
                try:
                    import moonshine_onnx
                    self._model = moonshine_onnx
                    logger.info("Local Moonshine (ONNX) model '%s' ready", self._model_name)
                except Exception as e2:
                    logger.error("Failed to load local Moonshine model '%s': %s", self._model_name, e)
                    raise STTError(f"Model load failed: {e}", backend=self.name)

    def _audio_bytes_to_float32(self, audio: bytes):
        import numpy as np
        if audio[:4] == b"RIFF":
            # Strip WAV header if present (44 bytes standard header)
            audio = audio[44:]
        pcm16 = np.frombuffer(audio, dtype=np.int16)
        return pcm16.astype(np.float32) / 32768.0

    # ── STTBackend interface ───────────────────────────────────────────

    def transcribe(self, audio: bytes) -> STTResult:
        """Transcribe PCM or WAV audio bytes using Moonshine."""
        try:
            self._ensure_model_loaded()
            import numpy as np
            import time
            t0 = time.time()
            audio_float32 = self._audio_bytes_to_float32(audio)
            if len(audio_float32) < 1600:  # < 0.1s
                return STTResult(success=True, text="", backend=self.name, duration_ms=0)

            # useful-sensors-moonshine API: moonshine.transcribe(audio_data, model_name)
            assert self._model is not None
            results = self._model.transcribe(audio_float32, self._model_name)
            if isinstance(results, list):
                text = " ".join([r.strip() if isinstance(r, str) else str(r) for r in results]).strip()
            else:
                text = str(results).strip()

            duration_ms = (time.time() - t0) * 1000
            return STTResult(
                success=True,
                text=text,
                backend=self.name,
                duration_ms=duration_ms,
            )
        except SetupError as e:
            return STTResult(success=False, backend=self.name, error=str(e))
        except Exception as e:
            logger.error("Moonshine transcription error: %s", e)
            return STTResult(success=False, backend=self.name, error=str(e))

    @property
    def supports_streaming(self) -> bool:
        return _check_moonshine()

    def start_streaming(self, on_partial) -> StreamHandle:
        """Start continuous mic capture → VAD → Moonshine transcription."""
        if not _check_moonshine():
            raise SetupError(
                tool="Moonshine STT",
                hint="Install useful-sensors-moonshine: pip install useful-sensors-moonshine",
                backend=self.name,
            )
        try:
            import numpy as np
            import sounddevice as sd
        except ImportError as e:
            logger.error("Moonshine STT streaming requires sounddevice and numpy: %s", e)
            raise STTError(f"Streaming dependencies missing: {e}", backend=self.name)

        try:
            self._ensure_model_loaded()
            self._running = True
            self._stop_event = threading.Event()
            self._speech_buffer = bytearray()
            self._in_speech = False
            self._silence_frames = 0

            from controller.state import state as _state

            def audio_callback(indata, frames, time_info, status):
                if self._stop_event and self._stop_event.is_set():
                    raise sd.CallbackStop

                if _state.tts_speaking or _state.muted:
                    return

                channel = indata[:, 0]
                rms = float(np.sqrt(np.mean(channel ** 2)))
                pcm16 = (channel * 32767).astype(np.int16).tobytes()

                threshold = 0.015 if self._in_speech else 0.03
                if rms > threshold:
                    self._in_speech = True
                    self._silence_frames = 0
                    self._speech_buffer.extend(pcm16)
                elif self._in_speech:
                    self._silence_frames += 1
                    self._speech_buffer.extend(pcm16)
                    # ~400ms silence ends utterance
                    if self._silence_frames > 12:
                        audio_data = bytes(self._speech_buffer)
                        self._speech_buffer = bytearray()
                        self._in_speech = False
                        self._silence_frames = 0

                        if len(audio_data) > 16000 * 2 * 0.35:  # >0.35s
                            def _run_transcribe():
                                try:
                                    res = self.transcribe(audio_data)
                                    if res.success and res.text:
                                        on_partial(res.text, True)
                                except Exception as err:
                                    logger.error("Moonshine stream transcribe error: %s", err)

                            threading.Thread(target=_run_transcribe, daemon=True).start()

            self._stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="float32",
                blocksize=512,
                callback=audio_callback,
            )
            self._stream.start()

            if self._state_callback:
                self._state_callback("IDLE")
            logger.info("Moonshine STT mic capture active")
            return StreamHandle(self)
        except Exception as e:
            logger.error("Failed to start Moonshine streaming: %s", e)
            on_partial("", True)
            raise STTError(f"Failed to start Moonshine streaming: {e}", backend=self.name)

    def health(self) -> bool:
        return _check_moonshine()

    def stop(self):
        self._running = False
        if hasattr(self, "_stop_event") and self._stop_event:
            self._stop_event.set()
        if hasattr(self, "_stream") and self._stream:
            with contextlib.suppress(Exception):
                self._stream.stop()
                self._stream.close()
            self._stream = None

    def close(self):
        self.stop()
        self._model = None
