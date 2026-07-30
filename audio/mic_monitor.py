"""
MicLevelMonitor — live microphone audio level detection.

Opens a low-latency sounddevice InputStream and computes RMS energy
of the incoming audio. Exposes a smoothed 0.0–1.0 level property and
an optional callback for push-based updates.

Uses the same sounddevice library already required by Raphael's STT
backends — no new dependencies.
"""

import logging
import threading
from typing import Callable

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
BLOCK_SIZE = 1024  # ~64ms per callback


class MicLevelMonitor:
    """Monitors microphone audio level in real-time.

    Opens a separate low-latency InputStream (separate from the STT
    stream) so the level meter works independently of whether STT is
    currently capturing.

    Thread-safe — ``level`` can be read from any thread.
    """

    def __init__(self, callback: Callable[[float], object] | None = None) -> None:
        self._stream: sd.InputStream | None = None
        self._smoothed = 0.0
        self._callback = callback
        self._running = False
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────────────────

    @property
    def level(self) -> float:
        """Current smoothed mic level, 0.0 (silent) to 1.0 (loud)."""
        with self._lock:
            return self._smoothed

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        """Open the InputStream and begin capturing.

        Returns True if capture started, False if no mic is available.
        """
        if self._running:
            return True

        # Quick mic-availability check (same pattern as STT backends)
        try:
            devices = sd.query_devices()
            has_input = any(
                d.get("max_input_channels", 0) > 0
                for d in devices
                if isinstance(d, dict)
            )
            if not has_input:
                logger.info("MicLevelMonitor: no input devices found")
                return False
        except Exception:
            pass

        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SIZE,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._running = True
            logger.debug("MicLevelMonitor: started")
            return True
        except sd.PortAudioError as e:
            logger.warning("MicLevelMonitor: mic unavailable (%s)", e)
            return False
        except Exception as e:
            logger.warning("MicLevelMonitor: start failed (%s)", e)
            return False

    def stop(self):
        """Close the InputStream and stop capturing."""
        self._running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        logger.debug("MicLevelMonitor: stopped")

    # ── Internal ────────────────────────────────────────────────────

    def _audio_callback(self, indata, frames, time_info, status):
        """sounddevice callback — compute RMS, smooth, and push."""
        if status:
            logger.debug("MicLevelMonitor: %s", status)

        # RMS of current block (float32, range ~0.0–1.0)
        rms = float(np.sqrt(np.mean(indata[:, 0] ** 2)))

        # Exponential smoothing: attack fast, release slower
        # This makes the visual responsive to speech starts but avoids
        # jittery drops during brief pauses between words.
        if rms > self._smoothed:
            smooth = 0.4 * rms + 0.6 * self._smoothed   # fast attack
        else:
            smooth = 0.15 * rms + 0.85 * self._smoothed  # slower release

        with self._lock:
            self._smoothed = smooth

        if self._callback:
            try:
                self._callback(smooth)
            except Exception:
                self._callback = None  # dead callback, drop it
