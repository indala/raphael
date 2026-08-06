"""
Cron Scheduler — Background ticker and job execution

Pattern from hermes-agent/cron/scheduler.py with Windows compatibility.

Features:
- Background ticker thread (checks for due jobs every N seconds)
- Job execution with LLM integration
- Process state tracking (running jobs)
- Liveness monitoring (heartbeat file)
- Graceful error handling
- Delivery integration (TTS/notifications for results)
"""

import json
import logging
import os
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Global State ───────────────────────────────────────────────────────────

_ticker_thread: Optional[threading.Thread] = None
_ticker_stop_event = threading.Event()
_running_jobs: Dict[str, Dict[str, Any]] = {}
_running_jobs_lock = threading.Lock()


# ── Job Execution ──────────────────────────────────────────────────────────

def run_job(job: Dict[str, Any], orchestrator: Optional[Any] = None) -> Tuple[bool, str, Optional[str]]:
    """
    Execute a single cron job.
    
    Args:
        job: Job dict from cron.jobs
        orchestrator: RaphaelOrchestrator instance (obtained dynamically if None)
    
    Returns:
        (success: bool, output_doc: str, error_message: Optional[str])
    """
    job_id = job.get("id", "unknown")
    prompt = job.get("prompt", "")
    
    if not prompt:
        return False, "", "Job prompt is empty"
    
    # Get orchestrator if not provided
    if orchestrator is None:
        try:
            from orchestrator.core import RaphaelOrchestrator
            orchestrator = RaphaelOrchestrator()
        except Exception as e:
            logger.error("Failed to initialize orchestrator for job %s: %s", job_id, e)
            return False, "", f"Orchestrator init failed: {e}"
    
    logger.info("Running cron job %s: %s", job_id, prompt[:50])
    
    try:
        # Submit the job prompt as a read-only interaction
        # Similar to proactive checks but labeled as CRON_JOB
        full_prompt = f"[CRON_JOB:{job_id}] {prompt}"
        
        # Call orchestrator to process the interaction
        # This returns the assistant's response
        response = orchestrator.process_interaction(
            full_prompt,
            interaction_type="cron",
            read_only=True,
        )
        
        # Return success
        return True, response, None
    
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error("Job %s failed: %s\n%s", job_id, error_msg, traceback.format_exc())
        return False, "", error_msg


def run_job_background(job: Dict[str, Any], orchestrator: Optional[Any] = None) -> None:
    """
    Execute a job in the background with state tracking.
    
    Updates:
    - _running_jobs tracking
    - Job's last_run and run_count via cron.jobs.mark_job_run()
    """
    job_id = job.get("id", "unknown")
    
    try:
        # Track as running
        with _running_jobs_lock:
            _running_jobs[job_id] = {
                "started_at": datetime.now().isoformat(),
                "status": "running",
            }
        
        # Execute job
        success, output, error = run_job(job, orchestrator)
        
        # Update job record
        from cron.jobs import mark_job_run
        mark_job_run(job_id, success=success, error=error)
        
        # Log result
        if success:
            logger.info("Job %s completed successfully", job_id)
            if output:
                logger.debug("Job %s output: %s", job_id, output[:200])
        else:
            logger.error("Job %s failed: %s", job_id, error)
        
        # Update tracking
        with _running_jobs_lock:
            if job_id in _running_jobs:
                _running_jobs[job_id]["status"] = "completed" if success else "failed"
                _running_jobs[job_id]["finished_at"] = datetime.now().isoformat()
                _running_jobs[job_id]["error"] = error
    
    except Exception as e:
        logger.error("Unexpected error in job background execution: %s", e)
        with _running_jobs_lock:
            if job_id in _running_jobs:
                _running_jobs[job_id]["status"] = "error"
                _running_jobs[job_id]["error"] = str(e)
    
    finally:
        # Remove from running after a delay (keep for logs)
        time.sleep(2)
        with _running_jobs_lock:
            _running_jobs.pop(job_id, None)


# ── Ticker Loop ────────────────────────────────────────────────────────────

def tick(verbose: bool = True, sync: bool = True) -> int:
    """
    Perform one cron tick: find due jobs and execute them.
    
    Args:
        verbose: Log detailed tick info
        sync: If True, run jobs in background threads (non-blocking).
              If False, run synchronously (blocking).
    
    Returns:
        Number of jobs executed
    """
    from cron.jobs import get_due_jobs
    import config
    
    due_jobs = get_due_jobs(grace_window_seconds=5.0)
    
    if verbose and due_jobs:
        logger.debug("Cron tick: %d due job(s) found", len(due_jobs))
    
    executed = 0
    max_parallel = config.CRON_MAX_PARALLEL_JOBS
    
    with _running_jobs_lock:
        running_count = len(_running_jobs)
    
    for job in due_jobs:
        # Limit parallel execution
        if running_count >= max_parallel:
            logger.debug("Reached max parallel jobs (%d); deferring %s", max_parallel, job.get("id"))
            break
        
        if sync:
            # Synchronous execution (blocking)
            run_job_background(job)
        else:
            # Background thread execution (non-blocking)
            thread = threading.Thread(
                target=run_job_background,
                args=(job,),
                name=f"cron-job-{job.get('id', 'unknown')[:8]}",
                daemon=True,
            )
            thread.start()
        
        executed += 1
        running_count += 1
    
    return executed


