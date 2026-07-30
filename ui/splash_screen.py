"""
RaphaelSplashScreen — A custom-designed loading splash screen with a cyber HUD aesthetic.
"""

import os
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QGraphicsDropShadowEffect


class RaphaelSplashScreen(QWidget):
    """
    A custom frameless splash screen with a futuristic, cyber-themed HUD aesthetic.
    Displays loading milestones, updates progress, and transitions with a fade-out animation.
    """

    def __init__(self):
        super().__init__()
        # Set frameless window and make it stay on top, hide taskbar entry using Tool window type
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Outer dimensions
        self.resize(550, 320)
        self._center_on_screen()

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # Container widget for styling
        container = QWidget()
        container.setObjectName("SplashContainer")
        container.setStyleSheet("""
            QWidget#SplashContainer {
                background-color: #000a12;
                border: 2px solid #00d4ff;
                border-radius: 12px;
            }
        """)

        # Shadow effect for cyber glow
        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(20)
        glow.setColor(QColor("#00d4ff"))
        glow.setOffset(0, 0)
        container.setGraphicsEffect(glow)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(30, 35, 30, 35)
        container_layout.setSpacing(15)

        # Logo + Title horizontal layout
        header_layout = QHBoxLayout()
        header_layout.setSpacing(15)

        # Logo Icon
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(64, 64)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            self.logo_label.setPixmap(pixmap.scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))
        header_layout.addWidget(self.logo_label)

        # Title & Subtitle vertical layout
        title_v_layout = QVBoxLayout()
        title_v_layout.setSpacing(2)

        self.title_label = QLabel("R A P H A E L")
        self.title_label.setObjectName("Title")
        self.title_label.setStyleSheet("""
            color: #00d4ff;
            font-size: 28px;
            font-family: 'Consolas', monospace;
            font-weight: bold;
            background: transparent;
            border: none;
        """)
        title_v_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("A.I. COGNITIVE HUD INTERFACE")
        self.subtitle_label.setObjectName("Subtitle")
        self.subtitle_label.setStyleSheet("""
            color: #88aacc;
            font-size: 10px;
            font-family: 'Consolas', monospace;
            letter-spacing: 2px;
            background: transparent;
            border: none;
        """)
        title_v_layout.addWidget(self.subtitle_label)
        title_v_layout.addStretch()
        header_layout.addLayout(title_v_layout)
        header_layout.addStretch()
        container_layout.addLayout(header_layout)

        # Spacer
        container_layout.addStretch()

        # Status Label
        self.status_label = QLabel("Initializing systems...")
        self.status_label.setStyleSheet("""
            color: #888888;
            font-size: 11px;
            font-family: 'Consolas', monospace;
            background: transparent;
            border: none;
        """)
        container_layout.addWidget(self.status_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #1a2a35;
                border-radius: 3px;
                background: #010d14;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                                  stop:0 #00ff88, stop:1 #00d4ff);
                border-radius: 2px;
            }
        """)
        container_layout.addWidget(self.progress_bar)

        # Version label
        self.ver_label = QLabel("v1.0.0")
        self.ver_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.ver_label.setStyleSheet("""
            color: #445566;
            font-size: 9px;
            font-family: 'Consolas', monospace;
            background: transparent;
            border: none;
        """)
        container_layout.addWidget(self.ver_label)

        layout.addWidget(container)

        self.fade_animation = None

    def _center_on_screen(self):
        """Center the frameless window on the user's primary monitor screen."""
        from PyQt6.QtWidgets import QApplication
        primary_screen = QApplication.primaryScreen()
        if primary_screen:
            screen_geo = primary_screen.geometry()
            x = (screen_geo.width() - self.width()) // 2
            y = (screen_geo.height() - self.height()) // 2
            self.move(x, y)

    def set_progress(self, progress: int, status_message: str):
        """Update the progress bar value and status text label."""
        self.progress_bar.setValue(progress)
        self.status_label.setText(status_message.upper())

    def fade_out_and_close(self, on_finish_callback=None):
        """Animate the window opacity to 0 and close/destroy the splash window."""
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(400)
        self.fade_animation.setStartValue(1.0)
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        def on_fade_finished():
            self.close()
            if on_finish_callback:
                on_finish_callback()

        self.fade_animation.finished.connect(on_fade_finished)
        self.fade_animation.start()
