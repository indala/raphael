"""Recycle Bin module via the C# Shell32 bridge (SHQueryRecycleBinW / SHEmptyRecycleBinW)."""

import logging

logger = logging.getLogger(__name__)

try:
    from hybrid.bridge import CRecycleBin as CsBin, is_available
    _CS_BIN = is_available()
except ImportError:
    _CS_BIN = False


def recycle_bin_get() -> str:
    """Query the recycle bin's item count and total size across all drives."""
    if not _CS_BIN:
        return "C# bridge not available — cannot query recycle bin"
    try:
        info = CsBin.Get() or {}
    except Exception as e:
        return f"Failed to query recycle bin: {e}"
    if info.get("hr", 0) != 0:
        return f"Failed to query recycle bin (Shell32 error 0x{info.get('hr', 0):X})."
    return f"Recycle bin: {info.get('item_count', 0)} item(s), {info.get('size_bytes', 0):,} bytes."


def recycle_bin_empty(confirm: bool = False) -> str:
    """Empty the recycle bin. No-op unless confirm=True (destructive)."""
    if not _CS_BIN:
        return "C# bridge not available — cannot empty recycle bin"
    if not confirm:
        return "Emptying the recycle bin is destructive. Call with confirm=true to proceed."
    try:
        info = CsBin.Empty(True) or {}
    except Exception as e:
        return f"Failed to empty recycle bin: {e}"
    return str(info.get("message", "Recycle bin emptied."))
