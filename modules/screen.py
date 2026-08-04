"""
Screen capture module.
Captures screenshots and performs OCR for UI understanding.
Uses C# GDI BitBlt for primary screen capture, falling back to mss.
"""

import logging
from io import BytesIO
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Optional C# hybrid bridge
try:
    from hybrid.bridge import CScreenCapture as CsScr, is_available
    _CS_SCR = is_available()
except ImportError:
    _CS_SCR = False


def capture_screen(output_path: str | None = None) -> str:
    """
    Capture the entire screen and save to file.

    Args:
        output_path: Path to save screenshot. Auto-generates if None.

    Returns:
        Path to the saved screenshot file.
    """
    import config
    output_dir = Path(getattr(config, "SCREENSHOT_DIR", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)

    if not output_path:
        output_path = str(output_dir / "screen.png")

    # Try C# BitBlt first (faster, more reliable)
    if _CS_SCR:
        try:
            png_bytes = CsScr.CapturePrimaryScreen()
            if png_bytes:
                Path(output_path).write_bytes(png_bytes)
                return output_path
        except Exception as e:
            logger.warning("C# capture failed: %s, falling back to mss", e)
    # Fall back to mss
    import mss
    try:
        with mss.MSS() as sct:
            sct.shot(output=output_path)
        return output_path
    except Exception as e:
        raise RuntimeError(f"Screen capture failed (Windows display access denied or locked): {e}") from e


def capture_region(left: int, top: int, width: int, height: int) -> Image.Image:
    """
    Capture a specific region of the screen.

    Returns:
        PIL Image of the specified region.
    """
    # For region capture, grab full screen via C# and crop
    if _CS_SCR:
        try:
            png_bytes = CsScr.CapturePrimaryScreen()
            if png_bytes:
                full = Image.open(BytesIO(png_bytes))
                return full.crop((left, top, left + width, top + height))
        except Exception as e:
            logger.warning("C# region capture failed: %s, falling back to mss", e)
    import mss
    with mss.mss() as sct:
        monitor = {"left": left, "top": top, "width": width, "height": height}
        screenshot = sct.grab(monitor)
        return Image.frombytes("RGB", screenshot.size, screenshot.rgb)
