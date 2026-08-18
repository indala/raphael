"""
FloatingIcon — draggable always-on-top Raphael minion icon.

Single click: wakes the icon (visual feedback).
Double click: opens CompactChatInput for typing messages.

CompactChatInput:
- Dynamic height that grows with content
- Follows the floating icon when dragged
- Single toggle button (Send ↔ Stop)
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

_ICON_SIZE = 64
_ICON_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")
_SNAP_PX = 15  # edge-snapping threshold


def _snap_to_screen_edge(pos: QPoint, width: int = _ICON_SIZE, height: int = _ICON_SIZE) -> QPoint:
    """Snap a position to screen edges within _SNAP_PX threshold."""
    screen = QGuiApplication.primaryScreen()
    if screen is None:
        return pos
    geo = screen.availableGeometry()
    x, y = pos.x(), pos.y()
    s = _SNAP_PX

    if abs(x - geo.left()) < s:
        x = geo.left()
    elif abs((x + width) - geo.right()) < s:
        x = geo.right() - width
    if abs(y - geo.top()) < s:
        y = geo.top()
    elif abs((y + height) - geo.bottom()) < s:
        y = geo.bottom() - height

    return QPoint(x, y)


class FloatingIcon(QWidget):
    """Draggable always-on-top Raphael icon that lives on the desktop."""

    single_clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    triple_clicked = pyqtSignal()
    right_clicked = pyqtSignal(QPoint)  # emitted with global position on right-click
    dragged = pyqtSignal(QPoint)  # emitted while being dragged with current global pos

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_ICON_SIZE, _ICON_SIZE)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip("Raphael Desktop Assistant — Drag to move • Double-click to chat • 3-clicks to stop/reopen")

        # Drag & Click state (supports single, double, triple clicks)
        self._dragging = False
        self._drag_start_pos = QPoint()
        self._drag_offset = QPoint()
        self._click_count = 0
        self._click_timer = QTimer()
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(320)
        self._click_timer.timeout.connect(self._on_click_timeout)

        # Pulsing glow animation state
        self._glow_alpha = 0
        self._glow_direction = 1
        self._glow_timer = QTimer()
        self._glow_timer.setInterval(50)
        self._glow_timer.timeout.connect(self._animate_glow)

        # Spinning processing ring state
        self._processing = False
        self._spin_angle = 0
        self._spin_timer = QTimer()
        self._spin_timer.setInterval(30)
        self._spin_timer.timeout.connect(self._animate_spin)

        # Load icon
        self._pixmap = self._load_icon()

        # Position at bottom-right of screen
        self._position_default()

    def _load_icon(self) -> QPixmap:
        if os.path.exists(_ICON_PATH):
            pix = QPixmap(_ICON_PATH)
            if not pix.isNull():
                return pix.scaled(
                    _ICON_SIZE - 8, _ICON_SIZE - 8,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
        # Fallback: generate a simple colored circle
        pix = QPixmap(_ICON_SIZE - 8, _ICON_SIZE - 8)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor("#6c5ce7"))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, pix.width(), pix.height())
        p.end()
        return pix

    def _position_default(self):
        screen = self.screen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.right() - _ICON_SIZE - 20
            y = geo.bottom() - _ICON_SIZE - 20
            self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Spinning processing ring (when busy)
        if self._processing:
            center = _ICON_SIZE / 2
            radius = _ICON_SIZE / 2 - 3
            pen = QPen(QColor("#6c5ce7"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            start = self._spin_angle
            span = 120  # degrees of visible arc
            painter.drawArc(
                int(center - radius), int(center - radius),
                int(radius * 2), int(radius * 2),
                int(start * 16), int(span * 16),
            )

        # Pulsing glow ring when active
        if self._glow_alpha > 0:
            glow = QColor("#6c5ce7")
            glow.setAlpha(self._glow_alpha)
            painter.setBrush(glow)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(2, 2, _ICON_SIZE - 4, _ICON_SIZE - 4)

        # Dark background circle
        painter.setBrush(QColor("#1a1a2e"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, _ICON_SIZE - 8, _ICON_SIZE - 8)

        # Icon pixmap centered
        x = (_ICON_SIZE - self._pixmap.width()) // 2
        y = (_ICON_SIZE - self._pixmap.height()) // 2
        painter.drawPixmap(x, y, self._pixmap)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self._dragging = False
                moved = (event.globalPosition().toPoint() - self._drag_start_pos).manhattanLength()
                if moved < 6:
                    # It was a click, not a drag
                    self._click_count += 1
                    if self._click_count == 3:
                        self._click_timer.stop()
                        self._click_count = 0
                        self.triple_clicked.emit()
                    else:
                        self._click_timer.start(320)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            pos = event.globalPosition().toPoint()
            self.right_clicked.emit(pos)
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            new_pos = _snap_to_screen_edge(new_pos, _ICON_SIZE, _ICON_SIZE)
            self.move(new_pos)
            self.dragged.emit(new_pos + QPoint(_ICON_SIZE // 2, _ICON_SIZE // 2))
            event.accept()

    def _on_click_timeout(self):
        count = self._click_count
        self._click_count = 0
        if count == 1:
            self.single_clicked.emit()
        elif count == 2:
            self.double_clicked.emit()

    # ── Glow animation ──

    def start_glow(self):
        """Start the pulsing glow animation."""
        self._glow_alpha = 100
        self._glow_direction = 1
        self._glow_timer.start()

    def stop_glow(self):
        """Stop glow animation."""
        self._glow_timer.stop()
        self._glow_alpha = 0
        self.update()

    def _animate_glow(self):
        self._glow_alpha += 8 * self._glow_direction
        if self._glow_alpha >= 200:
            self._glow_direction = -1
        elif self._glow_alpha <= 0:
            self._glow_alpha = 0
            self._glow_timer.stop()
        self.update()

    # ── Processing ring animation ──

    def set_processing(self, processing: bool):
        """Start or stop the spinning ring animation."""
        self._processing = processing
        if processing:
            self._spin_angle = 0
            self._spin_timer.start()
            self.start_glow()
        else:
            self._spin_timer.stop()
            self._processing = False
            self.stop_glow()
        self.update()

    def _animate_spin(self):
        self._spin_angle = (self._spin_angle - 12) % 360
        self.update()


# ── CompactChatInput ──────────────────────────────────────────────────────────

class CompactChatInput(QWidget):
    """Small floating chat input that appears near the minion icon.

    Features:
    - Dynamic height that grows smoothly with content
    - Automatically closes on message submission
    - Follows the floating icon when dragged
    """

    message_submitted = pyqtSignal(str)
    stop_requested = pyqtSignal()
    expand_requested = pyqtSignal()
    closed = pyqtSignal()

    _MIN_HEIGHT = 86
    _MAX_HEIGHT = 280

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None
        self._is_processing = False

        # Dark theme
        self.setStyleSheet(
            "QWidget { background: #16161e; border: 1px solid #333; border-radius: 10px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Text input — dynamic height via _adjust_height
        self._input = QTextEdit()
        self._input.setPlaceholderText("Ask Raphael...")
        self._input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._input.setStyleSheet(
            "QTextEdit { background: #0d1117; color: #c9d1d9; border: 1px solid #333; "
            "border-radius: 6px; padding: 6px 8px; font-size: 13px; }"
            "QScrollBar:vertical { width: 4px; background: transparent; }"
            "QScrollBar::handle:vertical { background: #444; border-radius: 2px; }"
        )
        self._input.installEventFilter(self)
        self._input.textChanged.connect(self._adjust_height)
        self._input.document().documentLayout().documentSizeChanged.connect(lambda _: self._adjust_height())
        layout.addWidget(self._input)

        # Action buttons row (Expand + Send)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._expand_btn = QPushButton("⤢ Expand Window")
        self._expand_btn.setFixedHeight(28)
        self._expand_btn.setToolTip("Open Raphael Main HUD Window")
        self._expand_btn.setStyleSheet(
            "QPushButton { background: #222736; color: #88aacc; border: 1px solid #30363d; "
            "border-radius: 6px; font-size: 11px; font-weight: bold; padding: 0 8px; }"
            "QPushButton:hover { background: #30363d; color: #00d4ff; }"
        )
        self._expand_btn.clicked.connect(self._on_expand)
        btn_row.addWidget(self._expand_btn)

        self._toggle_btn = QPushButton("➤ Send")
        self._toggle_btn.setFixedHeight(28)
        self._toggle_btn.setStyleSheet(self._send_style())
        self._toggle_btn.clicked.connect(self._on_toggle)
        btn_row.addWidget(self._toggle_btn)

        layout.addLayout(btn_row)

        # Initial size
        self.setFixedWidth(320)
        self.setFixedHeight(self._MIN_HEIGHT)

    def _on_expand(self):
        """Emit expand request to restore main HUD window."""
        self.expand_requested.emit()
        self.close()

    # ── Styles ──

    @staticmethod
    def _send_style() -> str:
        return (
            "QPushButton { background: #6c5ce7; color: white; border: none; "
            "border-radius: 6px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #7c6cf7; }"
        )

    @staticmethod
    def _stop_style() -> str:
        return (
            "QPushButton { background: #ff3366; color: white; border: none; "
            "border-radius: 6px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #ff5588; }"
        )

    # ── Dynamic height ──

    def _adjust_height(self):
        """Resize height to fit content dynamically, expanding upward without overflowing."""
        doc = self._input.document()
        # Use available width for wrapping calculation
        viewport_w = self._input.viewport().width()
        if viewport_w > 0:
            doc.setTextWidth(viewport_w)
        content_h = int(doc.size().height()) + 56
        h = max(self._MIN_HEIGHT, min(self._MAX_HEIGHT, content_h))
        if h != self.height():
            diff = h - self.height()
            self.setFixedHeight(h)
            if self.isVisible():
                self.move(self.x(), self.y() - diff)

    # ── Button toggle ──

    def set_processing(self, processing: bool):
        """Switch button state."""
        self._is_processing = processing
        self._input.setEnabled(not processing)
        if processing:
            self._toggle_btn.setText("\u25a0 Stop")
            self._toggle_btn.setStyleSheet(self._stop_style())
        else:
            self._toggle_btn.setText("\u27a4 Send")
            self._toggle_btn.setStyleSheet(self._send_style())

    def _on_toggle(self):
        if self._is_processing:
            self.stop_requested.emit()
            self.close()
        else:
            text = self._input.toPlainText().strip()
            if text:
                self.message_submitted.emit(text)
                self._input.clear()
                self._adjust_height()
                self.close()  # Close input box immediately on send

    # ── Key handling (Enter to submit, Escape to close) ──

    def eventFilter(self, obj, event):
        if obj is self._input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close()
                return True
            if event.key() == Qt.Key.Key_Return and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if not self._is_processing:
                    self._on_toggle()
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    # ── Positioning ──

    def popup_near(self, icon_pos: QPoint):
        """Show centered above the floating icon."""
        self._adjust_height()
        x = icon_pos.x() - (self.width() - _ICON_SIZE) // 2
        y = icon_pos.y() - self.height() - 8
        # Keep inside screen bounds
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = max(geo.left() + 10, min(geo.right() - self.width() - 10, x))
            y = max(geo.top() + 10, min(geo.bottom() - self.height() - 10, y))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self._input.setFocus()

    def follow_icon(self, icon_center: QPoint):
        """Reposition to stay centered above the icon (called during drag)."""
        if self.isVisible():
            x = icon_center.x() - self.width() // 2
            y = icon_center.y() - _ICON_SIZE // 2 - self.height() - 8
            self.move(x, y)

    # ── Drag support ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            new_pos = _snap_to_screen_edge(event.globalPosition().toPoint() - self._drag_pos, self.width(), self.height())
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

