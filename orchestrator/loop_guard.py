"""LoopGuard — tool-loop breakers for the LLM tool-call loop.

OpenJarvis pattern: detect and break degenerate tool-call repetition that the
existing failure-only guard misses. A model can loop productively-by-accident on
*successful* calls too:

* **Identical-call block** — the exact same call (name + canonicalized args,
  hashed with SHA-256) repeated N times in a row; breaks even when each call
  succeeds.
* **A-B-A-B ping-pong** — oscillation between two tools (open/close, show/hide…).
* **Poll-tool budget** — a hard cap on poll/status-style calls per request, so a
  stuck agent can't spin forever waiting on something.

State is intentionally *per request*: create one ``LoopGuard`` at the start of a
tool loop and discard it when the request ends, so no false positives carry
across independent user turns. Detectors fire once (a warning is injected, the
relevant counter resets) rather than spamming the model every round.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from typing import Any

import config

# Poll/status-style tool names that an agent may legitimately call in a loop
# while waiting — but should not call unboundedly in one request.
_POLL_NAME_RE = re.compile(r"poll|wait|status|check|progress|refresh|monitor", re.IGNORECASE)

# Search/filesystem-probe tool names — an agent should resolve a file path in
# at most a handful of attempts, not run 15+ shell searches across drives.
_SEARCH_NAME_RE = re.compile(
    r"run_system_command|run_command|list_directory|list_dir",
    re.IGNORECASE,
)


def _canonical_args(args: Any | None) -> str:
    """Stable string form of a tool-call's arguments for hashing.

    ``None``/empty -> ""; dicts serialized with sorted keys so key order never
    spuriously changes the signature.
    """
    if not args:
        return ""
    if isinstance(args, dict):
        return json.dumps(args, sort_keys=True, default=str)
    return str(args)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LoopGuard:
    """Per-request detector of degenerate tool-call loops.

    Thresholds default to ``config`` so production behavior is centralized,
    but may be overridden by constructor args for deterministic tests.
    """

    def __init__(
        self,
        identical_threshold: int | None = None,
        pingpong_threshold: int | None = None,
        poll_budget: int | None = None,
        search_budget: int | None = None,
    ) -> None:
        self.identical_threshold = (
            identical_threshold or int(getattr(config, "LOOP_GUARD_IDENTICAL_THRESHOLD", 3))
        )
        self.pingpong_threshold = (
            pingpong_threshold or int(getattr(config, "LOOP_GUARD_PINGPONG_THRESHOLD", 4))
        )
        self.poll_budget = poll_budget or int(getattr(config, "LOOP_GUARD_POLL_BUDGET", 5))
        self.search_budget = search_budget or int(getattr(config, "LOOP_GUARD_SEARCH_BUDGET", 5))

        # Rolling state (all reset naturally per-instance / per-request).
        self._id_hashes: deque[str] = deque(maxlen=self.identical_threshold)
        self._id_warned = False
        self._names: deque[str] = deque(maxlen=self.pingpong_threshold)
        self._ping_warned = False
        self._poll_count = 0
        self._poll_warned = False
        self._search_count = 0
        self._search_warned = False

    def check(self, tool_name: str, tool_args: Any | None = None, result: Any = "") -> str | None:
        """Record one executed tool call; return a warning to inject, else None.

        ``result`` is accepted for call-site symmetry but the detectors fire on
        repetition regardless of success/failure — that is the point.
        """
        # Identical-call block.
        sig = _sha256(f"{tool_name}|{_canonical_args(tool_args)}")
        self._id_hashes.append(sig)
        if (not self._id_warned
                and len(self._id_hashes) == self.identical_threshold
                and len(set(self._id_hashes)) == 1):
            self._id_warned = True
            self._id_hashes.clear()
            return (
                f"LoopGuard: you have called `{tool_name}` with identical arguments "
                f"{self.identical_threshold} times in a row. Stop repeating this exact call "
                "and change your approach."
            )

        # A-B-A-B ping-pong.
        self._names.append(tool_name)
        pp = self._detect_pingpong()
        if (not self._ping_warned and pp):
            self._ping_warned = True
            a, b = pp
            return (
                f"LoopGuard: you are oscillating between `{a}` and `{b}` "
                f"{self.pingpong_threshold} consecutive times. Break the loop and do something different."
            )

        # Poll-tool budget.
        if _POLL_NAME_RE.search(tool_name):
            self._poll_count += 1
            if not self._poll_warned and self._poll_count > self.poll_budget:
                self._poll_warned = True
                return (
                    f"LoopGuard: you have called polling/status tools {self._poll_count} times "
                    "this request without moving toward a final answer. Stop polling and either "
                    "act decisively or give your final answer now."
                )

        # Search/filesystem-probe budget — prevents 15+ shell searches for a file.
        if _SEARCH_NAME_RE.search(tool_name):
            self._search_count += 1
            if not self._search_warned and self._search_count > self.search_budget:
                self._search_warned = True
                return (
                    f"LoopGuard: you have called filesystem search/probe tools "
                    f"({tool_name}) {self._search_count} times this request. "
                    "Stop searching. If you created this file earlier in the conversation, "
                    "its exact path is listed in '=== FILES CREATED THIS SESSION ===' in your "
                    "system prompt — use that path directly with read_file then edit_file. "
                    "If the file was not created this session, tell the user you cannot locate it "
                    "and ask them to provide the exact path."
                )

        return None

    def _detect_pingpong(self) -> tuple[str, str] | None:
        """Return (A, B) if the last calls alternate A/B/A/B…, else None."""
        names = list(self._names)
        if len(names) < self.pingpong_threshold:
            return None
        # Sliding look at the two most recent: n[-1] vs n[-2]. Require the whole
        # window to alternate so non-oscillating runs don't trip it.
        tail = names[-(self.pingpong_threshold):]
        a, b = tail[0], tail[1]
        if a == b:
            return None
        for i in range(2, len(tail)):
            expected = a if i % 2 == 0 else b
            if tail[i] != expected:
                return None
        return a, b
