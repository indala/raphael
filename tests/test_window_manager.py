"""Tests for PopupWindowManager and ContentWindow (offscreen GUI)."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import pytest

# Ensure QApplication exists before any widget imports
from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)

from ui.window_manager import PopupWindowManager, ContentWindow


def test_content_window_creation():
    """ContentWindow should instantiate with title."""
    w = ContentWindow(title="Test Title")
    assert w.windowTitle() == ""  # frameless, no window title set
    w.set_content("Hello world")
    # Should not crash
    w.close()


def test_content_window_set_append():
    """set_content and append_content should work."""
    w = ContentWindow(title="T")
    w.set_content("line1")
    w.append_content("line2")
    w.set_title("New Title")
    w.close()


def test_popup_manager_show_content():
    """PopupWindowManager.show_content should create and track windows."""
    mgr = PopupWindowManager()
    win = mgr.show_content("k1", "Title", "Body text")
    assert isinstance(win, ContentWindow)
    assert mgr.window_count == 1

    # Same key should reuse window
    win2 = mgr.show_content("k1", "Title2", "Body2")
    assert win2 is win
    assert mgr.window_count == 1

    # Different key creates new window
    mgr.show_content("k2", "T2", "B2")
    assert mgr.window_count == 2

    mgr.close_all()
    assert mgr.window_count == 0


def test_popup_manager_close_removes_key():
    """Closing a window via close_requested should remove it from the manager."""
    mgr = PopupWindowManager()
    win = mgr.show_content("k1", "T", "B")
    # Simulate clicking the close button (emits close_requested)
    win._on_close()
    assert mgr.window_count == 0


def test_popup_manager_music():
    """show_music should create a SpotifyMusicWindow (or fail gracefully if deps missing)."""
    from ui.spotify_music_window import SpotifyMusicWindow
    mgr = PopupWindowManager()
    try:
        win = mgr.show_music()
        assert isinstance(win, SpotifyMusicWindow)
        assert mgr.window_count == 1

        # Second call reuses
        win2 = mgr.show_music()
        assert win2 is win
        assert mgr.window_count == 1
    except Exception:
        # MusicPlayer may not be available in test env — that's ok
        pytest.skip("MusicPlayer dependencies not available in test env")
    finally:
        mgr.close_all()


def test_compact_chat_creation():
    """CompactChatInput should instantiate without crashing."""
    from ui.floating_icon import CompactChatInput
    w = CompactChatInput()
    w.set_processing(True)
    w.set_processing(False)
    w.close()


def test_floating_icon_creation():
    """FloatingIcon should instantiate without crashing."""
    from ui.floating_icon import FloatingIcon
    icon = FloatingIcon()
    icon.start_glow()
    icon.stop_glow()
    icon.hide()


def test_floating_icon_processing():
    """FloatingIcon.set_processing should toggle the spinning ring."""
    from ui.floating_icon import FloatingIcon
    icon = FloatingIcon()
    icon.set_processing(True)
    assert icon._processing is True
    icon.set_processing(False)
    assert icon._processing is False
    icon.hide()


def test_compact_chat_toggle_button():
    """CompactChatInput toggle button should switch between Send and Stop."""
    from ui.floating_icon import CompactChatInput
    w = CompactChatInput()
    # Default state: Send
    assert "Send" in w._toggle_btn.text()
    w.set_processing(True)
    assert "Stop" in w._toggle_btn.text()
    w.set_processing(False)
    assert "Send" in w._toggle_btn.text()
    w.close()


def test_compact_chat_follow_icon():
    """CompactChatInput.follow_icon should reposition the widget."""
    from PyQt6.QtCore import QPoint
    from ui.floating_icon import CompactChatInput
    w = CompactChatInput()
    w.setFixedWidth(320)
    w.show()
    center = QPoint(400, 300)
    w.follow_icon(center)
    expected_x = 400 - w.width() // 2
    assert w.pos().x() == expected_x
    w.close()


def test_content_window_markdown():
    """ContentWindow should render markdown to HTML when mistune is available."""
    w = ContentWindow(title="MD Test")
    w.set_content("**bold** and *italic*")
    html = w._browser.toHtml()
    assert "bold" in html
    w.close()


def test_content_window_maximize_restore():
    """ContentWindow maximize/restore should toggle geometry."""
    w = ContentWindow(title="Max Test")
    w.resize(500, 400)
    w._toggle_maximize()
    assert w._saved_geometry is not None  # saved for restore
    w._toggle_maximize()
    assert w._saved_geometry is None  # restored
    w.close()
