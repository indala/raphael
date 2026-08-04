"""
Text-to-Speech module for Raphael.
Uses the TTSBackend ABC + Registry pattern (OpenJarvis-inspired).
Backends auto-register via @TTSRegistry.register() decorator.

Usage:
    speak("Hello world")                # Uses config.TTS_BACKEND
    speak("Hi", interrupt_event=evt)    # Custom interrupt signal
"""

import io
import logging
import re
import struct
import sys
import threading
import wave
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Silence Compression ────────────────────────────────────────────────

def _compress_silence(wav_data: bytes, sample_rate: int = 24000,
                      threshold: float = 0.02,
                      min_silence_dur: float = 0.3,
                      keep_dur: float = 0.1) -> bytes:
    """
    Remove long pauses from TTS audio for faster playback.

    Detects silence regions (amplitude < threshold) longer than
    ``min_silence_dur`` and compresses them to ``keep_dur``.

    Works on raw WAV PCM16 data. Handles both mono and stereo.

    From Mark-XLVIII pattern: silence removal improves perceived
    speech speed by ~2x without changing pitch or tempo.
    """
    if not wav_data or len(wav_data) < 44:
        return wav_data  # Too small to be a valid WAV

    try:
        buf = io.BytesIO(wav_data)
        with wave.open(buf, 'rb') as w:
            nchannels = w.getnchannels()
            sampwidth = w.getsampwidth()
            framerate = w.getframerate()
            nframes = w.getnframes()
            raw = w.readframes(nframes)

        if sampwidth != 2:
            return wav_data  # Only handle PCM16

        # Convert to array of (left, right) or (mono,) samples
        samples = struct.unpack_from(f"<{len(raw) // 2}h", raw)
        frame_size = nchannels
        frames = [samples[i:i + frame_size] for i in range(0, len(samples), frame_size)]

        # Find silence regions (max amplitude across channels < threshold)
        silence_regions = []
        in_silence = False
        start_frame = 0

        for i, frame in enumerate(frames):
            amp = max(abs(s) for s in frame) / 32768.0
            if amp < threshold:
                if not in_silence:
                    in_silence = True
                    start_frame = i
            else:
                if in_silence:
                    silence_dur = (i - start_frame) / framerate
                    if silence_dur >= min_silence_dur:
                        silence_regions.append((start_frame, i))
                    in_silence = False

        # Check final region
        if in_silence:
            silence_dur = (len(frames) - start_frame) / framerate
            if silence_dur >= min_silence_dur:
                silence_regions.append((start_frame, len(frames)))

        if not silence_regions:
            return wav_data  # Nothing to compress

        # Build compressed audio: keep keep_dur at each end of silence
        keep_frames = int(keep_dur * framerate)
        new_frames: list = []

        last_end = 0
        for s_start, s_end in silence_regions:
            # Copy frames before silence
            new_frames.extend(frames[last_end:s_start])
            # Copy keep_dur's worth at start of silence
            new_frames.extend(frames[s_start:s_start + min(keep_frames, s_end - s_start)])
            # Copy keep_dur's worth at end of silence
            new_frames.extend(frames[max(s_start, s_end - keep_frames):s_end])
            last_end = s_end

        # Copy remaining after last silence
        new_frames.extend(frames[last_end:])

        # Pack back to WAV bytes
        flat = [s for frame in new_frames for s in frame]
        out = io.BytesIO()
        with wave.open(out, 'wb') as w:
            w.setnchannels(nchannels)
            w.setsampwidth(sampwidth)
            w.setframerate(framerate)
            w.writeframes(struct.pack(f"<{len(flat)}h", *flat))
        compressed = out.getvalue()

        saved = len(wav_data) - len(compressed)
        saved_pct = 100.0 * saved / len(wav_data)
        if saved > 0:
            logger.debug("Silence compressed: %.1f%% smaller (%d bytes saved)",
                         saved_pct, saved)
        return compressed

    except Exception as e:
        logger.debug("Silence compression failed: %s — using original", e)
        return wav_data


def _compress_audio_file(path: str) -> bool:
    """
    Compress silence in a WAV audio file in-place.

    Reads the file, compresses silence, and writes it back.
    Returns True if compression was applied, False on failure.

    Used by TTS backends before playing generated audio files.
    """
    try:
        raw = Path(path).read_bytes()
        compressed = _compress_silence(raw)
        if len(compressed) < len(raw):
            Path(path).write_bytes(compressed)
            return True
        return False
    except Exception as e:
        logger.debug("Audio file compression skipped for %s: %s", path, e)
        return False


# ── Interrupt support ──────────────────────────────────────────────────────
_interrupted = threading.Event()

# Dedicated lock for TTS engine operations (sd.stop(), MCI, etc.)
# Prevents concurrent calls from multiple threads that could segfault
_TTS_ENGINE_LOCK = threading.Lock()


def stop() -> None:
    """Signal all TTS backends to stop speaking immediately.

    Thread-safe: serializes sounddevice/mci calls behind a lock to prevent
    segfaults from concurrent ``sd.stop()`` or ``mciSendStringW`` calls.
    """
    _interrupted.set()

    with _TTS_ENGINE_LOCK:
        # Stop sounddevice playback (used by kokoro, edgetts)
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        # Stop MCI playback (used by edge-tts)
        try:
            import ctypes
            ctypes.windll.winmm.mciSendStringW("close all", None, 0, None)
        except Exception:
            pass


