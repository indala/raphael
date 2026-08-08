"""
MusicPlayer — in-app music playback engine for Raphael.

Singleton class managing a song queue, background playback thread, streaming via
yt-dlp, chunked sounddevice playback, volume, seek, shuffle, repeat modes, and
playlist/library integration.

Thread safety:
  - All queue/state mutations: ``self._lock`` (RLock)
  - All ``sd.play()``/``sd.stop()`` calls: ``_AUDIO_LOCK`` (shared with TTS)
  - Stop/skip signalling: ``self._music_interrupted`` (Event) for music actions,
    ``_interrupted`` (from modules.tts) for global "stop Raphael"
"""

import logging
import os
import random
import subprocess
import threading
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from collections.abc import Callable

# pyrefly: ignore [missing-import]
import numpy as np

import sys

from modules.tts_engines import _AUDIO_LOCK
from modules.tts import _interrupted
import contextlib

logger = logging.getLogger(__name__)

CHUNK_SECONDS = 10            # seconds of audio per chunk during playback
STREAM_BUFFER_SECONDS = 3      # seconds of initial audio pre-buffer for streaming
MIN_PREBUF_SECONDS = 2         # minimum pre-buffer even on fast networks
MAX_PREBUF_SECONDS = 12        # maximum pre-buffer on very slow networks
BITRATE_FALLBACK_FACTOR = 0.5  # fallback to download if throughput < 50% of required
TEMP_DIR = Path(tempfile.gettempdir()) / "Raphael" / "temp_music"


# ── Network Monitor ────────────────────────────────────────────────────────


class NetworkMonitor:
    """Tracks throughput and jitter during streaming to enable adaptive buffering.

    Measures bytes/sec on the raw PCM pipe (ffmpeg output) and computes read-time
    variance to detect network jitter.  The required raw bitrate for 16-bit mono
    44.1 kHz audio is 44100 * 2 = 88 200 bytes/sec (~705 kbps).
    """

    REQUIRED_RAW_BPS = 44100 * 2  # bytes/sec for 16-bit mono 44.1 kHz

    def __init__(self) -> None:
        self._read_times: list[float] = []
        self._byte_counts: list[int] = []
        self._start_time: float = 0.0
        self._first_data_time: float = 0.0
        self._total_bytes: int = 0
        self._window_start: float = 0.0
        self._window_bytes: int = 0

    def start(self) -> None:
        self._start_time = time.time()
        self._first_data_time = 0.0
        self._window_start = self._start_time

    def record_read(self, nbytes: int) -> None:
        """Record a single pipe read for throughput/jitter calculation."""
        now = time.time()
        if self._first_data_time == 0.0 and nbytes > 0:
            self._first_data_time = now
            self._window_start = now

        elapsed = now - self._window_start
        self._total_bytes += nbytes
        self._window_bytes += nbytes

        # Keep a sliding window of recent read times (last 20 reads)
        if elapsed > 0:
            self._read_times.append(elapsed)
            self._byte_counts.append(nbytes)
            if len(self._read_times) > 20:
                self._read_times.pop(0)
                self._byte_counts.pop(0)
            self._window_start = now

    @property
    def throughput_bps(self) -> float:
        """Measured throughput in bytes/sec (raw PCM)."""
        if self._first_data_time == 0.0:
            return float(self.REQUIRED_RAW_BPS)
        elapsed = time.time() - self._first_data_time
        if elapsed < 1.0:
            return float(self.REQUIRED_RAW_BPS)  # not enough data yet
        return self._total_bytes / elapsed

    @property
    def throughput_ratio(self) -> float:
        """Throughput as a fraction of required bitrate (>1.0 = fast enough)."""
        return self.throughput_bps / self.REQUIRED_RAW_BPS

    @property
    def jitter_ms(self) -> float:
        """Standard deviation of recent read times in milliseconds."""
        if len(self._read_times) < 3:
            return 0.0
        import statistics
        return statistics.stdev(self._read_times) * 1000

    def recommended_prebuf_seconds(self) -> float:
        """Calculate adaptive pre-buffer duration based on measured throughput.

        If throughput >= required bitrate: use minimum buffer (fast start).
        If throughput < required bitrate: scale up buffer proportionally.
        """
        ratio = self.throughput_ratio
        if ratio >= 1.0:
            return MIN_PREBUF_SECONDS
        # Scale inversely: half speed → 2x buffer, capped at max
        recommended = MIN_PREBUF_SECONDS / max(ratio, 0.1)
        return min(recommended, MAX_PREBUF_SECONDS)

    def should_fallback_to_download(self) -> bool:
        """Return True if sustained throughput is too low for streaming."""
        # Only check after at least 5 seconds of active data transfer and at least 10 chunks read
        if self._first_data_time == 0.0 or len(self._read_times) < 10:
            return False
        elapsed = time.time() - self._first_data_time
        if elapsed < 5.0:
            return False
        return self.throughput_ratio < BITRATE_FALLBACK_FACTOR

    def recommended_chunk_frames(self) -> int:
        """Adaptive chunk size: larger chunks when jitter is high (fewer syscalls)."""
        if self.jitter_ms > 50:
            return 8192   # ~186 ms at 44100 Hz — fewer syscalls, smoother
        if self.jitter_ms > 20:
            return 4096   # default ~93 ms
        return 2048        # low jitter → smaller chunks for responsiveness


