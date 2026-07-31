import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from orchestrator.tool_orchestrator import ToolOrchestrator, ToolDomain


def test_classify_audio_query():
    orch = ToolOrchestrator()
    domains = orch.classify_query("set volume to 50")
    assert ToolDomain.AUDIO in domains
    schemas = orch.get_filtered_schemas("set volume to 50")
    assert any(s["function"]["name"] == "set_system_volume" for s in schemas)
    assert len(schemas) <= 15


def test_classify_music_query():
    orch = ToolOrchestrator()
    domains = orch.classify_query("play Alan Walker Faded")
    assert ToolDomain.MUSIC in domains
    schemas = orch.get_filtered_schemas("play Alan Walker Faded")
    assert any(s["function"]["name"] == "play_song" for s in schemas)


def test_classify_file_query():
    orch = ToolOrchestrator()
    domains = orch.classify_query("read file main.py")
    assert ToolDomain.FILES in domains
    schemas = orch.get_filtered_schemas("read file main.py")
    assert any(s["function"]["name"] == "read_file" for s in schemas)


def test_general_fallback():
    orch = ToolOrchestrator()
    schemas = orch.get_filtered_schemas("hello how are you")
    assert len(schemas) > 0
    assert any(s["function"]["name"] == "web_search" for s in schemas)