def clear_interrupt() -> None:
    """Reset the interrupt flag so new speech can proceed."""
    _interrupted.clear()


# Import config
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
import contextlib


# ── Text Sanitization ───────────────────────────────────────────────────

def _clean_text_for_tts(text: str) -> str:
    """Remove markdown, emojis, code fences, links, and extra spacing."""
    if not text:
        return ""

    # 1. Strip emojis by character class (covers all Unicode emoji ranges)
    import unicodedata
    cleaned = []
    for ch in text:
        cat = unicodedata.category(ch)
        # Remove: Symbol-Other (So), Modifier-Symbol (Sk), Format (Cf), Private Use (Co)
        if cat in ('So', 'Sk', 'Cf', 'Co'):
            continue
        # Remove chars in emoji-specific blocks via code point range
        cp = ord(ch)
        if (0x1F300 <= cp <= 0x1F9FF) or (cp == 0x200D):
            continue
        cleaned.append(ch)
    text = ''.join(cleaned)

    # 2. Remove code fences (```...``` and ````...````)
    text = re.sub(r'`{3,}[\s\S]*?`{3,}', '', text)
    # 3. Inline code backticks
    text = re.sub(r'`+', '', text)
    # 4. Markdown links [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # 5. Heading markers (###, ##, #) at line start
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # 6. Bold/italic markers
    text = re.sub(r'\*{1,3}', '', text)
    text = re.sub(r'_{1,3}', '', text)
    # 7. List markers (-, *, +, 1.) at line start with optional indent
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # 8. Blockquote markers
    text = re.sub(r'^>\s?', '', text, flags=re.MULTILINE)
    # 9. Horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # 10. Collapse multiple whitespaces and trim
    return re.sub(r'\s+', ' ', text).strip()


# ── Public API ──────────────────────────────────────────────────────────

# Lazy-import backends to avoid circular import at module level
_backends_loaded = False


def _ensure_backends():
    """Ensure all TTS backends are registered (import triggers registration)."""
    global _backends_loaded
    if not _backends_loaded:
        import modules.tts_backends  # noqa: F401 — triggers @register decorators
        _backends_loaded = True


def speak(text: str, voice: str | None = None,
          backend: str | None = None,
          interrupt_event: threading.Event | None = None,
          timeout: float = 30.0) -> bool:
    """Speak text aloud using the configured TTS backend.

    Args:
        text: The text to speak.
        voice: Voice name (backend-specific, uses config default if None).
        backend: Override backend name (default: config.TTS_BACKEND).
        interrupt_event: Optional external interrupt signal.
                        Falls back to global _interrupted if None.
        timeout: Max seconds to wait for synthesis before giving up.
                 Prevents hangs from deadlocked audio engines.

    Returns:
        True if speech was successful, False if skipped/interrupted/errored.
    """
    from controller.state import state
    if not state.tts_enabled or not state.audio_output_available:
        return False

    if not text:
        return False

    # Skip immediately if interrupted
    if _interrupted.is_set():
        return False

    text = _clean_text_for_tts(text)
    if not text:
        return False

    _ensure_backends()

    from modules.tts_registry import TTSRegistry
    backend_name = (backend or getattr(config, "TTS_BACKEND", "edge-tts")).lower()  # type: ignore[union-attr]
    # Runtime voice override takes precedence, then config default
    voice = voice or state.tts_voice or getattr(config, "TTS_VOICE", "en-US-JennyNeural")

    # Map legacy backend names
    BACKEND_ALIASES = {
        "edge-tts": "edgetts",
    }
    backend_name = BACKEND_ALIASES.get(backend_name, backend_name)

    # Instantiate backend
    backend_instance = TTSRegistry.create(backend_name)
    if backend_instance is None:
        logger.warning("TTS backend '%s' not found — trying discovery", backend_name)
        healthy = TTSRegistry.discover_healthy()
        if not healthy:
            logger.error("No healthy TTS backends available")
            return False
        backend_instance = healthy[0][1]

    # Wire interrupt
    backend_instance.interrupt_event = interrupt_event or _interrupted  # type: ignore[attr-defined]

    # ── Synthesize with timeout ────────────────────────────────────
    state.tts_speaking = True  # Signal STT to suppress microphone input
    try:
        result = backend_instance.synthesize(text, voice=voice)
        if not result.success and result.error != "interrupted":
            logger.warning("TTS backend '%s' failed: %s — trying fallback",
                           backend_name, result.error)
            # Try next available backend
            for name, alt_backend in TTSRegistry.discover_healthy():
                if name != backend_name:
                    alt_backend.interrupt_event = interrupt_event or _interrupted  # type: ignore[attr-defined]
                    try:
                        alt_result = alt_backend.synthesize(text, voice=voice)
                        if alt_result.success:
                            return True
                    except Exception as e2:
                        logger.debug("TTS fallback '%s' failed: %s", name, e2)
                        continue
        return result.success if result else False
    except Exception as e:
        logger.error("TTS speak() failed: %s", e)
        return False
    finally:
        state.tts_speaking = False  # Resume STT processing


def list_voices() -> list[str]:
    """List available voices from all healthy backends."""
    _ensure_backends()
    from modules.tts_registry import TTSRegistry
    voices = []
    for _name, instance in TTSRegistry.discover_healthy():
        with contextlib.suppress(Exception):
            voices.extend(instance.voices() or [])
    return voices
