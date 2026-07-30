"""
Application launcher module.
Opens applications, URLs, and files on Windows.
"""

import os
import subprocess
import webbrowser
from pathlib import Path


# Optional C# hybrid bridge
try:
    from hybrid.bridge import CShellHelper as CsShell, is_available
    _CS_SHELL = is_available()
except ImportError:
    _CS_SHELL = False


def launch(app_name_or_path: str) -> str:
    """
    Launch an application or open a file/URL.

    Args:
        app_name_or_path: App name, exe path, URL, or file path

    Returns:
        Status message
    """
    try:
        if app_name_or_path.startswith(("http://", "https://")):
            webbrowser.open(app_name_or_path)
            return f"Opened URL: {app_name_or_path}"

        path = Path(app_name_or_path)
        if path.exists():
            if _CS_SHELL and CsShell.Open(str(path)):
                return f"Opened: {app_name_or_path}"
            os.startfile(str(path))
            return f"Opened: {app_name_or_path}"

        # Try as a command or Windows app alias
        if _CS_SHELL and CsShell.Launch(app_name_or_path):
            return f"Launched: {app_name_or_path}"
        subprocess.Popen(app_name_or_path, shell=True)
        return f"Launched: {app_name_or_path}"

    except Exception as e:
        return f"Failed to launch {app_name_or_path}: {e}"
