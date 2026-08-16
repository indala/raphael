"""Unit tests for modules/native_core.py and hybrid/bridge.py typed exceptions."""

from __future__ import annotations

import math
from modules.native_core import (
    cosine_similarity,
    fast_token_estimate,
    is_rust_accelerated,
    perceptual_diff,
)
from hybrid.bridge import (
    BridgeError,
    BridgeExecutionError,
    BridgeTimeoutError,
    BridgeUnavailableError,
)


def test_perceptual_diff():
    # Identical buffers => 0.0 diff
    buf1 = b"\x00\x50\xff" * 100
    assert perceptual_diff(buf1, buf1) == 0.0

    # Completely opposite buffers (0 vs 255) => 1.0 diff
    b_black = b"\x00" * 100
    b_white = b"\xff" * 100
    assert math.isclose(perceptual_diff(b_black, b_white), 1.0, rel_tol=1e-5)

    # Empty or mismatched buffers => 1.0 diff
    assert perceptual_diff(b"", b"") == 1.0
    assert perceptual_diff(b"\x00", b"\x00\x00") == 1.0


def test_cosine_similarity():
    # Identical vectors => 1.0
    v1 = [1.0, 2.0, 3.0]
    assert math.isclose(cosine_similarity(v1, v1), 1.0, rel_tol=1e-5)

    # Orthogonal vectors => 0.0
    v_a = [1.0, 0.0]
    v_b = [0.0, 1.0]
    assert math.isclose(cosine_similarity(v_a, v_b), 0.0, rel_tol=1e-5)

    # Empty or mismatched vectors => 0.0
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


def test_fast_token_estimate():
    assert fast_token_estimate("") == 0
    assert fast_token_estimate("Hello world") >= 2
    long_text = "The quick brown fox jumps over the lazy dog. " * 10
    tokens = fast_token_estimate(long_text)
    assert tokens > 50


def test_typed_bridge_exceptions():
    assert issubclass(BridgeUnavailableError, BridgeError)
    assert issubclass(BridgeTimeoutError, BridgeError)
    assert issubclass(BridgeExecutionError, BridgeError)
