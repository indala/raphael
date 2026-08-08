"""
MusicPanel — playlists, now-playing, and transport controls for the HUD.

Sits in the right panel above the input row. All state is read from the
MusicPlayer singleton — this is a read-only display, not a controller.
"""

import logging
from functools import partial

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton,
                             QSlider, QVBoxLayout, QWidget, QScrollArea)

from audio.music_player import MusicPlayer, PlaybackState
import contextlib

logger = logging.getLogger(__name__)


class _CollapsibleSection(QWidget):
    """A titled section that can be collapsed/expanded."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._expanded = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Toggle header
        self._toggle = QPushButton(f"[−] {title}")
        self._toggle.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #00d4ff;
                font-size: 10px;
                font-family: Consolas;
                font-weight: bold;
                letter-spacing: 1px;
                border: none;
                text-align: left;
                padding: 2px 0;
            }
            QPushButton:hover {
                color: #66e6ff;
            }
        """)
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.clicked.connect(self._toggle_expand)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(4, 0, 0, 0)
        self._content_layout.setSpacing(4)

        layout.addWidget(self._toggle)
        layout.addWidget(self._content)

    def _toggle_expand(self):
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        prefix = "[+]" if not self._expanded else "[−]"
        self._toggle.setText(f"{prefix} {self._toggle.text()[4:]}")

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def set_content_visible(self, visible: bool):
        self._content.setVisible(visible)

    def set_title(self, title: str):
        prefix = "[+]" if not self._expanded else "[−]"
        self._toggle.setText(f"{prefix} {title}")


