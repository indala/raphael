"""
Cron Scheduler Package for Raphael

Provides background job scheduling with:
- Multiple schedule formats (interval, cron, once, timestamp)
- Cross-process file locking (Windows-compatible)
- Job persistence (JSON)
- Execution history tracking
- Graceful error handling

Architecture inspired by hermes-agent/cron/ system.
"""

from cron.jobs import (
    add_job,
    remove_job,
    get_job,
    list_jobs,
    update_job,
    get_due_jobs,
    parse_schedule,
)
from cron.scheduler import (
    tick,
    run_job,
    start_ticker_thread,
    stop_ticker_thread,
    get_running_jobs,
    is_ticker_running,
)

__all__ = [
    "add_job",
    "get_due_jobs",
    "get_job",
    "get_running_jobs",
    "is_ticker_running",
    "list_jobs",
    "parse_schedule",
    "remove_job",
    "run_job",
    "start_ticker_thread",
    "stop_ticker_thread",
    "tick",
    "update_job",
]
