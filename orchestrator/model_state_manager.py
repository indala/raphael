"""
Adaptive Model Fallback with State Tracking (Task 19).

Tracks endpoint health, rate limits, and model availability to intelligently
select working models and minimize API failures.

Features:
  - Per-endpoint health tracking (healthy, rate_limited, unavailable)
  - Automatic recovery with exponential backoff
  - Model priority reordering based on success/failure history
  - Request deduplication to reduce duplicate LLM calls
  - User-facing notifications on model switches
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EndpointState:
    """Tracks health and availability of a single endpoint."""

    name: str
    status: str = "healthy"  # healthy | rate_limited | unavailable
    last_failure_time: float | None = None
    failure_count: int = 0
    success_count: int = 0
    rate_limit_until: float | None = None  # Unix timestamp
    consecutive_failures: int = 0
    model_priority: list[str] = field(default_factory=list)


class ModelStateManager:
    """Manages model health, fallback strategy, and request deduplication."""

    def __init__(self):
        self._lock = threading.RLock()
        self._endpoints: dict[str, EndpointState] = {}
        self._request_cache: dict[str, tuple[str, float]] = {}
        self._cache_ttl_seconds = 300
        self._backoff_base_seconds = 2
        self._max_backoff_seconds = 600

    def register_endpoint(self, name: str, model_priority: list[str]) -> None:
        """Register a new endpoint with initial model priority."""
        with self._lock:
            self._endpoints[name] = EndpointState(
                name=name,
                model_priority=list(model_priority),
            )
            logger.info("Model state: registered endpoint '%s' (%d models)", name, len(model_priority))

    def record_success(self, endpoint: str, model: str) -> None:
        """Record a successful model call."""
        with self._lock:
            ep = self._endpoints.get(endpoint)
            if not ep:
                return

            ep.success_count += 1
            ep.consecutive_failures = 0

            if ep.status != "healthy":
                ep.status = "healthy"
                ep.rate_limit_until = None
                logger.info("Model state: endpoint '%s' recovered to healthy", endpoint)

            if model in ep.model_priority:
                ep.model_priority.remove(model)
                ep.model_priority.insert(0, model)

    def record_rate_limit(self, endpoint: str, retry_after_seconds: int | None = None) -> None:
        """Record a rate limit error with exponential backoff."""
        with self._lock:
            ep = self._endpoints.get(endpoint)
            if not ep:
                return

            ep.status = "rate_limited"
            ep.failure_count += 1
            ep.consecutive_failures += 1
            ep.last_failure_time = time.time()

            backoff = min(
                self._backoff_base_seconds * (2 ** (ep.consecutive_failures - 1)),
                self._max_backoff_seconds,
            )
            if retry_after_seconds:
                backoff = max(backoff, retry_after_seconds)

            ep.rate_limit_until = time.time() + backoff
            logger.warning(
                "Model state: endpoint '%s' rate limited (backoff: %.0fs, failures: %d)",
                endpoint, backoff, ep.consecutive_failures,
            )

    def record_failure(self, endpoint: str, error_type: str) -> None:
        """Record a general failure."""
        with self._lock:
            ep = self._endpoints.get(endpoint)
            if not ep:
                return

            ep.failure_count += 1
            ep.consecutive_failures += 1
            ep.last_failure_time = time.time()

            if error_type in ("401", "403", "404"):
                ep.status = "unavailable"
                logger.warning(
                    "Model state: endpoint '%s' marked unavailable (error: %s)",
                    endpoint, error_type,
                )

    def get_next_model(self, endpoint: str) -> str | None:
        """Get the next model to try for an endpoint."""
        with self._lock:
            ep = self._endpoints.get(endpoint)
            if not ep or not ep.model_priority:
                return None

            if ep.status == "rate_limited" and ep.rate_limit_until:
                if time.time() < ep.rate_limit_until:
                    return None

                ep.status = "healthy"
                ep.rate_limit_until = None
                ep.consecutive_failures = 0
                logger.info("Model state: endpoint '%s' backoff expired, attempting recovery", endpoint)

            if ep.status == "unavailable":
                return None

            return ep.model_priority[0]

    def cache_request(self, query_hash: str, response: str) -> None:
        """Cache a request response for deduplication."""
        with self._lock:
            self._request_cache[query_hash] = (response, time.time())

    def get_cached_request(self, query_hash: str) -> str | None:
        """Retrieve a cached request if not expired."""
        with self._lock:
            if query_hash not in self._request_cache:
                return None

            response, timestamp = self._request_cache[query_hash]
            if time.time() - timestamp > self._cache_ttl_seconds:
                del self._request_cache[query_hash]
                return None

            return response

    def stats(self) -> dict[str, Any]:
        """Get comprehensive statistics on all endpoints."""
        with self._lock:
            stats = {}
            for name, ep in self._endpoints.items():
                total_requests = ep.success_count + ep.failure_count
                success_rate = (
                    (ep.success_count / total_requests * 100)
                    if total_requests > 0
                    else 0
                )
                stats[name] = {
                    "status": ep.status,
                    "success_count": ep.success_count,
                    "failure_count": ep.failure_count,
                    "success_rate_percent": round(success_rate, 1),
                    "consecutive_failures": ep.consecutive_failures,
                    "rate_limit_until": ep.rate_limit_until,
                    "model_priority": list(ep.model_priority),
                }
            return stats


_instance_lock = threading.Lock()
_instance = None


def get_model_state_manager() -> ModelStateManager:
    """Get or create the global model state manager instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ModelStateManager()
    return _instance
