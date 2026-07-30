"""
Auto-updater module for Raphael.

Checks GitHub Releases for new versions and handles silent upgrades.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import config

logger = logging.getLogger(__name__)

GITHUB_REPO = "indala/raphael"
"""The GitHub repository path (owner/repo)."""


@dataclass
class ReleaseInfo:
    """Information about a GitHub release."""

    tag_name: str
    html_url: str
    body: str
    assets: list[dict]


# ── helpers ───────────────────────────────────────────────────────────────


def _parse_semver(tag: str) -> list[int]:
    """Parse a semver tag (``v0.2.0``) into a list of ints for comparison."""
    return [int(x) for x in tag.lstrip("v").split(".")]


def _is_newer_version(tag: str) -> bool:
    """Return ``True`` if *tag* is a newer semver than ``config.VERSION``."""
    return _parse_semver(tag) > _parse_semver(config.VERSION)


# ── public API ────────────────────────────────────────────────────────────


def get_latest_release() -> ReleaseInfo | None:
    """Fetch the latest release from GitHub API.

    Returns ``None`` on any failure (network error, no releases, etc.).
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    try:
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "Raphael"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        assets = [
            {
                "name": a["name"],
                "url": a["browser_download_url"],
                "size": a["size"],
            }
            for a in data.get("assets", [])
        ]

        return ReleaseInfo(
            tag_name=data["tag_name"],
            html_url=data["html_url"],
            body=data.get("body", ""),
            assets=assets,
        )
    except Exception as exc:
        logger.debug("Failed to fetch latest release: %s", exc)
        return None


def check_for_update() -> ReleaseInfo | None:
    """Check if a newer version is available.

    Returns ``ReleaseInfo`` if a newer version exists, ``None`` otherwise.
    """
    release = get_latest_release()
    if release is None:
        return None
    if not _is_newer_version(release.tag_name):
        logger.info("Already at latest version (%s)", config.VERSION)
        return None
    logger.info(
        "Update available: %s -> %s", config.VERSION, release.tag_name
    )
    return release


def find_installer_asset(release: ReleaseInfo) -> dict | None:
    """Locate the ``*_Setup.exe`` asset in a release."""
    for asset in release.assets:
        name = asset["name"]
        if name.endswith("_Setup.exe") or "Setup" in name:
            return asset
    return None


def download_installer(
    release: ReleaseInfo,
    dest_dir: Path | None = None,
    progress_callback: callable | None = None,
) -> Path | None:
    """Download the installer exe to a local temp directory.

    Returns the local path on success, ``None`` on failure.
    """
    asset = find_installer_asset(release)
    if asset is None:
        logger.warning("No installer asset found in release %s", release.tag_name)
        return None

    if dest_dir is None:
        dest_dir = Path(tempfile.gettempdir()) / "raphael_update"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / asset["name"]

    logger.info("Downloading %s ...", asset["url"])

    def _report(count, block_size, total_size):
        if progress_callback and total_size > 0:
            pct = min(count * block_size * 100 // total_size, 100)
            progress_callback(pct)

    try:
        urllib.request.urlretrieve(asset["url"], dest_path, reporthook=_report)
        size_mb = dest_path.stat().st_size / 1024 / 1024
        logger.info("Download complete: %.0f MB", size_mb)
        return dest_path
    except Exception as exc:
        logger.error("Download failed: %s", exc)
        return None


def apply_update(installer_path: Path) -> None:
    """Launch the downloaded installer in silent mode and exit the current app.

    The installer will auto-upgrade over the existing installation
    (same ``AppId`` in Inno Setup).
    """
    logger.info("Starting silent upgrade from %s ...", installer_path)
    subprocess.Popen(
        [str(installer_path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
        shell=True,
    )
    os._exit(0)


# ── background check (for GUI mode) ───────────────────────────────────────


def _check_in_background(on_update_found: callable) -> None:
    """Run ``check_for_update`` in a daemon thread.

    *on_update_found* is called on the **main thread** with the
    ``ReleaseInfo`` if an update is available.
    """
    def _run():
        release = check_for_update()
        if release is not None:
            # Schedule callback on main thread via QTimer
            try:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(0, lambda: on_update_found(release))
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True, name="update-check")
    t.start()
