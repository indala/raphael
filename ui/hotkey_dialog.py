"""
HotkeyDialog — Visual keyboard shortcuts cheatsheet modal.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QHeaderView,
)


class HotkeyDialog(QDialog):
    """Modern dark-themed keyboard shortcuts reference dialog."""

    SHORTCUTS = [
        ("Global", "Win + Shift + R", "Toggle Raphael Main HUD Window"),
        ("Global", "Alt + Shift + C", "Mute / Unmute Microphone"),
        ("Global", "Alt + Shift + B", "Toggle Voice Sleep / Active Mode"),
        ("Global", "Alt + Shift + M", "Open Spotify Music Player Window"),
        ("HUD Window", "Escape", "Minimize Window / Close Popups"),
        ("HUD Window", "?", "Open Keyboard Shortcuts Cheatsheet"),
        ("Minion Icon", "Double-Click", "Open Compact Quick Chat Input"),
        ("Minion Icon", "Right-Click", "Show Desktop Context Menu & Quick Settings"),
        ("Minion Icon", "Drag & Drop", "Reposition Minion Icon on Screen"),
        ("Music Player", "Scroll Wheel", "Adjust Music Volume smoothly (+/- 5%)"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Raphael — Keyboard Shortcuts & Gestures")
        self.resize(580, 420)
        self.setMinimumSize(480, 360)

        self.setStyleSheet("""
            QDialog {
                background-color: #0d1117;
                color: #c9d1d9;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
            QLabel#title {
                font-size: 18px;
                font-weight: bold;
                color: #00d4ff;
            }
            QTableWidget {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 8px;
                gridline-color: #21262d;
                color: #c9d1d9;
                font-size: 12px;
            }
            QTableWidget::item {
                padding: 6px 10px;
            }
            QHeaderView::section {
                background-color: #21262d;
                color: #8b949e;
                font-weight: bold;
                font-size: 11px;
                padding: 6px;
                border: none;
                border-bottom: 1px solid #30363d;
            }
            QPushButton#close_btn {
                background-color: #238636;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton#close_btn:hover {
                background-color: #2ea043;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_lbl = QLabel("⌨️ Keyboard Shortcuts & Gestures")
        title_lbl.setObjectName("title")
        header.addWidget(title_lbl)
        header.addStretch()
        layout.addLayout(header)

        table = QTableWidget(len(self.SHORTCUTS), 3)
        table.setHorizontalHeaderLabels(["Scope", "Shortcut / Gesture", "Action / Function"])
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 90)
        table.setColumnWidth(1, 160)

        for row, (scope, key, desc) in enumerate(self.SHORTCUTS):
            item_scope = QTableWidgetItem(scope)
            item_scope.setForeground(Qt.GlobalColor.cyan if scope == "Global" else Qt.GlobalColor.lightGray)
            table.setItem(row, 0, item_scope)

            item_key = QTableWidgetItem(key)
            item_key.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(row, 1, item_key)

            item_desc = QTableWidgetItem(desc)
            table.setItem(row, 2, item_desc)

        layout.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Got it!")
        close_btn.setObjectName("close_btn")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
