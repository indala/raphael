"""Music playback tools — play locally or download/play from YouTube via yt-dlp.

Note: ``play_song`` schema is provided by ``music_player_tools.py``, which
has the comprehensive version. This module only provides ``save_song``.
"""

import logging
import re
import tempfile
from pathlib import Path

import config
from audio.music_player import MusicPlayer

logger = logging.getLogger(__name__)

# Words that don't help distinguish one song from another during matching.
_STOPWORDS = frozenset(
    {"the", "a", "an", "and", "of", "in", "on", "at", "for", "to",
     "with", "feat", "ft", "official", "video", "audio", "lyrics",
     "lyric", "hd", "hq", "remastered"}
)

# yt-dlp appends "_<videoID>" (11 chars) to restricted filenames.
_VIDEO_ID_SUFFIX_RE = re.compile(r"_[A-Za-z0-9_-]{11}$")


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "save_song",
                "description": "Save the recently downloaded temporary song permanently to the offline local music library.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "song_name": {
                            "type": "string",
                            "description": "Name of the song to save from temporary folder",
                        }
                    },
                    "required": ["song_name"],
                },
            },
        },
    ]


def play_song(song_name: str) -> str:
    """Play a song — delegates to the native MusicPlayer."""
    logger.info("play_song: query: %s", song_name)
    result = MusicPlayer.get_instance().play_song(song_name)
    return str(result)


def save_song(song_name: str) -> str:
    """Save the downloaded temporary song permanently to the local library."""
    import shutil

    temp_dir = Path(tempfile.gettempdir()) / "Raphael" / "temp_music"
    music_dir = Path(getattr(config, "DATA_DIR", ".")) / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    if not temp_dir.exists():
        return "No temporary songs found to save."

    query_words = {w for w in song_name.lower().split() if w not in _STOPWORDS}
    if not query_words:
        return f"Could not find any downloaded song in temp matching '{song_name}'."

    best_match = None
    best_score = 0

    def _words(text: str) -> set[str]:
        """Lowercased significant words in a filename stem or query."""
        return {w for w in text.lower().replace("_", " ").replace("-", " ").split()
                if w not in _STOPWORDS}

    try:
        for filepath in temp_dir.glob("*"):
            if not filepath.is_file():
                continue
            name_words = _words(filepath.stem)
            overlap = len(query_words.intersection(name_words))
            # Require a meaningful match: several shared words, or a single-word
            # query whose one word appears in the filename.
            if overlap < 2 and not (len(query_words) == 1 and overlap == 1):
                continue
            if overlap > best_score:
                best_score = overlap
                best_match = filepath
            elif overlap == best_score and best_match is not None and len(filepath.name) < len(best_match.name):
                best_match = filepath
    except Exception as e:
        logger.error("Error searching temp folder: %s", e)

    if not best_match:
        return f"Could not find any downloaded song in temp matching '{song_name}'."

    try:
        # Strip yt-dlp's trailing "_<videoID>" so the saved name is readable.
        clean_stem = _VIDEO_ID_SUFFIX_RE.sub("", best_match.stem) or best_match.stem
        dest_path = music_dir / f"{clean_stem}{best_match.suffix}"
        if dest_path.exists():
            dest_path = music_dir / f"{clean_stem} (1){best_match.suffix}"
        try:
            # Move instead of copy so the temp folder stops accumulating; fall
            # back to copy when the file is locked (e.g. currently playing).
            shutil.move(str(best_match), str(dest_path))
            verb = "moved"
        except OSError:
            shutil.copy2(best_match, dest_path)
            verb = "copied"
        return f"Saved '{best_match.name}' to your offline music library ({verb})."
    except Exception as e:
        logger.error("Failed to save song offline: %s", e)
        return f"Error saving song offline: {e}"
