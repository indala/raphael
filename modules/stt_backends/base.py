"""
STT Backend Base — Abstract base class and typed errors for speech-to-text.

Mirrors the TTSBackend/TTSRegistry pattern in modules/tts_registry.py.
Inspired by Zero's internal/dictation/Transcriber interface.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from collections.abc import Callable


# ── Typed Errors ──────────────────────────────────────────────────────────

class STTError(Exception):
    """Base error for all STT operations."""
    def __init__(self, message: str, backend: str = ""):
        self.backend = backend
        super().__init__(message)


class SetupError(STTError):
    """
    Missing dependency or configuration — the backend is not usable.
    Carries a user-facing hint for how to fix it.
    """
    def __init__(self, tool: str, hint: str, backend: str = ""):
        self.tool = tool
        self.hint = hint
        super().__init__(f"{tool}: {hint}", backend=backend)


class AuthError(STTError):
    """Authentication failure (bad API key, expired token, 401/403)."""
    def __init__(self, provider: str, detail: str = "", backend: str = ""):
        self.provider = provider
        super().__init__(
            f"{provider} authentication failed: {detail}" if detail else f"{provider} authentication failed",
            backend=backend,
        )


class AudioError(STTError):
    """Microphone or audio capture failure."""
    pass


class TranscriptionError(STTError):
    """The audio was captured but transcription failed."""
    pass


# ── Typed Results ────────────────────────────────────────────────────────

@dataclass
class STTResult:
    """Result of a single transcription request."""
    success: bool
    text: str = ""
    backend: str = ""
    duration_ms: float = 0.0
    error: str = ""
    is_partial: bool = False
    metadata: dict = field(default_factory=dict)


# ── STTBackend ABC ───────────────────────────────────────────────────────

class STTBackend(ABC):
    """
    Abstract base for all STT backends.

    Two operation modes:
      - Batch: ``transcribe(audio_bytes) -> text``
      - Streaming: ``start_streaming(on_partial) -> StreamHandle``
        (optional; check ``supports_streaming`` first)

    Health checks let the registry skip unhealthy backends automatically.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique backend identifier (e.g. 'groq', 'openai', 'local')."""
        ...

    @property
    def supports_streaming(self) -> bool:
        """Whether this backend supports streaming (partial) transcripts."""
        return False

    @abstractmethod
    def transcribe(self, audio: bytes) -> STTResult:
        """
        Transcribe audio bytes to text (batch mode).
        Audio format: 16kHz mono WAV (or PCM16 for streaming).
        """
        ...

    def transcribe_file(self, path: str) -> STTResult:
        """
        Transcribe an audio file. Default: read bytes and call transcribe().
        Override for format-specific handling.
        """
        import pathlib
        audio = pathlib.Path(path).read_bytes()
        return self.transcribe(audio)

    def start_streaming(
        self,
        on_partial: Callable[[str, bool], None],
    ) -> StreamHandle:
        """
        Start streaming transcription. Returns a StreamHandle for control.

        ``on_partial(text, is_final)`` is called with partial results as they
        arrive. ``is_final=True`` marks a settled segment.

        Raise ``STTError`` if streaming is not supported.
        """
        raise STTError(f"{self.name} does not support streaming")

    def health(self) -> bool:
        """
        Quick health check — can this backend transcribe right now?
        Should be fast (no network calls); used by the registry for fallback.
        """
        return True

    def stop(self):
        """Stop any in-progress capture or transcription. Default: no-op."""
        pass

    def close(self):
        """Release any resources held by this backend. Default: no-op."""
        pass


class StreamHandle:
    """
    Handle for controlling an active streaming transcription session.

    Returned by ``STTBackend.start_streaming()``.
    """
    def __init__(self, backend: STTBackend):
        self.backend = backend
        self._stopped = False

    @property
    def is_active(self) -> bool:
        return not self._stopped

    def stop(self) -> STTResult:
        """
        Stop streaming and return the final accumulated transcript.
        """
        self._stopped = True
        return STTResult(success=True, backend=self.backend.name)

    def cancel(self):
        """Immediately cancel without collecting final text."""
        self._stopped = True
