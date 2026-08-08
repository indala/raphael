"""
Tests for Raphael Playground Studio window and native tools.
"""

from unittest.mock import MagicMock, patch
import pytest
from PyQt6.QtWidgets import QApplication

# Ensure QApplication instance exists
@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_playground_window_methods():
    from ui.playground_window import PlaygroundWindow

    win = PlaygroundWindow(title="Test Playground")
    assert win.windowTitle() == "Test Playground"

    # Test rendering HTML
    win.render_html("<p>Hello World</p>")
    assert "Hello World" in win._browser.toPlainText()

    # Test rendering Chart
    win.render_chart("bar", ["Jan", "Feb"], [{"data": [10, 20]}], "Sales Chart")
    assert "Sales Chart" in win._browser.toPlainText()
    assert "Jan" in win._browser.toPlainText()

    # Test rendering Diagram
    win.render_diagram("graph TD; A-->B;", "Flowchart")
    assert "Flowchart" in win._browser.toPlainText()
    assert "graph TD;" in win._browser.toPlainText()

    # Test clearing
    win.clear_playground()
    assert "Raphael Interactive Playground Studio" in win._browser.toPlainText()


def test_popup_window_manager_show_playground():
    from ui.window_manager import PopupWindowManager
    from ui.playground_window import PlaygroundWindow

    wm = PopupWindowManager()
    win1 = wm.show_playground()
    assert isinstance(win1, PlaygroundWindow)
    assert wm.window_count == 1

    # Second call returns the same window instance
    win2 = wm.show_playground()
    assert win2 is win1
    assert wm.window_count == 1


def test_playground_native_tools():
    from orchestrator.tools.native import playground_tools

    schemas = playground_tools.get_schemas()
    assert len(schemas) == 4
    tool_names = [s["function"]["name"] for s in schemas]
    assert "render_playground_chart" in tool_names
    assert "render_playground_diagram" in tool_names
    assert "render_playground_html" in tool_names
    assert "clear_playground" in tool_names

    # Mock controller
    mock_ctrl = MagicMock()
    mock_wm = MagicMock()
    mock_win = MagicMock()
    mock_wm.show_playground.return_value = mock_win
    mock_ctrl._window_manager = mock_wm

    with patch("orchestrator.tools.native.playground_tools._get_controller", return_value=mock_ctrl):
        res1 = playground_tools.render_playground_chart("bar", "Test Chart", ["A"], [10])
        assert "Rendered 'Test Chart'" in res1
        mock_win.render_chart.assert_called_once()

        res2 = playground_tools.render_playground_diagram("graph TD; A-->B;", "Test Flow")
        assert "Rendered diagram 'Test Flow'" in res2
        mock_win.render_diagram.assert_called_once()

        res3 = playground_tools.render_playground_html("<p>HTML</p>")
        assert "Rendered custom HTML" in res3
        mock_win.render_html.assert_called_once()

        res4 = playground_tools.clear_playground()
        assert "Cleared" in res4
        mock_win.clear_playground.assert_called_once()
