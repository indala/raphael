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
    with mss.mss() as sct:
        monitor = {"left": left, "top": top, "width": width, "height": height}
        screenshot = sct.grab(monitor)
        return Image.frombytes("RGB", screenshot.size, screenshot.rgb)


# ── In-Memory Fast Screen Frame Buffer (Inspired by Mark-XLVIII) ─────────────

_last_frame_bytes: bytes | None = None
_last_frame_time: float = 0.0
_FRAME_CACHE_TTL = 1.5  # Seconds to reuse a cached frame


def get_screen_frame_bytes(
    max_w: int = 1280,
    max_h: int = 720,
    quality: int = 82,
    use_cache: bool = True,
) -> tuple[bytes, str]:
    """Capture screen in-memory as downsampled JPEG bytes (zero disk I/O).

    Args:
        max_w: Maximum width constraint (default 1280).
        max_h: Maximum height constraint (default 720).
        quality: JPEG compression quality (default 82).
        use_cache: If True, return recent in-memory frame if within TTL.

    Returns:
        tuple of (jpeg_bytes, "image/jpeg").
    """
    global _last_frame_bytes, _last_frame_time
    import time

    now = time.time()
    if use_cache and _last_frame_bytes is not None and (now - _last_frame_time) < _FRAME_CACHE_TTL:
        return _last_frame_bytes, "image/jpeg"

    # Try C# BitBlt primary screen
    raw_img: Image.Image | None = None
    if _CS_SCR:
        try:
            png_bytes = CsScr.CapturePrimaryScreen()
            if png_bytes:
                raw_img = Image.open(BytesIO(png_bytes)).convert("RGB")
        except Exception as e:
            logger.debug("C# fast capture failed: %s", e)

    if raw_img is None:
        try:
            import mss
            with mss.mss() as sct:
                monitors = sct.monitors
                target = monitors[1] if len(monitors) > 1 else monitors[0]
                shot = sct.grab(target)
                raw_img = Image.frombytes("RGB", shot.size, shot.rgb)
        except Exception as e:
            logger.warning("MSS fast capture failed: %s, falling back to PIL ImageGrab", e)
            from PIL import ImageGrab
            raw_img = ImageGrab.grab().convert("RGB")

    raw_img.thumbnail((max_w, max_h), Image.Resampling.BILINEAR)
    buf = BytesIO()
    raw_img.save(buf, format="JPEG", quality=quality, optimize=False)
    jpeg_bytes = buf.getvalue()

    _last_frame_bytes = jpeg_bytes
    _last_frame_time = now
    return jpeg_bytes, "image/jpeg"
