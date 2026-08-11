"""Permission policy for Raphael tool calls.

Raphael is a personal desktop assistant, so routine local actions should feel
fast. Irreversible or system-level operations are never auto-allowed: they
either carry an explicit ``confirm=true`` from the conversation or raise a
``confirm_required`` decision that the HUD confirmation dialog resolves.
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


@dataclass(frozen=True)
class ConfirmationRequest:
    """Contract between the policy layer and the UI confirmation flow.

    Built when a tool call needs user approval; the executor hands it to
    its ``confirmation_provider`` (wired by the controller to the HUD).
    """

    tool_name: str
    args: dict[str, Any]
    reason: str
    risk: str


DESTRUCTIVE_COMMAND_PATTERNS = [
    r"\bdel\b",
    r"\berase\b",
    r"\brd\b",
    r"\brmdir\b",
    r"\bremove-item\b",
    r"\bremove-variable\b",
    r"\brm\b",
    r"\bformat\b",
    r"\bshutdown\b",
    r"\brestart-computer\b",
    r"\bstop-computer\b",
    r"\bsc\s+delete\b",
    r"\breg\s+delete\b",
    r"\btaskkill\b",
    r"\bkill\b",
]

SENSITIVE_COMMAND_PATTERNS = [
    r"\bnet\s+user\b",
    r"\bnet\s+localgroup\b",
    r"\bnew-localuser\b",
    r"\bremove-localuser\b",
    r"\badd-localgroupmember\b",
    r"\bremove-localgroupmember\b",
    r"\bset-executionpolicy\b",
    r"\bbcdedit\b",
    r"\bcipher\b",
    r"\btakeown\b",
    r"\bicacls\b",
    r"\bcredential\b",
    r"\bpassword\b",
    r"\btoken\b",
    r"\bsecret\b",
]

HIGH_IMPACT_TOOLS = {
    "power_hibernate",
    "power_reboot",
    "power_shutdown",
    "power_sleep",
    "process_kill",
    "recycle_bin_empty",
    "service_start",
    "service_stop",
    "env_set",
    "import_tool",
}


def evaluate_tool_call(tool_name: str, args: dict[str, Any] | None = None) -> PolicyDecision:
    """Classify a tool call."""
    args = args or {}

    if tool_name == "run_command":
        return _evaluate_command(str(args.get("command", "")))

    if tool_name == "launch_app":
        return _evaluate_launch(str(args.get("app_name", "")))

    if tool_name in HIGH_IMPACT_TOOLS and not bool(args.get("confirm")):
        return PolicyDecision(
            False,
            "confirm_required",
            f"{tool_name} can affect system state; ask the user to confirm",
            requires_confirmation=True,
        )

    return PolicyDecision(True, "auto_allowed")


def permission_message(tool_name: str, decision: PolicyDecision) -> str:
    """Return text for tools the policy did not auto-allow."""
    if decision.requires_confirmation:
        return f"Needs your confirmation: {tool_name}: {decision.reason}"
    return f"Blocked for safety: {tool_name}: {decision.reason}"


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
