"""Windows service module.

Lists, starts, and stops Windows services via the C# ServiceHelper (WMI).
"""

import logging

logger = logging.getLogger(__name__)

try:
    from hybrid.bridge import CServiceManager as CsSvc, is_available
    _CS_SVC = is_available()
except ImportError:
    _CS_SVC = False


def service_list() -> str:
    """Return all services formatted as name | display name | state | start mode."""
    if not _CS_SVC:
        return "C# bridge not available — cannot list services"
    try:
        services = CsSvc.List() or []
    except Exception as e:
        return f"Failed to list services: {e}"
    if not services:
        return "No services found."
    lines = [
        f"{s.get('name')} | {s.get('display_name')} | {s.get('state')} | {s.get('start_mode')}"
        for s in services
    ]
    return "\n".join(lines)


def service_start(name: str) -> str:
    """Start a service by name."""
    if not _CS_SVC:
        return "C# bridge not available — cannot start service"
    try:
        err = CsSvc.Start(name)
    except Exception as e:
        return f"Failed to start service {name}: {e}"
    if err:
        return f"Failed to start service '{name}': {err}"
    return f"Service '{name}' started."


def service_stop(name: str) -> str:
    """Stop a service by name."""
    if not _CS_SVC:
        return "C# bridge not available — cannot stop service"
    try:
        err = CsSvc.Stop(name)
    except Exception as e:
        return f"Failed to stop service {name}: {e}"
    if err:
        return f"Failed to stop service '{name}': {err}"
    return f"Service '{name}' stopped."
