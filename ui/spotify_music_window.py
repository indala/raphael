"""
SpotifyMusicWindow — Modern Spotify & SoundCloud inspired Music Player for Raphael.

Features:
  - Dark glassmorphic aesthetic with Spotify Green (#1DB954) & Cyber Cyan accents
  - Left Sidebar Navigation: Search/Discover, Local Library, Liked Songs, Playlists, History
  - Search & Online Streaming: Direct YouTube music search with 1-click play & library saving
  - Liked Songs ❤️ System: Persistent 1-click heart toggle on any track
  - Playlist Manager: Create, edit, play, shuffle, and download playlists offline
  - Bottom Transport Deck:
      * Track Cover Art & Metadata
      * Like / Heart Quick Toggle
      * Transport Controls (Shuffle, Prev, Play/Pause, Next, Repeat)
      * Interactive Progress Seek Bar with Timestamps
      * Real-Time Audio Waveform Visualizer
      * Volume Slider with Master Speaker Sync
"""

import math
import logging
from functools import partial

from PyQt6.QtCore import QThread, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QSlider,
    QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget
)

from audio.music_library import LikedSongsManager, PlaylistManager, RecentlyPlayed
from audio.music_player import MusicPlayer, RepeatMode

logger = logging.getLogger(__name__)


# ── Audio Waveform Visualizer Widget ──────────────────────────────────────────


