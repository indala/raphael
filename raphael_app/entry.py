"""
Console entry point for the ``raphael`` CLI command (installed via pip).

Usage:
    raphael              # Launch the desktop app
"""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from main import main


if __name__ == "__main__":
    main()
