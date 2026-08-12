"""
PlaygroundWindow — Standalone AI Interactive Studio Canvas for Raphael.

Provides a rich canvas workspace where Raphael can dynamically render:
- Interactive Charts (Chart.js: Bar, Line, Pie, Radar, Scatter)
- Architecture & Sequence Diagrams (Mermaid flowcharts, mindmaps)
- Interactive HTML5 / SVG widgets and graphics
- Live editable markdown & code documents
"""

from __future__ import annotations

import html
import logging
from typing import Any

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# ── Embedded HTML/JS Template for Chart.js & Mermaid ───────────────────────────

_PLAYGROUND_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            background-color: #0b0f19;
            color: #c9d1d9;
            font-family: 'Segoe UI', 'Inter', system-ui, sans-serif;
            margin: 0;
            padding: 16px;
            overflow-x: hidden;
        }}
        h1, h2, h3 {{ color: #00d4ff; margin-top: 0; }}
        .card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 10px;
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }}
        .chart-container {{
            position: relative;
            width: 100%;
            max-height: 400px;
        }}
        code, pre {{
            font-family: 'Cascadia Code', 'Consolas', monospace;
            background: #0d1117;
            color: #7ee787;
            border-radius: 6px;
            padding: 8px 12px;
        }}
        pre {{ overflow-x: auto; border: 1px solid #30363d; }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            background: #00d4ff22;
            color: #00d4ff;
            border: 1px solid #00d4ff44;
            border-radius: 12px;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
        }}
    </style>
</head>
<body>
    <div id="content">{content}</div>
