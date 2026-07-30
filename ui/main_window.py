"""
Three-panel HUD layout with thread-safe metric updates via signals.
"""

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QProgressBar,
                             QSplitter, QVBoxLayout, QWidget, QLineEdit, QPushButton)

from .hud_canvas import HudCanvas
from .log_widget import LogWidget
from .system_metrics import SystemMonitor
from .file_drop_zone import FileDropZone
from .settings_dialog import SettingsDialog


class TaskBadge(QWidget):
    """Visual capsule badge for a background task."""

    def __init__(self, task_id: str, label: str, status: str, tool_name: str = "", current_action: str = "", parent=None):
        super().__init__(parent)
        self.task_id = task_id
        self.label_text = label
        self.status_text = status
        self.tool_name = tool_name
        self.current_action = current_action

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        display_name = label
        if tool_name:
            clean_tool = tool_name.replace("_", " ").upper()
            display_name = f"{clean_tool}: {label}"

        self.lbl_name = QLabel(display_name.upper())
        self.lbl_name.setStyleSheet("""
            color: #cccccc;
            font-size: 11px;
            font-family: Consolas;
            font-weight: bold;
            border: none;
            background: transparent;
        """)
        header_layout.addWidget(self.lbl_name)

        header_layout.addStretch()

        self.lbl_status = QLabel()
        self.lbl_status.setStyleSheet("""
            font-family: Consolas;
            font-size: 10px;
            font-weight: bold;
            border: none;
            background: transparent;
        """)
        header_layout.addWidget(self.lbl_status)
        layout.addLayout(header_layout)

        self.lbl_action = QLabel()
        self.lbl_action.setStyleSheet("""
            color: #88aacc;
            font-size: 9px;
            font-family: Consolas;
            border: none;
            background: transparent;
        """)
        layout.addWidget(self.lbl_action)

        self.update_status(status, current_action)

    def update_status(self, status: str, current_action: str = ""):
        self.status_text = status
        self.current_action = current_action

        if current_action:
            self.lbl_action.setText(current_action)
            self.lbl_action.show()
        else:
            self.lbl_action.hide()

        if status == "pending":
            self.lbl_status.setText("● PENDING")
            self.lbl_status.setStyleSheet("color: #888888; font-family: Consolas; font-size: 10px; border: none; background: transparent;")
            self.setStyleSheet("background-color: #0b0f14; border: 1px solid #1a2a35; border-radius: 6px;")
        elif status == "running":
            self.lbl_status.setText("⟳ RUNNING")
            self.lbl_status.setStyleSheet("color: #00d4ff; font-family: Consolas; font-size: 10px; border: none; background: transparent;")
            self.setStyleSheet("background-color: #011424; border: 1px solid #00d4ff; border-radius: 6px;")
        elif status == "done":
            self.lbl_status.setText("✓ DONE")
            self.lbl_status.setStyleSheet("color: #00ff88; font-family: Consolas; font-size: 10px; border: none; background: transparent;")
            self.setStyleSheet("background-color: #001a11; border: 1px solid #00ff88; border-radius: 6px;")
            self.lbl_action.hide()
        elif status == "failed":
            self.lbl_status.setText("✗ FAILED")
            self.lbl_status.setStyleSheet("color: #ff3366; font-family: Consolas; font-size: 10px; border: none; background: transparent;")
            self.setStyleSheet("background-color: #1a050a; border: 1px solid #ff3366; border-radius: 6px;")
            self.lbl_action.hide()
        elif status == "canceled":
            self.lbl_status.setText("⊘ CANCELED")
            self.lbl_status.setStyleSheet("color: #888888; font-family: Consolas; font-size: 10px; border: none; background: transparent;")
            self.setStyleSheet("background-color: #0a0a0a; border: 1px solid #222222; border-radius: 6px;")
            self.lbl_action.hide()


class MetricBar(QWidget):
    """Thin color-coded metric bar with label."""

    def __init__(self, label: str, color: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self._label = label
        self._color = color
        self._value = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        self.name_label = QLabel(label)
        self.name_label.setStyleSheet("color: #888888; font-size: 11px; font-family: Consolas;")
        self.name_label.setFixedWidth(50)
        layout.addWidget(self.name_label)

        self.bar = QProgressBar(self)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFixedHeight(8)
        self.bar.setTextVisible(False)
        self.bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #0a1a2a;
                border: 1px solid #1a2a35;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self.bar)

        self.val_label = QLabel("0%")
        self.val_label.setStyleSheet("color: #cccccc; font-size: 11px; font-family: Consolas;")
        self.val_label.setFixedWidth(40)
        self.val_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.val_label)

    def set_value(self, value: float):
        self._value = value
        self.bar.setValue(int(value))
        self.val_label.setText(f"{int(value)}%")


