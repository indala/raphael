"""
Baseline performance recorder — Task 1 (structured logging + baseline measurements).

Wraps the LLM turn pipeline and samples per-stage timings:
  - total_turn    process_message() end-to-end
  - prompt_build  system prompt + memory assembly
  - routing       LLM endpoint selection
  - tool_exec     per tool-call execution

Percentiles come from statistics.quantiles (stdlib). A daily snapshot
``baseline_YYYYMMDD.json`` is written under DATA_DIR/baselines when
``config.PERF_BASELINE_ENABLED`` is True (default False — zero overhead).
"""

import functools
import inspect
import json
import logging
import threading
import time
from datetime import date
from pathlib import Path
from statistics import quantiles

logger = logging.getLogger(__name__)

STAGES = ("total_turn", "prompt_build", "routing", "tool_exec")
_KEYS = ("p50", "p95", "p99")


class BaselineRecorder:
    """Thread-safe recorder of per-stage timing samples with daily JSON snapshots."""

    def __init__(self, out_dir: Path | None = None, enabled: bool | None = None):
        self._out_dir = Path(out_dir) if out_dir is not None else None
        self._enabled = enabled  # None → read config.PERF_BASELINE_ENABLED per call
        self._lock = threading.Lock()
        self._samples: dict[str, list[float]] = {s: [] for s in STAGES}

    def enabled(self) -> bool:
        if self._enabled is not None:
            return self._enabled
        import config

        return bool(getattr(config, "PERF_BASELINE_ENABLED", False))

    def record(self, stage: str, duration_ms: float) -> None:
        """Record one duration sample for *stage*. No-op when disabled."""
        if not self.enabled() or stage not in self._samples:
            return
        with self._lock:
            self._samples[stage].append(duration_ms)

    def record_block(self, stage: str):
        """Context manager timing a block in ms. Usage:

        with recorder.record_block("routing"):
            ...
        """
        rec = self

        class _Ctx:
            def __enter__(self):
                self._t0 = time.perf_counter()
                return self

            def __exit__(self, *exc):
                rec.record(stage, (time.perf_counter() - self._t0) * 1000)
                return False

        return _Ctx()

    def percentiles(self, stage: str) -> dict[str, float] | None:
        """Return {p50, p95, p99} for a stage, or None when unsampled."""
        with self._lock:
            samples = sorted(self._samples[stage]) if stage in self._samples else []
        if not samples:
            return None
        if len(samples) == 1:
            v = samples[0]
            return {"p50": v, "p95": v, "p99": v}
        # "inclusive" clamps to [min, max] — exclusive extrapolates beyond
        # the observed range, which would inflate p99 past the worst sample.
        q = quantiles(samples, n=100, method="inclusive")  # 99 cut points: index 49/94/98
        return {"p50": q[49], "p95": q[94], "p99": q[98]}

    def save(self, out_dir: Path | None = None) -> Path | None:
        """Write baseline_YYYYMMDD.json for every sampled stage.

        Returns the written path, or None when disabled or nothing was
        recorded (nothing sampled → no file).
        """
        if not self.enabled():
            return None
        target = Path(out_dir) if out_dir is not None else self._default_dir()
        target.mkdir(parents=True, exist_ok=True)
        doc: dict = {"date": date.today().isoformat(), "stages": {}}
        for stage in STAGES:
            pcts = self.percentiles(stage)
            if pcts is None:
                continue
            with self._lock:
                count = len(self._samples[stage])
            doc["stages"][stage] = {**_pcts_sorted(pcts), "count": count}
        path = target / f"baseline_{date.today().strftime('%Y%m%d')}.json"
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        logger.info("[BASELINE] snapshot written: %s (%d stages)", path, len(doc["stages"]))
        return path

    def _default_dir(self) -> Path:
        import config

        return Path(getattr(config, "DATA_DIR", Path("."))) / "baselines"


def _pcts_sorted(pcts: dict[str, float]) -> dict[str, float]:
    return {k: pcts[k] for k in _KEYS}


def baseline_timed(stage: str):
    """Decorator recording the wall time of a sync/async call into the recorder."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                recorder.record(stage, (time.perf_counter() - t0) * 1000)

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                recorder.record(stage, (time.perf_counter() - t0) * 1000)

        return async_wrapper if inspect.iscoroutinefunction(fn) else wrapper

    return deco


# Module-level singleton shared across the pipeline.
recorder = BaselineRecorder()
