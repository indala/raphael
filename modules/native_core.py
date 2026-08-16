"""
Native Core Acceleration Adapter.

Bridges the native Rust (PyO3) `raphael_core` module with pure Python/NumPy fallbacks
for zero-copy visual diffing, SIMD vector math, and fast token estimation.
"""

from __future__ import annotations

import logging
import math
from typing import Sequence

logger = logging.getLogger(__name__)

_RUST_AVAILABLE = False
_native_mod = None

try:
    import raphael_core as _native_mod  # type: ignore
    _RUST_AVAILABLE = True
    logger.debug("Native Core: Rust (PyO3) acceleration loaded successfully.")
except ImportError:
    _RUST_AVAILABLE = False
    logger.debug("Native Core: Rust module not present. Using pure-Python/NumPy fallbacks.")


def is_rust_accelerated() -> bool:
    """Return True if the compiled Rust PyO3 acceleration module is active."""
    return _RUST_AVAILABLE


def perceptual_diff(buf_a: bytes, buf_b: bytes) -> f64:
    """Compute the mean absolute difference ratio between two image byte buffers in [0.0, 1.0]."""
    if _RUST_AVAILABLE and _native_mod is not None:
        try:
            return float(_native_mod.perceptual_diff(buf_a, buf_b))
        except Exception:
            pass

    # Pure Python fallback
    if not buf_a or not buf_b or len(buf_a) != len(buf_b):
        return 1.0

    diff_sum = sum(abs(a - b) for a, b in zip(buf_a, buf_b))
    max_possible = len(buf_a) * 255.0
    return float(diff_sum / max_possible)


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """Compute cosine similarity between two float vectors."""
    if _RUST_AVAILABLE and _native_mod is not None:
        try:
            return float(_native_mod.cosine_similarity(list(vec_a), list(vec_b)))
        except Exception:
            pass

    # Pure Python fallback
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    denom = norm_a * norm_b
    return float(dot / denom) if denom > 0 else 0.0


def fast_token_estimate(text: str) -> int:
    """Estimate token count quickly based on words and characters."""
    if not text:
        return 0

    if _RUST_AVAILABLE and _native_mod is not None:
        try:
            return int(_native_mod.fast_token_estimate(text))
        except Exception:
            pass

    # Pure Python fallback
    words = len(text.split())
    char_count = len(text)
    estimate = int(max(words * 1.33, char_count / 3.8))
    return max(1, estimate)
