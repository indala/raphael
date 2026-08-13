"""
STT Backend Registry — decorator-based registration with health-aware fallback.

Mirrors TTSRegistry pattern in modules/tts_registry.py.
"""

import logging
from .base import STTBackend, STTResult, AuthError, SetupError

logger = logging.getLogger(__name__)


class STTRegistry:
    """
    Registry for STT backends with decorator registration and fallback chain.

    Usage:
        @STTRegistry.register("cloud")
        class CloudBackend(STTBackend):
            ...
    """

    _backends: dict[str, type[STTBackend]] = {}
    _instances: dict[str, STTBackend] = {}
    _health_cache: dict[str, bool] = {}

    @classmethod
    def register(cls, name: str = ""):
        """Decorator: register an STTBackend subclass.

        Args:
            name: Backend name (defaults to class attribute ``name``).

        Usage:
            @STTRegistry.register("cloud")
            class CloudBackend(STTBackend):
                ...
        """
        def decorator(backend_cls: type[STTBackend]):
            _name = name if name else backend_cls().name
            cls._backends[_name] = backend_cls
            logger.debug("Registered STT backend: %s", _name)
            return backend_cls
        return decorator

    @classmethod
    def get(cls, name: str) -> STTBackend | None:
        """Get or create a backend instance by name."""
        if name in cls._instances:
            return cls._instances[name]

        backend_cls = cls._backends.get(name)
        if backend_cls is None:
            # Dynamic backend: any endpoint that declares an ``stt_model`` in
            # settings.toml ([[endpoints]]) can be used by name as a cloud STT
            # backend bound to that endpoint.
            bound = cls._resolve_endpoint_backend(name)
            if bound is not None:
                return bound
            logger.warning("Unknown STT backend: %s", name)
            return None

        try:
            instance = backend_cls()
            cls._instances[name] = instance
            return instance
        except Exception as e:
            logger.error("Failed to instantiate STT backend '%s': %s", name, e)
            return None

    @classmethod
    def _resolve_endpoint_backend(cls, name: str) -> STTBackend | None:
        """Map an endpoint name to a cloud STT backend bound to that endpoint."""
        try:
            from orchestrator.endpoint_registry import get as _ep_get
            ep = _ep_get(name)
            if ep is None or not getattr(ep, "stt_model", "") or not getattr(ep, "base_url", ""):
                return None
            backend_cls = next(
                (b for b in cls._backends.values() if getattr(b, "requires_endpoint", False)),
                None,
            )
            if backend_cls is None:
                return None
            instance = backend_cls(endpoint=ep)
            # Configure eagerly so the bound backend is ready (model/base_url
            # resolved) as soon as it's returned from get(). health() re-checks
            # lazily on later calls, so a failure here surfaces immediately.
            if not instance.health():
                logger.warning("STT: endpoint '%s' failed to configure as cloud backend", name)
                return None
            cls._instances[name] = instance
            logger.debug("STT: bound endpoint '%s' to cloud backend (model=%s)", name, ep.stt_model)
            return instance
        except Exception as e:
            logger.error("Failed to resolve STT backend for endpoint '%s': %s", name, e)
            return None

    @classmethod
    def available_backends(cls) -> list[str]:
        """Return names of all registered backends."""
        return list(cls._backends.keys())

    @classmethod
    def local_backends(cls) -> list[str]:
        """Names of built-in backends that don't require an endpoint (moonshine, ...)."""
        return [
            name
            for name, backend_cls in cls._backends.items()
            if not getattr(backend_cls, "requires_endpoint", False)
        ]

    @classmethod
    def check_health(cls, name: str) -> bool:
        """Check if a backend is healthy (with caching)."""
        # Re-check every 30s
        import time
        now = time.monotonic()
        cached = cls._health_cache.get(name)
        if cached is not None and now - cached < 30:
            return cached

        instance = cls.get(name)
        if instance is None:
            cls._health_cache[name] = False
            return False

        try:
            healthy = instance.health()
            cls._health_cache[name] = healthy
            return healthy
        except Exception:
            cls._health_cache[name] = False
            return False

    @classmethod
    def healthy_backends(cls) -> list[str]:
        """Return names of backends that pass health check."""
        return [n for n in cls.available_backends() if cls.check_health(n)]

    @classmethod
    def transcribe_with_fallback(
        cls,
        audio: bytes,
        preferred: list[str] | None = None,
    ) -> STTResult:
        """Try backends in order, falling through on failure.

        Args:
            audio: Audio bytes (16kHz mono WAV).
            preferred: Ordered list of backend names to try.
                      Defaults to all healthy backends.

        Returns:
            First successful STTResult, or the last error result.
        """
        if preferred is None:
            preferred = cls.healthy_backends()

        if not preferred:
            return STTResult(
                success=False,
                error="No STT backends available (none registered or healthy)",
            )

        last_result = STTResult(success=False, error="No backends attempted")

        for name in preferred:
            instance = cls.get(name)
            if instance is None:
                continue

            # Quick health check before attempting
            if not cls.check_health(name):
                logger.warning("STT backend '%s' is unhealthy, skipping", name)
                last_result = STTResult(
                    success=False,
                    error=f"Backend '{name}' is unhealthy",
                    backend=name,
                )
                continue

            try:
                logger.info("Transcribing with STT backend: %s", name)
                result = instance.transcribe(audio)
                if result.success:
                    result.backend = name
                    logger.info("STT success via '%s' (%d chars, %.0fms) -> \"%s\"",
                                name, len(result.text), result.duration_ms, result.text)
                    return result
                last_result = result
                logger.warning("STT backend '%s' returned failure: %s",
                               name, result.error)
            except AuthError as e:
                logger.error("STT auth error on '%s': %s", name, e)
                last_result = STTResult(success=False, error=str(e), backend=name)
                # Auth errors won't resolve with another provider — stop chain
                return last_result
            except SetupError as e:
                logger.error("STT setup error on '%s': %s", name, e)
                last_result = STTResult(success=False, error=str(e), backend=name)
                continue
            except Exception as e:
                logger.exception("STT backend '%s' crashed: %s", name, e)
                # Mark as unhealthy so we don't retry immediately
                cls._health_cache[name] = False
                last_result = STTResult(
                    success=False,
                    error=f"Backend '{name}' crashed: {e}",
                    backend=name,
                )
                continue

        return last_result

    @classmethod
    def shutdown_all(cls):
        """Close all backend instances."""
        for name, instance in cls._instances.items():
            try:
                instance.close()
            except Exception as e:
                logger.warning("Error closing STT backend '%s': %s", name, e)
        cls._instances.clear()
        cls._health_cache.clear()
