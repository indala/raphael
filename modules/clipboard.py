"""
Clipboard module.
Read/write clipboard for text, images, and files.
Uses C# bridge (via pythonnet) for text operations when available,
falling back to pyperclip.
"""

import logging

import pyperclip

logger = logging.getLogger(__name__)

# Optional C# hybrid bridge
try:
    from hybrid.bridge import CClipboardHelper as CsClip, is_available
    _CS_CLIP = is_available()
except ImportError:
    _CS_CLIP = False


def copy_text(text: str) -> bool:
    """Copy text to clipboard. Uses C# bridge if available."""
    if _CS_CLIP:
        try:
            result = CsClip.SetText(text)
            if result:
                return True
        except Exception:
            pass
    try:
        pyperclip.copy(text)
        return True
    except Exception as e:
        logger.error("Copy failed: %s", e)
        return False


def paste_text() -> str:
    """Read text from clipboard. Uses C# bridge if available."""
    if _CS_CLIP:
        try:
            result = CsClip.GetText()
            if result:
                return result
        except Exception:
            pass
    try:
        return pyperclip.paste()  # type: ignore[no-any-return]
    except Exception as e:
        logger.error("Paste failed: %s", e)
        return ""


def copy_image(image_path: str) -> bool:
    """
    Copy an image file to the Windows clipboard.
    Uses C# bridge (CF_DIB) as primary path, falls back to win32clipboard.
    """
    import io
    import base64
    from PIL import Image
    try:
        image = Image.open(image_path)
        output = io.BytesIO()
        # BMP without the 14-byte file header = DIB format
        image.convert("RGB").save(output, "BMP")
        dib_data = output.getvalue()[14:]
        output.close()

        # Primary: C# bridge
        if _CS_CLIP:
            dib_b64 = base64.b64encode(dib_data).decode("ascii")
            if CsClip.CopyImage(dib_b64):
                return True

        # Fallback: win32clipboard
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib_data)
        win32clipboard.CloseClipboard()
        return True
    except Exception as e:
        logger.error("Copy image failed: %s", e)
        return False


def get_file_list() -> list[str] | None:
    """Get list of file paths from clipboard (CF_HDROP)."""
    if _CS_CLIP:
        try:
            result = CsClip.GetFileDropList()
            if result is not None:
                return list(result)
        except Exception:
            pass
    return None


def has_files() -> bool:
    """Check if clipboard contains file drop list."""
    if _CS_CLIP:
        try:
            result = CsClip.HasFiles()
            if result is not None:
                return bool(result)
        except Exception:
            pass
    return False