class MainWindow(QMainWindow):
    """Three-panel HUD window with thread-safe metric updates."""

    # Signal for thread-safe metric updates from SystemMonitor
    metrics_signal = pyqtSignal(float, float, float, float, float)
    chat_submitted = pyqtSignal(str)
    closing = pyqtSignal()                     # emitted before Qt event loop shuts down
    toggle_sleep_triggered = pyqtSignal()
    toggle_mute_triggered = pyqtSignal()
    toggle_tts_triggered = pyqtSignal()
    interrupt_triggered = pyqtSignal()         # emitted on ESC key
    settings_triggered = pyqtSignal()           # emitted when settings requested
    reload_triggered = pyqtSignal()             # emitted when reload requested

    def __init__(self):
        super().__init__()
        self._is_quitting = False
        self._audio_input_available = True
        self._audio_output_available = True
        self.placeholder_tasks: QLabel | None = None
        self.setWindowTitle("Raphael")
        self.setStyleSheet("background-color: #00060a;")

        # ── Central widget ──
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Left panel: Metrics ──
        left_panel = QWidget()
        left_panel.setFixedWidth(220)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        sys_label = QLabel("SYSTEM")
        sys_label.setStyleSheet("""
            color: #00d4ff; font-size: 10px; font-family: Consolas; font-weight: bold;
            letter-spacing: 2px;
        """)
        left_layout.addWidget(sys_label)

        self.cpu_bar = MetricBar("CPU", "#00d4ff")
        self.mem_bar = MetricBar("MEM", "#00ff88")
        self.net_bar = MetricBar("NET", "#ffd700")
        self.gpu_bar = MetricBar("GPU", "#ff6b00")
        self.temp_bar = MetricBar("TEMP", "#ff3366")

        left_layout.addWidget(self.cpu_bar)
        left_layout.addWidget(self.mem_bar)
        left_layout.addWidget(self.net_bar)
        left_layout.addWidget(self.gpu_bar)
        left_layout.addWidget(self.temp_bar)

        # ── Background Processes section ──
        left_layout.addSpacing(15)
        self.tasks_header = QLabel("BACKGROUND PROCESSES")
        self.tasks_header.setStyleSheet("""
            color: #00d4ff; font-size: 10px; font-family: Consolas; font-weight: bold;
            letter-spacing: 2px;
        """)
        left_layout.addWidget(self.tasks_header)

        self.tasks_container = QWidget()
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setContentsMargins(0, 4, 0, 4)
        self.tasks_layout.setSpacing(6)

        self.placeholder_tasks = QLabel("No active tasks")
        self.placeholder_tasks.setStyleSheet("""
            color: #445566; font-size: 11px; font-family: Consolas;
        """)
        self.tasks_layout.addWidget(self.placeholder_tasks)
        left_layout.addWidget(self.tasks_container)

        # ── Music Panel (collapsible, shows now-playing + playlists) ──
        from .music_panel import MusicPanel
        self.music_panel = MusicPanel()
        left_layout.addWidget(self.music_panel)

        left_layout.addStretch()

        self._task_badges = {}

        # Loader spinner animation timer
        self._spinner_timer = QTimer(self)
        self._spinner_timer.timeout.connect(self._animate_running_badges)
        self._spinner_timer.start(250)

        # ── Controls row (Mute Mic & Mute Speaker) ──
        controls_widget = QWidget()
        controls_layout = QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(4, 0, 4, 0)
        controls_layout.setSpacing(10)

        # Mic Toggle Button
        self.mic_btn = QPushButton("🎙️")
        self.mic_btn.setFixedSize(32, 32)
        self.mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mic_btn.setToolTip("Microphone")
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #010d14;
                color: #00ff88;
                border: 1px solid #009955;
                border-radius: 4px;
                font-family: 'Segoe UI Emoji', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #001f14;
                border: 1px solid #00ff88;
            }
        """)
        self.mic_btn.clicked.connect(self.toggle_mute_triggered.emit)
        controls_layout.addWidget(self.mic_btn)

        # Speaker Toggle Button
        self.spk_btn = QPushButton("🔊")
        self.spk_btn.setFixedSize(32, 32)
        self.spk_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.spk_btn.setToolTip("Text-To-Speech Output")
        self.spk_btn.setStyleSheet("""
            QPushButton {
                background-color: #010d14;
                color: #00d4ff;
                border: 1px solid #007a99;
                border-radius: 4px;
                font-family: 'Segoe UI Emoji', sans-serif;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #001f2e;
                border: 1px solid #00d4ff;
            }
        """)
        self.spk_btn.clicked.connect(self.toggle_tts_triggered.emit)
        controls_layout.addWidget(self.spk_btn)

        # Settings Button
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setFixedSize(32, 32)
        self.settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_btn.setToolTip("Settings")
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #010d14;
                color: #888888;
                border: 1px solid #1a2a35;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #001a24;
                color: #00d4ff;
                border: 1px solid #00d4ff;
            }
        """)
        self.settings_btn.clicked.connect(self._open_settings)
        controls_layout.addWidget(self.settings_btn)

        # Reload Button
        self.reload_btn = QPushButton("⟳")
        self.reload_btn.setFixedSize(32, 32)
        self.reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_btn.setToolTip("Reload Configuration & Connections")
        self.reload_btn.setStyleSheet("""
            QPushButton {
                background-color: #010d14;
                color: #888888;
                border: 1px solid #1a2a35;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #001a24;
                color: #00ff88;
                border: 1px solid #00ff88;
            }
        """)
        self.reload_btn.clicked.connect(self.reload_triggered.emit)
        controls_layout.addWidget(self.reload_btn)

        left_layout.addWidget(controls_widget)

        # ── Volume indicator labels ──
        vol_widget = QWidget()
        vol_layout = QHBoxLayout(vol_widget)
        vol_layout.setContentsMargins(4, 0, 4, 0)
        vol_layout.setSpacing(10)

        self.mic_vol_label = QLabel("Mic: --")
        self.mic_vol_label.setStyleSheet("color: #888888; font-size: 10px; font-family: Consolas;")
        self.mic_vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vol_layout.addWidget(self.mic_vol_label)

        self.spk_vol_label = QLabel("Spk: --")
        self.spk_vol_label.setStyleSheet("color: #888888; font-size: 10px; font-family: Consolas;")
        self.spk_vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vol_layout.addWidget(self.spk_vol_label)

        left_layout.addWidget(vol_widget)

        main_layout.addWidget(left_panel)

        # ── Center panel: HUD ──
        self.hud = HudCanvas()

        # ── Right panel: Log (resizable via QSplitter) ──
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        act_label = QLabel("ACTIVITY")
        act_label.setStyleSheet("""
            color: #00d4ff; font-size: 10px; font-family: Consolas; font-weight: bold;
            letter-spacing: 2px;
        """)
        right_layout.addWidget(act_label)

        self.log_widget = LogWidget()
        self.log_widget.command_clicked.connect(self._on_command_clicked)
        right_layout.addWidget(self.log_widget)

        from .status_ticker import StatusTicker
        self.status_ticker = StatusTicker(self)
        self.status_ticker.setVisible(False)
        right_layout.addWidget(self.status_ticker)

        # ── Chat/Command Input Row ──
        input_widget = QWidget()
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(6)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a message to chat...")
        self.chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #00060a;
                color: #cccccc;
                border: 1px solid #1a2a35;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #00d4ff;
            }
        """)
        self.chat_input.returnPressed.connect(self._on_send)
        input_layout.addWidget(self.chat_input)

        self.send_btn = QPushButton("▸")
        self.send_btn.setFixedSize(30, 26)
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #010d14;
                color: #00d4ff;
                border: 1px solid #007a99;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #001f2e;
                border: 1px solid #00d4ff;
            }
        """)
        self.send_btn.clicked.connect(self._on_send)
        input_layout.addWidget(self.send_btn)

        # ── Stop Button (hidden until processing) ──
        self.stop_btn = QPushButton("■")
        self.stop_btn.setFixedSize(30, 26)
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setToolTip("Stop (ESC)")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #330000;
                color: #ff4444;
                border: 1px solid #661111;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #550000;
                border: 1px solid #ff4444;
            }
        """)
        self.stop_btn.clicked.connect(self._on_interrupt)
        self.stop_btn.hide()
        input_layout.addWidget(self.stop_btn)

        right_layout.addWidget(input_widget)

        self.drop_zone = FileDropZone()
        right_layout.addWidget(self.drop_zone)

        # ── Splitter: resizable HUD + right panel ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #1a2a35;
            }
            QSplitter::handle:hover {
                background-color: #00d4ff;
            }
        """)
        splitter.addWidget(self.hud)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)   # HUD stretches
        splitter.setStretchFactor(1, 0)   # right panel does not
        splitter.setSizes([700, 360])     # initial widths
        main_layout.addWidget(splitter)

        # ── System monitor (thread-safe via signal) ──
        self.metrics_signal.connect(self._on_metrics)
        self.monitor = SystemMonitor()
        self.monitor.set_callback(lambda cpu, mem, net, gpu, temp:
                                  self.metrics_signal.emit(cpu, mem, net, gpu, temp))
        self.monitor.start()

        # ── Default size ──
        self.resize(1280, 720)
        self.setMinimumSize(900, 500)

        # ── Global ESC shortcut (interrupt) ──
        esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        esc_shortcut.activated.connect(self._on_interrupt)

    def _open_settings(self):
        """Open the settings dialog in-place."""
        dlg = SettingsDialog(self)
        dlg.exec()

    def _on_metrics(self, cpu, mem, net, gpu, temp):
        self.cpu_bar.set_value(cpu)
        self.mem_bar.set_value(mem)
        self.net_bar.set_value(min(100, net / 10))     # scale network KB/s → %
        self.gpu_bar.set_value(gpu)
        self.temp_bar.set_value(min(100, temp / 1.2))  # scale temp → %

    def _on_send(self):
        text = self.chat_input.text().strip()
        if text:
            self.chat_input.clear()
            self.chat_submitted.emit(text)

    def _on_command_clicked(self, text: str):
        self.chat_input.setText(text)
        self.chat_input.setFocus()

    def set_processing(self, processing: bool):
        """Show stop button when processing, hide when idle. Keep input active."""
        self.stop_btn.setVisible(processing)
        self.send_btn.setVisible(not processing)
        self.chat_input.setEnabled(True)
        if not processing:
            self.chat_input.setFocus()

    def _on_interrupt(self):
        self.chat_input.clear()
        self.chat_input.setEnabled(True)
        self.send_btn.setVisible(True)
        self.chat_input.setFocus()
        self.stop_btn.hide()
        self.interrupt_triggered.emit()

    def closeEvent(self, event):
        if self._is_quitting:
            self.closing.emit()
            self.monitor.stop()
            self.monitor.join(timeout=2.0)
            super().closeEvent(event)
        else:
            event.ignore()
            self.hide()

    def keyPressEvent(self, event):
        modifiers = event.modifiers()
        key = event.key()
        if (modifiers & Qt.KeyboardModifier.AltModifier) and (modifiers & Qt.KeyboardModifier.ShiftModifier):
            if key == Qt.Key.Key_B:
                self.toggle_sleep_triggered.emit()
                event.accept()
                return
            elif key == Qt.Key.Key_C:
                self.toggle_mute_triggered.emit()
                event.accept()
                return
        super().keyPressEvent(event)

    def toggle_visibility(self):
        """Toggle main HUD window visibility."""
        if self.isVisible():
            if self.isMinimized():
                self.showNormal()
                self.activateWindow()
                self.raise_()
            else:
                self.hide()
        else:
            self.showNormal()
            self.activateWindow()
            self.raise_()

    def show_and_activate(self):
        """Bring main HUD window to top and set focus."""
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def set_audio_output_available(self, available: bool):
        """Update UI when no speaker hardware is detected."""
        self._audio_output_available = available
        if not available:
            self.spk_btn.setText("🔊")
            self.spk_btn.setToolTip("TTS Output: None Detected")
            self.spk_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0a0a0a;
                    color: #888888;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    font-family: 'Segoe UI Emoji', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #111111;
                    border: 1px solid #888888;
                }
            """)
            self.spk_btn.setEnabled(False)

    def set_audio_input_available(self, available: bool):
        """Update UI when no microphone hardware is detected."""
        self._audio_input_available = available
        if not available:
            self.mic_btn.setText("🎤")
            self.mic_btn.setToolTip("Microphone: None Detected")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0a0a0a;
                    color: #888888;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    font-family: 'Segoe UI Emoji', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #111111;
                    border: 1px solid #888888;
                }
            """)
            self.mic_btn.setEnabled(False)

    def set_muted(self, muted: bool):
        """Update the microphone button visual state."""
        if not self._audio_input_available:
            return
        if muted:
            self.mic_btn.setText("🔇")
            self.mic_btn.setToolTip("Microphone: Muted")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0a0204;
                    color: #ff3366;
                    border: 1px solid #991f3d;
                    border-radius: 4px;
                    font-family: 'Segoe UI Emoji', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1f050b;
                    border: 1px solid #ff3366;
                }
            """)
        else:
            self.mic_btn.setText("🎙️")
            self.mic_btn.setToolTip("Microphone: On")
            self.mic_btn.setStyleSheet("""
                QPushButton {
                    background-color: #010d14;
                    color: #00ff88;
                    border: 1px solid #009955;
                    border-radius: 4px;
                    font-family: 'Segoe UI Emoji', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #001f14;
                    border: 1px solid #00ff88;
                }
            """)

    def set_tts_enabled(self, enabled: bool):
        """Update the speaker button visual state."""
        if not self._audio_output_available:
            return
        if not enabled:
            self.spk_btn.setText("🔇")
            self.spk_btn.setToolTip("Text-To-Speech: Off")
            self.spk_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0a0204;
                    color: #ff3366;
                    border: 1px solid #991f3d;
                    border-radius: 4px;
                    font-family: 'Segoe UI Emoji', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1f050b;
                    border: 1px solid #ff3366;
                }
            """)
        else:
            self.spk_btn.setText("🔊")
            self.spk_btn.setToolTip("Text-To-Speech: On")
            self.spk_btn.setStyleSheet("""
                QPushButton {
                    background-color: #010d14;
                    color: #00d4ff;
                    border: 1px solid #007a99;
                    border-radius: 4px;
                    font-family: 'Segoe UI Emoji', sans-serif;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #001f2e;
                    border: 1px solid #00d4ff;
                }
            """)

    def set_audio_state(self, mic_vol: int, spk_vol: int, spk_muted: bool):
        """Update the volume indicator labels below the controls."""
        # Mic volume
        if not self._audio_input_available:
            self.mic_vol_label.setText("Mic: N/A")
            self.mic_vol_label.setStyleSheet(
                "color: #555555; font-size: 10px; font-family: Consolas;"
            )
        else:
            self.mic_vol_label.setText(f"Mic: {mic_vol}%")
            self.mic_vol_label.setStyleSheet(
                f"color: {'#ff3366' if mic_vol == 0 else '#00ff88'}; font-size: 10px; font-family: Consolas;"
            )
        # Speaker volume
        if not self._audio_output_available:
            self.spk_vol_label.setText("Spk: N/A")
            self.spk_vol_label.setStyleSheet(
                "color: #555555; font-size: 10px; font-family: Consolas;"
            )
        elif spk_muted:
            self.spk_vol_label.setText("Spk: MUTED")
            self.spk_vol_label.setStyleSheet(
                "color: #ff3366; font-size: 10px; font-family: Consolas;"
            )
        else:
            self.spk_vol_label.setText(f"Spk: {spk_vol}%")
            self.spk_vol_label.setStyleSheet(
                f"color: {'#ff3366' if spk_vol == 0 else '#00d4ff'}; font-size: 10px; font-family: Consolas;"
            )

    def update_task_badge(self, task_id: str, label: str, status: str, tool_name: str = "", current_action: str = ""):
        if task_id not in self._task_badges:
            # Remove placeholder
            if self.placeholder_tasks:
                self.placeholder_tasks.hide()
                self.tasks_layout.removeWidget(self.placeholder_tasks)
                self.placeholder_tasks.deleteLater()
                self.placeholder_tasks = None

            badge = TaskBadge(task_id, label, status, tool_name, current_action)
            self.tasks_layout.addWidget(badge)
            self._task_badges[task_id] = badge
        else:
            self._task_badges[task_id].update_status(status, current_action)

    def _animate_running_badges(self):
        spinner_chars = ["⟳", "⟲", "⟱", "⟴"]
        for _task_id, badge in list(self._task_badges.items()):
            if badge.status_text == "running":
                curr_txt = badge.lbl_status.text()
                # Find current spinner char index
                idx = 0
                for i, char in enumerate(spinner_chars):
                    if char in curr_txt:
                        idx = i
                        break
                next_char = spinner_chars[(idx + 1) % len(spinner_chars)]
                badge.lbl_status.setText(f"{next_char} RUNNING")
