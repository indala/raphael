"""
Cloud STT Backend — OpenAI-compatible /audio/transcriptions batch transcription.

Cloud-based transcription using any endpoint that declares an ``stt_model``
(settings.toml [[endpoints]]). There is no built-in provider or model — the
endpoint, model, API key and base URL are all resolved dynamically. Uses the
OpenAI-compatible /audio/transcriptions multipart endpoint.

Inspired by Zero's internal/dictation/transcriber_cloud.go
"""

import io
import logging
import threading
import time
import wave
from pathlib import Path

# pyrefly: ignore [missing-import]
import numpy as np
import requests

from .base import STTBackend, STTResult, AuthError, SetupError, StreamHandle
from .registry import STTRegistry
from controller.state import state as _app_state

logger = logging.getLogger(__name__)


# ── VAD + Mic Capture Constants ──────────────────────────────────────
_SAMPLE_RATE = 16000          # 16kHz mono
_FRAME_DURATION_MS = 30       # 30ms frames
_FRAME_SIZE = int(_SAMPLE_RATE * _FRAME_DURATION_MS / 1000)  # 480
# Energy VAD (pure numpy — no C extensions)
_SPEECH_RMS_THRESHOLD = 0.0025     # float32 RMS to enter speech
_SILENCE_RMS_THRESHOLD = 0.0012    # float32 RMS to stay in speech (lower = hysteresis)
_MIN_SPEECH_FRAMES = 10            # ~300ms sustained energy to trigger recording
_MAX_SILENCE_FRAMES = 40           # ~1200ms silence = end of utterance
_MIN_SEGMENT_FRAMES = 20           # ~600ms minimum segment to transcribe
_MAX_SEGMENT_FRAMES = 300          # ~9s max before forced send
_STARTUP_GRACE_FRAMES = 100   # ~3s of silence after mic starts
_TTS_COOLDOWN_FRAMES = 100    # ~3s cooldown after TTS finishes
# AGC (Automatic Gain Control) — boosts quiet mics to usable level
_AGC_TARGET_RMS = 0.05        # Target RMS level after gain
_AGC_MAX_GAIN = 20.0          # Max amplification (prevents noise explosion)
_AGC_SMOOTHING = 0.92         # Higher = slower adaptation to level changes


