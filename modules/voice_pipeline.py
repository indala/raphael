"""
Voice Pipeline — Rhasspy-style wake → VAD → ASR gating.

The microphone is no longer streamed continuously to a speech engine.
Instead:

  1. A lightweight Voice Activity Detector (VAD) decides whether a human
     is actually speaking. silero-vad (via onnxruntime) is used when the
     model file is present; an energy/RMS-based VAD is the built-in
     fallback, so the pipeline always works even without extra deps.
  2. Only complete spoken utterances are transcribed, on demand, using the
     configured *batch* STT backends (winrt is streaming-only and cannot be
     used here).
  3. In wake-word mode, a short VAD probe utterance is transcribed and
     matched against STT_WAKE_WORDS to "arm" the assistant. The next
     utterance is the command. If the wake word arrives with a trailing
     command in the same utterance ("hey raphael open notepad"), the
     remaining text is submitted directly.

TTS is unchanged — the existing controller wiring already plays responses
and gates STT during playback via ``state.tts_speaking``.
"""

import contextlib
import logging
import queue
import re
import threading
import time
from pathlib import Path

import numpy as np

import config
from controller.state import state

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
BLOCK = 512  # silero-vad consumes 512-sample frames; 32 ms at 16 kHz
SIL_BLOCK = np.zeros(BLOCK, dtype=np.float32)  # quiet block for flush/clear
_BLOCK_MS = BLOCK * 1000 // SAMPLE_RATE


# ── VAD engines ────────────────────────────────────────────────────────


class SileroSession:
    """Minimal silero-vad (silero_vad.onnx) wrapper over onnxruntime.

    Supports both graph layouts in the wild:

    * classic 4-input (input, h, c, sr) / 3-output (output, hn, cn), and
    * silero v5 (input, state, sr) / (output, stateN), where ``state``
      carries h and c stacked along the last axis (2, 1, 128).

    State is carried between frames for temporal context.
    """

    _V5_CONTEXT = 64  # rolling context samples silero v5 prepends to each frame

    def __init__(self, session, sample_rate: int = SAMPLE_RATE):
        self._sess = session
        self._sr = np.array(sample_rate, dtype=np.int64)
        self._in_names = [i.name for i in session.get_inputs()]
        self._out_names = [o.name for o in session.get_outputs()]
        self._v5 = "state" in self._in_names
        self.reset()

    def reset(self):
        if self._v5:
            self._state = np.zeros((2, 1, 128), dtype=np.float32)
            self._context = np.zeros((1, self._V5_CONTEXT), dtype=np.float32)
        else:
            self._h = np.zeros((2, 1, 64), dtype=np.float32)
            self._c = np.zeros((2, 1, 64), dtype=np.float32)

    def prob_speech(self, frame_f32) -> float:
        a = np.asarray(frame_f32, dtype=np.float32)
        if a.size < BLOCK:
            a = np.pad(a, (0, BLOCK - a.size))
        frame = a[-BLOCK:]
        if self._v5:
            # silero v5 expects [context(64) | window(512)] — the 64 samples
            # preceding the window are carried between calls for continuity.
            inp = np.concatenate([self._context, frame.reshape(1, -1)], axis=1)
            out = self._sess.run(
                None, {"input": inp, "state": self._state, "sr": self._sr}
            )
            self._state = out[1]
            self._context = frame.reshape(1, -1)[:, -self._V5_CONTEXT:]
        else:
            out = self._sess.run(
                None, {"input": frame.reshape(1, -1), "h": self._h, "c": self._c, "sr": self._sr}
            )
            self._h = out[1]
            self._c = out[2]
        if not out:
            return 0.0
        return float(np.asarray(out[0]).reshape(-1)[0])


