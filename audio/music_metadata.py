"""Song metadata extraction — title, artist, duration from file paths and ID3 tags."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_title(filepath: Path) -> str:
    """Extract a human-readable song title from a file path.

    Tries ID3 tags first via mutagen; falls back to cleaning the filename stem.
    """
    # Try mutagen for ID3 tags
    title = _try_mutagen_title(filepath)
    if title:
        return title

    # Fallback: clean up filename stem
    stem = filepath.stem
    # Remove common patterns like YouTube IDs, website names
    for sep in (" - YouTube", " (Official", " [", " (Audio)"):
        idx = stem.find(sep)
        if idx > 0:
            stem = stem[:idx]
            break
    # Replace separators with spaces
    for ch in ("_", "-", "."):
        stem = stem.replace(ch, " ")
    # Collapse whitespace
    return " ".join(stem.split()).title()


def extract_artist(filepath: Path) -> str:
    """Extract artist name from ID3 tags, or return 'Unknown'."""
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(filepath, easy=True)
        if audio is not None and "artist" in audio:
            return audio["artist"][0]  # type: ignore[no-any-return]
    except Exception:
        pass
    return "Unknown"


def parse_duration(samples_len: int, sample_rate: int) -> float:
    """Calculate duration in seconds from sample count and rate."""
    if sample_rate <= 0:
        return 0.0
    return samples_len / sample_rate


def _try_mutagen_title(filepath: Path) -> str | None:
    """Return title from ID3 tags if available."""
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(filepath, easy=True)
        if audio is not None and "title" in audio:
            return audio["title"][0]  # type: ignore[no-any-return]
    except Exception:
        pass
    return None