def _ticker_loop(interval: int = 60, verbose: bool = False) -> None:
    """
    Main background ticker loop.
    
    Args:
        interval: Seconds between ticks
        verbose: Enable debug logging
    """
    logger.info("Cron ticker started (interval: %ds)", interval)
    
    while not _ticker_stop_event.is_set():
        try:
            # Perform one tick
            count = tick(verbose=verbose, sync=True)
            
            if count > 0 and verbose:
                logger.debug("Executed %d cron job(s) in this tick", count)
            
            # Record heartbeat
            _record_ticker_heartbeat()
        
        except Exception as e:
            logger.error("Error in cron ticker: %s\n%s", e, traceback.format_exc())
        
        # Sleep until next tick (check stop event frequently)
        for _ in range(interval):
            if _ticker_stop_event.is_set():
                break
            time.sleep(1)
    
    logger.info("Cron ticker stopped")


def start_ticker_thread(interval: int = 60, verbose: bool = False) -> bool:
    """
    Start the background cron ticker thread.
    
    Args:
        interval: Seconds between ticks
        verbose: Enable debug logging
    
    Returns:
        True if started, False if already running
    """
    global _ticker_thread
    
    if _ticker_thread is not None and _ticker_thread.is_alive():
        logger.warning("Cron ticker already running")
        return False
    
    _ticker_stop_event.clear()
    _ticker_thread = threading.Thread(
        target=_ticker_loop,
        args=(interval, verbose),
        name="cron-ticker",
        daemon=True,
    )
    _ticker_thread.start()
    logger.info("Cron ticker thread started")
    return True


def stop_ticker_thread(timeout: float = 5.0) -> bool:
    """
    Stop the background cron ticker thread gracefully.
    
    Args:
        timeout: Max seconds to wait for thread to stop
    
    Returns:
        True if stopped, False if timeout or not running
    """
    global _ticker_thread
    
    if _ticker_thread is None or not _ticker_thread.is_alive():
        logger.debug("Cron ticker not running")
        return True
    
    logger.info("Stopping cron ticker...")
    _ticker_stop_event.set()
    
    try:
        _ticker_thread.join(timeout=timeout)
        if _ticker_thread.is_alive():
            logger.warning("Cron ticker thread did not stop within %fs", timeout)
            return False
        logger.info("Cron ticker stopped")
        return True
    except Exception as e:
        logger.error("Error stopping cron ticker: %s", e)
        return False


def is_ticker_running() -> bool:
    """Check if cron ticker is running."""
    return _ticker_thread is not None and _ticker_thread.is_alive()


# ── Job State Tracking ─────────────────────────────────────────────────────

def get_running_jobs() -> List[Dict[str, Any]]:
    """Get list of currently running jobs."""
    with _running_jobs_lock:
        return [
            {
                "id": job_id,
                "started_at": data.get("started_at"),
                "status": data.get("status"),
            }
            for job_id, data in _running_jobs.items()
        ]


def get_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """Get status of a specific job (if running)."""
    with _running_jobs_lock:
        return _running_jobs.get(job_id)


# ── Ticker Heartbeat ───────────────────────────────────────────────────────

def _get_heartbeat_file() -> Path:
    """Get path to ticker heartbeat file."""
    from _user_settings.paths import get_data_dir
    
    try:
        data_dir = get_data_dir()
    except Exception:
        data_dir = Path(".").resolve()
    
    cron_dir = data_dir / "cron"
    cron_dir.mkdir(parents=True, exist_ok=True)
    return cron_dir / ".ticker_heartbeat"


def _record_ticker_heartbeat() -> None:
    """Record that ticker is alive (for monitoring)."""
    try:
        heartbeat_file = _get_heartbeat_file()
        heartbeat_data = {
            "timestamp": datetime.now().isoformat(),
            "running_jobs": len(_running_jobs),
            "pid": os.getpid(),
        }
        heartbeat_file.write_text(
            json.dumps(heartbeat_data, indent=2),
            encoding="utf-8"
        )
    except Exception as e:
        logger.debug("Failed to record heartbeat: %s", e)


def get_ticker_heartbeat() -> Optional[Dict[str, Any]]:
    """Get last recorded heartbeat (for health checks)."""
    try:
        heartbeat_file = _get_heartbeat_file()
        if heartbeat_file.exists():
            data = json.loads(heartbeat_file.read_text(encoding="utf-8"))
            return data
    except Exception as e:
        logger.debug("Failed to read heartbeat: %s", e)
    
    return None


def is_ticker_healthy(max_age_seconds: float = 120.0) -> bool:
    """Check if ticker has recorded a recent heartbeat."""
    heartbeat = get_ticker_heartbeat()
    if not heartbeat:
        return False
    
    try:
        last_beat = datetime.fromisoformat(heartbeat.get("timestamp", ""))
        age = (datetime.now() - last_beat).total_seconds()
        return age <= max_age_seconds
    except (ValueError, TypeError):
        return False


# ── Convenience Functions ─────────────────────────────────────────────────

def get_scheduler_status() -> Dict[str, Any]:
    """Get overall scheduler status."""
    return {
        "ticker_running": is_ticker_running(),
        "ticker_healthy": is_ticker_healthy(),
        "running_jobs": get_running_jobs(),
        "last_heartbeat": get_ticker_heartbeat(),
    }


# ── Cleanup on Exit ────────────────────────────────────────────────────────

def _cleanup_on_exit() -> None:
    """Called on application exit to cleanly shut down scheduler."""
    stop_ticker_thread(timeout=3.0)


# Register cleanup handler
import atexit
atexit.register(_cleanup_on_exit)
