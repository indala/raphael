"""
PopupWindowManager — dynamic standalone windows for the floating minion.

When the minion submits a task, results open in independent popup windows
(ContentWindow for text/markdown, MusicWindow for the music player). Each
window is frameless, always-on-top, and has no parent connection to the
main HUD window.

ContentWindow features:
- Markdown rendering via mistune (falls back to plain text)
- Drag from anywhere (not just the title bar)
- Maximize / restore toggle
- Dynamic sizing based on content
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QGuiApplication, QKeySequence, QShortcut, QTextCursor, QTextDocument
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

try:
    import mistune

    _HAS_MISTUNE = True
except ImportError:
    _HAS_MISTUNE = False

# ── Markdown stylesheet ───────────────────────────────────────────────────────

_MD_STYLESHEET = """
body {
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
    color: #c9d1d9;
    background: #0d1117;
}
h1, h2, h3, h4, h5, h6 {
    color: #e6edf3;
    margin-top: 12px;
    margin-bottom: 6px;
}
h1 { font-size: 20px; }
h2 { font-size: 17px; }
h3 { font-size: 15px; }
p { margin: 4px 0; }
a { color: #6c5ce7; text-decoration: none; }
a:hover { text-decoration: underline; }
code {
    background: #161b22;
    padding: 1px 5px;
    border-radius: 4px;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 12px;
    color: #7ee787;
}
pre {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 10px;
    overflow-x: auto;
}
pre code {
    background: none;
    padding: 0;
    color: #c9d1d9;
}
blockquote {
    border-left: 3px solid #6c5ce7;
    margin: 6px 0;
    padding: 4px 12px;
    color: #8b949e;
    background: #161b22;
    border-radius: 0 4px 4px 0;
}
ul, ol { margin: 4px 0; padding-left: 24px; }
li { margin: 2px 0; }
table {
    border-collapse: collapse;
    margin: 8px 0;
}
th, td {
    border: 1px solid #30363d;
    padding: 6px 10px;
    text-align: left;
}
th { background: #161b22; color: #e6edf3; }
hr {
    border: none;
    border-top: 1px solid #30363d;
    margin: 10px 0;
}
img { max-width: 100%; border-radius: 6px; }
QScrollBar:horizontal {
    background: #0d1117;
    height: 8px;
    border: none;
}
QScrollBar::handle:horizontal {
    background: #333;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
"""


# ── ContentWindow ─────────────────────────────────────────────────────────────

class ContentWindow(QWidget):
    """Standalone scrollable text/markdown window for task results.

    Features:
    - Markdown rendering via mistune (falls back to plain text)
    - Drag from anywhere on the window
    - Maximize / restore toggle
    - Dynamic sizing based on content
    """

    close_requested = pyqtSignal()

    _MIN_W, _MIN_H = 360, 220
    _MAX_W, _MAX_H = 900, 700

    def __init__(self, title: str = "Result", parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(self._MIN_W, self._MIN_H)
        self.resize(520, 400)

        # Drag / maximize state
        self._drag_pos = None
        self._saved_geometry: QRect | None = None

        # Edge-resize state
        self._resizing = False
        self._resize_edge = 0
        self._resize_start_pos = None
        self._resize_start_geo: QRect | None = None
        self._EDGE_PX = 6  # resize handle thickness in pixels
        self._SNAP_PX = 15  # edge-snapping threshold

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar
        title_bar = QFrame()
        title_bar.setFixedHeight(32)
        title_bar.setStyleSheet(
            "QFrame { background: #1a1a2e; border-bottom: 1px solid #333; }"
        )
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 4, 0)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("color: #ccc; font-size: 12px;")
        tb_layout.addWidget(self._title_label)
        tb_layout.addStretch()

        # Maximize / restore button
        self._max_btn = QPushButton("\u25a1")
        self._max_btn.setFixedSize(28, 24)
        self._max_btn.setStyleSheet(
            "QPushButton { color: #999; border: none; font-size: 13px; }"
            "QPushButton:hover { color: #5eead4; }"
        )
        self._max_btn.setToolTip("Maximize / Restore")
        self._max_btn.clicked.connect(self._toggle_maximize)
        tb_layout.addWidget(self._max_btn)

        # Pin (always-on-top toggle)
        self._pinned = True  # starts on top
        self._pin_btn = QPushButton("\U0001f4cc")
        self._pin_btn.setFixedSize(28, 24)
        self._pin_btn.setStyleSheet(
            "QPushButton { color: #6c5ce7; border: none; font-size: 13px; }"
            "QPushButton:hover { color: #8b7cf7; }"
        )
        self._pin_btn.setToolTip("Toggle always on top")
        self._pin_btn.clicked.connect(self._toggle_always_on_top)
        tb_layout.addWidget(self._pin_btn)

        # Save button
        save_btn = QPushButton("\U0001f4be")
        save_btn.setFixedSize(28, 24)
        save_btn.setStyleSheet(
            "QPushButton { color: #999; border: none; font-size: 13px; }"
            "QPushButton:hover { color: #5eead4; }"
        )
        save_btn.setToolTip("Save content to file")
        save_btn.clicked.connect(self._save_content)
        tb_layout.addWidget(save_btn)

        # Close button
        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(28, 24)
        close_btn.setStyleSheet(
            "QPushButton { color: #999; border: none; font-size: 13px; }"
            "QPushButton:hover { color: #ff3366; }"
        )
        close_btn.clicked.connect(self._on_close)
        tb_layout.addWidget(close_btn)

        layout.addWidget(title_bar)

        # Search bar (hidden by default, toggled with Ctrl+F)
        self._search_bar = QFrame()
        self._search_bar.setFixedHeight(36)
        self._search_bar.setStyleSheet(
            "QFrame { background: #1a1a2e; border-bottom: 1px solid #333; }"
        )
        self._search_bar.hide()
        search_layout = QHBoxLayout(self._search_bar)
        search_layout.setContentsMargins(8, 4, 8, 4)
        search_layout.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Find...")
        self._search_input.setFixedWidth(200)
        self._search_input.setStyleSheet(
            "QLineEdit { background: #0d1117; color: #c9d1d9; border: 1px solid #333; "
            "border-radius: 4px; padding: 4px 8px; font-size: 12px; }"
        )
        self._search_input.textChanged.connect(self._on_search_text_changed)
        self._search_input.returnPressed.connect(self._find_next)
        search_layout.addWidget(self._search_input)

        prev_btn = QPushButton("\u25c0")
        prev_btn.setFixedSize(24, 24)
        prev_btn.setStyleSheet(
            "QPushButton { color: #999; border: none; font-size: 11px; }"
            "QPushButton:hover { color: #5eead4; }"
        )
        prev_btn.setToolTip("Previous (Shift+Enter)")
        prev_btn.clicked.connect(self._find_prev)
        search_layout.addWidget(prev_btn)

        next_btn = QPushButton("\u25b6")
        next_btn.setFixedSize(24, 24)
        next_btn.setStyleSheet(
            "QPushButton { color: #999; border: none; font-size: 11px; }"
            "QPushButton:hover { color: #5eead4; }"
        )
        next_btn.setToolTip("Next (Enter)")
        next_btn.clicked.connect(self._find_next)
        search_layout.addWidget(next_btn)

        self._search_count_label = QLabel("")
        self._search_count_label.setStyleSheet("color: #666; font-size: 11px;")
        search_layout.addWidget(self._search_count_label)

        search_layout.addStretch()

        close_search_btn = QPushButton("\u2715")
        close_search_btn.setFixedSize(20, 20)
        close_search_btn.setStyleSheet(
            "QPushButton { color: #999; border: none; font-size: 11px; }"
            "QPushButton:hover { color: #ff3366; }"
        )
        close_search_btn.clicked.connect(self._hide_search_bar)
        search_layout.addWidget(close_search_btn)

        layout.addWidget(self._search_bar)

        # Content area — QTextBrowser for markdown rendering
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            "QTextBrowser { background: #0d1117; color: #c9d1d9; "
            "border: none; padding: 12px; font-size: 13px; }"
            "QScrollBar:vertical { background: #0d1117; width: 8px; }"
            "QScrollBar::handle:vertical { background: #333; border-radius: 4px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar:horizontal { background: #0d1117; height: 8px; border: none; }"
            "QScrollBar::handle:horizontal { background: #333; border-radius: 4px; min-width: 20px; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        )
        layout.addWidget(self._browser)

        # Keyboard shortcuts
        QShortcut(QKeySequence("Esc"), self, self._on_esc)
        QShortcut(QKeySequence("Ctrl+="), self, lambda: self._browser.zoomIn(1))
        QShortcut(QKeySequence("Ctrl+-"), self, lambda: self._browser.zoomOut(1))
        QShortcut(QKeySequence("Ctrl+F"), self, self._toggle_search_bar)

    # ── Content ──

    def set_content(self, text: str):
        self._set_text(text)
        self._resize_to_content()

    def append_content(self, text: str):
        self._browser.append(text)
        self._resize_to_content()

    def set_title(self, title: str):
        self._title_label.setText(title)

    def _set_text(self, text: str):
        """Render text as markdown if available, else plain text."""
        if _HAS_MISTUNE and text.strip():
            html = mistune.html(text)
            full_html = (
                f"<html><head><style>{_MD_STYLESHEET}</style></head>"
                f"<body>{html}</body></html>"
            )
            self._browser.setHtml(full_html)
        else:
            self._browser.setPlainText(text)
        self._browser.moveCursor(QTextCursor.MoveOperation.Start)

    # ── Dynamic sizing ──

    def _resize_to_content(self):
        """Resize window to fit content, clamped between min and max."""
        doc = self._browser.document()
        viewport = self._browser.viewport()
        if doc is None or viewport is None:
            return
        doc.setTextWidth(viewport.width())
        ideal_h = int(doc.size().height()) + 60  # title bar + padding
        ideal_w = max(self._MIN_W, min(self._MAX_W, 520))
        ideal_h = max(self._MIN_H, min(self._MAX_H, ideal_h))
        self.resize(ideal_w, ideal_h)

    # ── Maximize / restore ──

    def _toggle_maximize(self):
        if self._saved_geometry is not None:
            # Restore
            self.setGeometry(self._saved_geometry)
            self._max_btn.setText("\u25a1")
            self._saved_geometry = None
        else:
            # Maximize to screen
            screen = self.screen()
            if screen:
                self._saved_geometry = self.geometry()
                geo = screen.availableGeometry()
                self.setGeometry(geo)
                self._max_btn.setText("\u29c9")

    # ── Close ──

    def _on_close(self):
        self.close_requested.emit()
        self.close()

    # ── Always-on-top pin toggle ──

    def _toggle_always_on_top(self):
        flags = self.windowFlags()
        if flags & Qt.WindowType.WindowStaysOnTopHint:
            self.setWindowFlags(flags & ~Qt.WindowType.WindowStaysOnTopHint)
            self._pinned = False
            self._pin_btn.setStyleSheet(
                "QPushButton { color: #666; border: none; font-size: 13px; }"
                "QPushButton:hover { color: #999; }"
            )
        else:
            self.setWindowFlags(flags | Qt.WindowType.WindowStaysOnTopHint)
            self._pinned = True
            self._pin_btn.setStyleSheet(
                "QPushButton { color: #6c5ce7; border: none; font-size: 13px; }"
                "QPushButton:hover { color: #8b7cf7; }"
            )
        self.show()

    # ── Save content to file ──

    def _save_content(self):
        """Save the browser text content to a file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Content", "result.md",
            "Markdown (*.md);;Text (*.txt);;All Files (*)",
        )
        if path:
            try:
                text = self._browser.toPlainText()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
            except Exception as exc:
                logger.warning("Failed to save content: %s", exc)

    # ── Search bar (Ctrl+F) ──

    def _toggle_search_bar(self):
        """Toggle search bar visibility."""
        if self._search_bar.isVisible():
            self._hide_search_bar()
        else:
            self._show_search_bar()

    def _show_search_bar(self):
        """Show search bar and focus the input."""
        self._search_bar.show()
        self._search_input.setFocus()
        self._search_input.selectAll()

    def _hide_search_bar(self):
        """Hide search bar and clear any highlights."""
        self._search_bar.hide()
        # Clear selection/highlight
        cursor = self._browser.textCursor()
        cursor.clearSelection()
        self._browser.setTextCursor(cursor)

    def _on_esc(self):
        """Esc: close search bar if open, otherwise close window."""
        if self._search_bar.isVisible():
            self._hide_search_bar()
        else:
            self.close()

    def _on_search_text_changed(self, text: str):
        """Highlight first match as user types."""
        if not text:
            self._search_count_label.setText("")
            return
        # Reset cursor to start for fresh search
        cursor = self._browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self._browser.setTextCursor(cursor)
        self._find_next()

    def _find_next(self):
        """Find and highlight the next occurrence."""
        text = self._search_input.text()
        if not text:
            return
        # Use QTextDocument.FindFlag for case-insensitive
        found = self._browser.find(text)
        if found:
            self._update_search_count()
        else:
            # Wrap to top
            cursor = self._browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._browser.setTextCursor(cursor)
            found = self._browser.find(text)
            if found:
                self._update_search_count()

    def _find_prev(self):
        """Find and highlight the previous occurrence."""
        text = self._search_input.text()
        if not text:
            return
        # For reverse, we need to use the document find with FindBackward
        cursor = self._browser.textCursor()
        # Move cursor back one character to avoid finding current match
        if cursor.hasSelection():
            pos = cursor.selectionStart()
            cursor.setPosition(pos)
            self._browser.setTextCursor(cursor)
        found = self._browser.find(text, QTextDocument.FindFlag.FindBackward)
        if not found:
            # Wrap to bottom
            cursor = self._browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._browser.setTextCursor(cursor)
            self._browser.find(text, QTextDocument.FindFlag.FindBackward)
        self._update_search_count()

    def _update_search_count(self):
        """Update the match count label."""
        text = self._search_input.text()
        if not text:
            self._search_count_label.setText("")
            return
        # Count occurrences (rough count)
        doc_text = self._browser.toPlainText()
        count = doc_text.lower().count(text.lower())
        self._search_count_label.setText(f"{count} found" if count else "No match")

    # ── Double-click title bar to maximize/restore ──

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.position().y() <= 32:
                self._toggle_maximize()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    # ── Resize edge detection ──

    _EDGE_TOP = Qt.Edge.TopEdge.value
    _EDGE_BOTTOM = Qt.Edge.BottomEdge.value
    _EDGE_LEFT = Qt.Edge.LeftEdge.value
    _EDGE_RIGHT = Qt.Edge.RightEdge.value

    _EDGE_TOP_LEFT = _EDGE_TOP | _EDGE_LEFT
    _EDGE_TOP_RIGHT = _EDGE_TOP | _EDGE_RIGHT
    _EDGE_BOTTOM_LEFT = _EDGE_BOTTOM | _EDGE_LEFT
    _EDGE_BOTTOM_RIGHT = _EDGE_BOTTOM | _EDGE_RIGHT

    def _detect_resize_edge(self, pos) -> int:
        """Return the edge/corner the mouse is near, or 0."""
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        e = self._EDGE_PX

        on_left = x < e
        on_right = x > w - e
        on_top = y < e
        on_bottom = y > h - e

        if on_top and on_left:
            return self._EDGE_TOP_LEFT
        if on_top and on_right:
            return self._EDGE_TOP_RIGHT
        if on_bottom and on_left:
            return self._EDGE_BOTTOM_LEFT
        if on_bottom and on_right:
            return self._EDGE_BOTTOM_RIGHT
        if on_top:
            return self._EDGE_TOP
        if on_bottom:
            return self._EDGE_BOTTOM
        if on_left:
            return self._EDGE_LEFT
        if on_right:
            return self._EDGE_RIGHT
        return 0

    @classmethod
    def _edge_cursor(cls, edge: int) -> Qt.CursorShape:
        """Return the cursor shape for a given resize edge."""
        if edge in (cls._EDGE_TOP_LEFT, cls._EDGE_BOTTOM_RIGHT):
            return Qt.CursorShape.SizeFDiagCursor
        if edge in (cls._EDGE_TOP_RIGHT, cls._EDGE_BOTTOM_LEFT):
            return Qt.CursorShape.SizeBDiagCursor
        if edge in (cls._EDGE_TOP, cls._EDGE_BOTTOM):
            return Qt.CursorShape.SizeVerCursor
        if edge in (cls._EDGE_LEFT, cls._EDGE_RIGHT):
            return Qt.CursorShape.SizeHorCursor
        return Qt.CursorShape.ArrowCursor

    def _apply_edge_snap(self, pos):
        """Snap window position to screen edges within _SNAP_PX threshold."""
        screen = self.screen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x, y = pos.x(), pos.y()
        s = self._SNAP_PX

        if abs(x - geo.left()) < s:
            x = geo.left()
        elif abs(x + self.width() - geo.right()) < s:
            x = geo.right() - self.width()
        if abs(y - geo.top()) < s:
            y = geo.top()
        elif abs(y + self.height() - geo.bottom()) < s:
            y = geo.bottom() - self.height()

        self.move(x, y)

    # ── Mouse events (drag, resize, snap) ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            edge = self._detect_resize_edge(pos)
            if edge != 0:
                self._resizing = True
                self._resize_edge = edge
                self._resize_start_pos = event.globalPosition().toPoint()
                self._resize_start_geo = self.geometry()
                event.accept()
                return
            self._drag_pos = pos - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        global_pos = event.globalPosition().toPoint()

        # Resize mode
        if self._resizing and self._resize_start_geo is not None:
            delta = global_pos - self._resize_start_pos
            geo = self._resize_start_geo
            edge = self._resize_edge
            min_w, min_h = self.minimumWidth(), self.minimumHeight()

            new_x = geo.x()
            new_y = geo.y()
            new_w = geo.width()
            new_h = geo.height()

            if edge & self._EDGE_LEFT:
                new_x = geo.x() + delta.x()
                new_w = geo.width() - delta.x()
            if edge & self._EDGE_RIGHT:
                new_w = geo.width() + delta.x()
            if edge & self._EDGE_TOP:
                new_y = geo.y() + delta.y()
                new_h = geo.height() - delta.y()
            if edge & self._EDGE_BOTTOM:
                new_h = geo.height() + delta.y()

            # Enforce minimums
            if new_w < min_w:
                new_w = min_w
                if edge & self._EDGE_LEFT:
                    new_x = geo.right() - min_w
            if new_h < min_h:
                new_h = min_h
                if edge & self._EDGE_TOP:
                    new_y = geo.bottom() - min_h

            self.setGeometry(new_x, new_y, new_w, new_h)
            event.accept()
            return

        # Update cursor when hovering near edges (not dragging)
        if self._drag_pos is None:
            edge = self._detect_resize_edge(event.position().toPoint())
            self.setCursor(self._edge_cursor(edge))
            if edge != 0:
                event.accept()
                return

        # Drag mode
        if self._drag_pos is not None:
            new_pos = global_pos - self._drag_pos
            self._apply_edge_snap(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resizing = False
        self._resize_edge = 0
        self._resize_start_pos = None
        self._resize_start_geo = None


# ── PopupWindowManager ────────────────────────────────────────────────────────

class PopupWindowManager:
    """Manages keyed popup windows. Prevents duplicates for the same key."""

    def __init__(self):
        self._windows: dict[str, QWidget] = {}

    def show_content(self, key: str, title: str, text: str) -> ContentWindow:
        """Show (or raise) a content window. Returns the window."""
        if key in self._windows:
            w = self._windows[key]
            if isinstance(w, ContentWindow):
                w.set_title(title)
                w.set_content(text)
                w.show()
                w.raise_()
                w.activateWindow()
                return w

        win = ContentWindow(title=title)
        win.set_content(text)
        win.close_requested.connect(lambda k=key: self._remove(k))
        self._windows[key] = win
        win.show()
        win.raise_()
        return win

    def show_music(self):
        """Show (or raise) the SpotifyMusicWindow."""
        from ui.spotify_music_window import SpotifyMusicWindow

        key = "__music__"
        if key in self._windows:
            w = self._windows[key]
            if isinstance(w, SpotifyMusicWindow):
                w.show()
                w.raise_()
                w.activateWindow()
                return w

        win = SpotifyMusicWindow(parent=None)
        self._windows[key] = win
        win.show()
        win.raise_()
        return win

    def close_all(self):
        for w in list(self._windows.values()):
            w.close()
        self._windows.clear()

    def _remove(self, key: str):
        self._windows.pop(key, None)

    @property
    def window_count(self) -> int:
        return len(self._windows)
