"""
Data directory resolution for cross-platform user config, memory, and outputs.
"""

import os
from pathlib import Path


def get_config_dir() -> Path:
    """Return the configuration directory (user profile/.raphael).

    Override via RAPHAEL_CONFIG_DIR env var for testing.
    """
    override = os.environ.get("RAPHAEL_CONFIG_DIR")
    path = Path(override) if override else Path.home() / ".raphael"

    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def get_data_dir() -> Path:
    """Return the user local data directory (LOCALAPPDATA/Raphael on Windows).

    Override via RAPHAEL_DATA_DIR env var for testing.
    """
    override = os.environ.get("RAPHAEL_DATA_DIR")
    if override:
        path = Path(override)
    else:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            path = Path(local_appdata) / "Raphael"
        else:
            path = Path.home() / ".local" / "share" / "raphael"

    path.mkdir(parents=True, exist_ok=True)
    (path / "outputs").mkdir(parents=True, exist_ok=True)
    return path.resolve()


def get_roaming_dir() -> Path:
    """Return the user roaming appdata directory (APPDATA/Raphael on Windows).

    Override via RAPHAEL_ROAMING_DIR env var for testing.
    """
    override = os.environ.get("RAPHAEL_ROAMING_DIR")
    if override:
        path = Path(override)
    else:
        appdata = os.environ.get("APPDATA")
        path = Path(appdata) / "Raphael" if appdata else Path.home() / ".config" / "raphael"

    path.mkdir(parents=True, exist_ok=True)
    (path / "memory").mkdir(parents=True, exist_ok=True)
    (path / "goals").mkdir(parents=True, exist_ok=True)
    (path / "logs").mkdir(parents=True, exist_ok=True)
    return path.resolve()
