"""Screen capture tool — capture the monitor."""

from modules import screen as _screen


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "capture_screen",
                "description": "Capture the entire screen and save it as an image in the outputs folder. Use when the user asks what is on their screen, for screenshots, or for visual inspection.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "output_path": {
                            "type": "string",
                            "description": "Custom file path to save screenshot (optional)",
                        },
                    },
                },
            },
        },
    ]


def capture_screen(output_path: str | None = None) -> str:
    """Capture the entire screen and save it to file."""
    try:
        path = _screen.capture_screen(output_path)
        return f"Screen captured and saved to {path}"
    except Exception as e:
        return f"Failed to capture screen: {e}"
