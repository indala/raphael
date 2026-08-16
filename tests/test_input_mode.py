"""
Tests for Context-Aware Input Mode (Text Chat vs. Voice STT) & Adaptive TTS Filtering
"""

import pytest
from unittest.mock import MagicMock
from orchestrator.prompt_builder import SystemPromptBuilder


def test_prompt_builder_input_modality_voice():
    prompt = SystemPromptBuilder.build(
        date_str="Monday, Jan 1",
        time_str="12:00 PM",
        spk_ok=True,
        tts_ok=True,
        mic_ok=True,
        input_mode="voice",
    )
    assert "=== USER INPUT MODALITY: VOICE (STT) ===" in prompt
    assert "user provided this prompt via speech" in prompt
    assert "suitable for text-to-speech" in prompt


def test_prompt_builder_input_modality_text():
    prompt = SystemPromptBuilder.build(
        date_str="Monday, Jan 1",
        time_str="12:00 PM",
        spk_ok=True,
        tts_ok=True,
        mic_ok=True,
        input_mode="text",
    )
    assert "=== USER INPUT MODALITY: TEXT (CHAT) ===" in prompt
    assert "user typed this prompt via chat UI" in prompt
    assert "Spoken TTS will be concise" in prompt


def test_filter_tts_for_input_mode_voice():
    from controller.raphael_controller import RaphaelController

    controller = MagicMock(spec=RaphaelController)
    filter_fn = RaphaelController._filter_tts_for_input_mode.__get__(controller, RaphaelController)

    long_response = (
        "Here is the detailed solution to your question.\n\n"
        "```python\ndef hello():\n    print('world')\n```\n"
        "You can run this function directly."
    )
    res = filter_fn(long_response, input_mode="voice")
    # Code blocks should be stripped for TTS readability, but full text preserved
    assert "Here is the detailed solution to your question." in res
    assert "You can run this function directly." in res
    assert "def hello()" not in res


def test_filter_tts_for_input_mode_text_short():
    from controller.raphael_controller import RaphaelController

    controller = MagicMock(spec=RaphaelController)
    filter_fn = RaphaelController._filter_tts_for_input_mode.__get__(controller, RaphaelController)

    short_response = "Sure, I have updated the file for you."
    res = filter_fn(short_response, input_mode="text")
    assert res == "Sure, I have updated the file for you."


def test_filter_tts_for_input_mode_text_headings_and_recommendations():
    from controller.raphael_controller import RaphaelController

    controller = MagicMock(spec=RaphaelController)
    filter_fn = RaphaelController._filter_tts_for_input_mode.__get__(controller, RaphaelController)

    long_formatted_response = (
        "Here is a comprehensive breakdown of the options:\n\n"
        "### Option A: Performance Optimization\n"
        "This option improves speed by 40%.\n\n"
        "### Option B: Memory Optimization\n"
        "This option reduces memory usage.\n\n"
        "Recommendation: Go with Option A for best results.\n\n"
        "```python\nprint('code example')\n```"
    )
    res = filter_fn(long_formatted_response, input_mode="text")
    assert "Option A: Performance Optimization" in res
    assert "Option B: Memory Optimization" in res
    assert "Recommendation: Go with Option A for best results." in res
    # Should not include code snippet
    assert "code example" not in res
