"""Tests for the native acceleration module and fallbacks."""

import math

from modules import native_core


def test_audio_rms_and_vad():
    samples_silence = [0.0] * 100
    assert native_core.audio_rms(samples_silence) == 0.0
    assert native_core.fast_vad_energy(samples_silence, threshold=0.01) is False

    samples_loud = [0.5, -0.5, 0.5, -0.5]
    rms = native_core.audio_rms(samples_loud)
    assert math.isclose(rms, 0.5, rel_tol=1e-3)
    assert native_core.fast_vad_energy(samples_loud, threshold=0.1) is True
    assert native_core.fast_vad_energy(samples_loud, threshold=0.9) is False


def test_batch_cosine_similarity():
    query = [1.0, 0.0, 0.0]
    candidates = [
        [1.0, 0.0, 0.0],   # identical (sim = 1.0)
        [0.0, 1.0, 0.0],   # orthogonal (sim = 0.0)
        [-1.0, 0.0, 0.0],  # opposite (sim = -1.0)
    ]
    sims = native_core.batch_cosine_similarity(query, candidates)
    assert len(sims) == 3
    assert math.isclose(sims[0], 1.0, rel_tol=1e-3)
    assert math.isclose(sims[1], 0.0, abs_tol=1e-3)
    assert math.isclose(sims[2], -1.0, rel_tol=1e-3)


def test_top_k_indices():
    scores = [0.1, 0.95, 0.4, 0.85, 0.2]
    top2 = native_core.top_k_indices(scores, 2)
    assert top2 == [1, 3]  # 0.95 at idx 1, 0.85 at idx 3
