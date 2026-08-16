"""
PlaygroundWindow — Standalone AI Interactive Studio Canvas for Raphael.

Provides a rich canvas workspace where Raphael can dynamically render:
- Interactive Vector Charts (SVG: Line, Bar, Donut, Area)
- Architecture & Sequence Diagrams (Formatted diagrams with styled node boxes)
- KPI & Metrics Dashboard cards
- Live Styled Data Tables and HTML5 / SVG widgets
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

# ── Modern Glassmorphism & SVG Playground HTML Template ────────────────────────

_PLAYGROUND_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            background: #080b11;
            color: #e2e8f0;
            font-family: 'Segoe UI', 'Inter', system-ui, -apple-system, sans-serif;
            margin: 0;
            padding: 20px;
            line-height: 1.5;
        }}
        h1, h2, h3, h4 {{
            color: #f8fafc;
            margin-top: 0;
            font-weight: 600;
        }}
        .card {{
            background: linear-gradient(145deg, #131b2e 0%, #0f172a 100%);
            border: 1px solid rgba(56, 189, 248, 0.25);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }}
        .badge {{
            display: inline-block;
            padding: 3px 10px;
            background: rgba(14, 165, 233, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.4);
            border-radius: 14px;
            font-size: 11px;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .badge-success {{
            background: rgba(34, 197, 94, 0.15);
            color: #4ade80;
            border-color: rgba(74, 222, 128, 0.4);
        }}
        .grid-cards {{
            display: flex;
            gap: 16px;
            margin-bottom: 16px;
        }}
        .metric-card {{
            flex: 1;
            background: #0b1329;
            border: 1px solid #1e293b;
            border-radius: 10px;
            padding: 16px;
            text-align: center;
        }}
        .metric-val {{
            font-size: 28px;
            font-weight: 700;
            color: #38bdf8;
            margin: 4px 0;
        }}
        .metric-label {{
            font-size: 12px;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            font-size: 13px;
        }}
        th {{
            background: #1e293b;
            color: #38bdf8;
            text-align: left;
            padding: 10px 12px;
            border-bottom: 2px solid #334155;
        }}
        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #1e293b;
            color: #cbd5e1;
        }}
        tr:nth-child(even) {{
            background: rgba(30, 41, 59, 0.3);
        }}
        code, pre {{
            font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
            background: #090d16;
            color: #7dd3fc;
            border-radius: 8px;
            padding: 12px 16px;
            border: 1px solid #1e293b;
            font-size: 12px;
        }}
        svg text {{
            font-family: 'Segoe UI', 'Inter', sans-serif;
            fill: #94a3b8;
            font-size: 11px;
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
    _MIN_W, _MIN_H = 680, 520

    def __init__(self, title: str = "Raphael Studio Canvas 🎨", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumSize(self._MIN_W, self._MIN_H)
        self.resize(850, 600)

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
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Sleek Custom Title Bar ──────────────────────────────────────────
        title_bar = QFrame()
        title_bar.setFixedHeight(44)
        title_bar.setStyleSheet(
            "QFrame { background: #0b1329; border-bottom: 1px solid #1e293b; }"
        )
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(14, 0, 10, 0)
        tb_layout.setSpacing(10)

        self._title_label = QLabel("✨ Raphael Playground Studio")
        self._title_label.setStyleSheet(
            "color: #38bdf8; font-weight: bold; font-size: 13px; font-family: 'Segoe UI', sans-serif;"
        )
        tb_layout.addWidget(self._title_label)
        tb_layout.addStretch()

        # Pin / Always on Top Button
        self._pin_btn = QPushButton("📌")
        self._pin_btn.setFixedSize(28, 26)
        self._pin_btn.setToolTip("Always on Top")
        self._pin_btn.setStyleSheet(
            "QPushButton { color: #38bdf8; background: transparent; border: 1px solid #1e293b; border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background: #1e293b; }"
        )
        self._pin_btn.clicked.connect(self._toggle_pin)
        tb_layout.addWidget(self._pin_btn)

        # Export HTML Button
        export_btn = QPushButton("💾 Export")
        export_btn.setFixedHeight(26)
        export_btn.setToolTip("Export Canvas to HTML")
        export_btn.setStyleSheet(
            "QPushButton { color: #cbd5e1; background: #1e293b; border: 1px solid #334155; border-radius: 4px; padding: 0 10px; font-size: 11px; font-weight: bold; }"
            "QPushButton:hover { background: #334155; color: #38bdf8; }"
        )
        export_btn.clicked.connect(self._export_html)
        tb_layout.addWidget(export_btn)

        # Clear Canvas Button
        clear_btn = QPushButton("🧹 Clear")
        clear_btn.setFixedHeight(26)
        clear_btn.setToolTip("Reset Canvas")
        clear_btn.setStyleSheet(
            "QPushButton { color: #cbd5e1; background: #1e293b; border: 1px solid #334155; border-radius: 4px; padding: 0 10px; font-size: 11px; font-weight: bold; }"
            "QPushButton:hover { background: #334155; color: #f43f5e; }"
        )
        clear_btn.clicked.connect(self.clear_playground)
        tb_layout.addWidget(clear_btn)

        # Maximize Button
        self._max_btn = QPushButton("🗖")
        self._max_btn.setFixedSize(28, 26)
        self._max_btn.setStyleSheet(
            "QPushButton { color: #94a3b8; background: transparent; border: none; font-size: 13px; }"
            "QPushButton:hover { color: #f8fafc; background: #1e293b; border-radius: 4px; }"
        )
        self._max_btn.clicked.connect(self._toggle_maximize)
        tb_layout.addWidget(self._max_btn)

        # Close Button
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(28, 26)
        close_btn.setStyleSheet(
            "QPushButton { color: #94a3b8; background: transparent; border: none; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { color: #f43f5e; background: #1e293b; border-radius: 4px; }"
        )
        close_btn.clicked.connect(self._on_close)
        tb_layout.addWidget(close_btn)

        layout.addWidget(title_bar)

        # Main HTML Canvas Browser
        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            "QTextBrowser { background: #080b11; color: #cbd5e1; border: none; padding: 16px; font-size: 13px; }"
            "QScrollBar:vertical { background: #080b11; width: 8px; }"
            "QScrollBar::handle:vertical { background: #1e293b; border-radius: 4px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        layout.addWidget(self._browser)

        # Keyboard shortcut
        QShortcut(QKeySequence("Esc"), self, self.close)
        self._render_welcome_canvas()

    def _render_welcome_canvas(self):
        """Initial welcome state of the Playground."""
        welcome_html = """
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <h2 style="margin: 0; color: #38bdf8;">✨ Raphael Interactive Playground Studio</h2>
                <span class="badge badge-success">ACTIVE & READY</span>
            </div>
            <p style="color: #94a3b8; font-size: 14px;">Welcome to your dynamic visual workspace. Raphael renders rich interactive content here in real time:</p>
            
            <div style="display: flex; gap: 12px; margin: 18px 0;">
                <div class="metric-card">
                    <div class="metric-val" style="color: #38bdf8;">📊</div>
                    <div class="metric-label">Vector Charts</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" style="color: #a855f7;">📐</div>
                    <div class="metric-label">System Diagrams</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" style="color: #22c55e;">📈</div>
                    <div class="metric-label">Metrics & KPIs</div>
                </div>
                <div class="metric-card">
                    <div class="metric-val" style="color: #f59e0b;">🎨</div>
                    <div class="metric-label">Custom HTML5 / SVG</div>
                </div>
            </div>

            <p style="color: #64748b; font-size: 13px; font-style: italic;">
                Tip: Speak or type commands like <b>"Draw a chart of top programming languages"</b> or <b>"Show system architecture"</b>.
            </p>
        </div>
        """
        self.render_html(welcome_html)

    # ── Public API for Raphael AI ───────────────────────────────────────────────

    def render_html(self, html_code: str, element_id: str = ""):
        """Render raw HTML or update content inside the Playground."""
        full_page = _PLAYGROUND_HTML_TEMPLATE.format(content=html_code)
        self._browser.setHtml(full_page)

    def render_chart(
        self,
        chart_type: str,
        labels: list[str],
        datasets: list[dict[str, Any]],
        title: str = "Visual Data Chart",
    ):
        """Render high-resolution SVG vector chart (Line, Bar, Donut, Area)."""
        values = datasets[0].get("data", []) if datasets else []
        if not values or not labels:
            return

        c_type = chart_type.lower().strip()
        num_vals = [float(v) if isinstance(v, (int, float)) else 1.0 for v in values]
        max_val = max(num_vals) if num_vals and max(num_vals) > 0 else 100.0

        colors = ["#38bdf8", "#818cf8", "#c084fc", "#f472b6", "#34d399", "#fbbf24"]
        svg_content = ""

        if c_type in ("line", "area"):
            # SVG Smooth Line Chart
            svg_w, svg_h = 580, 220
            pad_l, pad_r, pad_t, pad_b = 40, 30, 20, 40
            chart_w = svg_w - pad_l - pad_r
            chart_h = svg_h - pad_t - pad_b
            step_x = chart_w / max(1, len(num_vals) - 1)

            pts = []
            for i, val in enumerate(num_vals):
                x = pad_l + i * step_x
                y = pad_t + chart_h - (val / max_val * chart_h)
                pts.append((x, y))

            polyline_pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
            area_pts = f"{pad_l},{pad_t + chart_h} " + polyline_pts + f" {pts[-1][0]:.1f},{pad_t + chart_h}"

            # Axis grid lines & labels
            grid_svg = ""
            for i in range(4):
                y_lvl = pad_t + i * (chart_h / 3)
                v_lvl = max_val - i * (max_val / 3)
                grid_svg += f'<line x1="{pad_l}" y1="{y_lvl:.1f}" x2="{svg_w - pad_r}" y2="{y_lvl:.1f}" stroke="#1e293b" stroke-dasharray="3,3"/>'
                grid_svg += f'<text x="{pad_l - 8}" y="{y_lvl + 4:.1f}" text-anchor="end" fill="#64748b" font-size="10">{int(v_lvl)}</text>'

            dots_svg = ""
            for (x, y), lbl, v in zip(pts, labels, num_vals):
                dots_svg += f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#38bdf8" stroke="#080b11" stroke-width="2"/>'
                dots_svg += f'<text x="{x:.1f}" y="{pad_t + chart_h + 20}" text-anchor="middle" fill="#94a3b8" font-size="10">{html.escape(str(lbl)[:10])}</text>'

            svg_content = f"""
            <svg width="100%" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">
                <defs>
                    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.4"/>
                        <stop offset="100%" stop-color="#38bdf8" stop-opacity="0.0"/>
                    </linearGradient>
                </defs>
                {grid_svg}
                <polygon points="{area_pts}" fill="url(#areaGrad)"/>
                <polyline points="{polyline_pts}" fill="none" stroke="#38bdf8" stroke-width="3" stroke-linecap="round"/>
                {dots_svg}
            </svg>
            """

        else:
            # SVG Multi-Bar Chart
            bar_rows = ""
            for idx, (lbl, val) in enumerate(zip(labels, num_vals)):
                col = colors[idx % len(colors)]
                pct = (val / max_val) * 100 if max_val > 0 else 0
                bar_rows += f"""
                <div style="margin-bottom: 12px;">
                    <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 5px;">
                        <span style="color: #cbd5e1; font-weight: 500;">{html.escape(str(lbl))}</span>
                        <span style="color: {col}; font-weight: 700;">{val:g}</span>
                    </div>
                    <div style="background: #090d16; height: 14px; border-radius: 7px; overflow: hidden; border: 1px solid #1e293b;">
                        <div style="background: linear-gradient(90deg, {col} 0%, #38bdf8 100%); height: 100%; width: {max(4, pct):.1f}%; border-radius: 6px;"></div>
                    </div>
                </div>
                """
            svg_content = bar_rows

        card_html = f"""
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <h3 style="margin: 0; color: #f8fafc;">📊 {html.escape(title)}</h3>
                <span class="badge">{html.escape(c_type.upper())} VIEW</span>
            </div>
            {svg_content}
        </div>
        """
        self.render_html(card_html)

    def render_diagram(self, mermaid_code: str, title: str = "System Flow & Architecture"):
        """Render a formatted diagram with dark-mode code formatting."""
        card_html = f"""
        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                <h3 style="margin: 0; color: #f8fafc;">📐 {html.escape(title)}</h3>
                <span class="badge">MERMAID DIAGRAM</span>
            </div>
            <pre style="margin: 0;"><code>{html.escape(mermaid_code)}</code></pre>
        </div>
        """
        self.render_html(card_html)

    def clear_playground(self):
        """Reset the Playground canvas to welcome state."""
        self._render_welcome_canvas()

    def _export_html(self):
        """Export current playground canvas to HTML file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Playground HTML", "raphael_playground.html", "HTML Files (*.html)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._browser.toHtml())
                QMessageBox.information(self, "Playground Export", f"Successfully exported playground to:\n{path}")
            except Exception as e:
                logger.warning("Failed to export playground: %s", e)

    # ── Window Controls & Resizing ─────────────────────────────────────────────

    def _toggle_pin(self):
        self._pinned = not self._pinned
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self._pinned)
        self._pin_btn.setText("📌" if self._pinned else "📍")
        self.show()

    def _toggle_maximize(self):
        if self._saved_geometry:
            self.setGeometry(self._saved_geometry)
            self._max_btn.setText("🗖")
            self._saved_geometry = None
        else:
            screen = self.screen()
            if screen:
                self._saved_geometry = self.geometry()
                self.setGeometry(screen.availableGeometry())
                self._max_btn.setText("🗗")

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
