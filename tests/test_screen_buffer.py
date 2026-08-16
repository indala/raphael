"""Unit tests for in-memory fast screen buffer in modules/screen.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from PIL import Image

from modules.screen import get_screen_frame_bytes


def test_get_screen_frame_bytes_basic():
    # Test capture with a mocked PIL grab to work headless/in-CI
    fake_img = Image.new("RGB", (1920, 1080), color=(100, 150, 200))
    with patch("PIL.ImageGrab.grab", return_value=fake_img):
        with patch("modules.screen._CS_SCR", False):
            with patch("mss.mss", side_effect=Exception("mocked no mss")):
                jpeg_bytes, mime = get_screen_frame_bytes(max_w=640, max_h=360, use_cache=False)

                assert isinstance(jpeg_bytes, bytes)
                assert len(jpeg_bytes) > 0
                assert mime == "image/jpeg"

                # Verify compressed dimensions
                from io import BytesIO
                loaded = Image.open(BytesIO(jpeg_bytes))
                assert loaded.width <= 640
                assert loaded.height <= 360


def test_screen_frame_cache_ttl():
    fake_img = Image.new("RGB", (800, 600), color=(50, 50, 50))
    with patch("PIL.ImageGrab.grab", return_value=fake_img):
        with patch("modules.screen._CS_SCR", False):
            with patch("mss.mss", side_effect=Exception("mocked no mss")):
                b1, _ = get_screen_frame_bytes(use_cache=False)
                b2, _ = get_screen_frame_bytes(use_cache=True)
                assert b1 == b2
