"""
Startup Timer — measures initialization phase durations for startup profiling.
"""

import time
from dataclasses import dataclass, field


@dataclass
class PhaseMark:
    name: str
    timestamp: float


class StartupTimer:
    """Collects phase timing markers and formats a startup profiling report."""

    def __init__(self, start_now: bool = True):
        self.marks: list[PhaseMark] = []
        if start_now:
            self.mark("start")

    def mark(self, phase_name: str) -> None:
        self.marks.append(PhaseMark(name=phase_name, timestamp=time.perf_counter()))

    def get_durations(self) -> list[tuple[str, float]]:
        """Return list of (phase_name, duration_seconds) for interval between consecutive marks."""
        if len(self.marks) < 2:
            return []

        durations = []
        for i in range(1, len(self.marks)):
            prev = self.marks[i - 1]
            curr = self.marks[i]
            dur = curr.timestamp - prev.timestamp
            durations.append((curr.name, dur))
        return durations

    def report(self) -> str:
        """Return a formatted phase timing table."""
        durations = self.get_durations()
        if not durations:
            return "Startup profiling: insufficient marks recorded."

        total_time = self.marks[-1].timestamp - self.marks[0].timestamp
        lines = [
            "\n" + "=" * 54,
            "              RAPHAEL STARTUP PROFILING             ",
            "=" * 54,
            f"{'Phase':<34} | {'Duration (s)':<14}",
            "-" * 54,
        ]

        for name, dur in durations:
            lines.append(f"{name:<34} | {dur:>12.3f}s")

        lines.append("-" * 54)
        lines.append(f"{'TOTAL STARTUP TIME':<34} | {total_time:>12.3f}s")
        lines.append("=" * 54 + "\n")
        return "\n".join(lines)
