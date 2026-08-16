"""Unit tests for orchestrator/evidence_ledger.py."""

from __future__ import annotations

from pathlib import Path

from orchestrator.evidence_ledger import EvidenceLedger, VerificationEvidence


def test_classify_command_types():
    assert EvidenceLedger.classify_command("pytest tests/test_smoke.py") == "test"
    assert EvidenceLedger.classify_command("python -m unittest discover") == "test"
    assert EvidenceLedger.classify_command("ruff check .") == "lint"
    assert EvidenceLedger.classify_command("mypy .") == "lint"
    assert EvidenceLedger.classify_command("python build_app.py") == "build"
    assert EvidenceLedger.classify_command("python -m compileall .") == "syntax"
    assert EvidenceLedger.classify_command("echo hello") == "ad_hoc"


def test_evidence_ledger_recording():
    ledger = EvidenceLedger()
    ev = ledger.record_command("pytest tests/", exit_code=0, output="10 passed", scope=["test_file.py"])

    assert isinstance(ev, VerificationEvidence)
    assert ev.kind == "test"
    assert ev.status == "passed"
    assert ev.is_successful is True

    summary = ledger.summary()
    assert summary["total_events"] == 1
    assert summary["passed_events"] == 1
    assert summary["failed_events"] == 0


def test_scope_verification_and_unverified_files(tmp_path: Path):
    ledger = EvidenceLedger()
    f1 = tmp_path / "mod1.py"
    f2 = tmp_path / "mod2.py"
    f1.write_text("print(1)")
    f2.write_text("print(2)")

    ledger.record_file_modification(f1)
    ledger.record_file_modification(f2)

    assert len(ledger.get_unverified_files()) == 2

    # Run test for f1
    ledger.record_command("pytest tests/test_mod1.py", exit_code=0, output="OK", scope=[str(f1)])
    assert ledger.is_scope_verified(f1) is True
    assert ledger.is_scope_verified(f2) is False
    assert ledger.get_unverified_files() == [str(f2.resolve())]

    # Run global test suite (empty scope = all files verified)
    ledger.record_command("pytest tests/", exit_code=0, output="All passed", scope=[])
    assert ledger.is_scope_verified(f2) is True
    assert len(ledger.get_unverified_files()) == 0
