"""TTS tool — speak text aloud."""

from modules.tts import list_voices as _list_voices
from modules.tts import speak as tts_speak


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "speak",
                "description": "Speak text aloud using text-to-speech. Use this to verbally respond to the user. Optionally pass a voice name (see tts_list_voices) to override the currently selected voice for this call.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The text to speak aloud",
                        },
                        "voice": {
                            "type": "string",
                            "description": "Optional voice name to use for this utterance instead of the configured voice",
                        },
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "tts_list_voices",
                "description": "List all voices available from the installed text-to-speech backends. Use the returned voice names with speak or tts_set_voice to change how Raphael sounds.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "tts_set_voice",
                "description": "Persistently select which text-to-speech voice Raphael uses for all future speak calls until changed again. The voice name must come from tts_list_voices.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "voice": {
                            "type": "string",
                            "description": "The voice name to use for all future speech output",
                        }
                    },
                    "required": ["voice"],
                },
            },
        },
    ]


def speak(text: str, voice: str | None = None) -> str:
    """Speak text aloud via TTS, optionally overriding the active voice."""
    from controller.state import state
    if not state.audio_output_available:
        return "Audio output unavailable: no physical speaker device detected."
    if not state.tts_enabled:
        return "Audio output disabled: TTS is currently disabled."

    success = tts_speak(text, voice=voice)
    if not success:
        return "Audio playback skipped or failed."
    return f"Spoken: {text[:100]}{'...' if len(text) > 100 else ''}"


def tts_list_voices() -> str:
    """Return the list of available TTS voices as a formatted string."""
    voices = _list_voices()
    if not voices:
        return "No text-to-speech voices are currently available."
    preview = ", ".join(voices)
    return f"Available TTS voices ({len(voices)}): {preview}"


def tts_set_voice(voice: str) -> str:
    """Persist the chosen voice for all future speak calls."""
    from controller.state import state
    candidates = _list_voices()
    if voice not in candidates:
        sample = ", ".join(candidates[:8]) if candidates else "(none available)"
        return f"Error: voice '{voice}' not found. Available voices: {sample}"
    state.tts_voice = voice
    return f"TTS voice set to: {voice}"
