"""
System Tray Icon — Background system tray integration for Raphael.

Provides a notification area icon with a dark-teal context menu for quick controls:
Show/Hide HUD, Mute Mic, Toggle TTS, Take Screenshot, Settings, and Exit.
"""

import logging
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QImage, QPainter
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu

logger = logging.getLogger(__name__)


from PyQt6.QtGui import QPixmap

def _create_default_tray_icon() -> QIcon:
    """Generate a clean 32x32 dark-teal orb icon for the system tray."""
    img = QImage(32, 32, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    painter = QPainter()
    if painter.begin(img):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#0f172a"))
        painter.setPen(QColor("#1e293b"))
        painter.drawEllipse(2, 2, 28, 28)

        painter.setBrush(QColor("#14b8a6"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(7, 7, 18, 18)

        painter.setBrush(QColor("#5eead4"))
        painter.drawEllipse(12, 12, 8, 8)
        painter.end()

    return QIcon(QPixmap.fromImage(img))


class RaphaelTrayIcon(QSystemTrayIcon):
    """System tray icon for background Raphael management."""

    # Signals for main UI interaction
    toggle_hud_requested = pyqtSignal()
    toggle_mute_requested = pyqtSignal()
    toggle_tts_requested = pyqtSignal()
    take_screenshot_requested = pyqtSignal()
    open_music_requested = pyqtSignal()
    open_settings_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIcon(_create_default_tray_icon())
        self.setToolTip("Raphael — Voice-first AI Desktop Assistant")

        self._menu = QMenu()
        self._setup_menu()
        self.setContextMenu(self._menu)

        # Handle tray icon click / double click
        self.activated.connect(self._on_activated)

    def _setup_menu(self):
        """Construct context menu actions with custom styling."""
        self._menu.setStyleSheet("""
            QMenu {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 4px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 16px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1e293b;
                color: #14b8a6;
            }
            QMenu::separator {
                height: 1px;
                background-color: #334155;
                margin: 4px 0;
            }
        """)

        # Actions
        self._act_hud = QAction("👁️ Show / Hide HUD", self)
        self._act_hud.triggered.connect(self.toggle_hud_requested.emit)
        self._menu.addAction(self._act_hud)

        self._act_mute = QAction("🎤 Toggle Mute", self)
        self._act_mute.triggered.connect(self.toggle_mute_requested.emit)
        self._menu.addAction(self._act_mute)

        self._act_tts = QAction("🔊 Toggle TTS", self)
        self._act_tts.triggered.connect(self.toggle_tts_requested.emit)
        self._menu.addAction(self._act_tts)

        self._act_screenshot = QAction("📸 Take Screenshot", self)
        self._act_screenshot.triggered.connect(self.take_screenshot_requested.emit)
        self._menu.addAction(self._act_screenshot)

        self._menu.addSeparator()

        self._act_music = QAction("🎵 Music Player", self)
        self._act_music.triggered.connect(self.open_music_requested.emit)
        self._menu.addAction(self._act_music)

        self._menu.addSeparator()

        self._act_settings = QAction("⚙️ Settings", self)
        self._act_settings.triggered.connect(self.open_settings_requested.emit)
        self._menu.addAction(self._act_settings)

        self._menu.addSeparator()

        self._act_exit = QAction("❌ Exit Raphael", self)
        self._act_exit.triggered.connect(self.exit_requested.emit)
        self._menu.addAction(self._act_exit)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        """Handle mouse click / double click on tray icon."""
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_hud_requested.emit()
