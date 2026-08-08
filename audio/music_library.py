"""Persistent music library management — playlists, recently played tracking.

Design:
  - Temporary playlists are stored in ``%TEMP%/Raphael/playlists/`` by default.
    These are created when the user says "play some X" — quick, ephemeral.
  - When the user says "save this playlist as 'Name'", the playlist JSON is
    copied to ``DATA_DIR/music/playlists.json`` AND all songs are downloaded
    to ``DATA_DIR/music/<playlist_name>/`` for offline playback.
"""

import json
import logging
import subprocess
import tempfile
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

TEMP_PLAYLISTS_DIR = Path(tempfile.gettempdir()) / "Raphael" / "playlists"


def _config_data_dir() -> Path:
    """Lazy import config to avoid circular imports."""
    import config
    return Path(getattr(config, "DATA_DIR", "."))


def _music_data_dir() -> Path:
    d = _config_data_dir() / "music"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ytdlp_cmd() -> list[str]:
    """Resolve yt-dlp executable or fallback to python -m yt_dlp."""
    import os
    import shutil
    import sys
    yt_exe = shutil.which("yt-dlp")
    if yt_exe:
        return [yt_exe]
    user_scripts = Path(sys.prefix) / "Scripts" / "yt-dlp.exe"
    if user_scripts.exists():
        return [str(user_scripts)]
    appdata = os.environ.get("APPDATA")
    if appdata:
        py_ver = f"Python{sys.version_info.major}{sys.version_info.minor}"
        appdata_scripts = Path(appdata) / "Python" / py_ver / "Scripts" / "yt-dlp.exe"
        if appdata_scripts.exists():
            return [str(appdata_scripts)]
    return [sys.executable, "-m", "yt_dlp"]



# ── PlaylistManager ─────────────────────────────────────────────────────────


