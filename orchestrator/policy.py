"""
Permission policy for Raphael tool calls.

Only blocks truly destructive commands. Everything else is auto-allowed
since Raphael is a personal desktop assistant with the user present.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    risk: str
    reason: str = ""
    requires_confirmation: bool = False

    @property
    def blocked(self) -> bool:
        return not self.allowed and not self.requires_confirmation


DESTRUCTIVE_COMMAND_PATTERNS = [
    r"\bdel\b",
    r"\berase\b",
    r"\brd\b",
    r"\brmdir\b",
    r"\bremove-item\b",
    r"\brm\b",
    r"\bformat\b",
    r"\bshutdown\b",
    r"\brestart-computer\b",
    r"\bstop-computer\b",
    r"\breg\s+delete\b",
    r"\btaskkill\b",
    r"\bkill\b",
]

SENSITIVE_COMMAND_PATTERNS = [
    r"\bnet\s+user\b",
    r"\bnet\s+localgroup\b",
    r"\bset-executionpolicy\b",
    r"\bbcdedit\b",
    r"\bcipher\b",
    r"\bcredential\b",
    r"\bpassword\b",
    r"\btoken\b",
    r"\bsecret\b",
]


def evaluate_tool_call(tool_name: str, args: dict[str, Any] | None = None) -> PolicyDecision:
    """Classify a tool call. Only blocks destructive commands."""
    args = args or {}

    if tool_name == "run_command":
        return _evaluate_command(str(args.get("command", "")))

    if tool_name == "launch_app":
        return _evaluate_launch(str(args.get("app_name", "")))

    # Everything else is auto-allowed
    return PolicyDecision(True, "auto_allowed")


def permission_message(_tool_name: str, decision: PolicyDecision) -> str:
    """Return text for blocked tools."""
    if decision.blocked:
        return f"Blocked for safety: {decision.reason}"
    return "Allowed."


def _evaluate_launch(app_name: str) -> PolicyDecision:
    if not app_name.strip():
        return PolicyDecision(False, "blocked", "empty app name")
    if re.search(r'[;|&`$(){}]', app_name):
        return PolicyDecision(False, "blocked", "app name contains shell metacharacters")
    return PolicyDecision(True, "safe")


def _evaluate_command(command: str) -> PolicyDecision:
    normalized = _normalize_command(command)
    if not normalized:
        return PolicyDecision(False, "blocked", "empty command")

    if _matches_any(normalized, DESTRUCTIVE_COMMAND_PATTERNS):
        return PolicyDecision(False, "blocked", "that command looks destructive")

    if _matches_any(normalized, SENSITIVE_COMMAND_PATTERNS):
        return PolicyDecision(False, "blocked", "that command may affect credentials, accounts, or system policy")

    return PolicyDecision(True, "safe")


def _normalize_command(command: str) -> str:
    command = command.strip()
    if not command:
        return ""
    try:
        parts = shlex.split(command, posix=False)
        command = " ".join(parts)
    except ValueError:
        pass
    return re.sub(r"\s+", " ", command).lower()


def _matches_any(value: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in patterns)
