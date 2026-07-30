"""Music playback tools — play locally or download/play from YouTube via yt-dlp.

Note: ``play_song`` schema is provided by ``music_player_tools.py``, which
has the comprehensive version. This module only provides ``save_song``.
"""

import logging
import tempfile
from pathlib import Path

import config
from audio.music_player import MusicPlayer

logger = logging.getLogger(__name__)


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
    temp_dir = Path(tempfile.gettempdir()) / "Raphael" / "temp_music"
    music_dir = Path(getattr(config, "DATA_DIR", ".")) / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    if not temp_dir.exists():
        return "No temporary songs found to save."

    query_words = set(song_name.lower().split())
    best_match = None
    best_score = 0

    try:
        for filepath in temp_dir.glob("*"):
            if filepath.is_file():
                name_words = set(filepath.stem.lower().replace("_", " ").replace("-", " ").split())
                overlap = query_words.intersection(name_words)
                if overlap:
                    score = len(overlap)
                    if score > best_score:
                        best_score = score
                        best_match = filepath
    except Exception as e:
        logger.error("Error searching temp folder: %s", e)

    if not best_match:
        return f"Could not find any downloaded song in temp matching '{song_name}'."

    try:
        dest_path = music_dir / best_match.name
        import shutil
        shutil.copy2(best_match, dest_path)
        return f"Saved '{best_match.name}' to your offline music library successfully."
    except Exception as e:
        logger.error("Failed to save song offline: %s", e)
        return f"Error saving song offline: {e}"