class MusicPanel(QWidget):
    """HUD panel showing now-playing, queue, and playlists."""

    _state_changed = pyqtSignal(object, object)  # old, new

    open_music_requested = pyqtSignal()

    def __init__(self, parent=None, standalone: bool = False):
        super().__init__(parent)
        self._player = MusicPlayer.get_instance()
        self._standalone = standalone
        self.setVisible(standalone)  # standalone: always visible; HUD: hidden until music

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(4)

        # ── Section: Now Playing ──
        self._now_section = _CollapsibleSection("NOW PLAYING")
        np_layout = self._now_section.content_layout()

        self._song_label = QLabel("No song playing")
        self._song_label.setStyleSheet("color: #cccccc; font-size: 12px; font-family: Consolas;")
        self._song_label.setWordWrap(True)
        np_layout.addWidget(self._song_label)

        # Progress bar
        self._progress_bar = QSlider(Qt.Orientation.Horizontal)
        self._progress_bar.setRange(0, 1000)
        self._progress_bar.setValue(0)
        self._progress_bar.setEnabled(False)
        self._progress_bar.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #0a1a2a;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #00d4ff;
                width: 8px;
                height: 8px;
                margin: -2px 0;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #00d4ff;
                border-radius: 2px;
            }
        """)
        np_layout.addWidget(self._progress_bar)

        self._time_label = QLabel("0:00 / 0:00")
        self._time_label.setStyleSheet("color: #888888; font-size: 9px; font-family: Consolas;")
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        np_layout.addWidget(self._time_label)

        # Transport controls
        transport = QHBoxLayout()
        transport.setSpacing(6)
        transport.setContentsMargins(0, 0, 0, 0)

        def _btn(text, tooltip, callback):
            b = QPushButton(text)
            b.setFixedSize(28, 24)
            b.setToolTip(tooltip)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("""
                QPushButton {
                    background-color: #010d14;
                    color: #888888;
                    border: 1px solid #1a2a35;
                    border-radius: 3px;
                    font-size: 12px;
                    font-family: Consolas;
                }
                QPushButton:hover {
                    background-color: #001a24;
                    color: #00d4ff;
                    border: 1px solid #00d4ff;
                }
            """)
            b.clicked.connect(callback)
            return b

        self._prev_btn = _btn("|<", "Previous", lambda: self._run("previous"))
        self._play_btn = _btn(">", "Play/Pause", lambda: self._run("toggle_play"))
        self._next_btn = _btn(">|", "Next", lambda: self._run("next"))
        self._stop_btn = _btn("#", "Stop", lambda: self._run("stop"))

        transport.addWidget(self._prev_btn)
        transport.addWidget(self._play_btn)
        transport.addWidget(self._next_btn)
        transport.addWidget(self._stop_btn)

        # Expand Spotify Player Window button
        self._spotify_win_ref = None
        open_spotify_btn = QPushButton("🎵")
        open_spotify_btn.setFixedSize(28, 24)
        open_spotify_btn.setToolTip("Open Full Spotify Player (Ctrl+Shift+M)")
        open_spotify_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_spotify_btn.setStyleSheet("""
            QPushButton {
                background-color: #1db954;
                color: #000000;
                font-weight: bold;
                border-radius: 3px;
                font-size: 12px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1ed760;
            }
        """)
        open_spotify_btn.clicked.connect(self.open_spotify_player)
        transport.addWidget(open_spotify_btn)

        transport.addStretch()

        # Volume slider
        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(70)
        self._vol_slider.setFixedWidth(80)
        self._vol_slider.setToolTip("Volume")
        self._vol_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #0a1a2a;
                height: 3px;
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                background: #00ff88;
                width: 6px;
                height: 6px;
                margin: -1px 0;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #00ff88;
                border-radius: 1px;
            }
        """)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        transport.addWidget(self._vol_slider)

        np_layout.addLayout(transport)

        layout.addWidget(self._now_section)

        # ── Section: Queue ──
        self._queue_section = _CollapsibleSection("QUEUE")
        self._queue_label = QLabel("Queue is empty")
        self._queue_label.setStyleSheet("color: #445566; font-size: 10px; font-family: Consolas;")
        self._queue_section.content_layout().addWidget(self._queue_label)

        layout.addWidget(self._queue_section)

        # ── Section: Playlists ──
        self._playlist_section = _CollapsibleSection("PLAYLISTS")
        self._playlist_area = QScrollArea()
        self._playlist_area.setWidgetResizable(True)
        self._playlist_area.setMinimumHeight(80)
        self._playlist_area.setMaximumHeight(180)
        self._playlist_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: 1px solid #0a1a2a;
                border-radius: 4px;
            }
        """)
        self._playlist_container = QWidget()
        self._playlist_container.setStyleSheet("background-color: transparent;")
        self._playlist_inner_layout = QVBoxLayout(self._playlist_container)
        self._playlist_inner_layout.setContentsMargins(4, 4, 4, 4)
        self._playlist_inner_layout.setSpacing(4)
        self._playlist_area.setWidget(self._playlist_container)
        self._playlist_section.content_layout().addWidget(self._playlist_area)

        layout.addWidget(self._playlist_section)

        # ── Poll timer (1 Hz) — only active during playback ──
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)

        # ── Listen for playback state changes (via signal for thread safety) ──
        self._state_changed.connect(self._on_player_state)
        self._player.on_state_change(lambda old, new: self._state_changed.emit(old, new))

        # Initial state check (in case music is already playing at startup)
        try:
            s = self._player.get_playback_status().get("state", "idle")
            self._state_changed.emit(None, PlaybackState(s))
        except Exception:
            self._state_changed.emit(None, PlaybackState.IDLE)

    def _on_player_state(self, old, new):
        """React to playback state changes — show/hide panel and timer."""
        if new == PlaybackState.PLAYING:
            self.setVisible(True)
            self._refresh()
            if not self._timer.isActive():
                self._timer.start(1000)
        elif new == PlaybackState.PAUSED:
            self.setVisible(True)
            self._refresh()
            if self._timer.isActive():
                self._timer.stop()
        else:  # IDLE, STOPPED
            if self._timer.isActive():
                self._timer.stop()
            if not self._standalone:
                self.setVisible(False)
            else:
                self._refresh()

    def _run(self, action: str):
        """Execute a player action — ignore errors gracefully."""
        try:
            p = self._player
            if action == "previous":
                p.previous()
            elif action == "next":
                p.next()
            elif action == "stop":
                p.stop()
            elif action == "toggle_play":
                if p.get_playback_status().get("state") == "playing":
                    p.pause()
                else:
                    p.resume()
        except Exception as e:
            logger.warning("MusicPanel action '%s' failed: %s", action, e)

    def open_spotify_player(self):
        """Request opening/toggling the standalone SpotifyMusicWindow via the window manager."""
        self.open_music_requested.emit()

    def _on_volume_changed(self, val: int):
        with contextlib.suppress(Exception):
            self._player.set_volume(val / 100.0)
            from orchestrator.tools.native.system import set_system_volume
            set_system_volume(val)

    def update_system_volume(self, spk_vol: int):
        """Sync music player volume & UI slider when Windows master speaker volume changes."""
        with contextlib.suppress(Exception):
            self._player.set_volume(spk_vol / 100.0)
            if not self._vol_slider.isSliderDown():
                self._vol_slider.blockSignals(True)
                self._vol_slider.setValue(spk_vol)
                self._vol_slider.blockSignals(False)

    def refresh(self):
        """Public entry for external refresh trigger."""
        self._refresh()

    def _refresh(self):
        """Poll MusicPlayer and update all displayed state."""
        try:
            status = self._player.get_playback_status()
        except Exception:
            return

        state = status.get("state", "idle")
        title = status.get("title")
        artist = status.get("artist", "")
        queue_len = status.get("queue_length", 0)

        # ── Now Playing ──
        if title and state != "idle":
            if artist:
                self._song_label.setText(f"{title}  —  {artist}")
            else:
                self._song_label.setText(title)
            self._play_btn.setText("II" if state == "playing" else ">")
            self._now_section.set_content_visible(True)
        else:
            self._song_label.setText("No song playing")
            self._play_btn.setText(">")

        # ── Prev/Next visibility (hidden when ≤1 song in queue) ──
        has_queue = queue_len > 1
        self._prev_btn.setVisible(has_queue)
        self._next_btn.setVisible(has_queue)

        # ── Progress ──
        try:
            prog = self._player.get_playback_progress()
            pos = prog.get("position_sec", 0)
            dur = prog.get("duration_sec", 0)
            pct = prog.get("progress_pct", 0)
            pos_str = f"{int(pos // 60)}:{int(pos % 60):02d}"
            dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}" if dur else "?:??"
            self._time_label.setText(f"{pos_str} / {dur_str}")
            self._progress_bar.setValue(int(pct * 10) if pct else 0)
        except Exception:
            self._time_label.setText("0:00 / 0:00")
            self._progress_bar.setValue(0)

        # ── Volume ──
        try:
            vol = self._player.get_volume()
            self._vol_slider.blockSignals(True)
            self._vol_slider.setValue(int(vol * 100))
            self._vol_slider.blockSignals(False)
        except Exception:
            pass

        # ── Queue ──
        try:
            queue_text = self._player.show_queue()
            if queue_text and "No songs" not in queue_text and "empty" not in queue_text.lower():
                self._queue_label.setText(queue_text)
                self._queue_label.setStyleSheet("color: #cccccc; font-size: 9px; font-family: Consolas;")
                self._queue_section.setVisible(True)
            else:
                self._queue_section.setVisible(False)
        except Exception:
            self._queue_section.setVisible(False)

        # ── Playlists ──
        self._refresh_playlists()

    def _refresh_playlists(self):
        """Rebuild the playlist list from PlaylistManager."""
        from audio.music_library import PlaylistManager

        # Clear existing
        while self._playlist_inner_layout.count():
            item = self._playlist_inner_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        try:
            names = PlaylistManager.list_playlists()
            if not names:
                self._playlist_section.setVisible(False)
                return

            self._playlist_section.setVisible(True)

            for name in names:
                row = QHBoxLayout()
                row.setSpacing(6)

                lbl = QLabel(name)
                lbl.setStyleSheet("color: #cccccc; font-size: 10px; font-family: Consolas;")
                row.addWidget(lbl)

                row.addStretch()

                play_btn = QPushButton(">")
                play_btn.setFixedSize(20, 18)
                play_btn.setToolTip(f"Play '{name}'")
                play_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #010d14;
                        color: #00ff88;
                        border: 1px solid #009955;
                        border-radius: 2px;
                        font-size: 10px;
                        font-family: Consolas;
                    }
                    QPushButton:hover {
                        background-color: #001f14;
                        border: 1px solid #00ff88;
                    }
                """)
                play_btn.clicked.connect(partial(self._play_playlist, name))
                row.addWidget(play_btn)

                del_btn = QPushButton("X")
                del_btn.setFixedSize(20, 18)
                del_btn.setToolTip(f"Delete '{name}'")
                del_btn.setStyleSheet("""
                    QPushButton {
                        background-color: #010d14;
                        color: #ff3366;
                        border: 1px solid #661111;
                        border-radius: 2px;
                        font-size: 10px;
                        font-family: Consolas;
                    }
                    QPushButton:hover {
                        background-color: #001a0a;
                        border: 1px solid #ff3366;
                    }
                """)
                del_btn.clicked.connect(partial(self._delete_playlist, name))
                row.addWidget(del_btn)

                container = QWidget()
                container.setLayout(row)
                self._playlist_inner_layout.addWidget(container)

            self._playlist_inner_layout.addStretch()
        except Exception as e:
            lbl = QLabel(f"Error: {e}")
            lbl.setStyleSheet("color: #ff3366; font-size: 9px; font-family: Consolas;")
            self._playlist_inner_layout.addWidget(lbl)

    def _play_playlist(self, name: str):
        """Play a playlist via the orchestrator tool."""
        try:
            from orchestrator.tools.native.music_player_tools import play_playlist
            result = play_playlist(name)
            logger.info("MusicPanel: %s", result)
        except Exception as e:
            logger.warning("MusicPanel: failed to play playlist '%s': %s", name, e)

    def _delete_playlist(self, name: str):
        """Delete a playlist."""
        try:
            from audio.music_library import PlaylistManager
            result = PlaylistManager.delete(name)
            logger.info("MusicPanel: %s", result)
            self._refresh_playlists()
        except Exception as e:
            logger.warning("MusicPanel: failed to delete playlist '%s': %s", name, e)