class VadEngine:
    """Speech gate: silero-vad when available, energy/RMS otherwise.

    Both paths use hysteresis (different trigger/release thresholds) so
    background noise does not chatter the gate on and off.
    """

    def __init__(self, model_path: str | None = None, engine: str = "auto"):
        self._model_path = Path(model_path or config.VAD_MODEL_PATH)
        self._threshold = float(getattr(config, "VAD_RMS_THRESHOLD", 0.005))
        self._exit_threshold = self._threshold * 0.5
        self._active = False
        self._silero = None
        self._engine_name = "energy"
        if engine in ("auto", "silero"):
            self._silero = self._try_load_silero()
            if self._silero is not None:
                self._engine_name = "silero"
        if self._silero is None and engine == "silero":
            logger.warning("silero-vad requested but unavailable — using energy VAD")

    def _try_load_silero(self):
        try:
            import onnxruntime as ort  # type: ignore[import-not-found]

            if not self._model_path.exists():
                logger.debug("silero model not found at %s — using energy VAD", self._model_path)
                return None
            session = ort.InferenceSession(
                str(self._model_path), providers=["CPUExecutionProvider"]
            )
            return SileroSession(session)
        except Exception as e:
            logger.debug("silero-vad unavailable (%s) — using energy VAD", e)
            return None

    @property
    def engine_name(self) -> str:
        return self._engine_name

    @property
    def silero_available(self) -> bool:
        return self._silero is not None

    def reset(self):
        if self._silero is not None:
            self._silero.reset()
        self._active = False

    def is_speech(self, frame_f32) -> bool:
        frame = np.asarray(frame_f32, dtype=np.float32)
        if self._silero is not None:
            try:
                prob = self._silero.prob_speech(frame)
                if prob >= 0.50:
                    self._active = True
                elif prob <= 0.35:
                    self._active = False
                return self._active
            except Exception as e:
                logger.debug("silero inference failed (%s) — energy VAD", e)
        rms = float(np.sqrt(np.mean(frame ** 2))) if frame.size else 0.0
        if rms > self._threshold:
            self._active = True
        elif rms < self._exit_threshold:
            self._active = False
        return self._active


# ── Gated detector ─────────────────────────────────────────────────────


