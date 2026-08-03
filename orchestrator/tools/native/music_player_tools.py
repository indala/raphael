"""Music player tools — playback control, library management, streaming, playlists.

All functions delegate to the ``MusicPlayer`` singleton, ``PlaylistManager``,
or ``RecentlyPlayed`` classes.
"""

import logging

from audio.music_library import PlaylistManager, RecentlyPlayed
from audio.music_player import MusicPlayer, SongEntry

logger = logging.getLogger(__name__)

_player = MusicPlayer.get_instance


# ── Schemas ─────────────────────────────────────────────────────────────────


def get_schemas() -> list[dict]:
    return [
        # ═══ Playback Control ═══════════════════════════════════════════════
        {
            "type": "function",
            "function": {
                "name": "play_song",
                "description": "Play a specific single song track — searches local library first, downloads if missing. For generic or instant playback, use stream_song.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "song_name": {"type": "string", "description": "Specific single track name or artist (e.g., 'Alan Walker Faded', 'Adele Hello'). Do not use for multi-hour compilation titles."},
                    },
                    "required": ["song_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "play_playlist",
                "description": "Play a saved playlist by name from the local library.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "playlist_name": {"type": "string", "description": "Name of the playlist to play"},
                        "shuffle": {"type": "boolean", "description": "Play songs in random order", "default": False},
                    },
                    "required": ["playlist_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stream_song",
                "description": "Stream a song directly from YouTube with near-instant playback (no download wait). Best for one-off listening.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Song name, artist, or YouTube search query"},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stream_playlist",
                "description": "Stream a curated set of songs matching a mood, genre, or theme. Use for vague requests like 'some chill vibes', 'party music', or 'lofi beats'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Mood, genre, or theme (e.g., 'chill lofi', 'bollywood party', 'study music')"},
                        "count": {"type": "integer", "description": "Number of songs to stream (3-10 recommended)", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_online",
                "description": "Search YouTube for songs matching a query and return a list of results without playing anything. Use to browse before deciding what to play.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "max_results": {"type": "integer", "description": "Maximum number of results", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        },
        # ═══ Queue Management ══════════════════════════════════════════════
        {
            "type": "function",
            "function": {
                "name": "add_to_queue",
                "description": "Add a song to the end of the current playback queue.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "song_name": {"type": "string", "description": "Song name or search query to add"},
                    },
                    "required": ["song_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "clear_queue",
                "description": "Remove all queued songs except the currently playing one.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "show_queue",
                "description": "Show all songs currently in the playback queue with their positions.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        # ═══ Transport Controls ═════════════════════════════════════════════
        {
            "type": "function",
            "function": {
                "name": "pause_music",
                "description": "Pause the currently playing song. Use resume_music to continue.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "resume_music",
                "description": "Resume playback of a paused song.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stop_music",
                "description": "Stop music playback and clear the entire queue.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "next_song",
                "description": "Skip to the next song in the queue.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "previous_song",
                "description": "Go back to the previously played song.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "seek_music",
                "description": "Jump to a specific position in the current song.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "position_seconds": {"type": "integer", "description": "Target position in seconds from start"},
                    },
                    "required": ["position_seconds"],
                },
            },
        },
        # ═══ Volume ════════════════════════════════════════════════════════
        {
            "type": "function",
            "function": {
                "name": "set_music_volume",
                "description": "Set the music player internal playback volume (not system volume).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level": {"type": "number", "description": "Volume level from 0.0 (mute) to 1.0 (max)", "default": 0.7},
                    },
                    "required": ["level"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_music_volume",
                "description": "Get the current music player internal playback volume level (not system volume).",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        # ═══ Repeat / Shuffle ══════════════════════════════════════════════
        {
            "type": "function",
            "function": {
                "name": "set_repeat_mode",
                "description": "Set the repeat mode for music playback: 'off' (stop after queue ends), 'one' (repeat current song), 'all' (loop entire queue).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["off", "one", "all"], "description": "Repeat mode"},
                    },
                    "required": ["mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_shuffle",
                "description": "Enable or disable shuffle mode for the song queue.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "enabled": {"type": "boolean", "description": "True to shuffle, False for sequential"},
                    },
                    "required": ["enabled"],
                },
            },
        },
        # ═══ Info ══════════════════════════════════════════════════════════
        {
            "type": "function",
            "function": {
                "name": "get_current_song",
                "description": "Show information about the currently playing song including title, artist, and duration.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_playback_status",
                "description": "Get the full playback status including state, repeat mode, shuffle, volume, queue length, and current song info.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_playback_progress",
                "description": "Get the current playback position and total duration of the current song.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        # ═══ Local Library ═════════════════════════════════════════════════
        {
            "type": "function",
            "function": {
                "name": "scan_local_library",
                "description": "Scan the local music library folder for all audio files and return a list of found songs.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_local_songs",
                "description": "List every audio file saved in the local music library. Use to show which songs are available for offline playback (alias for scan_local_library).",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_to_library",
                "description": "Download a song from YouTube and save it permanently to your local music library.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "song_name": {"type": "string", "description": "Song name or query to download and save"},
                    },
                    "required": ["song_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "remove_from_library",
                "description": "Remove a song from the local music library by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "song_name": {"type": "string", "description": "Name of the song to remove"},
                    },
                    "required": ["song_name"],
                },
            },
        },
        # ═══ Playlists ═════════════════════════════════════════════════════
        {
            "type": "function",
            "function": {
                "name": "create_playlist",
                "description": "Create a new empty playlist.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name for the new playlist"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "add_to_playlist",
                "description": "Add a song to an existing playlist.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "playlist_name": {"type": "string", "description": "Name of the playlist"},
                        "song_name": {"type": "string", "description": "Song name or query to add"},
                    },
                    "required": ["playlist_name", "song_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_playlist",
                "description": "Delete a playlist and all its contents.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the playlist to delete"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_playlists",
                "description": "List all saved playlists.",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "save_playlist",
                "description": "Permanently save a playlist to disk. Downloads all songs in the playlist to the local music library for offline playback. Use this when the user says 'save this playlist'.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Name of the playlist to save permanently"},
                    },
                    "required": ["name"],
                },
            },
        },
        # ═══ History ═══════════════════════════════════════════════════════
        {
            "type": "function",
            "function": {
                "name": "show_recently_played",
                "description": "Show recently played songs.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of recent songs to show", "default": 10},
                    },
                    "required": [],
                },
            },
        },
    ]


