"""
Task 1 tests — structured logging prefix constants, request/phase
correlation, and the BaselineRecorder (p50/p95/p99 JSON snapshots).

Hermetic: no LLM calls, no network. Logging is asserted via caplog
with the RequestIDFilter attached, and the recorder is driven directly
with synthetic samples.
"""

import json
import logging

import pytest

import config
from orchestrator.baseline import STAGES, BaselineRecorder, baseline_timed, recorder
from orchestrator.log_utils import (
    LOG_PREFIX_CACHE,
    LOG_PREFIX_INTENT,
    LOG_PREFIX_PARALLEL,
    LOG_PREFIX_PRIORITY,
    LOG_PREFIX_PROACTIVE,
    LOG_PREFIX_PROMPT,
    LOG_PREFIX_ROUTING,
    RequestIDFilter,
    clear_phase,
    clear_request_id,
    get_phase,
    log_prefixed,
    set_phase,
    set_request_id,
)

ALL_PREFIXES = [
    LOG_PREFIX_CACHE,
    LOG_PREFIX_PARALLEL,
    LOG_PREFIX_INTENT,
    LOG_PREFIX_PROACTIVE,
    LOG_PREFIX_PRIORITY,
    LOG_PREFIX_ROUTING,
    LOG_PREFIX_PROMPT,
]


@pytest.fixture(autouse=True)
def clean_log_context():
    clear_request_id()
    clear_phase()
    yield
    clear_request_id()
    clear_phase()


# ── Prefix constants ───────────────────────────────────────────────


def test_all_prefixes_emitted_in_one_mocked_turn(caplog):
    """A single mocked turn emits every subsystem prefix with req id + phase."""
    rid = set_request_id()
    set_phase("user")
    caplog.handler.addFilter(RequestIDFilter())
    with caplog.at_level(logging.INFO):
        for prefix in ALL_PREFIXES:
            log_prefixed(prefix, logging.INFO, "turn event")

    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == len(ALL_PREFIXES)
    for prefix in ALL_PREFIXES:
        line = next(ln for ln in lines if prefix in ln)
        assert f"[req={rid}]" in line, f"{prefix} line lacks request ID"
        assert "[phase=user]" in line, f"{prefix} line lacks phase"


def test_phase_propagates_from_context(caplog):
    rid = set_request_id()
    set_phase("proactive")
    caplog.handler.addFilter(RequestIDFilter())
    with caplog.at_level(logging.INFO):
        log_prefixed(LOG_PREFIX_PROACTIVE, logging.INFO, "idle check")
    line = caplog.records[0].getMessage()
    assert f"[req={rid}]" in line
    assert "[phase=proactive]" in line
    assert "[PROACTIVE]" in line
    assert get_phase() == "proactive"


def test_set_phase_rejects_unknown_lane():
    with pytest.raises(ValueError):
        set_phase("teleport")


def test_clear_phase_resets_to_user():
    set_phase("background")
    clear_phase()
    assert get_phase() == "user"


def test_request_id_filter_annotates_plain_record():
    rid = set_request_id()
    set_phase("background")
    rec = logging.LogRecord("orchestrator.x", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    assert RequestIDFilter().filter(rec) is True
    assert f"[req={rid}]" in rec.msg
    assert "[phase=background]" in rec.msg
    assert "hello world" in rec.getMessage()


def test_no_request_id_emits_phase_only(caplog):
    set_phase("user")
    caplog.handler.addFilter(RequestIDFilter())
    with caplog.at_level(logging.INFO):
        log_prefixed(LOG_PREFIX_CACHE, logging.INFO, "cold")
    line = caplog.records[0].getMessage()
    assert "[req=" not in line
    assert "[phase=user]" in line


# ── BaselineRecorder ───────────────────────────────────────────────


def test_recorder_noop_when_disabled():
    r = BaselineRecorder(enabled=False)
    r.record("total_turn", 123.0)
    assert r.percentiles("total_turn") is None


def test_disabled_save_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PERF_BASELINE_ENABLED", False)
    r = BaselineRecorder()
    r.record("total_turn", 5.0)
    assert r.save(tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_recorder_writes_valid_json_with_percentiles(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PERF_BASELINE_ENABLED", True)
    r = BaselineRecorder(enabled=True)
    for v in (10.0, 20.0, 30.0, 40.0, 100.0, 200.0):
        r.record("total_turn", v)
    r.record("prompt_build", 7.0)  # single sample

    path = r.save(tmp_path)
    assert path is not None
    assert path.name.startswith("baseline_") and path.suffix == ".json"

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert "date" in doc and "stages" in doc
    st = doc["stages"]["total_turn"]
    assert {"p50", "p95", "p99", "count"} <= set(st)
    assert st["count"] == 6
    assert 30.0 <= st["p50"] <= 40.0  # median of 6 samples
    assert st["p50"] <= st["p95"] <= st["p99"]
    assert st["p99"] <= 200.0  # inclusive quantiles clamp to the observed max
    # single-sample stage: flat percentiles
    assert doc["stages"]["prompt_build"] == {"p50": 7.0, "p95": 7.0, "p99": 7.0, "count": 1}
    # unsampled stages are omitted entirely
    assert "routing" not in doc["stages"]


def test_record_block_samples_duration(monkeypatch):
    monkeypatch.setattr(config, "PERF_BASELINE_ENABLED", True)
    r = BaselineRecorder(enabled=True)
    with r.record_block("routing"):
        pass
    p = r.percentiles("routing")
    assert p is not None and p["p50"] >= 0.0


def test_unknown_stage_ignored(monkeypatch):
    monkeypatch.setattr(config, "PERF_BASELINE_ENABLED", True)
    r = BaselineRecorder(enabled=True)
    r.record("not_a_stage", 42.0)
    assert all(r.percentiles(s) is None for s in STAGES)


def test_baseline_timed_decorator(monkeypatch):
    monkeypatch.setattr(config, "PERF_BASELINE_ENABLED", True)

    @baseline_timed("tool_exec")
    def work(x: int) -> int:
        return x * 2

    assert work(21) == 42  # transparent to callers
    # the decorator samples into the module-level singleton recorder
    p = recorder.percentiles("tool_exec")
    assert p is not None and p["p50"] >= 0.0
    assert work.__name__ == "work"  # functools.wraps intact
