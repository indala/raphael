"""Process control module.

Kills and waits for processes by PID via the C# ProcessHelper bridge.
Kills are guarded: Raphael's own process chain and terminal/editor
processes are protected and can never be killed by automation.
"""

import logging

from modules.ui_control import _get_protected_pids, _get_protected_process_names

logger = logging.getLogger(__name__)

try:
    from hybrid.bridge import CProcessHelper as CsProc, is_available
    _CS_PROC = is_available()
except ImportError:
    _CS_PROC = False


def _validate_pid(pid) -> int | None:
    """Coerce a PID to an int, returning None if invalid."""
    try:
        return int(pid)
    except (TypeError, ValueError):
        return None


def process_kill(pid) -> str:
    """Kill a process by PID, refusing protected processes."""
    if not _CS_PROC:
        return "C# bridge not available — cannot kill process"
    parsed = _validate_pid(pid)
    if parsed is None:
        return "Please provide a valid process PID (integer)."

    protected_pids = _get_protected_pids()
    protected_names = _get_protected_process_names()

    try:
        import psutil
        p = psutil.Process(parsed)
        if parsed in protected_pids or p.name().lower() in protected_names:
            return f"Refusing to kill protected process {parsed} ({p.name()})."
    except ImportError:
        pass
    except psutil.NoSuchProcess:
        return f"No process with PID {parsed} exists."

    try:
        err = CsProc.Kill(parsed)
    except Exception as e:
        return f"Failed to kill process {parsed}: {e}"
    if err:
        return f"Failed to kill process {parsed}: {err}"
    return f"Killed process {parsed}."


def process_wait(pid, timeout_s: int = 30) -> str:
    """Wait up to timeout_s for a process to exit."""
    if not _CS_PROC:
        return "C# bridge not available — cannot wait on process"
    parsed = _validate_pid(pid)
    if parsed is None:
        return "Please provide a valid process PID (integer)."
    try:
        timeout_s = max(0, int(timeout_s))
    except (TypeError, ValueError):
        return "Please provide a valid timeout in seconds."
    try:
        result = CsProc.Wait(parsed, timeout_s * 1000) or {}
    except Exception as e:
        return f"Failed to wait on process {parsed}: {e}"
    if result.get("error"):
        return f"Error waiting on process {parsed}: {result['error']}"
    if result.get("exited"):
        return f"Process {parsed} has exited."
    return f"Process {parsed} is still running after {timeout_s}s."
