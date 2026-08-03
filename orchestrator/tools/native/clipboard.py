"""Clipboard tools — copy/paste text and images."""

from modules import clipboard as _clipboard


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "copy_to_clipboard",
                "description": "Copy a text string to the Windows clipboard so it can be pasted elsewhere. Use when the user asks to copy text for manual pasting.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The text to copy to clipboard",
                        }
                    },
                    "required": ["text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_clipboard",
                "description": "Read the current text content from the Windows clipboard and return it. Use when the user asks what is copied or to check clipboard contents.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "copy_image_to_clipboard",
                "description": "Copy an image file to the Windows clipboard as an image so it can be pasted into documents or chat apps. Use when the user asks to copy a picture for pasting.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "description": "Path to the image file to copy",
                        },
                    },
                    "required": ["image_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_clipboard_files",
                "description": "Get list of file paths currently copied to the clipboard (CF_HDROP). Use this to discover what files the user has copied from Windows Explorer before acting on them.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


def copy_to_clipboard(text: str) -> str:
    """Copy text to clipboard."""
    _clipboard.copy_text(text)
    return f"Copied to clipboard: {text[:100]}{'...' if len(text) > 100 else ''}"


def read_clipboard() -> str:
    """Read text from clipboard."""
    text = _clipboard.paste_text()
    if not text:
        return "Clipboard is empty or contains non-text data."
    return f"Clipboard contents: {text[:500]}"


def copy_image_to_clipboard(image_path: str) -> str:
    """Copy an image file to the clipboard."""
    if _clipboard.copy_image(image_path):
        return f"Successfully copied image '{image_path}' to clipboard."
    return f"Failed to copy image '{image_path}' to clipboard."


def get_clipboard_files() -> str:
    """Get file paths from clipboard (CF_HDROP)."""
    files = _clipboard.get_file_list()
    if not files:
        return "No files on clipboard."
    lines = [f"Found {len(files)} file(s) on clipboard:"]
    for f in files:
        lines.append(f"  • {f}")
    return "\n".join(lines)
