"""
Raphael — AI Desktop Assistant for Windows.

Invoke with: python -m raphael_app
"""

import sys
from pathlib import Path

_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

from main import main

main()