class AudioWaveformWidget(QWidget):
    """Dynamic animated waveform visualizer simulating audio frequencies."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(120, 36)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self.update)
        self._is_active = False
        self._phase = 0.0
        self._bars = [0.2] * 16

    def set_active(self, active: bool):
        self._is_active = active
        if active:
            if not self._anim_timer.isActive():
                self._anim_timer.start(50)  # 20 FPS
        else:
            if self._anim_timer.isActive():
                self._anim_timer.stop()
            self._bars = [0.15] * 16
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        n_bars = 16
        bar_w = 4
        gap = (w - (n_bars * bar_w)) / (n_bars + 1)

        if self._is_active:
            self._phase += 0.15
            for i in range(n_bars):
                # Generates smooth organic wave simulation
                val = 0.3 + 0.6 * math.sin(self._phase + i * 0.4) * math.cos(self._phase * 0.7 + i * 0.2)
                self._bars[i] = max(0.15, min(0.95, abs(val)))

        for i in range(n_bars):
            bh = int(h * self._bars[i])
            x = int(gap + i * (bar_w + gap))
            y = int((h - bh) / 2)

            grad = QLinearGradient(x, y, x, y + bh)
            grad.setColorAt(0.0, QColor("#00d4ff"))
            grad.setColorAt(1.0, QColor("#1db954"))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRoundedRect(x, y, bar_w, bh, 2, 2)


class HoverSeekSlider(QSlider):
    """QSlider with dynamic hover timestamp tooltip preview."""

    def __init__(self, orientation, duration_getter, parent=None):
        super().__init__(orientation, parent)
        self.duration_getter = duration_getter
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        dur = self.duration_getter()
        if dur > 0 and self.width() > 0:
            pos_ratio = max(0.0, min(1.0, event.position().x() / self.width()))
            target_sec = int(pos_ratio * dur)
            m, s = divmod(target_sec, 60)
            self.setToolTip(f"Seek to {m}:{s:02d}")


# ── Background Worker Threads for yt-dlp ──────────────────────────────────────


class _SearchWorker(QThread):
    finished = pyqtSignal(str, list)  # query, results
    failed = pyqtSignal(str, str)     # query, error message

    def __init__(self, query: str, player: MusicPlayer, parent=None):
        super().__init__(parent)
        self.query = query
        self.player = player

    def run(self):
        try:
            results = self.player.search_online(self.query, max_results=8)
            self.finished.emit(self.query, results)
        except Exception as e:
            self.failed.emit(self.query, str(e))


class _StreamWorker(QThread):
    finished = pyqtSignal(str)     # title
    failed = pyqtSignal(str, str)  # title, error message

    def __init__(self, title: str, player: MusicPlayer, parent=None):
        super().__init__(parent)
        self.title = title
        self.player = player

    def run(self):
        try:
            self.player.stream_song(self.title)
            self.finished.emit(self.title)
        except Exception as e:
            self.failed.emit(self.title, str(e))


class _SavePlaylistWorker(QThread):
    finished = pyqtSignal(str, str)  # name, result message
    failed = pyqtSignal(str, str)    # name, error message

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name

    def run(self):
        try:
            msg = PlaylistManager.save_to_disk(self.name)
            self.finished.emit(self.name, msg)
        except Exception as e:
            self.failed.emit(self.name, str(e))


# ── Standalone Spotify Music Window ───────────────────────────────────────────


class SpotifyMusicWindow(QMainWindow):
    """Full-featured modern Spotify/SoundCloud Music Player."""

    _state_signal = pyqtSignal(object, object)  # old state, new state

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Raphael Music — Spotify Player")
        self.resize(1100, 700)
        self.setMinimumSize(850, 550)

        self._player = MusicPlayer.get_instance()
        self._current_track_info = {}

        # Worker thread attributes to manage background yt-dlp tasks
        self._search_worker = None
        self._stream_worker = None
        self._save_worker = None

        self._apply_theme()
        self._init_ui()

        # Refresh Timer (1 Hz)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_refresh_tick)
        self._refresh_timer.start(1000)

        # Listen to player state
        self._state_signal.connect(self._on_playback_state_changed)
        self._player.on_state_change(lambda old, new: self._state_signal.emit(old, new))

        # Initial data populate
        self._load_local_library()
        self._load_liked_songs()
        self._load_playlists()
        self._load_history()
        self._update_player_deck()

    def _apply_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #121212;
            }
            QWidget {
                color: #e0e0e0;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QTableWidget {
                background-color: #181818;
                border: 1px solid #282828;
                border-radius: 8px;
                gridline-color: transparent;
                selection-background-color: #282828;
                font-size: 13px;
                outline: 0;
            }
            QTableWidget::item {
                padding: 6px 10px;
                color: #cccccc;
                border-bottom: 1px solid #222222;
            }
            QTableWidget::item:selected {
                color: #1db954;
                font-weight: bold;
                background-color: #242424;
            }
            QHeaderView::section {
                background-color: #121212;
                color: #888888;
                font-size: 11px;
                font-weight: bold;
                text-transform: uppercase;
                border: none;
                border-bottom: 1px solid #282828;
                padding: 8px 10px;
            }
            QLineEdit {
                background-color: #242424;
                color: #ffffff;
                border: 1px solid #333333;
                border-radius: 18px;
                padding: 8px 16px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1px solid #1db954;
            }
        """)

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Body Splitter (Sidebar + Content Pages) ──
        body_widget = QWidget()
        body_layout = QHBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # 1. Left Sidebar
        sidebar = QWidget()
        sidebar.setFixedWidth(210)
        sidebar.setStyleSheet("background-color: #000000; border-right: 1px solid #282828;")
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(12, 16, 12, 16)
        sb_layout.setSpacing(8)

        # Logo / Header
        header_lbl = QLabel("RAPHAEL 🎵")
        header_lbl.setStyleSheet("color: #1db954; font-size: 18px; font-weight: bold; letter-spacing: 2px;")
        sb_layout.addWidget(header_lbl)

        sub_lbl = QLabel("SPOTIFY PLAYER")
        sub_lbl.setStyleSheet("color: #666666; font-size: 9px; font-weight: bold; letter-spacing: 1px; margin-bottom: 12px;")
        sb_layout.addWidget(sub_lbl)

        # Nav Buttons
        self._nav_btn_search = self._create_nav_btn("🔍  Search & Discover", 0)
        self._nav_btn_library = self._create_nav_btn("🎵  Local Library", 1)
        self._nav_btn_liked = self._create_nav_btn("❤️  Liked Songs", 2)
        self._nav_btn_playlists = self._create_nav_btn("📁  Playlists", 3)
        self._nav_btn_history = self._create_nav_btn("🕒  Recently Played", 4)

        sb_layout.addWidget(self._nav_btn_search)
        sb_layout.addWidget(self._nav_btn_library)
        sb_layout.addWidget(self._nav_btn_liked)
        sb_layout.addWidget(self._nav_btn_playlists)
        sb_layout.addWidget(self._nav_btn_history)
        sb_layout.addStretch()

        body_layout.addWidget(sidebar)

        # 2. Main Stacked Pages
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background-color: #121212;")

        self._page_search = self._build_search_page()
        self._page_library = self._build_library_page()
        self._page_liked = self._build_liked_page()
        self._page_playlists = self._build_playlists_page()
        self._page_history = self._build_history_page()

        self._stack.addWidget(self._page_search)
        self._stack.addWidget(self._page_library)
        self._stack.addWidget(self._page_liked)
        self._stack.addWidget(self._page_playlists)
        self._stack.addWidget(self._page_history)

        body_layout.addWidget(self._stack)
        main_layout.addWidget(body_widget, stretch=1)

        # 3. Bottom Transport Deck
        deck = self._build_bottom_deck()
        main_layout.addWidget(deck, stretch=0)

        # Default open Library page
        self._switch_page(1)

    def _create_nav_btn(self, text: str, page_idx: int) -> QPushButton:
        btn = QPushButton(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(36)
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #b3b3b3;
                text-align: left;
                padding: 10px 14px;
                font-size: 13px;
                font-weight: 600;
                border-radius: 6px;
                border: none;
            }
            QPushButton:hover {
                color: #ffffff;
                background-color: #1a1a1a;
            }
        """)
        btn.clicked.connect(lambda: self._switch_page(page_idx))
        return btn

    def _switch_page(self, page_idx: int):
        self._stack.setCurrentIndex(page_idx)
        nav_btns = [
            self._nav_btn_search, self._nav_btn_library,
            self._nav_btn_liked, self._nav_btn_playlists, self._nav_btn_history
        ]
        for idx, btn in enumerate(nav_btns):
            if idx == page_idx:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #282828;
                        color: #1db954;
                        text-align: left;
                        padding: 10px 14px;
                        font-size: 13px;
                        font-weight: bold;
                        border-radius: 6px;
                        border-left: 3px solid #1db954;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        color: #b3b3b3;
                        text-align: left;
                        padding: 10px 14px;
                        font-size: 13px;
                        font-weight: 600;
                        border-radius: 6px;
                        border: none;
                    }
                    QPushButton:hover {
                        color: #ffffff;
                        background-color: #1a1a1a;
                    }
                """)

    # ── Page Builders ─────────────────────────────────────────────────────────

    def _build_search_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        title_lbl = QLabel("Search & Discover 🔍")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title_lbl)

        # Search Bar
        search_box = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search songs, artists, or genres on YouTube...")
        self._search_input.returnPressed.connect(self._do_search)
        search_box.addWidget(self._search_input)

        search_btn = QPushButton("Search")
        search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        search_btn.setStyleSheet("""
            QPushButton {
                background-color: #1db954;
                color: #000000;
                font-weight: bold;
                font-size: 13px;
                border-radius: 18px;
                padding: 8px 20px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1ed760;
            }
        """)
        search_btn.clicked.connect(self._do_search)
        search_box.addWidget(search_btn)
        layout.addLayout(search_box)

        # Status indicator
        self._search_status_lbl = QLabel("Type a query above to discover music")
        self._search_status_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        layout.addWidget(self._search_status_lbl)

        # Results Table
        self._search_table = QTableWidget(0, 4)
        self._search_table.setHorizontalHeaderLabels(["Title", "Artist", "Duration", "Actions"])
        self._search_table.verticalHeader().setVisible(False)
        self._search_table.verticalHeader().setDefaultSectionSize(42)
        self._search_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._search_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._search_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._search_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._search_table.setColumnWidth(1, 140)
        self._search_table.setColumnWidth(2, 90)
        self._search_table.setColumnWidth(3, 110)
        layout.addWidget(self._search_table)

        return page

    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        hdr_box = QHBoxLayout()
        title_lbl = QLabel("Local Library 🎵")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        hdr_box.addWidget(title_lbl)
        hdr_box.addStretch()

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet("background-color: #282828; color: #ffffff; border-radius: 14px; padding: 6px 14px;")
        refresh_btn.clicked.connect(self._load_local_library)
        hdr_box.addWidget(refresh_btn)
        layout.addLayout(hdr_box)

        self._library_table = QTableWidget(0, 4)
        self._library_table.setHorizontalHeaderLabels(["Song Title", "File Name", "Size", "Actions"])
        self._library_table.verticalHeader().setVisible(False)
        self._library_table.verticalHeader().setDefaultSectionSize(42)
        self._library_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._library_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._library_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._library_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._library_table.setColumnWidth(2, 90)
        self._library_table.setColumnWidth(3, 110)
        layout.addWidget(self._library_table)

        return page

    def _build_liked_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        hdr_box = QHBoxLayout()
        title_lbl = QLabel("Liked Songs ❤️")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #ff3366;")
        hdr_box.addWidget(title_lbl)
        hdr_box.addStretch()

        play_liked_btn = QPushButton("▶  Play All Shuffled")
        play_liked_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        play_liked_btn.setStyleSheet("""
            QPushButton {
                background-color: #1db954;
                color: #000000;
                font-weight: bold;
                font-size: 13px;
                border-radius: 18px;
                padding: 8px 18px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1ed760;
            }
        """)
        play_liked_btn.clicked.connect(self._play_all_liked_shuffled)
        hdr_box.addWidget(play_liked_btn)
        layout.addLayout(hdr_box)

        self._liked_table = QTableWidget(0, 3)
        self._liked_table.setHorizontalHeaderLabels(["Title", "Artist", "Actions"])
        self._liked_table.verticalHeader().setVisible(False)
        self._liked_table.verticalHeader().setDefaultSectionSize(42)
        self._liked_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._liked_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._liked_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._liked_table.setColumnWidth(2, 110)
        layout.addWidget(self._liked_table)

        return page

    def _build_playlists_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        hdr_box = QHBoxLayout()
        title_lbl = QLabel("Playlists 📁")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        hdr_box.addWidget(title_lbl)
        hdr_box.addStretch()

        new_pl_btn = QPushButton("+ New Playlist")
        new_pl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        new_pl_btn.setStyleSheet("""
            QPushButton {
                background-color: #1db954;
                color: #000000;
                font-weight: bold;
                border-radius: 14px;
                padding: 6px 16px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1ed760;
            }
        """)
        new_pl_btn.clicked.connect(self._create_new_playlist_dialog)
        hdr_box.addWidget(new_pl_btn)
        layout.addLayout(hdr_box)

        self._playlists_table = QTableWidget(0, 3)
        self._playlists_table.setHorizontalHeaderLabels(["Playlist Name", "Songs Count", "Actions"])
        self._playlists_table.verticalHeader().setVisible(False)
        self._playlists_table.verticalHeader().setDefaultSectionSize(42)
        self._playlists_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._playlists_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._playlists_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._playlists_table.setColumnWidth(1, 120)
        self._playlists_table.setColumnWidth(2, 180)
        layout.addWidget(self._playlists_table)

        return page

    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title_lbl = QLabel("Recently Played 🕒")
        title_lbl.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title_lbl)

        self._history_table = QTableWidget(0, 3)
        self._history_table.setHorizontalHeaderLabels(["Title", "Artist", "Actions"])
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.verticalHeader().setDefaultSectionSize(42)
        self._history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._history_table.setColumnWidth(2, 110)
        layout.addWidget(self._history_table)

        return page

    # ── Bottom Transport Deck ──────────────────────────────────────────────────

    def _build_bottom_deck(self) -> QWidget:
        deck = QFrame()
        deck.setFixedHeight(90)
        deck.setStyleSheet("background-color: #181818; border-top: 1px solid #282828;")

        layout = QHBoxLayout(deck)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)

        # 1. Left Card: Cover Art + Info + Like Button
        left_card = QHBoxLayout()
        left_card.setSpacing(12)

        self._cover_art_lbl = QLabel("🎵")
        self._cover_art_lbl.setFixedSize(54, 54)
        self._cover_art_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cover_art_lbl.setStyleSheet("""
            background-color: #282828;
            border-radius: 6px;
            font-size: 24px;
            color: #1db954;
        """)
        left_card.addWidget(self._cover_art_lbl)

        info_box = QVBoxLayout()
        info_box.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        info_box.setSpacing(2)

        self._deck_title_lbl = QLabel("No song playing")
        self._deck_title_lbl.setStyleSheet("color: #ffffff; font-size: 13px; font-weight: bold;")
        self._deck_artist_lbl = QLabel("Select a track to start")
        self._deck_artist_lbl.setStyleSheet("color: #b3b3b3; font-size: 11px;")

        info_box.addWidget(self._deck_title_lbl)
        info_box.addWidget(self._deck_artist_lbl)
        left_card.addLayout(info_box)

        self._heart_btn = QPushButton("♡")
        self._heart_btn.setFixedSize(32, 32)
        self._heart_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._heart_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #b3b3b3;
                font-size: 18px;
                border: none;
            }
            QPushButton:hover {
                color: #ff3366;
            }
        """)
        self._heart_btn.clicked.connect(self._toggle_like_current_song)
        left_card.addWidget(self._heart_btn)

        layout.addLayout(left_card, stretch=2)

        # 2. Center: Transport Buttons + Progress Seek Bar
        center_box = QVBoxLayout()
        center_box.setSpacing(4)
        center_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(14)
        btn_box.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._shuffle_btn = self._deck_btn("🔀", "Shuffle", self._toggle_shuffle, size=24, font_size=12)
        self._prev_btn = self._deck_btn("⏮", "Previous", lambda: self._run("previous"), size=28, font_size=14)
        self._play_btn = self._deck_btn("▶", "Play/Pause", lambda: self._run("toggle_play"), size=36, font_size=16, is_primary=True)
        self._next_btn = self._deck_btn("⏭", "Next", lambda: self._run("next"), size=28, font_size=14)
        self._repeat_btn = self._deck_btn("🔁", "Repeat", self._toggle_repeat, size=24, font_size=12)

        btn_box.addWidget(self._shuffle_btn)
        btn_box.addWidget(self._prev_btn)
        btn_box.addWidget(self._play_btn)
        btn_box.addWidget(self._next_btn)
        btn_box.addWidget(self._repeat_btn)
        center_box.addLayout(btn_box)

        # Progress bar + Timestamps
        seek_box = QHBoxLayout()
        seek_box.setSpacing(8)

        self._time_pos_lbl = QLabel("0:00")
        self._time_pos_lbl.setStyleSheet("color: #b3b3b3; font-size: 10px; font-family: monospace;")
        seek_box.addWidget(self._time_pos_lbl)

        self._seek_slider = HoverSeekSlider(
            Qt.Orientation.Horizontal,
            lambda: float(self._current_track_info.get("duration", 0) or 0)
        )
        self._seek_slider.setRange(0, 1000)
        self._seek_slider.setValue(0)
        self._seek_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._seek_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #4d4d4d;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #1db954;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 10px;
                height: 10px;
                margin: -3px 0;
                border-radius: 5px;
            }
            QSlider::handle:horizontal:hover {
                background: #1db954;
            }
        """)
        self._seek_slider.sliderReleased.connect(self._on_user_seek)
        seek_box.addWidget(self._seek_slider, stretch=1)

        self._time_dur_lbl = QLabel("0:00")
        self._time_dur_lbl.setStyleSheet("color: #b3b3b3; font-size: 10px; font-family: monospace;")
        seek_box.addWidget(self._time_dur_lbl)

        center_box.addLayout(seek_box)
        layout.addLayout(center_box, stretch=4)

        # 3. Right: Waveform Canvas + Volume Slider
        right_box = QHBoxLayout()
        right_box.setSpacing(12)
        right_box.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._waveform = AudioWaveformWidget()
        right_box.addWidget(self._waveform)

        vol_icon = QLabel("🔊")
        vol_icon.setStyleSheet("font-size: 14px;")
        right_box.addWidget(vol_icon)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(70)
        self._vol_slider.setFixedWidth(90)
        self._vol_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self._vol_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #4d4d4d;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #00d4ff;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 8px;
                height: 8px;
                margin: -2px 0;
                border-radius: 4px;
            }
        """)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        right_box.addWidget(self._vol_slider)

        layout.addLayout(right_box, stretch=2)

        return deck

    def _deck_btn(self, icon_txt: str, tooltip: str, callback, size: int = 28, font_size: int = 12, is_primary: bool = False) -> QPushButton:
        btn = QPushButton(icon_txt)
        btn.setFixedSize(size, size)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        if is_primary:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #ffffff;
                    color: #000000;
                    border-radius: {size // 2}px;
                    font-size: {font_size}px;
                    border: none;
                }}
                QPushButton:hover {{
                    background-color: #1db954;
                    color: #ffffff;
                }}
            """)
        else:
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: #b3b3b3;
                    border-radius: {size // 2}px;
                    font-size: {font_size}px;
                    border: none;
                }}
                QPushButton:hover {{
                    color: #ffffff;
                }}
            """)
        btn.clicked.connect(callback)
        return btn

    # ── Action Handlers ────────────────────────────────────────────────────────

    def _run(self, action: str):
        try:
            p = self._player
            if action == "previous":
                p.previous()
            elif action == "next":
                p.next()
            elif action == "toggle_play":
                if p.get_playback_status().get("state") == "playing":
                    p.pause()
                else:
                    p.resume()
        except Exception as e:
            logger.warning("SpotifyMusicWindow action '%s' failed: %s", action, e)

    def _toggle_shuffle(self):
        try:
            cur = self._player._shuffle
            self._player.set_shuffle(not cur)
            self._update_player_deck()
        except Exception:
            pass

    def _toggle_repeat(self):
        try:
            modes = [RepeatMode.OFF, RepeatMode.ONE, RepeatMode.ALL]
            cur = self._player._repeat
            idx = (modes.index(cur) + 1) % len(modes)
            self._player.set_repeat(modes[idx].value)
            self._update_player_deck()
        except Exception:
            pass

    def _on_user_seek(self):
        try:
            val = self._seek_slider.value()
            prog = self._player.get_playback_progress()
            dur = prog.get("duration_sec", 0)
            if dur > 0:
                target_sec = int((val / 1000.0) * dur)
                self._player.seek(target_sec)
        except Exception as e:
            logger.warning("User seek failed: %s", e)

    def _on_volume_changed(self, val: int):
        try:
            self._player.set_volume(val / 100.0)
        except Exception:
            pass

    def _toggle_like_current_song(self):
        status = self._player.get_playback_status()
        title = status.get("title")
        if not title:
            return
        artist = status.get("artist", "")
        filepath = status.get("current_song", "")
        song_info = {"title": title, "artist": artist, "filepath": filepath}
        is_now_liked = LikedSongsManager.toggle(song_info)
        self._heart_btn.setText("❤️" if is_now_liked else "♡")
        self._heart_btn.setStyleSheet("color: #ff3366; font-size: 18px; border: none; background: transparent;" if is_now_liked else "color: #b3b3b3; font-size: 18px; border: none; background: transparent;")
        self._load_liked_songs()

    # ── Refresh Loop & Sync ───────────────────────────────────────────────────

    def _on_refresh_tick(self):
        self._update_player_deck()

    def _on_playback_state_changed(self, old, new):
        self._update_player_deck()

    def _update_player_deck(self):
        try:
            status = self._player.get_playback_status()
            state = status.get("state", "idle")
            title = status.get("title")
            artist = status.get("artist", "")

            # Deck Track Labels
            if title and state != "idle":
                self._deck_title_lbl.setText(title)
                self._deck_artist_lbl.setText(artist if artist else "Unknown Artist")
                self._play_btn.setText("⏸" if state == "playing" else "▶")
                self._waveform.set_active(state == "playing")

                # Heart Icon Sync
                liked = LikedSongsManager.is_liked(title)
                self._heart_btn.setText("❤️" if liked else "♡")
                self._heart_btn.setStyleSheet("color: #ff3366; font-size: 18px; border: none; background: transparent;" if liked else "color: #b3b3b3; font-size: 18px; border: none; background: transparent;")
            else:
                self._deck_title_lbl.setText("No song playing")
                self._deck_artist_lbl.setText("Select a track to start")
                self._play_btn.setText("▶")
                self._waveform.set_active(False)
                self._heart_btn.setText("♡")

            # Progress & Seeking
            prog = self._player.get_playback_progress()
            pos = prog.get("position_sec", 0)
            dur = prog.get("duration_sec", 0)
            pct = prog.get("progress_pct", 0)

            pos_str = f"{int(pos // 60)}:{int(pos % 60):02d}"
            dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}" if dur else "0:00"

            self._time_pos_lbl.setText(pos_str)
            self._time_dur_lbl.setText(dur_str)

            if not self._seek_slider.isSliderDown():
                self._seek_slider.blockSignals(True)
                self._seek_slider.setValue(int(pct * 10) if pct else 0)
                self._seek_slider.blockSignals(False)

            # Shuffle & Repeat Active Highlights
            is_shuff = getattr(self._player, "_shuffle", False)
            self._shuffle_btn.setStyleSheet("color: #1db954; font-size: 12px; border: none; background: transparent;" if is_shuff else "color: #b3b3b3; font-size: 12px; border: none; background: transparent;")

            rep_mode = getattr(self._player, "_repeat", RepeatMode.OFF)
            if rep_mode == RepeatMode.ONE:
                self._repeat_btn.setText("🔂")
                self._repeat_btn.setStyleSheet("color: #1db954; font-size: 12px; border: none; background: transparent;")
            elif rep_mode == RepeatMode.ALL:
                self._repeat_btn.setText("🔁")
                self._repeat_btn.setStyleSheet("color: #1db954; font-size: 12px; border: none; background: transparent;")
            else:
                self._repeat_btn.setText("🔁")
                self._repeat_btn.setStyleSheet("color: #b3b3b3; font-size: 12px; border: none; background: transparent;")

            # Volume Sync
            vol = self._player.get_volume()
            if not self._vol_slider.isSliderDown():
                self._vol_slider.blockSignals(True)
                self._vol_slider.setValue(int(vol * 100))
                self._vol_slider.blockSignals(False)
        except Exception as e:
            logger.warning("Error updating player deck: %s", e)

    # ── Page Data Loaders ─────────────────────────────────────────────────────

    def _do_search(self):
        query = self._search_input.text().strip()
        if not query:
            return

        if self._search_worker and self._search_worker.isRunning():
            self._search_worker.quit()
            self._search_worker.wait()

        self._search_status_lbl.setText(f"Searching for '{query}'...")
        self._search_table.setRowCount(0)

        self._search_worker = _SearchWorker(query, self._player, parent=self)
        self._search_worker.finished.connect(self._on_search_finished)
        self._search_worker.failed.connect(self._on_search_failed)
        self._search_worker.start()

    def _on_search_finished(self, query: str, results: list):
        if not results:
            self._search_status_lbl.setText(f"No results found for '{query}'.")
            return

        self._search_status_lbl.setText(f"Top YouTube results for '{query}':")
        self._search_table.setRowCount(len(results))

        for row, r in enumerate(results):
            title = r.get("title", "Unknown")
            dur_sec = r.get("duration", 0)
            dur_str = f"{dur_sec // 60}:{dur_sec % 60:02d}" if dur_sec else "Stream"

            item_title = QTableWidgetItem(title)
            item_artist = QTableWidgetItem("YouTube Stream")
            item_dur = QTableWidgetItem(dur_str)

            self._search_table.setItem(row, 0, item_title)
            self._search_table.setItem(row, 1, item_artist)
            self._search_table.setItem(row, 2, item_dur)

            act_widget = QWidget()
            act_layout = QHBoxLayout(act_widget)
            act_layout.setContentsMargins(4, 0, 4, 0)
            act_layout.setSpacing(6)
            act_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

            play_b = QPushButton("▶")
            play_b.setFixedSize(26, 26)
            play_b.setCursor(Qt.CursorShape.PointingHandCursor)
            play_b.setToolTip("Play track")
            play_b.setStyleSheet("background-color: #1db954; color: #000; font-weight: bold; border-radius: 13px; border: none;")
            play_b.clicked.connect(partial(self._play_online_track, title))
            act_layout.addWidget(play_b)

            like_b = QPushButton("❤️")
            like_b.setFixedSize(26, 26)
            like_b.setCursor(Qt.CursorShape.PointingHandCursor)
            like_b.setToolTip("Add to Liked Songs")
            like_b.setStyleSheet("background-color: #282828; color: #ff3366; border-radius: 13px; border: none;")
            like_b.clicked.connect(partial(self._like_track_dict, {"title": title, "artist": "YouTube Stream"}))
            act_layout.addWidget(like_b)

            self._search_table.setCellWidget(row, 3, act_widget)

    def _on_search_failed(self, query: str, error_msg: str):
        self._search_status_lbl.setText(f"Search failed: {error_msg}")

    def _play_online_track(self, title: str):
        if self._stream_worker and self._stream_worker.isRunning():
            self._stream_worker.quit()
            self._stream_worker.wait()

        self._search_status_lbl.setText(f"Starting stream for '{title}'...")
        self._stream_worker = _StreamWorker(title, self._player, parent=self)
        self._stream_worker.finished.connect(self._on_stream_finished)
        self._stream_worker.failed.connect(self._on_stream_failed)
        self._stream_worker.start()

    def _on_stream_finished(self, title: str):
        self._search_status_lbl.setText(f"Streaming: '{title}'")
        self._update_player_deck()

    def _on_stream_failed(self, title: str, error_msg: str):
        self._search_status_lbl.setText(f"Failed to stream '{title}': {error_msg}")
        logger.warning("Failed to play online track '%s': %s", title, error_msg)

    def _like_track_dict(self, song_info: dict):
        msg = LikedSongsManager.add(song_info)
        self._load_liked_songs()
        QMessageBox.information(self, "Liked Songs", msg)

    def _load_local_library(self):
        try:
            import config
            music_dir = config.DATA_DIR / "music"

            self._library_table.setRowCount(0)
            if not music_dir.exists():
                return

            files = list(music_dir.glob("*.mp3")) + list(music_dir.glob("*.wav")) + list(music_dir.glob("*.flac"))
            self._library_table.setRowCount(len(files))

            for row, fp in enumerate(files):
                clean_title = fp.stem.replace("_", " ")
                size_mb = f"{fp.stat().st_size / (1024 * 1024):.1f} MB"

                self._library_table.setItem(row, 0, QTableWidgetItem(clean_title))
                self._library_table.setItem(row, 1, QTableWidgetItem(fp.name))
                self._library_table.setItem(row, 2, QTableWidgetItem(size_mb))

                act_widget = QWidget()
                act_layout = QHBoxLayout(act_widget)
                act_layout.setContentsMargins(4, 0, 4, 0)
                act_layout.setSpacing(4)
                act_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                play_b = QPushButton("▶ Play")
                play_b.setCursor(Qt.CursorShape.PointingHandCursor)
                play_b.setStyleSheet("background-color: #1db954; color: #000; font-weight: bold; border-radius: 10px; padding: 2px 10px; border: none;")
                play_b.clicked.connect(partial(self._play_local_file, str(fp)))
                act_layout.addWidget(play_b)

                self._library_table.setCellWidget(row, 3, act_widget)
        except Exception as e:
            logger.warning("Failed to load local library: %s", e)

    def _play_local_file(self, filepath: str):
        try:
            self._player.play_file(filepath)
            self._update_player_deck()
        except Exception as e:
            logger.warning("Failed to play file: %s", e)

    def _load_liked_songs(self):
        try:
            songs = LikedSongsManager.list()
            self._liked_table.setRowCount(len(songs))

            for row, s in enumerate(songs):
                title = s.get("title", "Unknown")
                artist = s.get("artist", "")

                self._liked_table.setItem(row, 0, QTableWidgetItem(title))
                self._liked_table.setItem(row, 1, QTableWidgetItem(artist if artist else "Unknown"))

                act_widget = QWidget()
                act_layout = QHBoxLayout(act_widget)
                act_layout.setContentsMargins(4, 0, 4, 0)
                act_layout.setSpacing(4)
                act_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                play_b = QPushButton("▶ Play")
                play_b.setCursor(Qt.CursorShape.PointingHandCursor)
                play_b.setStyleSheet("background-color: #1db954; color: #000; font-weight: bold; border-radius: 10px; padding: 2px 10px; border: none;")
                play_b.clicked.connect(partial(self._play_online_track, title))
                act_layout.addWidget(play_b)

                del_b = QPushButton("❌")
                del_b.setCursor(Qt.CursorShape.PointingHandCursor)
                del_b.setStyleSheet("background-color: transparent; color: #ff3366; border: none;")
                del_b.clicked.connect(partial(self._remove_liked_song, title))
                act_layout.addWidget(del_b)

                self._liked_table.setCellWidget(row, 2, act_widget)
        except Exception as e:
            logger.warning("Failed to load liked songs: %s", e)

    def _remove_liked_song(self, title: str):
        LikedSongsManager.remove(title)
        self._load_liked_songs()
        self._update_player_deck()

    def _play_all_liked_shuffled(self):
        from orchestrator.tools.native.music_player_tools import play_liked_songs
        play_liked_songs(shuffle=True)
        self._update_player_deck()

    def _load_playlists(self):
        try:
            temp_names = PlaylistManager.list_playlists()
            persistent_names = set(PlaylistManager.list_persistent())
            all_names = temp_names + sorted(persistent_names - set(temp_names))

            self._playlists_table.setRowCount(len(all_names))

            for row, name in enumerate(all_names):
                songs = PlaylistManager.get(name) or PlaylistManager.get_persistent(name)
                marker = " (Saved)" if name in persistent_names else " (Temp)"

                self._playlists_table.setItem(row, 0, QTableWidgetItem(name + marker))
                self._playlists_table.setItem(row, 1, QTableWidgetItem(f"{len(songs)} tracks"))

                act_widget = QWidget()
                act_layout = QHBoxLayout(act_widget)
                act_layout.setContentsMargins(4, 0, 4, 0)
                act_layout.setSpacing(4)
                act_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

                play_b = QPushButton("▶ Play")
                play_b.setCursor(Qt.CursorShape.PointingHandCursor)
                play_b.setStyleSheet("background-color: #1db954; color: #000; font-weight: bold; border-radius: 10px; padding: 2px 8px; border: none;")
                play_b.clicked.connect(partial(self._play_playlist, name))
                act_layout.addWidget(play_b)

                save_b = QPushButton("💾 Save")
                save_b.setCursor(Qt.CursorShape.PointingHandCursor)
                save_b.setStyleSheet("background-color: #282828; color: #00d4ff; font-weight: bold; border-radius: 10px; padding: 2px 8px; border: none;")
                save_b.clicked.connect(partial(self._save_playlist, name))
                act_layout.addWidget(save_b)

                del_b = QPushButton("❌")
                del_b.setCursor(Qt.CursorShape.PointingHandCursor)
                del_b.setStyleSheet("background-color: transparent; color: #ff3366; border: none;")
                del_b.clicked.connect(partial(self._delete_playlist, name))
                act_layout.addWidget(del_b)

                self._playlists_table.setCellWidget(row, 2, act_widget)
        except Exception as e:
            logger.warning("Failed to load playlists: %s", e)

    def _create_new_playlist_dialog(self):
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "New Playlist", "Enter Playlist Name:")
        if ok and name.strip():
            msg = PlaylistManager.create(name.strip())
            QMessageBox.information(self, "Playlist", msg)
            self._load_playlists()

    def _play_playlist(self, name: str):
        from orchestrator.tools.native.music_player_tools import play_playlist
        play_playlist(name)
        self._update_player_deck()

    def _save_playlist(self, name: str):
        if self._save_worker and self._save_worker.isRunning():
            QMessageBox.warning(self, "Save Playlist", "A playlist is already saving in the background. Please wait.")
            return

        self._save_worker = _SavePlaylistWorker(name, parent=self)
        self._save_worker.finished.connect(self._on_save_playlist_finished)
        self._save_worker.failed.connect(self._on_save_playlist_failed)
        self._save_worker.start()
        QMessageBox.information(self, "Save Playlist", f"Downloading songs for playlist '{name}' in the background...")

    def _on_save_playlist_finished(self, name: str, msg: str):
        QMessageBox.information(self, "Save Playlist Complete", msg)
        self._load_playlists()

    def _on_save_playlist_failed(self, name: str, error_msg: str):
        QMessageBox.critical(self, "Save Playlist Error", f"Failed to save playlist '{name}': {error_msg}")
        self._load_playlists()

    def _delete_playlist(self, name: str):
        msg = PlaylistManager.delete(name)
        self._load_playlists()

    def _load_history(self):
        try:
            songs = RecentlyPlayed.list(20)
            self._history_table.setRowCount(len(songs))

            for row, s in enumerate(songs):
                title = s.get("title", "Unknown")
                artist = s.get("artist", "")

                self._history_table.setItem(row, 0, QTableWidgetItem(title))
                self._history_table.setItem(row, 1, QTableWidgetItem(artist if artist else "Unknown"))

                play_b = QPushButton("▶ Replay")
                play_b.setCursor(Qt.CursorShape.PointingHandCursor)
                play_b.setStyleSheet("background-color: #1db954; color: #000; font-weight: bold; border-radius: 10px; padding: 2px 8px; border: none;")
                play_b.clicked.connect(partial(self._play_online_track, title))
                self._history_table.setCellWidget(row, 2, play_b)
        except Exception as e:
            logger.warning("Failed to load history: %s", e)

    def wheelEvent(self, event):
        """Scroll wheel over music window smoothly adjusts volume (+/- 5%)."""
        delta = event.angleDelta().y()
        if delta != 0:
            current_vol = self._vol_slider.value()
            step = 5 if delta > 0 else -5
            new_vol = max(0, min(100, current_vol + step))
            if new_vol != current_vol:
                self._vol_slider.setValue(new_vol)
                self._on_vol_changed(new_vol)
        super().wheelEvent(event)