class PlaylistManager:
    """JSON-based playlist storage — temporary by default, persist on demand.

    Temporary playlists live in ``%TEMP%/Raphael/playlists/playlists.json``.
    Use ``save_to_disk()`` to permanently persist a playlist + download all songs.
    """

    _lock = threading.Lock()

    @staticmethod
    def _playlist_path(temp: bool = True) -> Path:
        """Return the playlist JSON path, optionally in temp vs. persistent dir."""
        if temp:
            TEMP_PLAYLISTS_DIR.mkdir(parents=True, exist_ok=True)
            return TEMP_PLAYLISTS_DIR / "playlists.json"
        return _music_data_dir() / "playlists.json"

    # ── Public API ──────────────────────────────────────────────────────────

    @staticmethod
    def create(name: str) -> str:
        name = name.strip()
        if not name:
            return "Playlist name cannot be empty."
        data = _load()
        if name in data:
            return f"Playlist '{name}' already exists."
        data[name] = []
        _save(data)
        return f"Created playlist '{name}'."

    @staticmethod
    def delete(name: str) -> str:
        data = _load()
        if name not in data:
            return f"Playlist '{name}' not found."
        del data[name]
        _save(data)
        # Also drop the saved (persistent) copy, if any, so the user can
        # delete a saved playlist and re-create it under the same name.
        persistent_path = PlaylistManager._playlist_path(temp=False)
        persistent_data = _read_json(persistent_path, {})
        if name in persistent_data:
            del persistent_data[name]
            _write_json(persistent_path, persistent_data)
            return f"Deleted playlist '{name}' (temporary and saved copies)."
        return f"Deleted playlist '{name}'."

    @staticmethod
    def list_playlists() -> list[str]:
        return list(_load().keys())

    @staticmethod
    def get(name: str) -> list[dict]:
        return _load().get(name, [])  # type: ignore[no-any-return]

    @staticmethod
    def add_song(playlist_name: str, song_info: dict) -> str:
        """Add a song dict to a playlist.

        ``song_info`` can contain keys like ``title``, ``artist``, ``filepath``.
        """
        data = _load()
        if playlist_name not in data:
            return f"Playlist '{playlist_name}' not found."
        data[playlist_name].append(song_info)
        _save(data)
        title = song_info.get("title", "Unknown")
        return f"Added '{title}' to '{playlist_name}'."

    @staticmethod
    def remove_song(playlist_name: str, index: int) -> str:
        """Remove a song from a playlist by index (1-based)."""
        data = _load()
        if playlist_name not in data:
            return f"Playlist '{playlist_name}' not found."
        pl = data[playlist_name]
        idx = index - 1
        if idx < 0 or idx >= len(pl):
            return f"Index {index} out of range (1-{len(pl)})."
        removed = pl.pop(idx)
        _save(data)
        title = removed.get("title", "Unknown")
        return f"Removed '{title}' from '{playlist_name}'."

    @staticmethod
    def rename(old_name: str, new_name: str) -> str:
        data = _load()
        if old_name not in data:
            return f"Playlist '{old_name}' not found."
        if new_name in data:
            return f"Playlist '{new_name}' already exists."
        data[new_name] = data.pop(old_name)
        _save(data)
        return f"Renamed '{old_name}' to '{new_name}'."

    @staticmethod
    def save_to_disk(name: str) -> str:
        """Permanently save a temp playlist: copy JSON + download all songs.

        This moves the playlist from ``%TEMP%/Raphael/playlists/`` to
        ``DATA_DIR/music/playlists.json``, and downloads every song in the
        playlist to ``DATA_DIR/music/<name>/`` for offline playback.
        """
        data = _load()
        if name not in data:
            return f"Playlist '{name}' not found in temporary storage."

        songs = data[name]
        if not songs:
            return f"Playlist '{name}' is empty — nothing to save."

        # ── 1. Merge into persistent playlist store ──
        persistent_path = PlaylistManager._playlist_path(temp=False)
        persistent_data = _read_json(persistent_path, {})
        if name in persistent_data:
            return (f"Playlist '{name}' is already saved to your library. "
                    "Delete it first if you want to replace it.")
        persistent_data[name] = songs
        _write_json(persistent_path, persistent_data)

        # ── 2. Download all songs to DATA_DIR/music/<name>/ ──
        playlist_dir = _music_data_dir() / name
        playlist_dir.mkdir(parents=True, exist_ok=True)

        downloaded = 0
        for song in songs:
            title = song.get("title", "")
            if not title:
                continue
            # Skip if already downloaded
            existing = list(playlist_dir.glob("*"))
            if any(title.lower() in fp.stem.lower() for fp in existing):
                downloaded += 1
                continue
            try:
                cmd = _ytdlp_cmd() + [
                    f"ytsearch1:{title}",
                    "-f", "ba",
                    "-o", f"{playlist_dir}/%(title)s_%(id)s.%(ext)s",
                    "--no-playlist", "--restrict-filenames",
                    "--extract-audio", "--audio-format", "mp3",
                ]
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=120)
                downloaded += 1
            except Exception as e:
                logger.warning("Failed to download '%s' for playlist: %s", title, e)

        result = f"Saved playlist '{name}' ({len(songs)} songs, {downloaded} downloaded)."
        if downloaded < len(songs):
            result += f" {len(songs) - downloaded} failed."

        # ── 3. Drop the now-persisted temp copy to avoid a stale duplicate ──
        data.pop(name, None)
        _save(data)
        return result

    @staticmethod
    def has_persistent(name: str) -> bool:
        """Check if a playlist exists in the persistent store."""
        persistent_path = PlaylistManager._playlist_path(temp=False)
        data = _read_json(persistent_path, {})
        return bool(name in data)

    @staticmethod
    def list_persistent() -> list[str]:
        """List only persistent playlists (in DATA_DIR)."""
        persistent_path = PlaylistManager._playlist_path(temp=False)
        return list(_read_json(persistent_path, {}).keys())

    @staticmethod
    def get_persistent(name: str) -> list[dict]:
        """Get a playlist from the persistent store (DATA_DIR)."""
        persistent_path = PlaylistManager._playlist_path(temp=False)
        data = _read_json(persistent_path, {})
        return data.get(name, [])  # type: ignore[no-any-return]