# ── Tool Implementations ────────────────────────────────────────────────────


def play_song(song_name: str) -> str:
    return str(_player().play_song(song_name))


def _match_local_song_file(title: str, local_files: list) -> object | None:
    """Find the downloaded file for a saved playlist song, if any.

    yt-dlp writes ``<title>_<videoID>.mp3``, so compare significant words
    rather than raw substrings (the title may use spaces/separators).
    """
    title_words = {w for w in title.lower().replace("_", " ").replace("-", " ").split()}
    if not title_words:
        return None
    for fp in local_files:
        stem_words = set(fp.stem.lower().replace("_", " ").replace("-", " ").split())
        if title_words.issubset(stem_words):
            return fp
    # Loose fallback: any shared word still beats re-streaming.
    for fp in local_files:
        stem_words = set(fp.stem.lower().replace("_", " ").replace("-", " ").split())
        if title_words.intersection(stem_words):
            return fp
    return None


def play_playlist(playlist_name: str, shuffle: bool = False) -> str:
    songs = PlaylistManager.get(playlist_name)
    is_persistent = False
    if not songs:
        songs = PlaylistManager.get_persistent(playlist_name)
        is_persistent = bool(songs)
        if not songs:
            return f"Playlist '{playlist_name}' is empty or not found."
    p = _player()
    p.stop()
    if is_persistent:
        # Saved playlists download songs to DATA_DIR/music/<name>/ for offline
        # playback; prefer those local files over re-streaming from YouTube.
        from pathlib import Path
        import config
        playlist_dir = Path(getattr(config, "DATA_DIR", ".")) / "music" / playlist_name
        local = list(playlist_dir.glob("*")) if playlist_dir.exists() else []
        entries = [SongEntry(title=s.get("title", "Unknown"), artist=s.get("artist", ""),
                             filepath=_match_local_song_file(s.get("title", ""), local))
                   for s in songs]
    else:
        entries = [SongEntry(title=s.get("title", "Unknown"), artist=s.get("artist", ""))
                   for s in songs]
    p._queue = entries
    p._current_index = 0
    p.set_shuffle(shuffle)
    p._start_bg_thread()
    label = "saved" if is_persistent else "temporary"
    offline = " (local files)" if is_persistent and any(e.filepath for e in entries) else ""
    return f"Playing {label} playlist '{playlist_name}' ({len(entries)} songs){offline}."


def stream_song(query: str) -> str:
    return str(_player().stream_song(query))


def stream_playlist(query: str, count: int = 5) -> str:
    return str(_player().stream_playlist(query, count))


def search_online(query: str, max_results: int = 5) -> str:
    results = _player().search_online(query, max_results)
    if not results:
        return f"No results found for '{query}'."
    lines = [f"Results for '{query}':"]
    for i, r in enumerate(results, 1):
        dur = r.get("duration", 0)
        dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else "?"
        lines.append(f"{i}. {r['title']} ({dur_str})")
    return "\n".join(lines)