def cleanup_temp_files(max_age_days: int = 7) -> int:
    """Delete temp-downloaded music files older than *max_age_days* days.

    Temp downloads accumulate in ``%TEMP%/Raphael/temp_music/`` and nothing
    else removes them; anything older than a week is considered stale.
    Returns the number of files deleted.
    """
    if not TEMP_DIR.exists():
        return 0
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for fp in TEMP_DIR.iterdir():
        try:
            if fp.is_file() and fp.stat().st_mtime < cutoff:
                fp.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("Cleaned up %d stale temp song file(s) from %s", removed, TEMP_DIR)
    return removed


# ── Enums & Data ────────────────────────────────────────────────────────────


class PlaybackState(Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"


class RepeatMode(Enum):
    OFF = "off"
    ONE = "one"
    ALL = "all"


@dataclass
class SongEntry:
    """Represents a single song in the queue."""
    title: str
    artist: str = ""
    filepath: Path | None = None
    duration_sec: float = 0.0
    samples: np.ndarray | None = None          # decoded PCM float32 [-1, 1]
    sample_rate: int = 0
    stream_proc: subprocess.Popen | None = None  # set for streaming mode


def _config_data_dir() -> Path:
    """Lazy import config to avoid circular imports."""
    import config
    return Path(getattr(config, "DATA_DIR", "."))


# ── FFmpeg path resolution ──────────────────────────────────────────────────


def _ffmpeg_path() -> str:
    """Resolve ffmpeg.exe — bundled next to main exe, or fallback to PATH."""
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "ffmpeg.exe"
    else:
        bundled = Path(__file__).resolve().parent.parent / "bin" / "ffmpeg.exe"
    return str(bundled) if bundled.exists() else "ffmpeg"


def _ffprobe_path() -> str:
    """Resolve ffprobe.exe — bundled next to main exe, or fallback to PATH."""
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / "ffprobe.exe"
    else:
        bundled = Path(__file__).resolve().parent.parent / "bin" / "ffprobe.exe"
    return str(bundled) if bundled.exists() else "ffprobe"


def _ytdlp_cmd() -> list[str]:
    """Resolve yt-dlp executable or fallback to python -m yt_dlp with ffmpeg location."""
    import shutil
    ffmpeg_dir = str(Path(_ffmpeg_path()).parent)
    base = []
    yt_exe = shutil.which("yt-dlp")
    if yt_exe:
        base = [yt_exe]
    else:
        user_scripts = Path(sys.prefix) / "Scripts" / "yt-dlp.exe"
        if user_scripts.exists():
            base = [str(user_scripts)]
        else:
            appdata = os.environ.get("APPDATA")
            if appdata:
                py_ver = f"Python{sys.version_info.major}{sys.version_info.minor}"
                appdata_scripts = Path(appdata) / "Python" / py_ver / "Scripts" / "yt-dlp.exe"
                if appdata_scripts.exists():
                    base = [str(appdata_scripts)]
            if not base:
                base = [sys.executable, "-m", "yt_dlp"]
    return base + ["--ffmpeg-location", ffmpeg_dir]



def _parse_seconds(val: float | str) -> float:
    """Parse float seconds or MM:SS / HH:MM:SS timestamp strings."""
    if isinstance(val, (int, float)):
        return float(val)
    s_val = str(val).strip()
    if ":" in s_val:
        parts = s_val.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        if len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
    return float(s_val)


# ── MusicPlayer ─────────────────────────────────────────────────────────────


class MusicPlayer:
    """Singleton music player — queue, chunked playback, streaming, full controls."""

    _instance = None
    _singleton_lock = threading.Lock()

    def __init__(self) -> None:
        if MusicPlayer._instance is not None:
            raise RuntimeError("Use MusicPlayer.get_instance()")
        self._queue: list[SongEntry] = []
        self._current_index: int = 0
        self._history: list[SongEntry] = []
        self._repeat: RepeatMode = RepeatMode.OFF
        self._shuffle: bool = False
        self._volume: float = 0.7
        self._playhead_frames: int = 0
        self._state: PlaybackState = PlaybackState.IDLE
        self._thread: threading.Thread | None = None
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._music_interrupted = threading.Event()
        self._seek_stream_sec: float | None = None
        self._active_stream_accumulated: list[np.ndarray] = []
        self._lock = threading.RLock()
        self._state_callbacks: list[Callable] = []
        TEMP_DIR.mkdir(parents=True, exist_ok=True)
        cleanup_temp_files()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def on_state_change(self, callback: Callable):
        """Register a callback fired when PlaybackState changes.
        Callback receives (old_state: PlaybackState, new_state: PlaybackState)."""
        with self._lock:
            self._state_callbacks.append(callback)

    def _notify_state(self, old: PlaybackState, new: PlaybackState):
        for cb in self._state_callbacks:
            try:
                cb(old, new)  # type: ignore[misc]
            except Exception:
                logger.exception("State callback error")

    # ── Public API: Playback Control ────────────────────────────────────────

    def play(self) -> str:
        """Start or resume playback."""
        with self._lock:
            old = self._state
            if self._state == PlaybackState.PAUSED:
                self._state = PlaybackState.PLAYING
                self._pause_event.set()
                self._notify_state(old, self._state)
                return "Resumed."
            if self._state == PlaybackState.IDLE and self._queue:
                self._current_index = 0
                self._start_bg_thread()
                return f"Playing: {self._queue[0].title}"
            if self._state == PlaybackState.PLAYING:
                return "Already playing."
            return "Queue is empty."

    def pause(self) -> str:
        with self._lock:
            if self._state != PlaybackState.PLAYING:
                return "Nothing to pause."
            old = self._state
            self._state = PlaybackState.PAUSED
            self._pause_event.clear()
            self._notify_state(old, self._state)
            return "Paused."

    def resume(self) -> str:
        return self.play()

    def stop(self) -> str:
        """Stop playback, clear queue, reset everything."""
        with self._lock:
            old = self._state
            self._music_interrupted.set()
            self._state = PlaybackState.STOPPED
            self._pause_event.set()
            self._queue.clear()
            self._history.clear()
            self._current_index = 0
            self._playhead_frames = 0
            self._notify_state(old, self._state)
            return "Stopped and queue cleared."

    def next(self) -> str:
        """Skip to next song."""
        with self._lock:
            if self._state in (PlaybackState.IDLE, PlaybackState.STOPPED):
                return "Nothing playing."
            self._music_interrupted.set()
            return "Skipping to next song..."

    def previous(self) -> str:
        """Go back to previous song via history stack."""
        with self._lock:
            if not self._history:
                return "No previous song."
            # Insert history entry before current in queue
            prev = self._history.pop()
            self._queue.insert(self._current_index, prev)
            self._music_interrupted.set()
            return "Going back..."

    def seek(self, position_sec: float | str) -> str:
        """Jump to a position (seconds or MM:SS) in the current song, supporting both cached and live streaming modes."""
        try:
            sec = _parse_seconds(position_sec)
        except (ValueError, TypeError):
            return f"Invalid position format: '{position_sec}'"

        sec = max(0.0, sec)
        m, s = int(sec // 60), int(sec % 60)
        time_str = f"{m}:{s:02d}"

        with self._lock:
            if self._current_index >= len(self._queue):
                return "No song playing."
            entry = self._queue[self._current_index]

            # Mode 1: Fully decoded or cached track
            if entry.samples is not None and entry.sample_rate > 0:
                max_frames = len(entry.samples)
                target = int(sec * entry.sample_rate)
                self._playhead_frames = max(0, min(target, max_frames - 1))
                self._music_interrupted.set()
                return f"Jumped to {time_str}."

            # Mode 2: Live streaming track — check if target is within already buffered stream PCM
            buffered_frames = sum(len(c) for c in self._active_stream_accumulated)
            buffered_sec = buffered_frames / 44100.0 if buffered_frames > 0 else 0.0

            if sec <= buffered_sec and buffered_frames > 0:
                # Seek within already buffered stream audio
                entry.samples = np.concatenate(self._active_stream_accumulated)
                entry.sample_rate = 44100
                max_frames = len(entry.samples)
                target = int(sec * 44100)
                self._playhead_frames = max(0, min(target, max_frames - 1))
                self._music_interrupted.set()
                return f"Jumped to {time_str}."

            # Mode 3: Seek beyond currently buffered stream -> seek via ffmpeg timestamp
            self._seek_stream_sec = sec
            self._playhead_frames = int(sec * 44100)
            self._music_interrupted.set()

            # Respawn stream process starting at target timestamp if title exists
            if entry.title:
                cmd = _ytdlp_cmd() + [
                    "-f", "ba", "-o", "-",
                    f"ytsearch1:{entry.title}",
                    "--no-playlist", "--restrict-filenames",
                ]
                with contextlib.suppress(Exception):
                    if entry.stream_proc is not None:
                        entry.stream_proc.kill()
                try:
                    entry.stream_proc = subprocess.Popen(
                        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        bufsize=2**20,
                    )
                except Exception as e:
                    logger.warning("Failed to respawn stream proc for seek: %s", e)

            return f"Seeking live stream to {time_str}..."

    def set_volume(self, level: float | str) -> str:
        try:
            val = float(level)
            if val > 1.0:
                val /= 100.0
            val = max(0.0, min(1.0, val))
            self._volume = val
            return f"Volume set to {int(val * 100)}%."
        except Exception:
            return f"Invalid volume level: {level}"

    def get_volume(self) -> float:
        return self._volume

    def set_repeat(self, mode: str) -> str:
        mode = mode.lower()
        if mode not in ("off", "one", "all"):
            return "Invalid mode. Use 'off', 'one', or 'all'."
        self._repeat = RepeatMode(mode)
        return f"Repeat mode: {mode}."

    def set_shuffle(self, enabled: bool) -> str:
        self._shuffle = enabled
        if enabled:
            self._shuffle_remaining()
        return f"Shuffle {'enabled' if enabled else 'disabled'}."

    # ── Public API: Song / Playlist / Queue ─────────────────────────────────

    def play_song(self, query: str) -> str:
        """Play a single song: check local library, then download from YouTube."""
        with self._lock:
            self.stop()
            entry = self._resolve_local(query)
            if entry is None:
                entry = self._download_single(query)
            if entry is None:
                return f"Could not find or download '{query}'."
            self._queue = [entry]
            self._current_index = 0
            self._start_bg_thread()
            return f"Now playing: {entry.title}"

    def play_playlist(self, query: str, count: int = 5) -> str:
        """Download and enqueue multiple songs matching a broad query."""
        with self._lock:
            self.stop()
            entries = self._download_multiple(query, count)
            if not entries:
                return f"Could not find songs for '{query}'."
            self._queue = entries
            self._current_index = 0
            if self._shuffle:
                self._shuffle_remaining()
            self._start_bg_thread()
            return f"Queued {len(entries)} songs. Now playing: {entries[0].title}"

    @staticmethod
    def _resolve_youtube_info(query: str) -> tuple[str, str, float]:
        """Fetch exact YouTube video title, artist/channel, and duration_sec for a search query."""
        try:
            cmd = _ytdlp_cmd() + [
                "--print", "%(title)s|||%(uploader)s|||%(duration)s",
                f"ytsearch1:{query}",
                "--no-playlist",
            ]
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r.returncode == 0 and "|||" in r.stdout:
                line = r.stdout.strip().splitlines()[0]
                if "|||" in line:
                    parts = line.split("|||")
                    title = parts[0].strip() if parts[0].strip() else query
                    artist = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "YouTube"
                    dur = 0.0
                    if len(parts) > 2 and parts[2].strip():
                        with contextlib.suppress(ValueError):
                            dur = float(parts[2].strip())
                    return title, artist, dur
        except Exception:
            pass
        return query, "YouTube Stream", 0.0

    def stream_song(self, query: str) -> str:
        """Stream a song directly from YouTube with exact title and duration resolution."""
        real_title, real_artist, real_dur = self._resolve_youtube_info(query)
        with self._lock:
            self.stop()
            cmd = _ytdlp_cmd() + [
                "-f", "ba", "-o", "-",
                f"ytsearch1:{query}",
                "--no-playlist", "--restrict-filenames",
            ]
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    bufsize=2**20,
                )
            except FileNotFoundError:
                return "yt-dlp not found. Please install it."
            entry = SongEntry(
                title=real_title,
                artist=real_artist,
                duration_sec=real_dur,
                stream_proc=proc,
            )
            self._queue = [entry]
            self._current_index = 0
            self._start_bg_thread()
            dur_msg = f" ({int(real_dur // 60)}:{int(real_dur % 60):02d})" if real_dur > 0 else ""
            return f"Streaming: '{real_title}' by {real_artist}{dur_msg}."

    def stream_playlist(self, query: str, count: int = 5) -> str:
        """Stream multiple songs in sequence from YouTube search."""
        with self._lock:
            self.stop()
            entries = [
                SongEntry(title=f"{query} #{i+1}", artist="YouTube Stream")
                for i in range(count)
            ]
            self._queue = entries
            self._current_index = 0
            self._start_bg_thread(playlist_query=query)
            return f"Streaming {count} songs matching '{query}'"

    def add_to_queue(self, song_name: str) -> str:
        """Resolve and append a song to the playback queue."""
        entry = self._resolve_local(song_name)
        if entry is None:
            entry = self._download_single(song_name)
        if entry is None:
            return f"Could not find '{song_name}'."
        with self._lock:
            self._queue.append(entry)
            return f"Added '{entry.title}' to queue."

    def clear_queue(self) -> str:
        with self._lock:
            remaining = self._queue[self._current_index + 1:]
            self._queue = self._queue[:self._current_index + 1]
            return f"Cleared {len(remaining)} queued song(s)."

    def show_queue(self) -> str:
        with self._lock:
            if not self._queue:
                return "Queue is empty."
            lines = []
            for i, e in enumerate(self._queue):
                marker = "→ " if i == self._current_index else "  "
                lines.append(f"{marker}{i+1}. {e.title}")
            return "\n".join(lines)

    # ── Public API: Info ────────────────────────────────────────────────────

    def get_current_song(self) -> dict:
        with self._lock:
            if not self._queue or self._current_index >= len(self._queue):
                return {"status": "no_song", "title": None}
            e = self._queue[self._current_index]
            return {
                "status": self._state.value if self._state == PlaybackState.PLAYING else "paused",
                "title": e.title,
                "artist": e.artist,
                "duration_sec": e.duration_sec,
                "source": "stream" if e.stream_proc else ("local" if e.filepath else "downloaded"),
            }

    def get_playback_status(self) -> dict:
        with self._lock:
            cur = self.get_current_song()
            return {
                "state": self._state.value,
                "repeat": self._repeat.value,
                "shuffle": self._shuffle,
                "volume": self._volume,
                "queue_length": len(self._queue),
                "current_index": self._current_index if self._queue else -1,
                **cur,
            }

    def get_playback_progress(self) -> dict:
        with self._lock:
            if self._current_index >= len(self._queue):
                return {"position_sec": 0, "duration_sec": 0, "progress_pct": 0}
            e = self._queue[self._current_index]
            pos = 0.0
            if e.samples is not None and e.sample_rate > 0:
                pos = self._playhead_frames / e.sample_rate
            dur = e.duration_sec
            pct = round(pos / dur * 100, 1) if dur > 0 else 0
            return {"position_sec": pos, "duration_sec": dur, "progress_pct": pct}

    def search_online(self, query: str, max_results: int = 5) -> list[dict]:
        """Search YouTube for songs and return metadata without playing."""
        results = []
        try:
            cmd = _ytdlp_cmd() + [
                "--flat-playlist", "--dump-json",
                f"ytsearch{max_results}:{query}",
                "--no-playlist",
            ]
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            import json
            for line in out.stdout.strip().splitlines():
                if not line.strip():
                    continue
                data = json.loads(line)
                results.append({
                    "title": data.get("title", "Unknown"),
                    "duration": data.get("duration", 0),
                    "url": f"https://youtube.com/watch?v={data.get('id', '')}",
                })
        except Exception as e:
            logger.error("search_online failed: %s", e)
        return results

    # ── Public API: Local Library ───────────────────────────────────────────

    def scan_local_library(self) -> list[SongEntry]:
        """Scan configured local music directories for audio files."""
        from audio.music_metadata import extract_title, extract_artist
        audio_ext = {".mp3", ".wav", ".m4a", ".flac", ".webm", ".opus"}
        dirs = [
            Path.home() / "Music",
            _config_data_dir() / "music",
        ]
        found = []
        for d in dirs:
            if not d.exists():
                continue
            for fp in sorted(d.rglob("*")):
                if fp.is_file() and fp.suffix.lower() in audio_ext:
                    found.append(SongEntry(
                        title=extract_title(fp),
                        artist=extract_artist(fp),
                        filepath=fp,
                    ))
        return found

    def add_to_library(self, song_name: str) -> str:
        """Download a song and save it permanently to the local music library."""
        from audio.music_metadata import extract_title
        entry = self._download_single(song_name)
        if entry is None or entry.filepath is None:
            return f"Could not download '{song_name}'."
        music_dir = _config_data_dir() / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        dest = music_dir / entry.filepath.name
        shutil.copy2(str(entry.filepath), str(dest))
        return f"Saved '{extract_title(dest)}' to your library."

    def remove_from_library(self, song_name: str) -> str:
        """Remove a matching song from the local music library."""
        music_dir = _config_data_dir() / "music"
        if not music_dir.exists():
            return "Local library is empty."
        words = set(song_name.lower().split())
        best = None
        best_score = 0
        for fp in music_dir.iterdir():
            if fp.is_file():
                w = set(fp.stem.lower().replace("_", " ").replace("-", " ").split())
                overlap = words.intersection(w)
                if overlap and len(overlap) > best_score:
                    best_score = len(overlap)
                    best = fp
        if best is None:
            return f"Could not find '{song_name}' in library."
        best.unlink()
        return f"Removed '{best.stem}' from library."

    # ── Internal: Background Thread ─────────────────────────────────────────

    def _start_bg_thread(self, playlist_query: str | None = None):
        """Start the background playback loop in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        old = self._state
        self._state = PlaybackState.PLAYING
        self._playhead_frames = 0
        self._music_interrupted.clear()
        self._pause_event.set()
        self._thread = threading.Thread(
            target=self._playback_loop,
            args=(playlist_query,),
            daemon=True,
        )
        self._thread.start()
        self._notify_state(old, self._state)

    def _playback_loop(self, playlist_query: str | None = None):
        """Main loop — iterates the queue, handles download/decode/stream/play."""
        try:
            while True:
                # 🛑 Check stop condition
                with self._lock:
                    if self._state == PlaybackState.STOPPED:
                        break
                    if self._current_index >= len(self._queue):
                        if self._repeat == RepeatMode.ALL:
                            self._current_index = 0
                            self._shuffle_remaining()
                        else:
                            old = self._state
                            self._state = PlaybackState.IDLE
                            self._notify_state(old, self._state)
                            break
                    entry = self._queue[self._current_index]

                # Stream mode — pass entry to cache PCM on completion
                if entry.stream_proc is not None:
                    start_sec = 0.0
                    with self._lock:
                        if self._seek_stream_sec is not None:
                            start_sec = self._seek_stream_sec
                            self._seek_stream_sec = None

                    result = self._stream_from_proc(entry.stream_proc, entry, start_sec=start_sec)
                    if result is False:
                        # Adaptive streaming fell back to download — kill stream
                        # proc and re-resolve via download
                        with contextlib.suppress(Exception):
                            entry.stream_proc.kill()
                        entry.stream_proc = None
                        logger.info("Fallback: downloading '%s' instead of streaming.", entry.title)
                        downloaded = self._download_single(entry.title)
                        if downloaded is not None:
                            entry = downloaded
                        if entry.filepath is None:
                            logger.warning("Fallback download failed for '%s', skipping.", entry.title)
                            with self._lock:
                                self._advance()
                            continue
                        self._download_and_decode(entry)
                        self._play_entry(entry)
                    with self._lock:
                        if self._music_interrupted.is_set():
                            # Interrupted (seek/replay) — entry is now cached,
                            # re-play from the new _playhead_frames
                            self._music_interrupted.clear()
                        else:
                            self._advance()
                    continue

                # Playlist streaming mode
                if playlist_query and entry.samples is None:
                    self._stream_playlist_item(entry, self._current_index, playlist_query)
                    with self._lock:
                        if self._music_interrupted.is_set():
                            self._music_interrupted.clear()
                        self._advance()
                    continue

                # Download + decode if needed
                if entry.samples is None:
                    if entry.filepath is None and entry.title:
                        # No filepath → stream on-demand (playlist entries)
                        logger.info("Streaming: %s", entry.title)
                        self._stream_playlist_item(entry, 0, entry.title)
                        with self._lock:
                            if self._music_interrupted.is_set():
                                self._music_interrupted.clear()
                            self._advance()
                        continue
                    logger.info("Downloading + decoding: %s", entry.title)
                    self._download_and_decode(entry)
                    if self._music_interrupted.is_set():
                        self._music_interrupted.clear()
                        with self._lock:
                            self._current_index += 1
                        continue

                # Play the decoded song
                self._play_entry(entry)

                # 🛑 Check global interrupt (stop Raphael) — don't advance
                if _interrupted.is_set():
                    with self._lock:
                        old = self._state
                        self._queue.clear()
                        self._state = PlaybackState.IDLE
                        self._notify_state(old, self._state)
                    _interrupted.clear()
                    return

                # Advance to next
                with self._lock:
                    if self._repeat == RepeatMode.ONE:
                        self._playhead_frames = 0
                        self._history.append(entry)
                        continue
                    self._history.append(entry)
                    self._current_index += 1
                    if self._shuffle and self._current_index < len(self._queue):
                        self._shuffle_remaining()

        except Exception as e:
            logger.error("Playback loop error: %s", e)
        finally:
            with self._lock:
                if self._state != PlaybackState.STOPPED:
                    new = PlaybackState.IDLE
                    old = self._state
                    self._state = new
                    self._notify_state(old, new)

    def _advance(self):
        """Advance queue index, respecting ALL repeat. Called under lock."""
        if self._repeat == RepeatMode.ALL and self._current_index + 1 >= len(self._queue):
            self._current_index = 0
            self._shuffle_remaining()
        else:
            self._current_index += 1

    # ── Internal: Playback ──────────────────────────────────────────────────

    def _play_entry(self, entry: SongEntry):
        """Play a fully-decoded song entry in chunks under _AUDIO_LOCK."""
        if entry.samples is None or entry.sample_rate <= 0:
            return
        sr = entry.sample_rate
        total = len(entry.samples)
        cf = int(CHUNK_SECONDS * sr)
        off = min(self._playhead_frames, total - 1) if self._playhead_frames < total else 0

        while off < total:
            # ── Interrupt checks between chunks ──
            if self._music_interrupted.is_set():
                self._music_interrupted.clear()
                return
            if _interrupted.is_set():
                return

            # ── Pause handling ──
            if self._state == PlaybackState.PAUSED:
                while self._state == PlaybackState.PAUSED:
                    if self._music_interrupted.is_set():
                        self._music_interrupted.clear()
                        return
                    if _interrupted.is_set():
                        return
                    self._pause_event.wait(0.05)
                continue  # type: ignore[unreachable]

            end = min(off + cf, total)
            chunk = entry.samples[off:end].astype(np.float32) * self._volume

            with _AUDIO_LOCK:
                # pyrefly: ignore [missing-import]
                import sounddevice as sd
                sd.stop()
                sd.play(chunk, sr)
                while sd.get_stream().active:
                    if self._music_interrupted.is_set() or _interrupted.is_set():
                        sd.stop()
                        self._music_interrupted.clear()
                        return
                    if self._state == PlaybackState.PAUSED:
                        sd.stop()  # type: ignore[unreachable]
                        off = self._playhead_frames  # preserve position
                        break
                    time.sleep(0.05)
                else:
                    off = end
                    self._playhead_frames = off

    def _stream_from_proc(self, proc: subprocess.Popen, entry: SongEntry | None = None, start_sec: float = 0.0):
        """Stream and play audio from a yt-dlp pipe via ffmpeg → raw PCM → sounddevice.

        Uses a persistent ``sd.OutputStream`` to avoid the open/close glitching
        from calling ``sd.play()`` / ``sd.stop()`` per chunk.

        Adaptively adjusts pre-buffer size and chunk size based on measured
        network throughput and jitter.  Falls back to returning ``False`` if
        sustained bandwidth is too low (caller should switch to download mode).
        """
        # pyrefly: ignore [missing-import]
        import sounddevice as sd
        accumulated: list[np.ndarray] = []
        with self._lock:
            self._active_stream_accumulated = accumulated

        monitor = NetworkMonitor()
        monitor.start()
        fallback = False

        try:
            # Pipe yt-dlp output through ffmpeg → raw mono PCM
            ffmpeg_cmd = [_ffmpeg_path()]
            if start_sec > 0:
                ffmpeg_cmd.extend(["-ss", f"{start_sec:.2f}"])
            ffmpeg_cmd.extend(["-i", "-", "-f", "s16le", "-ac", "1", "-ar", "44100", "-"])

            ffmpeg_proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=proc.stdout, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            proc.stdout.close()  # type: ignore[union-attr]

            # ── Adaptive pre-buffer: measure throughput before playback ──
            # Start with minimum buffer, expand if network is slow
            prebuf_target = int(MIN_PREBUF_SECONDS * 44100 * 2)  # bytes
            prebuf_bytes = bytearray()
            adaptive_chunk = 4096 * 2  # start with default chunk size (bytes)

            while len(prebuf_bytes) < prebuf_target:
                chunk = ffmpeg_proc.stdout.read(adaptive_chunk)  # type: ignore[union-attr]
                if not chunk:
                    break
                prebuf_bytes.extend(chunk)
                monitor.record_read(len(chunk))

                # Recalculate target based on measured throughput
                if monitor.throughput_ratio < 1.0 and len(prebuf_bytes) >= int(MIN_PREBUF_SECONDS * 44100 * 2):
                    new_target = int(monitor.recommended_prebuf_seconds() * 44100 * 2)
                    prebuf_target = max(prebuf_target, new_target)

                # Check for fallback during pre-buffer phase
                if monitor.should_fallback_to_download():
                    logger.warning("Network too slow for streaming (%.0f%% throughput), "
                                   "falling back to download.", monitor.throughput_ratio * 100)
                    fallback = True
                    break

            if fallback:
                return False  # signal caller to use download mode

            if prebuf_bytes:
                raw = np.frombuffer(bytes(prebuf_bytes), dtype=np.int16).astype(np.float32) / 32768.0
                accumulated.append(raw.copy())
                self._playhead_frames += len(raw)

            # Use float latency (0.1s) for glitch-resistant playback (avoids CFFI string latency crash)
            stream = sd.OutputStream(samplerate=44100, channels=1,
                                     dtype="float32", latency=0.1)
            vol = float(self._volume)
            with _AUDIO_LOCK:
                stream.start()
                if prebuf_bytes:
                    stream.write((raw * vol).astype(np.float32))

            try:
                while True:
                    if self._music_interrupted.is_set() or _interrupted.is_set():
                        break
                    if self._state == PlaybackState.PAUSED:
                        while self._state == PlaybackState.PAUSED:
                            self._pause_event.wait(0.05)
                            if self._music_interrupted.is_set() or _interrupted.is_set():
                                break
                        continue

                    # Adaptive chunk size based on jitter
                    chunk_frames = monitor.recommended_chunk_frames()
                    raw_bytes = ffmpeg_proc.stdout.read(chunk_frames * 2)  # type: ignore[union-attr]
                    if not raw_bytes:
                        break

                    monitor.record_read(len(raw_bytes))

                    # int16 → float32 mono
                    raw = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    accumulated.append(raw.copy())

                    self._playhead_frames += len(raw)
                    # Write outside _AUDIO_LOCK — dedicated OutputStream won't conflict
                    stream.write((raw * vol).astype(np.float32))
            finally:
                with _AUDIO_LOCK:
                    stream.stop()
                    stream.close()

        except Exception as e:
            logger.error("Stream decode error: %s", e)
        finally:
            with self._lock:
                self._active_stream_accumulated = []
            with contextlib.suppress(Exception):
                proc.kill()
            with contextlib.suppress(Exception):
                ffmpeg_proc.kill()

        # Cache accumulated PCM back to the entry for seek/replay
        if entry is not None and accumulated:
            entry.samples = np.concatenate(accumulated)
            entry.sample_rate = 44100
            entry.duration_sec = len(entry.samples) / 44100
            entry.stream_proc = None
            logger.info("Cached stream: %s (%.1fs) [throughput: %.0f%%, jitter: %.0fms]",
                        entry.title, entry.duration_sec,
                        monitor.throughput_ratio * 100, monitor.jitter_ms)

        return not fallback

    def _stream_playlist_item(self, entry: SongEntry, index: int, base_query: str):
        """Run a single yt-dlp stream for one item in a playlist query.

        Falls back to download mode if adaptive streaming detects low bandwidth.
        """
        q = base_query
        if index > 0:
            q = f"{base_query} #{index+1}"
        logger.info("Playlist stream %d: %s", index + 1, q)
        try:
            proc = subprocess.Popen(
                _ytdlp_cmd() + ["-f", "ba", "-o", "-",
                 f"ytsearch1:{q}",
                 "--no-playlist", "--restrict-filenames"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            result = self._stream_from_proc(proc, entry)
            if result is False:
                # Adaptive streaming fell back — download instead
                logger.info("Playlist item %d: falling back to download.", index + 1)
                resolved = self._resolve_local(q)
                if resolved is None or resolved.filepath is None:
                    resolved = self._download_single(q)
                if resolved is not None and resolved.filepath is not None:
                    entry.filepath = resolved.filepath
                    self._download_and_decode(entry)
        except Exception as e:
            logger.error("Playlist item %d failed: %s", index, e)

    # ── Internal: Download & Decode ─────────────────────────────────────────

    @staticmethod
    def _probe_duration(filepath: Path) -> float:
        """Quickly get audio duration via ffprobe (no full decode)."""
        try:
            r = subprocess.run(
                [_ffprobe_path(), "-v", "quiet", "-print_format", "json",
                 "-show_format", str(filepath)],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                import json
                data = json.loads(r.stdout)
                return float(data["format"]["duration"])
        except Exception:
            pass
        return 0.0

    def _resolve_local(self, query: str) -> SongEntry | None:
        """Search local music libraries for a matching song."""
        from audio.music_metadata import extract_title, extract_artist
        audio_ext = {".mp3", ".wav", ".m4a", ".flac", ".webm", ".opus"}
        dirs = [
            Path.home() / "Music",
            _config_data_dir() / "music",
        ]
        words = set(query.lower().split())
        best = None
        best_score = 0

        for d in dirs:
            if not d.exists():
                continue
            for fp in d.rglob("*"):
                if fp.is_file() and fp.suffix.lower() in audio_ext:
                    w = set(fp.stem.lower().replace("_", " ").replace("-", " ").split())
                    overlap = words.intersection(w)
                    if overlap and len(overlap) > best_score:
                        best_score = len(overlap)
                        best = fp

        if best and best_score >= len(words) * 0.5:
            return SongEntry(
                title=extract_title(best),
                artist=extract_artist(best),
                filepath=best,
                duration_sec=self._probe_duration(best),
            )
        return None

    def _download_single(self, query: str) -> SongEntry | None:
        """Download one song from YouTube to temp dir."""
        from audio.music_metadata import extract_title, extract_artist
        cmd = _ytdlp_cmd() + [
            f"ytsearch1:{query}",
            "-f", "ba",
            "-o", f"{TEMP_DIR}/%(title)s_%(id)s.%(ext)s",
            "--no-playlist", "--restrict-filenames",
            "--extract-audio", "--audio-format", "mp3",
            "--print", "after_move:filepath",
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
            lines = r.stdout.strip().splitlines()
            fp = lines[-1].strip() if lines else None
            if not fp or not os.path.exists(fp):
                return None
            p = Path(fp)
            return SongEntry(title=extract_title(p), artist=extract_artist(p), filepath=p,
                             duration_sec=self._probe_duration(p))
        except subprocess.TimeoutExpired:
            logger.error("Download timed out for '%s'", query)
            return None
        except Exception as e:
            logger.error("Download failed for '%s': %s", query, e)
            return None

    def _download_multiple(self, query: str, count: int) -> list[SongEntry]:
        """Download up to *count* songs matching *query*."""
        from audio.music_metadata import extract_title, extract_artist
        entries = []
        cmd = _ytdlp_cmd() + [
            f"ytsearch{count}:{query}",
            "-f", "ba",
            "-o", f"{TEMP_DIR}/%(title)s_%(id)s.%(ext)s",
            "--no-playlist", "--restrict-filenames",
            "--extract-audio", "--audio-format", "mp3",
            "--print", "after_move:filepath",
            "--max-downloads", str(count),
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
            for line in r.stdout.strip().splitlines():
                fp = line.strip()
                if fp and os.path.exists(fp):
                    p = Path(fp)
                    entries.append(SongEntry(title=extract_title(p), artist=extract_artist(p), filepath=p,
                                             duration_sec=self._probe_duration(p)))
        except Exception as e:
            logger.error("Failed to download playlist '%s': %s", query, e)
        return entries

    def _download_and_decode(self, entry: SongEntry):
        """Download (if needed) and decode a SongEntry to PCM.

        Uses miniaudio for native formats (MP3/FLAC/WAV), falls back to
        ffmpeg → WAV pipe for anything else (WebM, Opus, M4A, etc.).
        """
        if entry.filepath is None:
            return
        fp = entry.filepath
        if not fp.exists():
            logger.warning("File vanished: %s", fp)
            return

        native_exts = {".mp3", ".flac", ".wav"}
        ext = fp.suffix.lower()

        try:
            import miniaudio

            if ext in native_exts:
                # Native miniaudio decode (generic read_file works for all)
                a = miniaudio.read_file(str(fp))
            else:
                # Unsupported format → pipe through ffmpeg to WAV
                raw_data = subprocess.check_output(
                    [_ffmpeg_path(), "-i", str(fp), "-f", "wav", "-"],
                    stderr=subprocess.DEVNULL, timeout=300,
                )
                a = miniaudio.wav_read_s16(raw_data)

            raw = np.frombuffer(a.samples, dtype=np.int16).astype(np.float32) / 32768.0
            if a.nchannels >= 2:
                raw = raw.reshape(-1, a.nchannels).mean(axis=1)
            entry.samples = raw
            entry.sample_rate = a.sample_rate
            entry.duration_sec = len(raw) / a.sample_rate
        except Exception as e:
            logger.error("Decode failed for %s: %s", entry.filepath, e)

    # ── Internal: Queue Helpers ─────────────────────────────────────────────

    def _shuffle_remaining(self):
        """Randomize songs after current index."""
        with self._lock:
            nxt = self._current_index + 1
            if nxt < len(self._queue):
                rest = self._queue[nxt:]
                random.shuffle(rest)
                self._queue = self._queue[:nxt] + rest
