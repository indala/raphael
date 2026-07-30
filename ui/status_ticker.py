from PyQt6.QtCore import Qt, QPropertyAnimation, QPoint, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtWidgets import QWidget, QLabel

class StatusTicker(QWidget):
    """
    A single-line status ticker featuring a vertical slide animation
    (Vertical Carousel) for displaying active agent steps.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setStyleSheet("""
            StatusTicker {
                background-color: #010d14;
                border: 1px solid #1a2a35;
                border-radius: 4px;
            }
        """)

        # Two labels for vertical carousel sliding transitions
        self.label_active = QLabel(self)
        self.label_next = QLabel(self)

        for lbl in (self.label_active, self.label_next):
            lbl.setStyleSheet("""
                color: #00d4ff;
                font-family: 'Consolas', monospace;
                font-size: 11px;
                background: transparent;
                border: none;
            """)
            lbl.setGeometry(8, 0, 500, 28)
            lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.label_next.move(8, 28)  # Hidden below viewport initially

        # Setup parallel animation group
        self.anim_group = QParallelAnimationGroup(self)

        self.anim_active = QPropertyAnimation(self.label_active, b"pos", self)
        self.anim_active.setDuration(250)
        self.anim_active.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_next = QPropertyAnimation(self.label_next, b"pos", self)
        self.anim_next.setDuration(250)
        self.anim_next.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.anim_group.addAnimation(self.anim_active)
        self.anim_group.addAnimation(self.anim_next)
        self.anim_group.finished.connect(self._on_animation_finished)

        self._current_text = ""

    def show_status(self, text: str):
        """Update active status message with a vertical slide-up transition."""
        if not text or text == self._current_text:
            return

        self._current_text = text
        self.setVisible(True)

        if self.anim_group.state() == QParallelAnimationGroup.State.Running:
            self.anim_group.stop()
            self._on_animation_finished()

        self.label_next.setText(text)

        self.anim_active.setStartValue(QPoint(8, 0))
        self.anim_active.setEndValue(QPoint(8, -28))

        self.anim_next.setStartValue(QPoint(8, 28))
        self.anim_next.setEndValue(QPoint(8, 0))

        self.anim_group.start()

    def _on_animation_finished(self):
        self.label_active.setText(self._current_text)
        self.label_active.move(8, 0)
        self.label_next.move(8, 28)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Scale active labels dynamically with container width
        w = max(100, self.width() - 16)
        self.label_active.setFixedWidth(w)
        self.label_next.setFixedWidth(w)

    def clear_status(self):
        """Clear message contents and hide the status ticker widget."""
        self._current_text = ""
        self.label_active.clear()
        self.label_next.clear()
        self.setVisible(False)