def add_to_queue(song_name: str) -> str:
    return str(_player().add_to_queue(song_name))


def clear_queue() -> str:
    return str(_player().clear_queue())


def show_queue() -> str:
    return str(_player().show_queue())


def pause_music() -> str:
    return str(_player().pause())


def resume_music() -> str:
    return str(_player().resume())


def stop_music() -> str:
    return str(_player().stop())


def next_song() -> str:
    return str(_player().next())


def previous_song() -> str:
    return str(_player().previous())


def seek_music(position_seconds: int) -> str:
    return str(_player().seek(float(position_seconds)))


def set_music_volume(level: float) -> str:
    return str(_player().set_volume(level))


def get_music_volume() -> str:
    v = _player().get_volume()
    return f"Current music player volume: {int(v * 100)}%."


def set_repeat_mode(mode: str) -> str:
    return str(_player().set_repeat(mode))


def set_shuffle(enabled: bool) -> str:
    return str(_player().set_shuffle(enabled))


def get_current_song() -> str:
    info = _player().get_current_song()
    if info.get("title") is None:
        return "No song playing."
    artist = info.get("artist", "")
    dur = info.get("duration_sec", 0)
    dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}" if dur else "?"
    parts = [f"Now playing: {info['title']}"]
    if artist:
        parts.append(f"by {artist}")
    parts.append(f"({dur_str})")
    return " ".join(parts)


def get_playback_status() -> str:
    s = _player().get_playback_status()
    parts = [
        f"State: {s['state']}",
        f"Repeat: {s['repeat']}",
        f"Shuffle: {'on' if s['shuffle'] else 'off'}",
        f"Volume: {int(s['volume'] * 100)}%",
        f"Queue: {s['queue_length']} song(s)",
    ]
    if s.get("title"):
        parts.append(f"Current: {s['title']}")
    return " | ".join(parts)


def get_playback_progress() -> str:
    p = _player().get_playback_progress()
    pos = p["position_sec"]
    dur = p["duration_sec"]
    pos_str = f"{int(pos // 60)}:{int(pos % 60):02d}"
    dur_str = f"{int(dur // 60)}:{int(dur % 60):02d}" if dur else "?"
    return f"{pos_str} / {dur_str} ({p['progress_pct']}%)"


def scan_local_library() -> str:
    songs = _player().scan_local_library()
    if not songs:
        return "No local songs found. Use 'add_to_library' to download some."
    lines = [f"Found {len(songs)} song(s) in local library:"]
    for i, s in enumerate(songs, 1):
        artist = f" - {s.artist}" if s.artist and s.artist != "Unknown" else ""
        lines.append(f"{i}. {s.title}{artist}")
    return "\n".join(lines)


def list_local_songs() -> str:
    """List all local audio files in the music library (alias for scan_local_library)."""
    return scan_local_library()


def add_to_library(song_name: str) -> str:
    return str(_player().add_to_library(song_name))


def remove_from_library(song_name: str) -> str:
    return str(_player().remove_from_library(song_name))


def create_playlist(name: str) -> str:
    return str(PlaylistManager.create(name))


def add_to_playlist(playlist_name: str, song_name: str) -> str:
    return str(PlaylistManager.add_song(playlist_name, {"title": song_name, "artist": ""}))


def delete_playlist(name: str) -> str:
    return str(PlaylistManager.delete(name))


def list_playlists() -> str:
    temp = PlaylistManager.list_playlists()
    persistent = set(PlaylistManager.list_persistent())
    names = temp + sorted(persistent - set(temp))
    if not names:
        return "No playlists saved yet."
    lines = ["Playlists:"]
    for i, name in enumerate(names, 1):
        marker = " (saved)" if name in persistent else ""
        songs = PlaylistManager.get(name) or PlaylistManager.get_persistent(name)
        lines.append(f"{i}. {name}{marker} ({len(songs)} songs)")
    return "\n".join(lines)


def show_recently_played(limit: int = 10) -> str:
    songs = RecentlyPlayed.list(limit)
    if not songs:
        return "No recently played songs."
    lines = [f"Recently played (last {len(songs)}):"]
    for i, s in enumerate(songs, 1):
        title = s.get("title", "Unknown")
        artist = s.get("artist", "")
        label = f"{title} - {artist}" if artist else title
        lines.append(f"{i}. {label}")
    return "\n".join(lines)


def save_playlist(name: str) -> str:
    """Permanently save a playlist: copy to DATA_DIR + download all songs."""
    from audio.music_library import PlaylistManager
    return str(PlaylistManager.save_to_disk(name))
