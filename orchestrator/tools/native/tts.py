"""TTS tool — speak text aloud."""

from modules.tts import speak as tts_speak


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "speak",
                "description": "Speak text aloud using text-to-speech. Use this to verbally respond to the user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The text to speak aloud",
                        }
                    },
                    "required": ["text"],
                },
            },
        },
    ]


def speak(text: str) -> str:
    """Speak text aloud via TTS."""
    from controller.state import state
    if not state.audio_output_available:
        return "Audio output unavailable: no physical speaker device detected."
    if not state.tts_enabled:
        return "Audio output disabled: TTS is currently disabled."

    success = tts_speak(text)
    if not success:
        return "Audio playback skipped or failed."
    return f"Spoken: {text[:100]}{'...' if len(text) > 100 else ''}"
