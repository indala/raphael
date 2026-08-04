"""Shortcut (.lnk) creation module via the C# WScript.Shell COM bridge."""

import logging

logger = logging.getLogger(__name__)

try:
    from hybrid.bridge import CShortcutHelper as CsShortcut, is_available
    _CS_SHORTCUT = is_available()
except ImportError:
    _CS_SHORTCUT = False


def create_shortcut(
    link_path: str,
    target: str,
    arguments: str = "",
    working_dir: str = "",
    description: str = "",
) -> str:
    """Create a .lnk shortcut pointing at target. Returns a human-readable result."""
    if not _CS_SHORTCUT:
        return "C# bridge not available — cannot create shortcut"
    try:
        err = CsShortcut.Create(link_path, target, arguments, working_dir, description)
    except Exception as e:
        return f"Failed to create shortcut: {e}"
    if err:
        return f"Failed to create shortcut: {err}"
    return f"Created shortcut {link_path} → {target}."