@STTRegistry.register("cloud")
class CloudSTTBackend(STTBackend):
    """
    Cloud STT via an OpenAI-compatible /audio/transcriptions endpoint.

    Provider-agnostic: bound to whichever endpoint in settings.toml declares
    an ``stt_model`` (+ base URL). There is no built-in provider or model
    default. Supports both one-shot transcription (transcribe/transcribe_file)
    and continuous streaming via mic capture + VAD (start_streaming/stop).
    """

    PROVIDER = "cloud"
    #: API/endpoint-driven backend — the settings UI lists it through
    #: STT-capable endpoints, not as a hardcoded "(built-in)" provider.
    requires_endpoint = True

    @property
    def name(self) -> str:
        return "cloud"

    def __init__(self, endpoint=None):
        self._endpoint = endpoint  # optional bound endpoint from the registry
        self._endpoint_name = ""
        self._ready = False
        self._api_key = ""
        self._model = ""  # resolved dynamically from the endpoint's stt_model
        self._base_url = ""  # resolved dynamically from the endpoint's base_url
        # Streaming state
        self._stream = None
        self._stop_event = None
        self._vad = None
        self._speech_buffer = None
        self._in_speech = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._total_speech_frames = 0
        # AGC state
        self._rms_track = 0.0
        self._agc_gain = 1.0

    def _configure(self):
        """Resolve endpoint, model, and base URL dynamically from the endpoint registry (settings.toml [[endpoints]]).

        A bound endpoint is used as-is; an unbound instance picks the first
        STT-capable endpoint (registry order = priority given in settings).
        There is no built-in provider or model default.
        """
        if self._ready:
            return True
        if self._endpoint is not None:
            return self._configure_from_endpoint(self._endpoint)
        try:
            from orchestrator.endpoint_registry import all as _all_eps
            for ep in _all_eps():
                if getattr(ep, "stt_model", "") and getattr(ep, "base_url", ""):
                    return self._configure_from_endpoint(ep)
        except Exception as e:
            logger.debug("CloudSTT endpoint resolution error: %s", e)
        return False

    def _configure_from_endpoint(self, ep) -> bool:
        """Apply an endpoint's stt_model/base_url/api_key to this backend."""
        stt_model = (getattr(ep, "stt_model", "") or "").strip()
        base_url = (getattr(ep, "base_url", "") or "").strip()
        if not stt_model or not base_url:
            logger.warning(
                "CloudSTT: endpoint '%s' is missing stt_model/base_url — add stt_model = \"<model>\" "
                "under [[endpoints]] in settings.toml",
                getattr(ep, "name", "?"),
            )
            return False
        self._api_key = getattr(ep, "api_key", "") or ""
        self._model = stt_model
        self._base_url = base_url
        self._endpoint_name = getattr(ep, "name", "")
        self._ready = True
        logger.info("CloudSTT: configured from endpoint '%s' (model: %s)", self._endpoint_name, self._model)
        return True

    @property
    def supports_streaming(self) -> bool:
        return True  # Mic capture + VAD + cloud API = streaming-like behavior

    def health(self) -> bool:
        return bool(self._configure())

    # ── Streaming (mic capture + energy VAD) ──────────────────────────

    def start_streaming(self, callback) -> StreamHandle:
        """Start continuous mic capture → energy VAD → cloud transcription.

        Uses ``sounddevice.InputStream`` for capture and pure energy
        detection for voice activity (no C extensions in the audio thread).
        Detected speech segments are sent to the transcription API in background threads.

        Args:
            callback: Callable ``text: str, is_final: bool`` receiving results.

        Returns:
            A ``StreamHandle`` if capture started, ``None`` otherwise so the
            caller can fall through to the next STT backend.
        """
        if not self._configure():
            logger.error("CloudSTT: cannot start — no endpoint with stt_model configured")
            return None

        try:
            import sounddevice as sd
        except ImportError:
            logger.error("CloudSTT: sounddevice not installed")
            return None

        # Pre-import state reference (NOT in the callback — imports in
        # real-time audio threads can deadlock or crash the process)
        from controller.state import state as _state

        self._stop_event = threading.Event()
        self._speech_buffer = bytearray()
        self._in_speech = False
        self._silence_frames = 0
        self._speech_frames = 0
        self._total_speech_frames = 0
        self._frame_count = 0  # For startup grace period
        self._rms_track = 0.0  # Reset AGC state
        self._agc_gain = 1.0

        def audio_callback(indata, frames, time_info, status):
            try:
                _audio_callback_body(indata, frames, time_info, status)
            except sd.CallbackStop:
                raise  # Let sounddevice handle this
            except Exception as e:
                logger.error("CloudSTT callback error: %s", e)

        def _audio_callback_body(indata, frames, time_info, status):
            """Inner callback with no C extension calls — pure numpy."""
            nonlocal _state
            assert self._speech_buffer is not None  # set before stream starts
            if self._stop_event and self._stop_event.is_set():
                raise sd.CallbackStop

            # ── Startup grace period — ignore first ~3s ──
            self._frame_count += 1
            if self._frame_count < _STARTUP_GRACE_FRAMES:
                return

            # ── TTS feedback suppression ──
            if _state.tts_speaking:
                if self._in_speech:
                    self._in_speech = False
                    self._speech_buffer = bytearray()
                    self._silence_frames = 0
                    self._speech_frames = 0
                    self._total_speech_frames = 0
                return

            # ── AGC: Boost quiet signals to target RMS ──
            channel = indata[:, 0]
            raw_rms = np.sqrt(np.mean(channel ** 2))

            # Running average of input level (slow attack/release)
            self._rms_track = _AGC_SMOOTHING * self._rms_track + (1 - _AGC_SMOOTHING) * raw_rms

            # Calculate gain to bring running RMS to target
            target_gain = _AGC_TARGET_RMS / self._rms_track if self._rms_track > 0.0001 else 1.0

            # Smooth gain changes to avoid pumping
            self._agc_gain = 0.85 * self._agc_gain + 0.15 * min(target_gain, _AGC_MAX_GAIN)

            # Apply gain + hard clamp to prevent clipping
            channel *= self._agc_gain
            np.clip(channel, -1.0, 1.0, out=channel)

            # Recompute RMS after gain for VAD
            rms = np.sqrt(np.mean(channel ** 2))

            # Hysteresis: higher threshold to enter speech, lower to stay
            threshold = _SILENCE_RMS_THRESHOLD if self._in_speech else _SPEECH_RMS_THRESHOLD

            # Log RMS periodically for debugging (every ~100 frames ≈ 3s)
            if self._frame_count % 100 == 0:
                logger.info("VAD rms=%.4f  gain=%.1fx  threshold=%.3f  state=%s",
                            rms, self._agc_gain, threshold,
                            "speech" if self._in_speech else "silence")

            is_speech = rms > threshold

            if is_speech:
                self._silence_frames = 0
                if not self._in_speech:
                    self._speech_frames += 1
                    if self._speech_frames >= _MIN_SPEECH_FRAMES:
                        self._in_speech = True
                        self._total_speech_frames = 1
                        # Convert to int16 PCM and store
                        audio_int16 = (channel * 32767).astype(np.int16)
                        self._speech_buffer = bytearray(audio_int16.tobytes())
                        logger.debug("CloudSTT: speech started (rms=%.4f)", rms)
                else:
                    self._total_speech_frames += 1
                    audio_int16 = (channel * 32767).astype(np.int16)
                    self._speech_buffer.extend(audio_int16.tobytes())
                    # Force-send on max segment length
                    if self._total_speech_frames >= _MAX_SEGMENT_FRAMES:
                        segment = bytes(self._speech_buffer)
                        self._speech_buffer = bytearray()
                        self._total_speech_frames = 0
                        threading.Thread(
                            target=self._transcribe_stream_segment,
                            args=(segment, callback),
                            daemon=True,
                        ).start()
            else:
                self._speech_frames = 0
                if self._in_speech:
                    self._silence_frames += 1
                    self._total_speech_frames += 1
                    audio_int16 = (channel * 32767).astype(np.int16)
                    self._speech_buffer.extend(audio_int16.tobytes())
                    if self._silence_frames >= _MAX_SILENCE_FRAMES:
                        segment = bytes(self._speech_buffer)
                        self._in_speech = False
                        self._silence_frames = 0
                        self._speech_frames = 0
                        self._total_speech_frames = 0
                        self._speech_buffer = bytearray()
                        threading.Thread(
                            target=self._transcribe_stream_segment,
                            args=(segment, callback),
                            daemon=True,
                        ).start()

        logger.info("CloudSTT: starting mic capture at %dHz", _SAMPLE_RATE)
        try:
            import sounddevice as sd

            # ── Check for available mic devices ──
            try:
                devices = sd.query_devices()
                has_input = any(d.get("max_input_channels", 0) > 0 for d in devices if isinstance(d, dict))
                if not has_input:
                    logger.warning("CloudSTT: no microphone input devices found — skipping mic capture")
                    return StreamHandle(self)
            except Exception as dev_err:
                logger.debug("CloudSTT: device query failed: %s", dev_err)

            # ── Check UI mute state ──
            if _app_state.muted:
                logger.info("CloudSTT: mic muted in UI — not starting capture")
                return StreamHandle(self)

            self._stream = sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=_FRAME_SIZE,
                callback=audio_callback,
            )
            self._stream.start()
            return StreamHandle(self)
        except sd.PortAudioError as e:
            logger.warning("CloudSTT: mic unavailable (device busy or missing): %s", e)
            self._stream = None
            return StreamHandle(self)
        except AttributeError as e:
            # sounddevice might not expose query_devices properly on some builds
            logger.debug("CloudSTT: device query attribute error: %s", e)
            self._stream = None
            return StreamHandle(self)
        except Exception as e:
            logger.error("CloudSTT: mic capture failed: %s", e)
            self._stream = None
            self._vad = None
            return StreamHandle(self)

    def stop(self):
        """Stop mic capture."""
        if self._stop_event:
            self._stop_event.set()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def _transcribe_stream_segment(self, audio_segment: bytes, callback):
        """Transcribe a VAD-detected speech segment."""
        # Count 30ms frames — skip very short segments (background noise blips)
        num_frames = len(audio_segment) // 2 // _FRAME_SIZE
        if num_frames < _MIN_SEGMENT_FRAMES:
            logger.debug("CloudSTT: segment too short (%d frames), skipping", num_frames)
            return
        try:
            wav_data = self._ensure_wav(audio_segment)
            text = self._transcribe_wav(wav_data)
            if text:
                logger.debug("CloudSTT: transcribed (%d chars): %s", len(text), text[:60])
                callback(text, is_final=True)
        except AuthError as e:
            logger.error("CloudSTT auth failed: %s", e)
        except Exception as e:
            logger.debug("CloudSTT transcription error: %s", e)

    def transcribe(self, audio: bytes) -> STTResult:
        if not self._configure():
            return STTResult(
                success=False, backend=self.name,
                error="cloud STT not configured (no endpoint with stt_model)",
            )

        t0 = time.time()
        try:
            # Ensure audio is in WAV format
            wav_data = self._ensure_wav(audio)
            text = self._transcribe_wav(wav_data)
            elapsed = (time.time() - t0) * 1000
            return STTResult(
                success=True, text=text, backend=self.name,
                duration_ms=elapsed,
            )
        except AuthError:
            raise
        except SetupError:
            raise
        except Exception as e:
            return STTResult(
                success=False, backend=self.name,
                error=str(e), duration_ms=(time.time() - t0) * 1000,
            )

    def transcribe_file(self, path: str) -> STTResult:
        if not self._configure():
            return STTResult(
                success=False, backend=self.name,
                error="cloud STT not configured (no endpoint with stt_model)",
            )
        t0 = time.time()
        try:
            with open(path, "rb") as f:
                files = {"file": (Path(path).name, f, "audio/wav")}
                data = {"model": self._model, "response_format": "json"}
                headers = {}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"
                resp = requests.post(
                    f"{self._base_url}/audio/transcriptions",
                    headers=headers,
                    files=files, data=data, timeout=60,
                )
                if resp.status_code == 401:
                    raise AuthError(self.PROVIDER, "Invalid API key", backend=self.name)
                if resp.status_code == 403:
                    raise AuthError(self.PROVIDER, "API key lacks permissions", backend=self.name)
                resp.raise_for_status()
                text = resp.json().get("text", "").strip()
                return STTResult(
                    success=True, text=text, backend=self.name,
                    duration_ms=(time.time() - t0) * 1000,
                )
        except AuthError:
            raise
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 413:
                return STTResult(
                    success=False, backend=self.name,
                    error="Audio file too large (max 25MB)",
                    duration_ms=(time.time() - t0) * 1000,
                )
            status = e.response.status_code if e.response is not None else 0
            detail = e.response.text[:200] if e.response is not None else str(e)
            return STTResult(
                success=False, backend=self.name,
                error=f"HTTP {status}: {detail}",
                duration_ms=(time.time() - t0) * 1000,
            )
        except Exception as e:
            return STTResult(
                success=False, backend=self.name,
                error=str(e), duration_ms=(time.time() - t0) * 1000,
            )

    # ── Internal ──────────────────────────────────────────────────────

    def _ensure_wav(self, audio: bytes) -> bytes:
        """Convert raw PCM16 to WAV if needed (detected by RIFF header)."""
        if audio[:4] == b"RIFF":
            return audio  # Already WAV
        # Assume PCM16 mono 16kHz — wrap in WAV header
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(audio)
        return buf.getvalue()

    def _transcribe_wav(self, wav_data: bytes) -> str:
        """Send WAV data to the transcription API."""
        files = {"file": ("audio.wav", wav_data, "audio/wav")}
        data = {"model": self._model, "response_format": "json"}
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        resp = requests.post(
            f"{self._base_url}/audio/transcriptions",
            headers=headers,
            files=files, data=data, timeout=60,
        )
        if resp.status_code == 401:
            raise AuthError(self.PROVIDER, "Invalid API key", backend=self.name)
        if resp.status_code == 403:
            raise AuthError(self.PROVIDER, "API key lacks permissions", backend=self.name)
        resp.raise_for_status()
        text = resp.json().get("text", "")
        return str(text).strip()


