"""
TTS backend implementations — auto-discovered via imports.
Each module registers its backend via @TTSRegistry.register().
"""

# Import all backends to trigger registration
from . import edgetts_backend

# Discovery helper: list all registered backends
from ..tts_registry import TTSRegistry

__all__ = ["TTSRegistry", "discover_backends"]


def discover_backends() -> list[str]:
    """Return list of all registered TTS backend names."""
    return TTSRegistry.list_backends()
