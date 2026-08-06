"""
Cron Job Management — CRUD, schedule parsing, due detection

Pattern from hermes-agent/cron/jobs.py with Windows-compatible file locking.

Features:
- Add/remove/list/update jobs (CRUD)
- Multiple schedule formats: "30m", "every 2h", "0 9 * * *", "2026-08-07T14:00"
- Due job detection with grace window
- Cross-process advisory file locking (msvcrt on Windows, fcntl on Unix)
- Atomic file writes
"""

import json
import logging
import os
import re
import threading
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── File locking ───────────────────────────────────────────────────────────

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False
    try:
        import msvcrt
        HAS_MSVCRT = True
    except ImportError:
        HAS_MSVCRT = False
        msvcrt = None

_jobs_file_lock = threading.RLock()


def _get_jobs_path() -> Path:
    """Get path to jobs.json file."""
    from pathlib import Path
    from _user_settings.paths import get_data_dir
    
    try:
        data_dir = get_data_dir()
    except Exception:
        data_dir = Path(".").resolve()
    
    cron_dir = data_dir / "cron"
    cron_dir.mkdir(parents=True, exist_ok=True)
    return cron_dir / "jobs.json"


def _get_lock_file() -> Path:
    """Get path to lock file."""
    jobs_path = _get_jobs_path()
    return jobs_path.parent / ".jobs.lock"


@contextmanager
def _jobs_lock():
    """
    Cross-process advisory file locking.
    
    Uses msvcrt (Windows) or fcntl (Unix) for inter-process synchronization.
    Intra-process locking via RLock prevents re-entrancy issues.
    """
    with _jobs_file_lock:
        lock_file = _get_lock_file()
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        
        fd = None
        try:
            fd = open(lock_file, "a+")
            
            # Acquire cross-process lock
            if HAS_MSVCRT and hasattr(fd, "fileno"):
                try:
                    msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
                except (OSError, IOError) as e:
                    logger.warning("msvcrt.locking failed: %s (proceeding without lock)", e)
            elif HAS_FCNTL:
                try:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
                except (OSError, IOError) as e:
                    logger.warning("fcntl.flock failed: %s (proceeding without lock)", e)
            
            yield
            
            # Release lock
            if HAS_MSVCRT and hasattr(fd, "fileno"):
                try:
                    msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                except (OSError, IOError):
                    pass
            elif HAS_FCNTL:
                try:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
                except (OSError, IOError):
                    pass
        finally:
            if fd:
                fd.close()


# ── Schedule Parsing ──────────────────────────────────────────────────────

def parse_schedule(schedule_str: str) -> Dict[str, Any]:
    """
    Parse various schedule formats into a normalized dict.
    
    Formats:
    - "30m" / "30 minutes" → Run once in 30 minutes
    - "every 30m" → Recurring every 30 minutes
    - "every 2h" → Recurring every 2 hours
    - "every 1d" → Recurring daily
    - "0 9 * * *" → Cron expression (requires croniter)
    - "2026-08-07T14:00" → Run once at specific time (ISO format)
    
    Returns:
        {"kind": "interval"|"once"|"cron", "value": ..., "next_run": ISO timestamp}
    """
    s = schedule_str.strip().lower()
    
    # ── Relative time (once) ─────────────────────────────────────
    # "30m", "2h", "1d", etc.
    match = re.match(r"^(\d+)\s*([mhd])$", s)
    if match:
        value, unit = match.groups()
        value = int(value)
        
        if unit == "m":
            delta = timedelta(minutes=value)
        elif unit == "h":
            delta = timedelta(hours=value)
        elif unit == "d":
            delta = timedelta(days=value)
        
        next_run = (datetime.now() + delta).isoformat()
        return {"kind": "once", "value": value, "unit": unit, "next_run": next_run}
    
    # ── Recurring interval ───────────────────────────────────────
    # "every 30m", "every 2h", "every 1d"
    match = re.match(r"^every\s+(\d+)\s*([mhd])$", s)
    if match:
        value, unit = match.groups()
        value = int(value)
        
        if unit == "m":
            delta = timedelta(minutes=value)
        elif unit == "h":
            delta = timedelta(hours=value)
        elif unit == "d":
            delta = timedelta(days=value)
        
        next_run = (datetime.now() + delta).isoformat()
        return {"kind": "interval", "value": value, "unit": unit, "next_run": next_run}
    
    # ── ISO timestamp ────────────────────────────────────────────
    # "2026-08-07T14:00"
    if "T" in s or "t" in s:
        try:
            dt = datetime.fromisoformat(s.replace("z", "+00:00"))
            return {"kind": "once", "value": schedule_str.strip(), "next_run": dt.isoformat()}
        except ValueError:
            pass
    
    # ── Cron expression ──────────────────────────────────────────
    # "0 9 * * *" — requires croniter library
    # For MVP, we'll accept it but note that croniter is optional
    if re.match(r"^\d+\s+\d+\s+\*?\s+\*?\s+\*?$", s):
        try:
            from croniter import croniter
            cron = croniter(s, datetime.now())
            next_run = cron.get_next(datetime).isoformat()
            return {"kind": "cron", "value": s, "next_run": next_run}
        except ImportError:
            logger.warning("croniter not installed; cron expressions not supported")
            return {"kind": "unsupported", "error": "croniter required for cron expressions"}
        except Exception as e:
            return {"kind": "unsupported", "error": str(e)}
    
    return {"kind": "unsupported", "error": f"Invalid schedule: {schedule_str}"}


