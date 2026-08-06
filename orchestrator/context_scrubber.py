"""
StreamingContextScrubber — prevents memory context tags from leaking into streaming UI.

Adapted from hermes-agent's StreamingContextScrubber pattern. Strips injected
memory context markers from streaming responses so they never appear in the UI.

Pattern:
    [WHAT YOU KNOW ABOUT THIS PERSON -- use naturally, never recite like a list]
    [WHAT YOU KNOW ABOUT THE USER -- use naturally, never recite like a list]
    [Agent Evolution Memory — learned behavior for '...']
    
The LLM should never echo these tags, but as a safety net, this scrubber
removes them from the token stream during streaming responses.
"""

import re
from typing import Generator


class StreamingContextScrubber:
    """Scrubs memory context tags from streaming token chunks.
    
    Handles split-chunk detection: if a tag spans multiple chunks,
    the scrubber holds partial matches in a buffer until the full
    pattern completes or is ruled out.
    """

    # Patterns to scrub from streaming output
    _PATTERNS = [
        re.compile(r"\[WHAT YOU KNOW ABOUT (THIS PERSON|THE USER)[^\]]*\]", re.IGNORECASE),
        re.compile(r"\[Agent Evolution Memory[^\]]*\]", re.IGNORECASE),
        re.compile(r"\[Compressed history\]:", re.IGNORECASE),
        re.compile(r"\[TASK PROGRESS\]", re.IGNORECASE),
    ]

    # Prefix patterns that could start a tag (for buffer holding)
    _PREFIX_PATTERNS = [
        "[WHAT YOU KNOW",
        "[Agent Evolution",
        "[Compressed history",
        "[TASK PROGRESS",
    ]

    def __init__(self):
        self._buffer = ""

    def scrub_stream(self, tokens: Generator[str, None, None]) -> Generator[str, None, None]:
        """Scrub memory context tags from a token stream.
        
        Yields clean tokens with memory context markers removed.
        Handles split-chunk detection by buffering partial matches.
        """
        self._buffer = ""
        
        for token in tokens:
            self._buffer += token
            
            # Check if buffer contains a complete tag to remove
            cleaned = self._buffer
            for pattern in self._PATTERNS:
                cleaned = pattern.sub("", cleaned)
            
            # Check if buffer might be an incomplete tag prefix
            could_be_prefix = any(
                cleaned.endswith(prefix[:i])
                for prefix in self._PREFIX_PATTERNS
                for i in range(1, len(prefix) + 1)
            )
            
            if could_be_prefix:
                # Hold in buffer — might be incomplete tag
                continue
            
            # Buffer doesn't match any tag pattern — yield it
            if cleaned:
                yield cleaned
                self._buffer = ""
        
        # End of stream — yield any remaining buffer
        if self._buffer:
            # Do a final scrub pass
            cleaned = self._buffer
            for pattern in self._PATTERNS:
                cleaned = pattern.sub("", cleaned)
            if cleaned:
                yield cleaned
            self._buffer = ""

    def scrub_text(self, text: str) -> str:
        """Scrub memory context tags from a complete text string.
        
        Used for non-streaming responses or final assembly.
        """
        result = text
        for pattern in self._PATTERNS:
            result = pattern.sub("", result)
        return result


# Global singleton for convenience
_scrubber = StreamingContextScrubber()


def scrub_stream(tokens: Generator[str, None, None]) -> Generator[str, None, None]:
    """Scrub a token stream using the global scrubber instance."""
    return _scrubber.scrub_stream(tokens)


def scrub_text(text: str) -> str:
    """Scrub a text string using the global scrubber instance."""
    return _scrubber.scrub_text(text)
