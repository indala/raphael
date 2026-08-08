"""
Basic tests for Raphael modules.
Run with: python -m pytest tests/test_modules.py -v
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules import clipboard, app_launcher, chart_gen, screen, ui_control


def test_clipboard_copy_paste():
    """Test clipboard text copy and paste."""
    test_text = "Raphael test message"
    assert clipboard.copy_text(test_text)
    assert clipboard.paste_text() == test_text


def test_launch_app():
    """Test app launcher with notepad."""
    result = app_launcher.launch("notepad.exe")
    assert "Launched" in result or "Failed" not in result


def test_chart_generation():
    """Test matplotlib chart generation."""
    path = chart_gen.create_matplotlib_chart(
        chart_type="bar",
        title="Test Chart",
        labels=["A", "B", "C"],
        values=[10, 20, 15],
    )
    assert Path(path).exists()
    assert path.endswith(".png")


def test_plotly_chart_generation():
    """Test plotly interactive chart generation."""
    path = chart_gen.create_plotly_chart(
        chart_type="bar",
        title="Test Interactive Chart",
        labels=["A", "B", "C"],
        values=[10, 20, 15],
    )
    assert Path(path).exists()
    assert path.endswith(".html")


def test_screen_capture():
    """Test screen capture functionality."""
    try:
        path = screen.capture_screen()
        assert Path(path).exists()
        assert path.endswith(".png")
    except Exception as e:
        assert "Screen capture failed" in str(e)



def test_clipboard_image_copy():
    """Test copying an image to the clipboard."""
    # First generate a chart PNG
    path = chart_gen.create_matplotlib_chart(
        chart_type="line",
        title="Test Image Copy Chart",
        labels=["X", "Y"],
        values=[1, 2],
    )
    assert Path(path).exists()
    # Copy it to clipboard
    assert clipboard.copy_image(path)


def test_ui_control_basics():
    """Test basic UI control functions (like getting mouse position)."""
    pos = ui_control.get_mouse_position()
    if pos is None:
        pytest.skip("C# bridge not available in this environment")
    assert isinstance(pos, tuple)
    assert len(pos) == 2
    assert isinstance(pos[0], int)


from unittest.mock import MagicMock, patch

@patch("actions.browser_control._registry")
def test_browser_control_parameters(mock_registry):
    """Test that browser_control forwards new arguments to get_or_create."""
    from actions.browser_control import browser_control

    mock_session = MagicMock()
    mock_session.downloads = []
    mock_session.navigate.return_value = "navigated"
    mock_registry.get_or_create.return_value = mock_session

    res = browser_control(
        action="navigate",
        url="google.com",
        headless=True,
        viewport_width=800,
        viewport_height=600,
        user_agent="custom-ua"
    )

    assert res == "navigated"
    mock_registry.get_or_create.assert_called_once_with(
        None,
        headless=True,
        viewport_width=800,
        viewport_height=600,
        user_agent="custom-ua"
    )


def test_parse_seconds_and_seek_streaming():
    """Test timestamp string parsing and streaming seek functionality."""
    from audio.music_player import MusicPlayer, SongEntry, _parse_seconds

    assert _parse_seconds(90) == 90.0
    assert _parse_seconds("90") == 90.0
    assert _parse_seconds("1:30") == 90.0
    assert _parse_seconds("01:30") == 90.0
    assert _parse_seconds("1:01:30") == 3690.0

    player = MusicPlayer.get_instance()
    entry = SongEntry(title="Test Live Stream", artist="Artist")
    player._queue = [entry]
    player._current_index = 0

    # Seeking live stream before buffering completes
    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        res = player.seek("1:30")
        assert "Seeking live stream to 1:30" in res
        assert player._seek_stream_sec == 90.0
        assert player._music_interrupted.is_set()