# ── Job CRUD Operations ────────────────────────────────────────────────────

def _load_jobs() -> Dict[str, Dict[str, Any]]:
    """Load jobs from disk (non-atomic read)."""
    jobs_path = _get_jobs_path()
    if not jobs_path.exists():
        return {}
    
    try:
        content = jobs_path.read_text(encoding="utf-8")
        data = json.loads(content)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.warning("Failed to load jobs: %s", e)
        return {}


def _save_jobs(jobs: Dict[str, Dict[str, Any]]) -> None:
    """Save jobs to disk (atomic write with temp file)."""
    jobs_path = _get_jobs_path()
    
    try:
        # Write to temp file
        fd, tmp_path = tempfile.mkstemp(
            dir=str(jobs_path.parent),
            suffix=".tmp",
            prefix=".jobs"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass  # fsync not available on all platforms
        
        # Atomic rename
        Path(tmp_path).replace(jobs_path)
        logger.debug("Jobs saved to %s", jobs_path)
    except Exception as e:
        logger.error("Failed to save jobs: %s", e)


def add_job(
    prompt: str,
    schedule: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    """
    Add a new cron job.
    
    Args:
        prompt: The prompt to send to the LLM (what the job does)
        schedule: Schedule string ("30m", "every 2h", "0 9 * * *", "2026-08-07T14:00")
        name: Optional display name
        description: Optional longer description
        enabled: Whether job is active
    
    Returns:
        Created job dict
    """
    with _jobs_lock():
        jobs = _load_jobs()
        
        # Generate job ID
        import hashlib
        import uuid
        job_id = hashlib.md5(
            f"{prompt}{datetime.now().isoformat()}{uuid.uuid4().hex}".encode("utf-8")
        ).hexdigest()[:12]
        
        # Parse schedule
        schedule_info = parse_schedule(schedule)
        if schedule_info.get("kind") == "unsupported":
            raise ValueError(f"Invalid schedule: {schedule_info.get('error')}")
        
        job = {
            "id": job_id,
            "prompt": prompt,
            "schedule_format": schedule,
            "schedule": schedule_info,
            "name": name or f"Job {job_id[:8]}",
            "description": description or "",
            "enabled": enabled,
            "created": datetime.now().isoformat(),
            "last_run": None,
            "next_run": schedule_info.get("next_run"),
            "run_count": 0,
            "last_error": None,
        }
        
        jobs[job_id] = job
        _save_jobs(jobs)
        logger.info("Added job %s: %s", job_id, name or prompt[:30])
        return job


def remove_job(job_id: str) -> bool:
    """Remove a job by ID."""
    with _jobs_lock():
        jobs = _load_jobs()
        if job_id in jobs:
            del jobs[job_id]
            _save_jobs(jobs)
            logger.info("Removed job %s", job_id)
            return True
        return False


def get_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a job by ID."""
    with _jobs_lock():
        jobs = _load_jobs()
        return jobs.get(job_id)


def list_jobs(enabled_only: bool = False) -> List[Dict[str, Any]]:
    """List all jobs (optionally filtered to enabled only)."""
    with _jobs_lock():
        jobs = _load_jobs()
        job_list = list(jobs.values())
        
        if enabled_only:
            job_list = [j for j in job_list if j.get("enabled", True)]
        
        return sorted(job_list, key=lambda j: j.get("next_run", ""))


def update_job(job_id: str, **kwargs) -> Optional[Dict[str, Any]]:
    """
    Update a job's fields.
    
    Allowed fields: name, description, schedule, enabled, last_run, next_run, etc.
    """
    with _jobs_lock():
        jobs = _load_jobs()
        if job_id not in jobs:
            return None
        
        job = jobs[job_id]
        
        # Update schedule if provided
        if "schedule" in kwargs:
            schedule_str = kwargs.pop("schedule")
            schedule_info = parse_schedule(schedule_str)
            if schedule_info.get("kind") != "unsupported":
                job["schedule_format"] = schedule_str
                job["schedule"] = schedule_info
                job["next_run"] = schedule_info.get("next_run")
        
        # Update other fields
        allowed_fields = {"name", "description", "enabled", "last_run", "last_error"}
        for key, value in kwargs.items():
            if key in allowed_fields:
                job[key] = value
        
        _save_jobs(jobs)
        logger.info("Updated job %s", job_id)
        return job


# ── Due Job Detection ──────────────────────────────────────────────────────

def get_due_jobs(grace_window_seconds: float = 5.0) -> List[Dict[str, Any]]:
    """
    Get all jobs that are due to run.
    
    Args:
        grace_window_seconds: How many seconds past due to still consider a job runnable.
                             Prevents race conditions with fast tickers.
    
    Returns:
        List of due jobs, sorted by next_run time
    """
    with _jobs_lock():
        jobs = _load_jobs()
        
        now = datetime.now()
        grace = timedelta(seconds=grace_window_seconds)
        due = []
        
        for job in jobs.values():
            # Skip disabled jobs
            if not job.get("enabled", True):
                continue
            
            # Parse next_run timestamp
            try:
                next_run_str = job.get("next_run")
                if not next_run_str:
                    continue
                
                next_run = datetime.fromisoformat(next_run_str)
                
                # Check if due (now >= next_run - grace)
                if now >= next_run - grace:
                    due.append(job)
            except (ValueError, TypeError) as e:
                logger.warning("Failed to parse next_run for job %s: %s", job.get("id"), e)
        
        # Sort by next_run time
        due.sort(key=lambda j: j.get("next_run", ""))
        return due


def mark_job_run(job_id: str, success: bool = True, error: Optional[str] = None) -> None:
    """Mark a job as having run (update run_count, last_run, next_run)."""
    with _jobs_lock():
        jobs = _load_jobs()
        if job_id not in jobs:
            return
        
        job = jobs[job_id]
        job["last_run"] = datetime.now().isoformat()
        job["run_count"] = job.get("run_count", 0) + 1
        
        if not success and error:
            job["last_error"] = error
        else:
            job["last_error"] = None
        
        # Calculate next_run based on schedule kind
        schedule_info = job.get("schedule", {})
        kind = schedule_info.get("kind")
        
        if kind == "once":
            # One-time job; mark as completed (no future run)
            job["next_run"] = None
        elif kind == "interval":
            # Recurring: calculate next run from now
            unit = schedule_info.get("unit", "m")
            value = schedule_info.get("value", 1)
            
            if unit == "m":
                delta = timedelta(minutes=value)
            elif unit == "h":
                delta = timedelta(hours=value)
            elif unit == "d":
                delta = timedelta(days=value)
            else:
                delta = timedelta(minutes=1)
            
            job["next_run"] = (datetime.now() + delta).isoformat()
        elif kind == "cron":
            # Cron: calculate next run using croniter
            try:
                from croniter import croniter
                cron_expr = schedule_info.get("value")
                cron = croniter(cron_expr, datetime.now())
                job["next_run"] = cron.get_next(datetime).isoformat()
            except Exception as e:
                logger.warning("Failed to calculate next cron run: %s", e)
                job["next_run"] = None
        
        _save_jobs(jobs)
        logger.debug("Marked job %s as run (count: %d)", job_id, job["run_count"])


# ── Convenience Functions ──────────────────────────────────────────────────

def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed status of a single job."""
    job = get_job(job_id)
    if not job:
        return None
    
    return {
        "id": job["id"],
        "name": job.get("name", ""),
        "enabled": job.get("enabled", True),
        "schedule": job.get("schedule_format", ""),
        "next_run": job.get("next_run"),
        "last_run": job.get("last_run"),
        "run_count": job.get("run_count", 0),
        "last_error": job.get("last_error"),
    }


def disable_job(job_id: str) -> bool:
    """Disable a job without removing it."""
    result = update_job(job_id, enabled=False)
    return result is not None


def enable_job(job_id: str) -> bool:
    """Enable a previously disabled job."""
    result = update_job(job_id, enabled=True)
    return result is not None


def clear_all_jobs() -> int:
    """Clear all jobs (for testing/reset)."""
    with _jobs_lock():
        jobs = _load_jobs()
        count = len(jobs)
        _save_jobs({})
        logger.warning("Cleared %d jobs", count)
        return count
