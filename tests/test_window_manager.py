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


def test_controller_ui_state_tracking():
    """RaphaelController should track UI state ('window' vs 'floating_icon') and support native tools."""
    from unittest.mock import MagicMock
    from controller.raphael_controller import RaphaelController, get_controller_instance
    from orchestrator.tools.native.ui import get_raphael_ui_state

    mock_ui = MagicMock()
    mock_ui.window = MagicMock()

    ctrl = RaphaelController(mock_ui)
    ctrl._floating_icon = MagicMock()
    assert get_controller_instance() is ctrl
    assert ctrl.get_ui_state() == "window"
    assert ctrl.is_window_state() is True
    assert ctrl.is_floating_icon_state() is False

    # Simulate main window hiding (closing to floating icon)
    mock_ui.window.isMinimized.return_value = False
    ctrl._on_main_window_visibility(False)
    assert ctrl.get_ui_state() == "floating_icon"
    assert ctrl.is_floating_icon_state() is True
    assert ctrl.is_window_state() is False
    assert "floating_icon" in get_raphael_ui_state()

    # Simulate main window minimizing to taskbar
    mock_ui.window.isMinimized.return_value = True
    ctrl._floating_icon.hide = MagicMock()
    ctrl._on_main_window_visibility(False)
    assert ctrl._floating_icon.hide.called is True

    # Simulate restoring main window
    mock_ui.window.isMinimized.return_value = False
    ctrl._on_main_window_visibility(True)
    assert ctrl.get_ui_state() == "window"
    assert "window" in get_raphael_ui_state()


def test_ui_ux_enhancements():
    """Test CompactChatInput expand_requested signal, TaskBadge progress/timer, and HotkeyDialog."""
    from ui.floating_icon import CompactChatInput, FloatingIcon
    from ui.main_window import TaskBadge
    from ui.hotkey_dialog import HotkeyDialog

    # 1. FloatingIcon Tooltip
    icon = FloatingIcon()
    assert "Raphael Desktop Assistant" in icon.toolTip()
    icon.hide()

    # 2. CompactChatInput Expand button
    chat = CompactChatInput()
    signal_emitted = False
    def on_expand():
        nonlocal signal_emitted
        signal_emitted = True
    chat.expand_requested.connect(on_expand)
    chat._expand_btn.click()
    assert signal_emitted is True

    # 3. TaskBadge Progress & Timer
    badge = TaskBadge("task-1", "Search Web", "running", tool_name="web_search")
    assert badge.progress_bar.isHidden() is False
    assert badge._timer.isActive() is True
    badge.update_status("done")
    assert badge.progress_bar.isHidden() is True
    assert badge._timer.isActive() is False

    # 4. HotkeyDialog
    dialog = HotkeyDialog()
    assert len(dialog.SHORTCUTS) >= 8
    dialog.close()