# ── RecentlyPlayed ──────────────────────────────────────────────────────────


class RecentlyPlayed:
    """JSON-backed recently-played log, max 50 entries."""

    MAX_ENTRIES = 50
    _lock = threading.Lock()

    @staticmethod
    def add(song_info: dict):
        """Record a played song. Newest is prepended; duplicates removed."""
        with RecentlyPlayed._lock:
            path = _music_data_dir() / "recently_played.json"
            data = _read_json(path, [])
            # Remove duplicate if exists
            title = song_info.get("title", "")
            data = [s for s in data if s.get("title") != title]
            # Prepend
            data.insert(0, song_info)
            # Trim
            data = data[:RecentlyPlayed.MAX_ENTRIES]
            _write_json(path, data)

    @staticmethod
    def list(limit: int = 10) -> list[dict]:
        path = _music_data_dir() / "recently_played.json"
        data = _read_json(path, [])
        return data[:limit]  # type: ignore[no-any-return]

    @staticmethod
    def clear():
        path = _music_data_dir() / "recently_played.json"
        _write_json(path, [])


# ── LikedSongsManager ───────────────────────────────────────────────────────


class LikedSongsManager:
    """JSON-backed Liked Songs storage in DATA_DIR/music/liked_songs.json."""

    _lock = threading.Lock()

    @staticmethod
    def _file_path() -> Path:
        return _music_data_dir() / "liked_songs.json"

    @staticmethod
    def add(song_info: dict) -> str:
        """Add a song to Liked Songs."""
        with LikedSongsManager._lock:
            path = LikedSongsManager._file_path()
            data = _read_json(path, [])
            title = song_info.get("title", "")
            if not title:
                return "Cannot like song without a title."
            # Avoid duplicate
            if any(s.get("title", "").lower() == title.lower() for s in data):
                return f"'{title}' is already in your Liked Songs."
            data.insert(0, song_info)
            _write_json(path, data)
            return f"Added '{title}' to Liked Songs ❤️"

    @staticmethod
    def remove(title: str) -> str:
        """Remove a song from Liked Songs by title."""
        with LikedSongsManager._lock:
            path = LikedSongsManager._file_path()
            data = _read_json(path, [])
            initial_len = len(data)
            data = [s for s in data if s.get("title", "").lower() != title.lower()]
            if len(data) == initial_len:
                return f"'{title}' not found in Liked Songs."
            _write_json(path, data)
            return f"Removed '{title}' from Liked Songs."

    @staticmethod
    def is_liked(title: str) -> bool:
        """Check if a song title is in Liked Songs."""
        if not title:
            return False
        with LikedSongsManager._lock:
            path = LikedSongsManager._file_path()
            data = _read_json(path, [])
            return any(s.get("title", "").lower() == title.lower() for s in data)

    @staticmethod
    def toggle(song_info: dict) -> bool:
        """Toggle liked state. Returns True if now liked, False if unliked."""
        title = song_info.get("title", "")
        if not title:
            return False
        if LikedSongsManager.is_liked(title):
            LikedSongsManager.remove(title)
            return False
        else:
            LikedSongsManager.add(song_info)
            return True

    @staticmethod
    def list() -> list[dict]:
        """List all liked songs."""
        with LikedSongsManager._lock:
            path = LikedSongsManager._file_path()
            res = _read_json(path, [])
            return list(res) if isinstance(res, list) else []



# ── Internal helpers ────────────────────────────────────────────────────────


def _load() -> dict:
    """Load all playlists from temp storage."""
    with PlaylistManager._lock:
        path = PlaylistManager._playlist_path(temp=True)
        return _read_json(path, {})  # type: ignore[no-any-return]


def _save(data: dict):
    """Save all playlists to temp storage."""
    with PlaylistManager._lock:
        path = PlaylistManager._playlist_path(temp=True)
        _write_json(path, data)


def _read_json(path: Path, default):
    try:
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning("Failed to read %s: %s", path, e)
    return default


def _write_json(path: Path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to write %s: %s", path, e)
