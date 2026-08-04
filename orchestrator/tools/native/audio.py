"""Audio playback tools — play and stop local audio files via the C# MCI bridge."""

import os

from modules import audio_playback as _audio_playback


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "play_audio_file",
                "description": "Play a local audio file (for example MP3, WAV, or M4A) on the machine using the C# media bridge. Provide an absolute or relative file path. Returns confirmation once playback is launched.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path of the audio to play",
                        },
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "stop_audio",
                "description": "Stop all currently playing audio that was launched through the C# media bridge (for example a previous play_audio_file call). It is a no-op if nothing is currently playing.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


def play_audio_file(path: str) -> str:
    """Play a local audio file via the C# bridge."""
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        return f"Error: File not found: {path}"
    if _audio_playback.play_file(expanded):
        return f"Started playing audio file: {expanded}."
    return f"Error: Failed to start audio playback for: {expanded}."


def stop_audio() -> str:
    """Stop all C# bridge audio playback."""
    if _audio_playback.stop():
        return "Stopped all audio playback."
    return "Failed to stop audio playback (bridge unavailable or a playback error occurred)."
