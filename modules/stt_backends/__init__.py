"""STT backends — auto-imports all backends so their @register decorators fire."""

from . import base
from . import registry
from . import cloud
from . import winrt
from . import whisper_local
from . import isolated

# Convenience exports
from .base import (
    STTBackend, STTResult, StreamHandle,
    STTError, SetupError, AuthError, AudioError, TranscriptionError,
)
from .registry import STTRegistry
from .isolated import IsolatedSTTRunner, IsolatedSTTConfig

__all__ = [
    "AudioError",
    "AuthError",
    "IsolatedSTTConfig",
    "IsolatedSTTRunner",
    "STTBackend",
    "STTError",
    "STTRegistry",
    "STTResult",
    "SetupError",
    "StreamHandle",
    "TranscriptionError",
]
