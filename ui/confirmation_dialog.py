"""
ConfirmationDialog — modal approval prompt for high-impact tool calls.

Shown when the permission policy returns ``confirm_required`` (e.g. shutdown,
process kill, recycle bin empty). The user gets three choices:
  - Allow once: run this single call now
  - Always allow: grant the tool for the rest of the session (never persisted)
  - Deny: refuse; the assistant is told the tool was not allowed
"""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from orchestrator.policy import ConfirmationRequest

RISK_COLORS = {
    "high": "#f85149",
    "medium": "#d29922",
    "confirm_required": "#f85149",
}


class ConfirmationDialog(QDialog):
    """Dark-themed permission prompt matching the HUD's visual language."""

    RESULT_DENY = 0
    RESULT_ALLOW_ONCE = 1
    RESULT_ALLOW_SESSION = 2

    def __init__(self, request: ConfirmationRequest, parent: QWidget | None = None):
        super().__init__(parent)
        self.request = request
        self.setWindowTitle("Raphael needs your confirmation")
        self.setModal(True)
        self.resize(520, 320)
        self.setMinimumSize(460, 280)

        self.setStyleSheet("""
            QDialog {
                background-color: #0d1117;
                color: #c9d1d9;
                font-family: 'Segoe UI', 'Inter', sans-serif;
            }
            QLabel#title {
                font-size: 17px;
                font-weight: bold;
                color: #00d4ff;
            }
            QLabel#tool {
                font-size: 14px;
                font-weight: bold;
                color: #ffffff;
            }
            QLabel#hint, QLabel#args {
                color: #8b949e;
                font-size: 12px;
            }
            QLabel#args {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 8px;
                color: #c9d1d9;
            }
            QPushButton {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 8px 14px;
                color: #c9d1d9;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #30363d;
            }
            QPushButton#allow {
                background-color: #238636;
                border: 1px solid #2ea043;
                color: #ffffff;
            }
            QPushButton#allow:hover {
                background-color: #2ea043;
            }
            QPushButton#deny {
                background-color: #21262d;
                border: 1px solid #f85149;
                color: #f85149;
            }
            QPushButton#deny:hover {
                background-color: #3d1d1f;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("Raphael needs your confirmation")
        title.setObjectName("title")
        layout.addWidget(title)

        risk = request.risk if request.risk in RISK_COLORS else "high"
        tool_label = QLabel(
            f'<span style="color:{RISK_COLORS[risk]}">&#9888;</span> '
            f"<span id='tool'>{request.tool_name}</span>"
        )
        tool_label.setObjectName("tool")
        layout.addWidget(tool_label)

        hint = QLabel(
            f"This action can affect your system: {request.reason}"
            "\nChoose what Raphael is allowed to do."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # Scrollable, truncated args preview
        args_text = self._format_args(request.args)
        args_label = QLabel(args_text)
        args_label.setObjectName("args")
        args_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        args_label.setWordWrap(True)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setWidget(args_label)
        layout.addWidget(scroll, stretch=1)

        buttons = QHBoxLayout()
        deny_btn = QPushButton("Deny")
        deny_btn.setObjectName("deny")
        once_btn = QPushButton("Allow once")
        session_btn = QPushButton("Always allow (this session)")
        session_btn.setObjectName("allow")
        once_btn.setObjectName("allow")
        buttons.addWidget(deny_btn)
        buttons.addStretch(1)
        buttons.addWidget(once_btn)
        buttons.addWidget(session_btn)
        layout.addLayout(buttons)

        deny_btn.clicked.connect(lambda: self.done(self.RESULT_DENY))
        once_btn.clicked.connect(lambda: self.done(self.RESULT_ALLOW_ONCE))
        session_btn.clicked.connect(lambda: self.done(self.RESULT_ALLOW_SESSION))

    @staticmethod
    def _format_args(args: dict) -> str:
        """Compact JSON preview of the tool arguments, truncated to ~1.5k chars."""
        try:
            text = json.dumps(args, ensure_ascii=False, indent=2, default=str)
        except Exception:
            text = str(args)
        if len(text) > 1500:
            text = text[:1500] + "\n… [truncated]"
        return text
