"""Thread-safe runtime state — mutable state separate from config.py.

All mutable state that changes during runtime (mute toggle, wake word
mode, audio availability) lives here with explicit lock protection,
instead of on `config` module attributes which are not thread-safe.
"""
import threading

import config


class RuntimeState:
    """Thread-safe mutable state with lock-protected properties."""

    def __init__(self):
        self._lock = threading.Lock()
        # Seed initial values from config
        self._muted = config.STT_MUTED
        self._wake_word_required = config.STT_WAKE_WORD_REQUIRED
        self._audio_input_available = config.STT_AUDIO_INPUT_AVAILABLE
        self._audio_output_available = True
        self._tts_enabled = config.TTS_ENABLED
        self._memory_needs_consolidation = False
        self._tts_speaking = False
        # Audio device state (seeded from real hardware at startup)
        self._speaker_muted = False
        self._speaker_volume = 100
        self._mic_volume = 100
        self._mic_level = 0.0

    # ── Muted ──

    @property
    def muted(self) -> bool:
        with self._lock:
            return self._muted  # type: ignore[no-any-return]

    @muted.setter
    def muted(self, value: bool):
        with self._lock:
            self._muted = bool(value)

    # ── Wake word required ──

    @property
    def wake_word_required(self) -> bool:
        with self._lock:
            return self._wake_word_required  # type: ignore[no-any-return]

    @wake_word_required.setter
    def wake_word_required(self, value: bool):
        with self._lock:
            self._wake_word_required = bool(value)

    # ── Audio input available ──

    @property
    def audio_input_available(self) -> bool:
        with self._lock:
            return self._audio_input_available  # type: ignore[no-any-return]

    @audio_input_available.setter
    def audio_input_available(self, value: bool):
        with self._lock:
            self._audio_input_available = bool(value)

    # ── Audio output available ──

    @property
    def audio_output_available(self) -> bool:
        with self._lock:
            return self._audio_output_available  # type: ignore[no-any-return]

    @audio_output_available.setter
    def audio_output_available(self, value: bool):
        with self._lock:
            self._audio_output_available = bool(value)

    # ── TTS enabled ──

    @property
    def tts_enabled(self) -> bool:
        with self._lock:
            return self._tts_enabled  # type: ignore[no-any-return]

    @tts_enabled.setter
    def tts_enabled(self, value: bool):
        with self._lock:
            self._tts_enabled = bool(value)

    # ── Memory consolidation flag ──

    @property
    def memory_needs_consolidation(self) -> bool:
        with self._lock:
            return self._memory_needs_consolidation  # type: ignore[no-any-return]

    @memory_needs_consolidation.setter
    def memory_needs_consolidation(self, value: bool):
        with self._lock:
            self._memory_needs_consolidation = bool(value)

    # ── Speaker muted (playback hardware) ──

    @property
    def speaker_muted(self) -> bool:
        with self._lock:
            return self._speaker_muted  # type: ignore[no-any-return]

    @speaker_muted.setter
    def speaker_muted(self, value: bool):
        with self._lock:
            self._speaker_muted = bool(value)

    # ── TTS speaking (used by STT to avoid feedback loop) ──

    @property
    def tts_speaking(self) -> bool:
        with self._lock:
            return self._tts_speaking  # type: ignore[no-any-return]

    @tts_speaking.setter
    def tts_speaking(self, value: bool):
        with self._lock:
            self._tts_speaking = bool(value)

    # ── Speaker volume (0-100) ──

    @property
    def speaker_volume(self) -> int:
        with self._lock:
            return self._speaker_volume  # type: ignore[no-any-return]

    @speaker_volume.setter
    def speaker_volume(self, value: int):
        with self._lock:
            self._speaker_volume = max(0, min(100, int(value)))

    # ── Microphone volume (0-100) ──

    @property
    def mic_volume(self) -> int:
        with self._lock:
            return self._mic_volume  # type: ignore[no-any-return]

    @mic_volume.setter
    def mic_volume(self, value: int):
        with self._lock:
            self._mic_volume = max(0, min(100, int(value)))

    # ── Microphone live level (0.0–1.0, from sounddevice RMS) ──

    @property
    def mic_level(self) -> float:
        with self._lock:
            return self._mic_level  # type: ignore[no-any-return]

    @mic_level.setter
    def mic_level(self, value: float):
        with self._lock:
            self._mic_level = max(0.0, min(1.0, float(value)))


# Singleton — import this in any module that needs runtime state
state = RuntimeState()
