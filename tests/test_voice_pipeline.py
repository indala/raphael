"""
Tests for the Rhasspy-style wake → VAD → ASR voice pipeline
(modules/voice_pipeline.py).

These are hermetic: no real microphone, no sounddevice stream, no STT
backends. The GatedDetector state machine is driven directly via
``_advance(speech, chunk)`` with a stubbed ``_transcribe``.
"""

import numpy as np
import pytest
from pathlib import Path

import config
from controller.state import state
from modules.voice_pipeline import BLOCK, GatedDetector, VadEngine, _load_wav

LOUD = np.full(BLOCK, 0.3, dtype=np.float32)  # "speaking"
SIL = np.zeros(BLOCK, dtype=np.float32)  # "silence"


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.setattr(state, "muted", False)
    monkeypatch.setattr(state, "tts_speaking", False)


def make_detector(wake_required: bool, transcribe=None):
    d = GatedDetector(batch_backends=["fake"])
    d._wake_required = wake_required
    d._armed = not wake_required
    d.wake_handled = wake_required
    d._wake_words = ["hey raphael", "raphael"]
    if transcribe is not None:
        d._transcribe = transcribe
    return d


def feed_utterance(d, n_speech):
    """Feed a spoken utterance of n_speech loud frames, then its tail silence."""
    for _ in range(n_speech):
        d._advance(True, LOUD)
    for _ in range(d._tail_frames):
        d._advance(False, SIL)


# ── VAD engine ─────────────────────────────────────────────────────────


def test_energy_vad_hysteresis():
    v = VadEngine(engine="energy")
    assert v.engine_name == "energy"
    assert not v.silero_available
    assert not v.is_speech(SIL)      # silent → no speech
    assert v.is_speech(LOUD)         # onset
    assert v.is_speech(LOUD)         # sustained
    assert not v.is_speech(SIL)      # released after crossing exit threshold
    assert not v.is_speech(SIL)


def test_energy_fallback_when_model_absent():
    # With the model file missing (explicit nonexistent path), auto mode
    # falls back to energy regardless of what the repo has checked in.
    v = VadEngine(model_path="__no_such_model__.onnx", engine="auto")
    assert v.engine_name == "energy"
    assert not v.silero_available


@pytest.mark.skipif(
    not Path(config.VAD_MODEL_PATH).exists(),
    reason="silero_vad.onnx not present in assets/models",
)
def test_auto_uses_silero_when_model_present():
    # With the model file in place, auto mode loads silero and genuine
    # inference separates real TTS speech from silence. (Synthetic constant
    # noise is rejected by silero — it is a speech detector, so the test
    # drives real speech from the generated fixture instead.)
    v = VadEngine(engine="auto")
    assert v.engine_name == "silero"
    assert v.silero_available

    fixture = Path(__file__).parent / "generated" / "speech_16k.wav"
    assert fixture.exists(), "generate tests/generated/speech_16k.wav first"
    data, _ = _load_wav(fixture)
    probs = [
        v._silero.prob_speech(data[start : start + BLOCK])
        for start in range(0, len(data) - BLOCK + 1, BLOCK)
    ]

    speech = [p for p in probs if p >= 0.5]
    assert len(speech) >= 5      # real speech is actually detected
    assert max(probs) >= 0.8     # genuine inference, not a stub path
    assert probs[0] < 0.5        # leading silence pad is quiet
    assert probs[-1] < 0.5       # trailing silence pad is quiet


# ── Gated detector ─────────────────────────────────────────────────────


def test_available_reflects_batch_backends():
    assert make_detector(False).available() is True
    assert GatedDetector(batch_backends=[]).available() is False


def test_always_listen_transcribes_utterance():
    d = make_detector(wake_required=False, transcribe=lambda a: "play music")
    states = []
    d.set_state_callback(states.append)

    feed_utterance(d, 15)

    assert not d.transcript_queue.empty()
    assert d.transcript_queue.get() == "play music"
    assert "LISTENING" in states


def test_wake_mode_arms_then_transcribes_command():
    texts = iter(["hey raphael", "open notepad"])
    d = make_detector(wake_required=True, transcribe=lambda a: next(texts))

    # Wake probe utterance — matches, so the detector arms but pushes nothing
    feed_utterance(d, 12)
    assert d._armed is True
    assert d.transcript_queue.empty()

    # Next utterance is the command
    feed_utterance(d, 15)
    assert d.transcript_queue.get() == "open notepad"
    assert d._armed is False


def test_wake_probe_non_wake_discarded():
    d = make_detector(wake_required=True, transcribe=lambda a: "some ambient noise")

    feed_utterance(d, 12)

    assert d._armed is False
    assert d.transcript_queue.empty()


def test_wake_plus_command_in_single_utterance():
    d = make_detector(wake_required=True, transcribe=lambda a: "hey raphael open notepad")

    feed_utterance(d, 15)

    assert d.transcript_queue.get() == "open notepad"
    assert d._armed is False


def test_long_probe_not_treated_as_wake():
    d = make_detector(wake_required=True, transcribe=lambda a: "a long rambling speech")

    feed_utterance(d, d._probe_max_frames + 5)

    assert d._armed is False
    assert d.transcript_queue.empty()


def test_does_not_transcribe_during_tts(monkeypatch):
    d = make_detector(wake_required=False, transcribe=lambda a: "should not be pushed")
    monkeypatch.setattr(state, "tts_speaking", True)

    feed_utterance(d, 15)

    assert d.transcript_queue.empty()


def test_min_utterance_is_ignored():
    d = make_detector(wake_required=False, transcribe=lambda a: "nope")

    feed_utterance(d, 2)  # below STT_MIN_UTTERANCE_MS

    assert d.transcript_queue.empty()


def test_empty_transcript_not_pushed():
    d = make_detector(wake_required=False, transcribe=lambda a: "   ")

    feed_utterance(d, 15)

    assert d.transcript_queue.empty()


def test_match_wake_bidirectional():
    d = make_detector(False)
    assert d._match_wake("Hey Raphael what time is it")[0] is True
    assert d._match_wake("what time is it")[0] is False


def test_strip_wake_removes_leading_wake_word():
    d = make_detector(False)
    assert d._strip_wake("Hey Raphael open notepad", "hey raphael") == "open notepad"
    assert d._strip_wake("raphael stop", "raphael") == "stop"