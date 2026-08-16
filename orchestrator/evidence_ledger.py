"""
Verification Evidence Ledger — Proof-based completion tracking for Raphael.

Inspired by Hermes Agent: tracks ground-truth evidence (command executions, exit codes,
test suite runs, linter passes, and modified file scopes) to prevent autonomous subagents
from declaring tasks complete without verification.
"""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Command classification patterns
_TEST_PATTERNS = re.compile(r"(pytest|unittest|jest|vitest|cargo\s+test|go\s+test|npm\s+test)", re.IGNORECASE)
_LINT_PATTERNS = re.compile(r"(ruff|flake8|eslint|mypy|pylint|black\s+--check|cargo\s+clippy)", re.IGNORECASE)
_SYNTAX_PATTERNS = re.compile(r"(compileall|py_compile|node\s+--check)", re.IGNORECASE)
_BUILD_PATTERNS = re.compile(r"(build|compile|cargo\s+build|dotnet\s+build|tsc|webpack|vite\s+build)", re.IGNORECASE)


@dataclass(frozen=True)
class VerificationEvidence:
    """A classified command or tool result proving an action's ground truth."""

    command: str
    kind: str           # "test" | "lint" | "build" | "syntax" | "ad_hoc"
    scope: tuple[str, ...]
    exit_code: int
    status: str         # "passed" | "failed"
    output_summary: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_successful(self) -> bool:
        return self.status == "passed" and self.exit_code == 0


class EvidenceLedger:
    """Thread-safe ledger recording verification actions across agent turns."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._evidence: list[VerificationEvidence] = []
        self._modified_files: set[str] = set()

    @staticmethod
    def classify_command(command: str) -> str:
        """Classify a shell command into a verification kind."""
        cmd = command.strip()
        if _TEST_PATTERNS.search(cmd):
            return "test"
        if _LINT_PATTERNS.search(cmd):
            return "lint"
        if _SYNTAX_PATTERNS.search(cmd):
            return "syntax"
        if _BUILD_PATTERNS.search(cmd):
            return "build"
        return "ad_hoc"

    def record_command(
        self,
        command: str,
        exit_code: int,
        output: str = "",
        scope: list[str] | tuple[str, ...] | None = None,
    ) -> VerificationEvidence:
        """Record a command execution in the evidence ledger."""
        kind = self.classify_command(command)
        status = "passed" if exit_code == 0 else "failed"
        norm_scope = tuple(str(Path(p).resolve()) for p in (scope or []))

        summary = output.strip()
        if len(summary) > 500:
            summary = summary[:250] + " ... " + summary[-250:]

        evidence = VerificationEvidence(
            command=command,
            kind=kind,
            scope=norm_scope,
            exit_code=exit_code,
            status=status,
            output_summary=summary,
        )

        with self._lock:
            self._evidence.append(evidence)

        logger.debug(
            "EvidenceLedger: recorded [%s] status=%s (exit %d) scope=%s",
            kind,
            status,
            exit_code,
            norm_scope,
        )
        return evidence

    def record_file_modification(self, file_path: str | Path) -> None:
        """Track that a file was modified and needs verification."""
        norm_path = str(Path(file_path).resolve())
        with self._lock:
            self._modified_files.add(norm_path)

    def is_scope_verified(self, file_path: str | Path) -> bool:
        """Check if any successful test/build/lint evidence covers the given file."""
        norm_path = str(Path(file_path).resolve())
        with self._lock:
            for ev in reversed(self._evidence):
                if ev.is_successful:
                    # An unconstrained test run (empty scope) or matching path counts as verification
                    if not ev.scope or norm_path in ev.scope or any(norm_path.endswith(s) for s in ev.scope):
                        return True
            return False

    def get_unverified_files(self) -> list[str]:
        """Return all modified files that lack successful verification evidence."""
        with self._lock:
            unverified = []
            for path in self._modified_files:
                verified = False
                for ev in reversed(self._evidence):
                    if ev.is_successful:
                        if not ev.scope or path in ev.scope or any(path.endswith(s) for s in ev.scope):
                            verified = True
                            break
                if not verified:
                    unverified.append(path)
            return unverified

    def summary(self) -> dict[str, Any]:
        """Return a structured summary of the verification ledger."""
        with self._lock:
            passed = sum(1 for e in self._evidence if e.is_successful)
            failed = sum(1 for e in self._evidence if not e.is_successful)
            return {
                "total_events": len(self._evidence),
                "passed_events": passed,
                "failed_events": failed,
                "modified_files_count": len(self._modified_files),
                "unverified_files": self.get_unverified_files(),
            }

    def clear(self) -> None:
        """Reset the evidence ledger."""
        with self._lock:
            self._evidence.clear()
            self._modified_files.clear()
