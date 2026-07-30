"""Startup dependency checker — logs availability of optional components."""

import importlib
import logging

logger = logging.getLogger(__name__)

CHECKS: list[dict] = [
    {"name": "Playwright", "module": "playwright", "pip": "playwright", "purpose": "Browser automation"},
    {"name": "Pillow", "module": "PIL", "pip": "Pillow", "purpose": "Image processing"},
    {"name": "Plotly", "module": "plotly", "pip": "plotly", "purpose": "Interactive charts"},
    {"name": "python-docx", "module": "docx", "pip": "python-docx", "purpose": "Word documents"},
    {"name": "openpyxl", "module": "openpyxl", "pip": "openpyxl", "purpose": "Excel files"},
    {"name": "python-pptx", "module": "pptx", "pip": "python-pptx", "purpose": "PowerPoint files"},
    {"name": "pypdf2", "module": "PyPDF2", "pip": "pypdf2", "purpose": "PDF processing"},
    {"name": "edge-tts", "module": "edge_tts", "pip": "edge-tts", "purpose": "Edge TTS engine"},
]


def check_dependencies():
    """Check all optional deps and log their status."""
    for dep in CHECKS:
        try:
            importlib.import_module(dep["module"])
            logger.info("  ✓ %s (%s) — available", dep["name"], dep["purpose"])
        except ImportError:
            logger.warning("  ✗ %s — not installed. Install: pip install %s", dep["name"], dep["pip"])