class GatedDetector:
    """
    Wake → VAD → ASR gating detector.

    Opens a single 16 kHz mono float32 InputStream; audio frames are pushed
    to a queue and processed on a worker thread. Utterances are segmented
    by VAD (speech onset → trailing silence) and transcribed in batch mode
    on demand — the mic is never continuously streamed to an ASR backend.

    Duck-type compatible with ``BaseSpeechDetector`` (start/stop/
    set_state_callback/transcript_queue) so the controller can treat it as
    a drop-in replacement. ``wake_handled`` tells the controller that this
    detector already enforced the wake-word gate (commands arriving here
    must not be re-gated against the wake word text).
    """

    def __init__(self, batch_backends: list[str] | None = None):
        from modules.stt import transcript_queue  # local import avoids cycles

        self.transcript_queue = transcript_queue
        self._running = False
        self._state_callback = None

        if batch_backends is None:
            prefs = getattr(config, "STT_BATCH_PREFERRED_BACKENDS", None) or []
            if not prefs:
                prefs = ["whisper_local", "groq"]
            self._batch_backends = self._resolve_batch_backends(prefs)
        else:
            self._batch_backends = list(batch_backends)

        self._stream = None
        self._frame_q: queue.Queue = queue.Queue(maxsize=256)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._engine: VadEngine | None = None

        # State machine (mutated only on the worker thread)
        self.wake_handled = False
        self._wake_required = False
        self._armed = False
        self._armed_until = 0.0
        self._buf: list[np.ndarray] = []
        self._in_speech = False
        self._silence = 0
        self._too_long = False

        self._active_window = float(getattr(config, "STT_ACTIVE_LISTENING_TIMEOUT", 300))
        self._probe_max_frames = max(1, int(getattr(config, "STT_WAKE_PROBE_MS", 1500) // _BLOCK_MS))
        self._min_frames = max(1, int(getattr(config, "STT_MIN_UTTERANCE_MS", 350) // _BLOCK_MS))
        self._tail_frames = max(1, int(getattr(config, "STT_VAD_TAIL_FRAMES", 10)))
        self._wake_words = [
            w.strip().lower() for w in getattr(config, "STT_WAKE_WORDS", []) if w.strip()
        ]

    # ── Availability ──

    @property
    def is_running(self) -> bool:
        return self._running

    def available(self) -> bool:
        """True if the gate can run (a batch ASR backend is usable)."""
        return bool(self._batch_backends)

    def _resolve_batch_backends(self, prefs: list[str]) -> list[str]:
        """Keep only usable batch backends; winrt is streaming-only."""
        resolved: list[str] = []
        try:
            from modules.stt_backends import STTRegistry

            for name in prefs:
                name = str(name).strip()
                if not name or name == "winrt":
                    continue
                try:
                    instance = STTRegistry.get(name)
                    if instance is not None:
                        resolved.append(name)
                except Exception as e:
                    logger.debug("batch backend '%s' unavailable: %s", name, e)
        except Exception as e:
            logger.warning("could not inspect STT backends: %s", e)
        return resolved

    # ── Lifecycle ──

    def set_state_callback(self, cb):
        self._state_callback = cb

    def start(self) -> bool:
        if not self._batch_backends:
            logger.warning("VAD gate: no batch STT backend available — not starting")
            return False

        import sounddevice as sd  # local import keeps module import light

        try:
            devices = sd.query_devices()
            has_input = any(
                d.get("max_input_channels", 0) > 0 for d in devices if isinstance(d, dict)
            )
            if not has_input:
                logger.warning("No microphone input devices found — chat-only mode")
                return False
        except Exception as e:
            logger.warning("VAD gate: mic check failed (%s)", e)
            return False

        self._engine = VadEngine()
        self._stop.clear()
        self._frame_q = queue.Queue(maxsize=256)

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK,
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as e:
            logger.warning("VAD gate: could not open mic stream (%s) — streaming fallback", e)
            self._stream = None
            return False

        self._wake_required = bool(state.wake_word_required)
        self._armed = not self._wake_required
        self.wake_handled = self._wake_required  # pipeline owns the gate in wake mode
        self._buf = []
        self._in_speech = False
        self._silence = 0
        self._too_long = False

        self._thread = threading.Thread(target=self._worker, daemon=True, name="vad-gate")
        self._thread.start()
        self._running = True
        logger.info(
            "VAD gate active (engine=%s, wake_required=%s, batch=%s)",
            self._engine.engine_name, self._wake_required, self._batch_backends,
        )
        self._emit_state("SLEEPING" if self._wake_required else "LISTENING")
        return True

    def stop(self):
        self._running = False
        self._stop.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.debug("VAD gate stream stop error: %s", e)
            self._stream = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._emit_state("SLEEPING")

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug("VAD gate audio status: %s", status)
        try:
            self._frame_q.put_nowait(np.array(indata[:, 0], dtype=np.float32))
        except queue.Full:
            pass  # drop audio rather than block the PortAudio thread

    def _worker(self):
        try:
            while not self._stop.is_set():
                try:
                    chunk = self._frame_q.get(timeout=0.1)
                except queue.Empty:
                    self._tick_timeouts()
                    continue
                try:
                    speech = self._engine.is_speech(chunk)  # type: ignore[union-attr]
                except Exception as e:
                    logger.debug("VAD gate engine error: %s", e)
                    speech = False
                self._advance(speech, chunk)
        except Exception:
            logger.exception("VAD gate worker crashed")

    def _tick_timeouts(self):
        """Armed-window expiry while idle (wake mode only)."""
        if (
            self._wake_required and self._armed
            and not self._in_speech and not self._buf
            and time.time() > self._armed_until
        ):
            self._armed = False
            self._emit_state("SLEEPING")

    def _advance(self, speech: bool, chunk):
        """Incremental state machine fed with one VAD verdict per frame."""
        self._tick_timeouts()

        if speech:
            self._silence = 0
            if not self._in_speech:
                self._in_speech = True
                if not self._wake_required or self._armed:
                    self._emit_state("LISTENING")
            self._buf.append(chunk)
            if self._wake_required and not self._armed and len(self._buf) > self._probe_max_frames:
                self._too_long = True
        else:
            if self._in_speech:
                self._silence += 1
                if self._silence >= self._tail_frames:
                    was_command = self._finalize_utterance()
                    self._buf = []
                    self._in_speech = False
                    self._silence = 0
                    self._too_long = False
                    # End the armed window only after a real command;
                    # a wake probe that just armed keeps listening.
                    if self._wake_required and self._armed and was_command:
                        self._armed = False
                        self._emit_state("SLEEPING")
            else:
                self._buf = []

    # ── Utterance handling ──

    def _finalize_utterance(self) -> bool:
        """Handle one complete spoken utterance.

        Returns True when the utterance was a command (wake+command or an
        armed/always-listening command), so the caller can end an armed
        window in wake mode. Wake probes that merely arm the detector
        return False — the armed window stays open until it times out.
        """
        if not self._buf:
            return False
        audio = np.concatenate(self._buf)
        blocks = len(self._buf)  # 32 ms VAD blocks (not samples)

        if state.muted or state.tts_speaking:
            return False  # never transcribe our own TTS playback or muted mic
        if blocks < self._min_frames:
            return False  # too short to be meaningful speech

        if self._wake_required and not self._armed:
            if self._too_long or blocks > self._probe_max_frames:
                return False  # too long to be a wake word
            text = self._transcribe(audio)
            matched, word = self._match_wake(text)
            if not matched:
                return False
            remaining = self._strip_wake(text, word)
            if remaining:
                # "hey raphael open notepad" — deliver the command directly
                logger.info("VAD gate: wake + command in one utterance")
                self._push(remaining)
                return True
            self._armed = True
            self._armed_until = time.time() + self._active_window
            self._emit_state("LISTENING")
            return False

        # Armed or always-listening — this is a command utterance
        text = self._transcribe(audio)
        if text and text.strip():
            logger.debug('VAD gate transcript: "%s"', text[:80])
            self._push(text)
            return True
        return False

    def _push(self, text: str):
        with contextlib.suppress(queue.Full):
            self.transcript_queue.put_nowait(text)

    def _transcribe(self, audio_f32) -> str:
        if not self._batch_backends:
            return ""
        pcm = (np.clip(np.asarray(audio_f32, dtype=np.float32), -1.0, 1.0) * 32767).astype(
            "<i2"
        ).tobytes()
        try:
            from modules.stt_backends import STTRegistry

            result = STTRegistry.transcribe_with_fallback(
                pcm, preferred=self._batch_backends
            )
            if result.success:
                return str(result.text or "").strip()
        except Exception as e:
            logger.warning("VAD gate ASR failed: %s", e)
        return ""

    # ── Wake-word matching (mirrors controller _poll_vad logic) ──

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^\w\s]", "", text.lower()).strip()

    def _match_wake(self, text: str):
        """Return (matched, wake_word) using bidirectional substring match."""
        clean = self._normalize(text)
        if not clean:
            return False, None
        for wake_word in self._wake_words:
            if wake_word in clean:
                return True, wake_word
            if clean in wake_word:
                return True, clean
        return False, None

    def _strip_wake(self, text: str, matched: str | None) -> str:
        remaining = text
        if matched:
            remaining = re.sub(re.escape(matched), "", remaining, flags=re.IGNORECASE)
        return re.sub(r"[^\w\s]", "", remaining).strip()

    def _emit_state(self, new_state: str):
        if self._state_callback:
            try:
                self._state_callback(new_state)
            except Exception as e:
                logger.debug("VAD gate state callback error: %s", e)


# ====================================================================
# Mic-less replay harness — test the gate with WAV files
# ====================================================================
#
#   python -m modules.voice_pipeline path/to/audio.wav [--wake]
#
# Feeds a 16 kHz-ish WAV through the real VAD engine and the gate state
# machine without a microphone or an ASR backend. Transcription is
# stubbed so the wake/command *flow* can be exercised on any audio file
# (record a clip on a phone and drag it in). Use --wake to demo the
# wake-word flow: the first utterance is treated as the wake probe and
# arms the detector; later utterances are commands.
# ====================================================================


def _load_wav(path) -> tuple[np.ndarray, int]:
    """Load a WAV as mono float32 [-1, 1] resampled to SAMPLE_RATE."""
    import wave

    with wave.open(str(path), "rb") as w:
        sample_rate = w.getframerate()
        channels = w.getnchannels()
        raw = w.readframes(w.getnframes())
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if sample_rate != SAMPLE_RATE:
        old = np.arange(len(data))
        new = np.linspace(0, len(data) - 1, int(len(data) * SAMPLE_RATE / sample_rate))
        data = np.interp(new, old, data).astype(np.float32)
    return data, len(data) / SAMPLE_RATE


def _replay_wav(path, wake_required: bool = False) -> list[str]:
    """Run the real VAD + gate over a WAV; return pushed transcripts.

    The transcribe step is stubbed (no ASR backend needed): the first
    utterance yields the wake word in wake mode, later ones a marker.
    """
    det = GatedDetector(batch_backends=[])
    det._wake_required = wake_required
    det._armed = not wake_required
    det.wake_handled = wake_required
    engine = VadEngine(engine="auto")

    seen = {"n": 0}

    def stub_transcribe(audio_f32) -> str:
        n = seen["n"]
        seen["n"] += 1
        if wake_required and n == 0:
            return "hey raphael"  # probe utterance → arms the detector
        rms = float(np.sqrt(np.mean(np.asarray(audio_f32) ** 2)))
        return f"[utterance {n}: {len(audio_f32) / SAMPLE_RATE:.1f}s rms={rms:.3f}]"

    det._transcribe = stub_transcribe
    states: list[str] = []
    det.set_state_callback(states.append)

    data, duration = _load_wav(path)
    speech_blocks = 0
    total_blocks = len(range(0, len(data) - BLOCK + 1, BLOCK))
    for start in range(0, len(data) - BLOCK + 1, BLOCK):
        block = data[start : start + BLOCK]
        is_speech = engine.is_speech(block)
        speech_blocks += int(is_speech)
        det._advance(is_speech, block)
    # Flush the final utterance: the WAV rarely ends in tail silence, so
    # replay enough quiet blocks for the gate to finalize what's buffered.
    for _ in range(det._tail_frames + 1):
        det._advance(False, SIL_BLOCK)
        total_blocks += 1
    det._tick_timeouts()

    out = list(det.transcript_queue.queue)
    print(f"engine={engine.engine_name} duration={duration:.1f}s "
          f"speech={100 * speech_blocks / max(1, total_blocks):.0f}% "
          f"mode={'wake' if wake_required else 'listen'} states={states}")
    for i, text in enumerate(out):
        print(f"  [{i}] {text}")
    return out


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(
        description="Replay a WAV through the VAD gate (no mic, no ASR)."
    )
    parser.add_argument("wav", help="16-bit PCM .wav file to replay")
    parser.add_argument(
        "--wake", action="store_true", help="demo wake-word flow (first utterance arms)"
    )
    args = parser.parse_args()
    if not Path(args.wav).exists():
        print(f"error: no such file: {args.wav}", file=sys.stderr)
        sys.exit(1)
    _replay_wav(args.wav, wake_required=args.wake)
