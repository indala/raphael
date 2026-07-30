"""
TTS Backend Registry — ABC + decorator-based plugin system.

Inspired by OpenJarvis's speech architecture:
each backend extends TTSBackend ABC, registers via @register(),
and the registry handles discovery, health checks, and dispatch.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TTSResult:
    """Typed result for TTS synthesis."""
    success: bool
    backend: str = ""
    duration_ms: float = 0.0
    audio_path: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class TTSBackend(ABC):
    """Abstract base for all TTS backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique backend identifier (e.g. 'edgetts')."""
        ...

    @abstractmethod
    def synthesize(self, text: str, **kwargs) -> TTSResult:
        """Synthesize text to speech. Must handle interrupt flag if provided."""
        ...

    def health(self) -> bool:
        """Check if this backend is available for use. Default: True."""
        return True

    def voices(self) -> list[str]:
        """Return list of available voice names."""
        return []

    def stop(self):
        """Stop current playback immediately. Default: no-op."""
        pass


class TTSRegistry:
    """Registry for TTS backends with decorator registration."""

    _backends: dict[str, type[TTSBackend]] = {}

    @classmethod
    def register(cls, name: str = ""):
        """Decorator: register a TTSBackend subclass.

        Usage:
            @TTSRegistry.register("edgetts")
            class EdgeTTSBackend(TTSBackend):
                ...
        """
        def decorator(backend_cls: type[TTSBackend]):
            key = name or backend_cls.__name__.lower().replace("backend", "")
            if key in cls._backends:
                logger.warning("TTS backend '%s' already registered — overriding", key)
            cls._backends[key] = backend_cls
            logger.debug("Registered TTS backend: %s", key)
            return backend_cls
        return decorator

    @classmethod
    def get(cls, name: str) -> type[TTSBackend] | None:
        """Get a backend class by name."""
        return cls._backends.get(name)

    @classmethod
    def create(cls, name: str, **kwargs) -> TTSBackend | None:
        """Instantiate a backend by name. Returns None if not found."""
        backend_cls = cls.get(name)
        if backend_cls is None:
            return None
        return backend_cls(**kwargs)

    @classmethod
    def list_backends(cls) -> list[str]:
        """List all registered backend names."""
        return list(cls._backends.keys())

    @classmethod
    def discover_healthy(cls) -> list[tuple[str, TTSBackend]]:
        """Instantiate all registered backends and return healthy ones."""
        healthy = []
        for name, cls_ in cls._backends.items():
            try:
                instance = cls_()
                if instance.health():
                    healthy.append((name, instance))
            except Exception as e:
                logger.debug("TTS backend '%s' health check failed: %s", name, e)
        return healthy