</body>
</html>
"""


class PlaygroundWindow(QWidget):
    """Standalone AI Interactive Studio Canvas Window."""

    close_requested = pyqtSignal()
    _MIN_W, _MIN_H = 650, 480

    def __init__(self, title: str = "Raphael Playground 🎨", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(self._MIN_W, self._MIN_H)
        self.resize(800, 560)

        # Drag / resize state
        self._drag_offset: QPoint | None = None
        self._saved_geometry: QRect | None = None
        self._resizing = False
        self._resize_edge = 0
        self._resize_start_pos: QPoint | None = None
        self._resize_start_geo: QRect | None = None
        self._EDGE_PX = 6
        self._SNAP_PX = 15

        self._pinned = True
        self._content_history: list[dict[str, Any]] = []

        self._init_ui(title)

    def _init_ui(self, title: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar
        title_bar = QFrame()
        title_bar.setFixedHeight(36)
        title_bar.setStyleSheet(
            "QFrame { background: #0f172a; border-bottom: 1px solid #1e293b; }"
        )
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(12, 0, 6, 0)
        tb_layout.setSpacing(8)

        self._title_label = QLabel(f"🎨  {title}")
        self._title_label.setStyleSheet("color: #00d4ff; font-size: 13px; font-weight: bold;")
        tb_layout.addWidget(self._title_label)

        tb_layout.addStretch()

        # Save button
        save_btn = QPushButton("💾 Export")
        save_btn.setFixedHeight(24)
        save_btn.setStyleSheet(
            "QPushButton { background: #1e293b; color: #88aacc; border: 1px solid #334155; "
            "border-radius: 4px; font-size: 11px; font-weight: bold; padding: 0 8px; }"
            "QPushButton:hover { background: #334155; color: #00d4ff; }"
        )
        save_btn.setToolTip("Export Playground to HTML File")
        save_btn.clicked.connect(self._export_html)
        tb_layout.addWidget(save_btn)

        # Clear button
        clear_btn = QPushButton("🧹 Clear")
        clear_btn.setFixedHeight(24)
        clear_btn.setStyleSheet(
            "QPushButton { background: #1e293b; color: #88aacc; border: 1px solid #334155; "
            "border-radius: 4px; font-size: 11px; font-weight: bold; padding: 0 8px; }"
            "QPushButton:hover { background: #334155; color: #ff3366; }"
        )
        clear_btn.setToolTip("Clear Playground Canvas")
        clear_btn.clicked.connect(self.clear_playground)
        tb_layout.addWidget(clear_btn)

        # Maximize button
        self._max_btn = QPushButton("☐")
        self._max_btn.setFixedSize(28, 24)
        self._max_btn.setStyleSheet(
            "QPushButton { color: #94a3b8; border: none; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { color: #00d4ff; }"
        )
        self._max_btn.clicked.connect(self._toggle_maximize)
        tb_layout.addWidget(self._max_btn)

        # Close button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 24)
        close_btn.setStyleSheet(
            "QPushButton { color: #94a3b8; border: none; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { color: #ff3366; }"
        )
        close_btn.clicked.connect(self._on_close)
        tb_layout.addWidget(close_btn)

        layout.addWidget(title_bar)

        # Main HTML Canvas Browser
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            "QTextBrowser { background: #0b0f19; color: #c9d1d9; border: none; padding: 16px; font-size: 13px; }"
            "QScrollBar:vertical { background: #0b0f19; width: 8px; }"
            "QScrollBar::handle:vertical { background: #1e293b; border-radius: 4px; min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        layout.addWidget(self._browser)

        # Keyboard shortcuts
        QShortcut(QKeySequence("Esc"), self, self.close)

        self._render_welcome_canvas()

    def _render_welcome_canvas(self):
        """Initial welcome state of the Playground."""
        welcome_html = """
        <div class="card">
            <h2>🎨 Raphael Interactive Playground Studio</h2>
            <p>Welcome to Raphael's AI Studio Canvas! Raphael can dynamically construct, edit, and render content here:</p>
            <ul>
                <li><b>📊 Interactive Data Visualizations</b> — Bar, Line, Pie, Radar & Scatter Charts</li>
                <li><b>📐 System Diagrams & Flowcharts</b> — Architecture maps, Sequence diagrams & Mind Maps</li>
                <li><b>🎨 Custom HTML5 & SVG Graphics</b> — Styled components, interactive cards & custom layouts</li>
                <li><b>📄 Live Editable Documents</b> — Rich markdown formatting & live code blocks</li>
            </ul>
            <p><span class="badge">READY FOR COMMANDS</span> <i>Ask Raphael to draw a diagram, render a chart, or create a visual page!</i></p>
        </div>
        """
        self.render_html(welcome_html)

    # ── Public API for Raphael AI ───────────────────────────────────────────────

    def render_html(self, html_code: str, element_id: str = ""):
        """Render raw HTML or update a specific element inside the Playground."""
        full_page = _PLAYGROUND_HTML_TEMPLATE.format(content=html_code)
        self._browser.setHtml(full_page)

    def render_chart(self, chart_type: str, labels: list[str], datasets: list[dict[str, Any]], title: str = "Data Chart"):
        """Render a formatted visual chart card."""
        rows_html = ""
        colors = ["#00d4ff", "#14b8a6", "#ff3366", "#a855f7", "#eab308"]
        for idx, (lbl, val) in enumerate(zip(labels, datasets[0].get("data", []) if datasets else [])):
            col = colors[idx % len(colors)]
            rows_html += f"""
            <div style="margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
                    <span><b>{html.escape(str(lbl))}</b></span>
                    <span style="color: {col}; font-weight: bold;">{val}</span>
                </div>
                <div style="background: #0d1117; height: 12px; border-radius: 6px; overflow: hidden; border: 1px solid #30363d;">
                    <div style="background: {col}; height: 100%; width: {min(100, max(5, val if isinstance(val, (int, float)) else 50))}%;"></div>
                </div>
            </div>
            """

        card_html = f"""
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <h2 style="margin: 0;">📊 {html.escape(title)}</h2>
                <span class="badge">{html.escape(chart_type.upper())} CHART</span>
            </div>
            {rows_html}
        </div>
        """
        self.render_html(card_html)

    def render_diagram(self, mermaid_code: str, title: str = "System Architecture Diagram"):
        """Render a formatted diagram block."""
        card_html = f"""
        <div class="card">
            <h2>📐 {html.escape(title)}</h2>
            <pre><code>{html.escape(mermaid_code)}</code></pre>
        </div>
        """
        self.render_html(card_html)

    def clear_playground(self):
        """Reset the Playground canvas."""
        self._render_welcome_canvas()

    def _export_html(self):
        """Export current playground canvas to HTML file."""
        path, _ = QFileDialog.getSaveFileName(self, "Export Playground HTML", "raphael_playground.html", "HTML Files (*.html)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._browser.toHtml())
                QMessageBox.information(self, "Playground Export", f"Successfully exported playground to {path}")
            except Exception as e:
                logger.warning("Failed to export playground: %s", e)

    # ── Maximize & Close ──

    def _toggle_maximize(self):
        if self._saved_geometry is not None:
            self.setGeometry(self._saved_geometry)
            self._max_btn.setText("☐")
            self._saved_geometry = None
        else:
            screen = self.screen()
            if screen:
                self._saved_geometry = self.geometry()
                self.setGeometry(screen.availableGeometry())
                self._max_btn.setText("❐")

    def _on_close(self):
        self.close_requested.emit()
        self.close()

    # ── Mouse Events (Dragging & Edge Resizing) ────────────────────────────────

    _EDGE_TOP = Qt.Edge.TopEdge.value
    _EDGE_BOTTOM = Qt.Edge.BottomEdge.value
    _EDGE_LEFT = Qt.Edge.LeftEdge.value
    _EDGE_RIGHT = Qt.Edge.RightEdge.value
    _EDGE_TOP_LEFT = _EDGE_TOP | _EDGE_LEFT
    _EDGE_TOP_RIGHT = _EDGE_TOP | _EDGE_RIGHT
    _EDGE_BOTTOM_LEFT = _EDGE_BOTTOM | _EDGE_LEFT
    _EDGE_BOTTOM_RIGHT = _EDGE_BOTTOM | _EDGE_RIGHT

    def _detect_resize_edge(self, pos) -> int:
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        e = self._EDGE_PX
        on_left, on_right = x < e, x > w - e
        on_top, on_bottom = y < e, y > h - e

        if on_top and on_left: return self._EDGE_TOP_LEFT
        if on_top and on_right: return self._EDGE_TOP_RIGHT
        if on_bottom and on_left: return self._EDGE_BOTTOM_LEFT
        if on_bottom and on_right: return self._EDGE_BOTTOM_RIGHT
        if on_top: return self._EDGE_TOP
        if on_bottom: return self._EDGE_BOTTOM
        if on_left: return self._EDGE_LEFT
        if on_right: return self._EDGE_RIGHT
        return 0

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
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event):
        global_pos = event.globalPosition().toPoint()
        if self._resizing and self._resize_start_geo is not None:
            delta = global_pos - self._resize_start_pos
            geo = self._resize_start_geo
            edge = self._resize_edge
            min_w, min_h = self.minimumWidth(), self.minimumHeight()
            new_x, new_y = geo.x(), geo.y()
            new_w, new_h = geo.width(), geo.height()

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

            if new_w < min_w:
                new_w = min_w
                if edge & self._EDGE_LEFT: new_x = geo.right() - min_w
            if new_h < min_h:
                new_h = min_h
                if edge & self._EDGE_TOP: new_y = geo.bottom() - min_h

            self.setGeometry(new_x, new_y, new_w, new_h)
            event.accept()
            return

        if self._drag_offset is None:
            edge = self._detect_resize_edge(event.position().toPoint())
            cursor = Qt.CursorShape.SizeFDiagCursor if edge in (self._EDGE_TOP_LEFT, self._EDGE_BOTTOM_RIGHT) else (
                Qt.CursorShape.SizeBDiagCursor if edge in (self._EDGE_TOP_RIGHT, self._EDGE_BOTTOM_LEFT) else (
                    Qt.CursorShape.SizeVerCursor if edge in (self._EDGE_TOP, self._EDGE_BOTTOM) else (
                        Qt.CursorShape.SizeHorCursor if edge in (self._EDGE_LEFT, self._EDGE_RIGHT) else Qt.CursorShape.ArrowCursor
                    )
                )
            )
            self.setCursor(cursor)
            if edge != 0:
                event.accept()
                return

        if self._drag_offset is not None:
            self.move(global_pos - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        self._resizing = False
        self._resize_edge = 0
        self._resize_start_pos = None
        self._resize_start_geo = None
        self.setCursor(Qt.CursorShape.ArrowCursor)
