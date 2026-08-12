"""Thread-safe runtime state — mutable state separate from config.py.

All mutable state that changes during runtime (mute toggle, wake word
mode, audio availability) lives here with explicit lock protection,
instead of on ``config`` module attributes which are not thread-safe.

Reactive pattern: each property setter notifies registered callbacks on
change, enabling decoupled UI updates.  The controller wires these
callbacks to ``pyqtSignal``\\s for automatic cross-thread delivery.
"""
import threading
from typing import Any
from collections.abc import Callable

import config


class RuntimeState:
    """Thread-safe mutable state with reactive change notifications.

    Register a callback for a property::

        state.on_change("muted", my_callback)

    The callback receives ``(property_name, new_value)``.
    Callbacks always fire on the caller's thread — use ``pyqtSignal``
    in the controller to marshal to the GUI thread.
    """

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
        self._tts_voice: str | None = None
        # Audio device state (seeded from real hardware at startup)
        self._speaker_muted = False
        self._speaker_volume = 100
        self._mic_volume = 100

        # Reactive callbacks: {property_name: [callback, ...]}
        self._listeners: dict[str, list[Callable[[str, Any], None]]] = {}

        # Session-scoped tool permissions ("Always allow" grants).
        # Ephemeral by design: cleared on restart, never persisted, so a
        # forgotten grant cannot outlive the session that issued it.
        self._session_allowed_tools: set[str] = set()

    # ── Observer registration ──

    def on_change(self, prop: str, callback: Callable[[str, Any], None]) -> None:
        """Register *callback* to fire when *prop* changes.

        Callback signature: ``callback(prop_name, new_value)``.
        """
        self._listeners.setdefault(prop, []).append(callback)

    def _notify(self, prop: str, value: Any) -> None:
        """Notify all listeners of a property change (caller's thread)."""
        for cb in self._listeners.get(prop, ()):
            try:
                cb(prop, value)
            except Exception:
                pass  # never let a broken listener break state

    # ── Session tool permissions ──

    def session_allows(self, tool_name: str) -> bool:
        """True if the user granted *tool_name* for this session."""
        with self._lock:
            return tool_name in self._session_allowed_tools

    def allow_session_tool(self, tool_name: str) -> None:
        """Grant *tool_name* for the rest of this session (never persisted)."""
        with self._lock:
            self._session_allowed_tools.add(tool_name)

    # ── Muted ──

    @property
    def muted(self) -> bool:
        with self._lock:
            return self._muted  # type: ignore[no-any-return]

    @muted.setter
    def muted(self, value: bool):
        new = bool(value)
        with self._lock:
            if self._muted == new:
                return
            self._muted = new
        self._notify("muted", new)

    # ── Wake word required ──

    @property
    def wake_word_required(self) -> bool:
        with self._lock:
            return self._wake_word_required  # type: ignore[no-any-return]

    @wake_word_required.setter
    def wake_word_required(self, value: bool):
        new = bool(value)
        with self._lock:
            if self._wake_word_required == new:
                return
            self._wake_word_required = new
        self._notify("wake_word_required", new)

    # ── Audio input available ──

    @property
    def audio_input_available(self) -> bool:
        with self._lock:
            return self._audio_input_available  # type: ignore[no-any-return]

    @audio_input_available.setter
    def audio_input_available(self, value: bool):
        new = bool(value)
        with self._lock:
            if self._audio_input_available == new:
                return
            self._audio_input_available = new
        self._notify("audio_input_available", new)

    # ── Audio output available ──

    @property
    def audio_output_available(self) -> bool:
        with self._lock:
            return self._audio_output_available  # type: ignore[no-any-return]

    @audio_output_available.setter
    def audio_output_available(self, value: bool):
        new = bool(value)
        with self._lock:
            if self._audio_output_available == new:
                return
            self._audio_output_available = new
        self._notify("audio_output_available", new)

    # ── TTS enabled ──

    @property
    def tts_enabled(self) -> bool:
        with self._lock:
            return self._tts_enabled  # type: ignore[no-any-return]

    @tts_enabled.setter
    def tts_enabled(self, value: bool):
        new = bool(value)
        with self._lock:
            if self._tts_enabled == new:
                return
            self._tts_enabled = new
        self._notify("tts_enabled", new)

    # ── Memory needs consolidation ──

    @property
    def memory_needs_consolidation(self) -> bool:
        with self._lock:
            return self._memory_needs_consolidation  # type: ignore[no-any-return]

    @memory_needs_consolidation.setter
    def memory_needs_consolidation(self, value: bool):
        new = bool(value)
        with self._lock:
            if self._memory_needs_consolidation == new:
                return
            self._memory_needs_consolidation = new
        self._notify("memory_needs_consolidation", new)

    # ── TTS speaking ──

    @property
    def tts_speaking(self) -> bool:
        with self._lock:
            return self._tts_speaking  # type: ignore[no-any-return]

    @tts_speaking.setter
    def tts_speaking(self, value: bool):
        new = bool(value)
        with self._lock:
            if self._tts_speaking == new:
                return
            self._tts_speaking = new
        self._notify("tts_speaking", new)

    # ── TTS voice ──

    @property
    def tts_voice(self) -> str | None:
        with self._lock:
            return self._tts_voice

    @tts_voice.setter
    def tts_voice(self, value: str | None):
        with self._lock:
            if self._tts_voice == value:
                return
            self._tts_voice = value
        self._notify("tts_voice", value)

    # ── Speaker muted ──

    @property
    def speaker_muted(self) -> bool:
        with self._lock:
            return self._speaker_muted  # type: ignore[no-any-return]

    @speaker_muted.setter
    def speaker_muted(self, value: bool):
        new = bool(value)
        with self._lock:
            if self._speaker_muted == new:
                return
            self._speaker_muted = new
        self._notify("speaker_muted", new)

    # ── Speaker volume ──

    @property
    def speaker_volume(self) -> int:
        with self._lock:
            return self._speaker_volume  # type: ignore[no-any-return]

    @speaker_volume.setter
    def speaker_volume(self, value: int):
        new = int(value)
        with self._lock:
            if self._speaker_volume == new:
                return
            self._speaker_volume = new
        self._notify("speaker_volume", new)

    # ── Mic volume ──

    @property
    def mic_volume(self) -> int:
        with self._lock:
            return self._mic_volume  # type: ignore[no-any-return]

    @mic_volume.setter
    def mic_volume(self, value: int):
        new = int(value)
        with self._lock:
            if self._mic_volume == new:
                return
            self._mic_volume = new
        self._notify("mic_volume", new)


# Module-level singleton (created at import time — safe because
# RuntimeState no longer inherits QObject).
state = RuntimeState()
