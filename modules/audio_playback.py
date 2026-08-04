"""Audio playback module.

Plays local audio files via the C# MCI bridge (audio_play_mp3) and stops
playback (audio_stop_all). Available only when the hybrid bridge is up.
"""

import logging

logger = logging.getLogger(__name__)

try:
    from hybrid.bridge import CAudioPlayer, is_available
    _CS_AUDIO = is_available()
except ImportError:
    _CS_AUDIO = False


def play_file(path: str) -> bool:
    """Play a local audio file via the C# MCI bridge. Returns True if launched."""
    if not _CS_AUDIO:
        logger.error("C# bridge not available — cannot play audio")
        return False
    try:
        CAudioPlayer.PlayMp3(path)
        return True
    except Exception as e:
        logger.error("C# PlayMp3 failed: %s", e)
        return False


def stop() -> bool:
    """Stop all C# MCI audio playback. Returns True if successful."""
    if not _CS_AUDIO:
        logger.warning("C# bridge not available — cannot stop audio")
        return False
    try:
        CAudioPlayer.StopAll()
        return True
    except Exception as e:
        logger.error("C# StopAll failed: %s", e)
        return False
