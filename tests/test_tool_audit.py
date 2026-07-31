import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from orchestrator.tool_audit import MIN_DESCRIPTION_LENGTH, audit_tool_registry


@pytest.fixture(scope="module")
def warnings():
    return audit_tool_registry()


def _kind(warning: str) -> str:
    return warning.split(":")[0]


def test_audit_returns_list(warnings):
    assert isinstance(warnings, list)


def test_no_phantom_tools(warnings):
    """Every name in DOMAIN_TOOL_MAP / CORE_FALLBACK_TOOLS must be registered."""
    assert [w for w in warnings if _kind(w) == "PHANTOM TOOL"] == []


def test_no_unreachable_tools(warnings):
    """Every registered tool must be exposed via a domain map, core fallback,
    or the prompt tool guide — otherwise the model can never call it."""
    assert [w for w in warnings if _kind(w) == "UNREACHABLE TOOL"] == []


def test_no_prompt_references_unregistered(warnings):
    """Every tool name in the rendered system prompt must be registered."""
    assert [w for w in warnings if _kind(w) == "PROMPT REFERENCES UNREGISTERED TOOL"] == []


def test_weak_description_check_fires():
    """The weak-description check must actually detect short descriptions."""
    warnings = audit_tool_registry()
    weak = [w for w in warnings if _kind(w) == "WEAK DESCRIPTION"]
    assert weak, "expected at least one WEAK DESCRIPTION warning"
    # Sanity: known-short tools must be flagged (they are under the threshold).
    assert any("'list_playlists'" in w for w in weak)
    assert MIN_DESCRIPTION_LENGTH == 60
