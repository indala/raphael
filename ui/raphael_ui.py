"""
RaphaelUI — public API facade for the PyQt6 HUD.
Wraps MainWindow, QApplication, and provides thread-safe state/log access.
"""

import sys

from PyQt6.QtWidgets import QApplication

from .main_window import MainWindow
from .splash_screen import RaphaelSplashScreen
import contextlib


class RaphaelUI:
    """Public API for the Raphael HUD interface."""

    def __init__(self):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setStyle("Fusion")
        self._app.setQuitOnLastWindowClosed(False)

        # Show splash screen first
        self._splash = RaphaelSplashScreen()
        self._splash.show()
        self._app.processEvents()

        self._window = MainWindow()

        self._log_tag_colors = {
            "ai":   "#00ff88",
            "err":  "#ff3366",
            "file": "#ff6b00",
            "sys":  "#888888",
        }

    @property
    def hud(self):
        return self._window.hud

    @property
    def log(self):
        return self._window.log_widget

    @property
    def status_ticker(self):
        return self._window.status_ticker

    @property
    def window(self):
        return self._window

    # ── State management (thread-safe via signals) ──

    def set_state(self, state: str):
        """Update HUD state indicator (LISTENING, THINKING, SPEAKING, etc.)."""
        self.hud.set_state(state)

    def set_audio_output_available(self, available: bool):
        self._window.set_audio_output_available(available)

    def set_audio_input_available(self, available: bool):
        self.hud.set_audio_input_available(available)
        self._window.set_audio_input_available(available)

    def set_muted(self, muted: bool):
        self.hud.set_muted(muted)
        self._window.set_muted(muted)

    def set_tts_enabled(self, enabled: bool):
        self._window.set_tts_enabled(enabled)

    def set_processing(self, processing: bool):
        self._window.set_processing(processing)

    def set_audio_state(self, mic_vol: int, spk_vol: int, spk_muted: bool):
        """Update volume indicator labels from system audio state."""
        self._window.set_audio_state(mic_vol, spk_vol, spk_muted)

    def set_mic_level(self, level: float):
        """Update live mic level on the HUD (0.0–1.0)."""
        self.hud.set_mic_level(level)

    def update_splash(self, progress: int, message: str):
        """Update progress bar and status message on the splash screen."""
        if hasattr(self, "_splash") and self._splash:
            self._splash.set_progress(progress, message)
            self._app.processEvents()

    def close_splash_and_show_main(self):
        """Transition from splash screen to main window with fade-out."""
        if hasattr(self, "_splash") and self._splash:
            self._splash.fade_out_and_close(self._window.show_and_activate)
        else:
            self._window.show_and_activate()

    def exit_app(self):
        """Public method to close the application cleanly."""
        self._window._is_quitting = True
        self._window.hide()
        self._window.close()
        self._app.quit()

    def write_log(self, tag: str, text: str):
        """Add an activity log entry (thread-safe)."""
        self.log.write_log(tag, text)

    def update_task_badge(self, task_id: str, label: str, status: str, tool_name: str = "", current_action: str = ""):
        """Update a background task's status badge in the Left Panel."""
        self._window.update_task_badge(task_id, label, status, tool_name, current_action)

    # ── Event loop ──

    def mainloop(self):
        """Run the Qt event loop (blocks). This replaces the terminal loop."""
        with contextlib.suppress(SystemExit):
            sys.exit(self._app.exec())

    # ── UI callbacks (for main.py to register) ──

    def register_callbacks(self, on_state_change, on_log, on_chat_submit=None):
        """Wire external state/log signals into the HUD."""
        if on_chat_submit:
            self._window.chat_submitted.connect(on_chat_submit)

        def _state_cb(state):
            self.set_state(state)
            if on_state_change:
                on_state_change(state)

        def _log_cb(tag, text):
            self.write_log(tag, text)
            if on_log:
                on_log(tag, text)

        return _state_cb, _log_cb

