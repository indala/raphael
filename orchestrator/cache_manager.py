"""
Unified cache manager for Raphael (Task 8).

Provides centralized, thread-safe caching with:
  - Single RLock for all cache operations
  - Namespace-based keys (namespace:key)
  - Version-based expiration (auto-invalidate when version changes)
  - TTL support for time-based invalidation
  - Observability: hit/miss rates, eviction tracking

Design rationale:
  - Single lock: avoids deadlock complexity; per-cache locks would introduce
    subtle race conditions in multi-namespace scenarios
  - Namespace keys: allows coexistence of multiple cache types (tools, routing,
    prompts) without key collisions
  - Version tracking: invalidates entire cache when registry reloads or config
    changes without explicit invalidation calls
"""

import threading
import time
from typing import Any, TypeVar

T = TypeVar("T")


class CacheManager:
    """Thread-safe unified cache with namespace support and version tracking."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[Any, float, int]] = {}  # (value, ttl_expiry, version)
        self._versions: dict[str, int] = {}  # namespace -> version
        self._stats: dict[str, dict[str, int]] = {}  # namespace -> {hits, misses, evictions}

    def set_version(self, namespace: str, version: int) -> int:
        """Atomically set the version for a namespace, invalidating all cached entries.

        Returns the previous version (0 if none).
        """
        with self._lock:
            old_version = self._versions.get(namespace, 0)
            if old_version != version:
                # Invalidate all entries in this namespace
                keys_to_delete = [k for k in self._cache if k.startswith(f"{namespace}:")]
                for k in keys_to_delete:
                    del self._cache[k]
                # Track evictions
                if namespace not in self._stats:
                    self._stats[namespace] = {"hits": 0, "misses": 0, "evictions": 0}
                self._stats[namespace]["evictions"] += len(keys_to_delete)
                self._versions[namespace] = version
            return old_version

    def get_version(self, namespace: str) -> int:
        """Get the current version of a namespace (0 if not set)."""
        with self._lock:
            return self._versions.get(namespace, 0)

    def set(
        self,
        namespace: str,
        key: str,
        value: T,
        ttl_seconds: float | None = None,
    ) -> None:
        """Store a value in the cache.

        Args:
            namespace: cache namespace (e.g., "tools", "routing", "prompts")
            key: cache key within the namespace
            value: value to cache
            ttl_seconds: optional TTL in seconds; None = no expiration
        """
        with self._lock:
            cache_key = f"{namespace}:{key}"
            ttl_expiry = time.time() + ttl_seconds if ttl_seconds else float("inf")
            self._cache[cache_key] = (value, ttl_expiry, self._versions.get(namespace, 0))

    def get(self, namespace: str, key: str) -> Any | None:
        """Retrieve a value from the cache, or None if not found/expired.

        Records hit/miss stats.
        """
        with self._lock:
            cache_key = f"{namespace}:{key}"
            if cache_key not in self._cache:
                self._record_miss(namespace)
                return None

            value, ttl_expiry, cached_version = self._cache[cache_key]
            current_version = self._versions.get(namespace, 0)

            # Check TTL expiration
            if ttl_expiry < time.time():
                del self._cache[cache_key]
                self._record_miss(namespace)
                return None

            # Check version expiration
            if cached_version != current_version:
                del self._cache[cache_key]
                self._record_miss(namespace)
                return None

            self._record_hit(namespace)
            return value

    def delete(self, namespace: str, key: str) -> bool:
        """Remove a specific key from the cache.

        Returns True if the key existed, False otherwise.
        """
        with self._lock:
            cache_key = f"{namespace}:{key}"
            if cache_key in self._cache:
                del self._cache[cache_key]
                return True
            return False

    def clear(self, namespace: str | None = None) -> int:
        """Clear cache entries.

        Args:
            namespace: if provided, clear only that namespace; else clear all

        Returns the number of entries cleared.
        """
        with self._lock:
            if namespace is None:
                count = len(self._cache)
                self._cache.clear()
                return count
            else:
                prefix = f"{namespace}:"
                keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
                for k in keys_to_delete:
                    del self._cache[k]
                return len(keys_to_delete)

    def exists(self, namespace: str, key: str) -> bool:
        """Check if a key exists and is valid (not expired, correct version)."""
        return self.get(namespace, key) is not None

    def size(self, namespace: str | None = None) -> int:
        """Return the number of valid cache entries.

        Args:
            namespace: if provided, return size of that namespace; else total

        Returns count of entries.
        """
        with self._lock:
            if namespace is None:
                return len(self._cache)
            else:
                prefix = f"{namespace}:"
                return sum(1 for k in self._cache if k.startswith(prefix))

    def stats(self, namespace: str | None = None) -> dict[str, Any]:
        """Get cache statistics (hits, misses, hit rate, etc.).

        Args:
            namespace: if provided, return stats for that namespace; else aggregate

        Returns a dict with hit/miss/eviction counts and computed hit rate.
        """
        with self._lock:
            if namespace is None:
                total_hits = sum(s["hits"] for s in self._stats.values())
                total_misses = sum(s["misses"] for s in self._stats.values())
                total_evictions = sum(s["evictions"] for s in self._stats.values())
                total_requests = total_hits + total_misses
                hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
                return {
                    "total_hits": total_hits,
                    "total_misses": total_misses,
                    "total_evictions": total_evictions,
                    "hit_rate_percent": round(hit_rate, 2),
                    "cache_size": len(self._cache),
                }
            else:
                ns_stats = self._stats.get(namespace, {"hits": 0, "misses": 0, "evictions": 0})
                total = ns_stats["hits"] + ns_stats["misses"]
                hit_rate = (ns_stats["hits"] / total * 100) if total > 0 else 0
                return {
                    "namespace": namespace,
                    "hits": ns_stats["hits"],
                    "misses": ns_stats["misses"],
                    "evictions": ns_stats["evictions"],
                    "hit_rate_percent": round(hit_rate, 2),
                    "cache_size": self.size(namespace),
                }

    def _record_hit(self, namespace: str) -> None:
        """Record a cache hit (called with lock held)."""
        if namespace not in self._stats:
            self._stats[namespace] = {"hits": 0, "misses": 0, "evictions": 0}
        self._stats[namespace]["hits"] += 1

    def _record_miss(self, namespace: str) -> None:
        """Record a cache miss (called with lock held)."""
        if namespace not in self._stats:
            self._stats[namespace] = {"hits": 0, "misses": 0, "evictions": 0}
        self._stats[namespace]["misses"] += 1


# Global instance (singleton pattern for ease of use across modules)
_instance: CacheManager | None = None
_instance_lock = threading.Lock()


def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = CacheManager()
    return _instance


def reset_cache_manager() -> None:
    """Reset the global cache manager (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
