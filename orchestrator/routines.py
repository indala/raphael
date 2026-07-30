"""
Startup and recurring routines for Raphael.

Routines are deliberately small: they describe what should run, when it should
run, and which tool performs the work. The main app can call this module on
launch without turning Raphael into a background daemon.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class RoutineSpec:
    name: str
    tool_name: str
    args: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    frequency: str = "every_launch"  # every_launch, daily, weekdays
    enabled: bool = True
    speak_summary: bool = True
    requires_internet: bool = False
    subagent: str = "automation"
    last_run: str | None = None  # YYYY-MM-DD


@dataclass(slots=True)
class RoutineResult:
    name: str
    ok: bool
    output: str
    skipped: bool = False
    reason: str = ""


def build_default_startup_routines(
    location: str | None = None,
    stock_symbols: Iterable[str] | None = None,
) -> list[RoutineSpec]:
    """Build a conservative startup routine list from known preferences."""
    routines: list[RoutineSpec] = []

    if location:
        routines.append(
            RoutineSpec(
                name="daily_weather",
                description=f"Weather briefing for {location}",
                tool_name="get_weather",
                args={"location": location, "forecast_days": 0},
                frequency="daily",
                requires_internet=True,
                subagent="research",
            )
        )

    for symbol in stock_symbols or []:
        routines.append(
            RoutineSpec(
                name=f"stock_{symbol.lower()}",
                description=f"Market snapshot for {symbol}",
                tool_name="web_search",
                args={"query": f"{symbol} stock price today"},
                frequency="daily",
                requires_internet=True,
                speak_summary=False,
                subagent="research",
            )
        )

    return routines


def should_run(routine: RoutineSpec, now: datetime | None = None) -> tuple[bool, str]:
    """Return whether a routine should run now and why."""
    now = now or datetime.now()
    if not routine.enabled:
        return False, "disabled"

    frequency = routine.frequency.lower()
    today = now.strftime("%Y-%m-%d")

    if frequency == "every_launch":
        return True, "every launch"

    if frequency == "daily":
        if routine.last_run == today:
            return False, "already ran today"
        return True, "daily"

    if frequency == "weekdays":
        if now.weekday() >= 5:
            return False, "weekend"
        if routine.last_run == today:
            return False, "already ran today"
        return True, "weekday"

    return False, f"unknown frequency: {routine.frequency}"


def run_startup_routines(executor, routines: Iterable[RoutineSpec], now: datetime | None = None) -> list[RoutineResult]:
    """Run due startup routines through the existing ToolExecutor (sequential, blocking)."""
    results: list[RoutineResult] = []
    for routine in routines:
        due, reason = should_run(routine, now)
        if not due:
            results.append(RoutineResult(routine.name, True, "", skipped=True, reason=reason))
            continue

        output = executor.execute(routine.tool_name, dict(routine.args))
        ok = not output.startswith("Error:") and not output.startswith("Blocked for safety:")
        results.append(RoutineResult(routine.name, ok, output, reason=reason))
    return results


def run_startup_routines_async(
    bg_runner,
    routines: Iterable[RoutineSpec],
    now: datetime | None = None,
) -> dict[str, str]:
    """
    Submit all due startup routines to the background runner in parallel.

    Returns immediately — routines run concurrently in the thread pool and
    fire on_done notifications when each completes. Raphael can begin
    listening for voice commands straight away without waiting for weather
    checks, stock lookups, etc.

    Returns a dict mapping routine name → task_id.
    """
    task_ids: dict[str, str] = {}
    for routine in routines:
        due, _reason = should_run(routine, now)
        if not due:
            continue
        task_id = bg_runner.submit_tool(
            routine.tool_name,
            dict(routine.args),
            label=routine.description or routine.name,
        )
        task_ids[routine.name] = task_id
    return task_ids
