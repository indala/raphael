"""
Audio playback utilities for Raphael TTS backends.

Used by edgetts backend for interrupt-safe
sounddevice audio playback.
"""


from __future__ import annotations

import logging
import os
import threading

import numpy as np
import sounddevice as sd

# Shared interrupt flag from tts module — checked by playback poll loops
# to abort audio mid-play when the user says "stop".
from modules.tts import _interrupted
import contextlib


os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

logger = logging.getLogger(__name__)


# ── Global audio lock ──────────────────────────────────────────────────
# Prevents concurrent sd.play() calls from overlapping PortAudio streams.
# Overlapping streams on Windows can crash the audio driver → BSOD/restart.
_AUDIO_LOCK = threading.Lock()


# ── Audio helpers ───────────────────────────────────────────────────────


def _to_numpy(samples) -> np.ndarray:
    """Convert samples to float32 numpy array (handles PyTorch tensors too)."""
    if hasattr(samples, "detach"):
        t = samples.detach().cpu().float()
        try:
            return t.numpy()  # type: ignore[no-any-return]
        except RuntimeError:
            return np.asarray(t.tolist(), dtype=np.float32)
    return np.asarray(samples, dtype=np.float32)


def _compress_silence(
    arr: np.ndarray,
    sample_rate: int = 24_000,
    max_silence_ms: int = 500,
    threshold: float = 0.003,
) -> np.ndarray:
    """Shorten excessive punctuation pauses while preserving natural rhythm."""
    max_samp = int(max_silence_ms * sample_rate / 1000)
    frame_len = 240
    out: list[np.ndarray] = []
    silent_acc = 0

    for i in range(0, len(arr), frame_len):
        chunk = arr[i : i + frame_len]
        if np.sqrt(np.mean(chunk ** 2) + 1e-12) < threshold:
            silent_acc += len(chunk)
            if silent_acc <= max_samp:
                out.append(chunk)
        else:
            silent_acc = 0
            out.append(chunk)

    return np.concatenate(out) if out else arr


def _play_np(samples, sample_rate: int,
             interrupt_event: threading.Event | None = None) -> None:
    """Play float32 audio via sounddevice (blocking).

    Args:
        samples: Audio samples (numpy array or list).
        sample_rate: Sample rate in Hz.
        interrupt_event: Optional threading.Event — if set, playback stops
                         immediately. Falls back to global _interrupted.

    Uses a global lock to prevent overlapping PortAudio streams, which
    can crash the Windows audio driver on some systems.

    Safety measures:
    - sd.stop() before sd.play() closes any lingering stream from the
      previous call (prevents double-open on the same device).
    - Polling loop with interrupt check so stop() signal takes effect
      within 100ms instead of blocking for 30s.
    """
    import time as _time
    arr = _to_numpy(samples)
    check_event = interrupt_event if interrupt_event is not None else _interrupted
    with _AUDIO_LOCK:
        try:
            sd.stop()  # close any lingering stream before opening a new one
            sd.play(arr, sample_rate)

            # Poll for completion with interrupt checking (non-blocking wait)
            # This avoids PortAudio hangs that can lead to BSOD on Windows
            # when a stream is never closed.
            poll_interval = 0.05  # 50ms
            timeout = 30.0
            elapsed = 0.0
            while sd.get_stream() is not None and sd.get_stream().active:
                if check_event.is_set():
                    sd.stop()
                    return
                _time.sleep(poll_interval)
                elapsed += poll_interval
                if elapsed >= timeout:
                    logger.warning("Audio playback timed out — forcing stop")
                    sd.stop()
                    return
        except Exception as exc:
            logger.error("Audio playback error: %s", exc)
            with contextlib.suppress(Exception):
                sd.stop()


play_audio_from_numpy = _play_np  # Public alias for external callers


