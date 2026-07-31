"""System tools — launch apps, open URLs, run commands.

App launching now uses librarian-aware memory: if an app isn't in config.APPS,
it checks previously learned paths in memory, searches Windows if still unknown,
and saves the result for next time.
"""

import logging
import os
import subprocess
import webbrowser
from pathlib import Path

# Optional C# hybrid bridge
try:
    from hybrid.bridge import CShellHelper as CsShell
    from hybrid.bridge import is_available
    _CS_SHELL = is_available()
except ImportError:
    _CS_SHELL = False

logger = logging.getLogger(__name__)

# Common install locations for searching unknown apps
_SEARCH_ROOTS = [
    Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")),
    Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")),
    Path(os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local")),
    Path(os.environ.get("APPDATA", "C:\\Users\\Default\\AppData\\Roaming")),
]


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "launch_app",
                "description": "Launch an application or open a URL. Works for apps listed in config, previously learned apps, or any .exe path. Unknown apps are auto-discovered and remembered.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "app_name": {
                            "type": "string",
                            "description": "Name of the app (e.g., 'notepad', 'chrome', 'soundcloud')",
                        }
                    },
                    "required": ["app_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "open_url",
                "description": "Open a URL in the default web browser",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The full URL to open",
                        }
                    },
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Run a system command and return the output",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The command to run",
                        }
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_system_volume",
                "description": "Get the current Windows system master volume level (0-100)",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "set_system_volume",
                "description": "Set the Windows system master volume level",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "integer",
                            "description": "Volume level from 0 to 100",
                        }
                    },
                    "required": ["level"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_agent_performance",
                "description": "Get agent performance metrics (call count, success rate, latency). Shows stats for all agents or a specific one.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_name": {
                            "type": "string",
                            "description": "Optional agent name to filter (e.g., 'raphael', 'analytics', 'researcher'). Omit for all.",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_tool_health",
                "description": "Run a health check on all tools or a specific tool. Reports latency, error rate, and state transition recommendations.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Optional tool name to check (e.g., 'compress_pdf'). Omit to check all tools.",
                        }
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "show_capability_graph",
                "description": "Show the dependency graph of all tools as a Mermaid.js diagram.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "export_tool",
                "description": "Package a generated tool into a .cap file for sharing. Only generated tools (from generated/production/) can be exported.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "Name of the generated tool to export.",
                        },
                    },
                    "required": ["tool_name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "import_tool",
                "description": "Install a tool from a .cap file. Validates dependencies and registers it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "cap_path": {
                            "type": "string",
                            "description": "Path to the .cap file to import.",
                        },
                    },
                    "required": ["cap_path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_marketplace",
                "description": "List all available .cap files in the local marketplace directory.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    ]


def check_tool_health(tool_name: str = "") -> str:
    """Run a health check on all tools or a specific tool."""
    from orchestrator.health_monitor import HealthMonitor
    monitor = HealthMonitor()
    if tool_name and tool_name.strip():
        result = monitor.check_tool(tool_name.strip())
        return monitor.format_report([result])
    return monitor.format_report()


def get_agent_performance(agent_name: str = "") -> str:
    """Return agent performance metrics as a formatted report."""
    from orchestrator.agent_metrics import MetricsCollector
    if agent_name and agent_name.strip():
        stats = MetricsCollector().get_stats(agent_name.strip())
    else:
        stats = MetricsCollector().get_stats()
    if not stats:
        return "No agent performance data recorded yet."
    return MetricsCollector().format_report()


def show_capability_graph() -> str:
    """Show the dependency graph of all tools."""
    from tools_meta.graph import show_capability_graph as _graph
    return _graph()


def export_tool(tool_name: str) -> str:
    """Export a generated tool to a .cap file."""
    from tools_meta.marketplace import export_tool as _export
    return _export(tool_name)


def import_tool(cap_path: str) -> str:
    """Install a tool from a .cap file."""
    from tools_meta.marketplace import import_tool as _import
    return _import(cap_path)


def list_marketplace() -> str:
    """List all .cap files in the marketplace."""
    from tools_meta.marketplace import list_marketplace as _list
    return _list()


def _load_app_paths() -> dict[str, str]:
    """Load previously learned app paths from memory."""
    try:
        from memory import load_memory
        memory = load_memory()
        app_paths = memory.get("feature_memory", {}).get("app_paths", {})
        if isinstance(app_paths, dict):
            return {k: v.get("value", "") if isinstance(v, dict) else str(v) for k, v in app_paths.items()}
    except Exception as e:
        logger.debug("Failed to load app paths from memory: %s", e)
    return {}


def _save_app_path_to_memory(app_name: str, app_path: str):
    """Save a discovered app path to memory so the librarian can recall it."""
    try:
        from memory import update_memory
        update_memory({
            "feature_memory": {
                "app_paths": {
                    app_name: {"value": app_path}
                }
            }
        })
        logger.info("Learned app path: %s → %s", app_name, app_path)
    except Exception as e:
        logger.debug("Failed to save app path to memory: %s", e)


def _search_app_path(app_name: str) -> str | None:
    """Search for an unknown app's executable path.

    Tries:
    1. `where.exe` (Windows PATH lookup)
    2. Scanning common install directories for matching .exe files
    3. Start Menu shortcuts (.lnk resolution)
    """
    name_lower = app_name.lower().strip()

    # 1. Try where.exe (fast PATH lookup)
    try:
        result = subprocess.run(
            ["where.exe", f"{name_lower}.exe"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            path = result.stdout.strip().split("\n")[0].strip()
            if path:
                return path
    except Exception:
        pass

    # 2. Try common install roots
    exe_name = f"{name_lower}.exe"
    for root in _SEARCH_ROOTS:
        if not root.exists():
            continue
        # Walk up to 3 levels deep (avoid crawling entire drive)
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                depth = dirpath.count(os.sep) - root.as_posix().count(os.sep)
                if depth > 3:
                    dirnames.clear()  # Don't go deeper
                    continue
                for f in filenames:
                    if f.lower() == exe_name:
                        found = os.path.join(dirpath, f)
                        return found
        except PermissionError:
            continue

    # 3. Try Start Menu shortcuts (search .lnk files by name match)
    start_menu_roots = [
        Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "Microsoft\\Windows\\Start Menu",
        Path(os.environ.get("APPDATA", "")) / "Microsoft\\Windows\\Start Menu",
    ]
    for root in start_menu_roots:
        if not root.exists():
            continue
        try:
            for f_path in root.rglob(f"{name_lower}.lnk"):
                # Shortcut found — try to resolve target via PowerShell
                try:
                    safe_path = str(f_path).replace("'", "''")
                    ps_cmd = (
                        f"(New-Object -COM WScript.Shell)."
                        f"CreateShortcut('{safe_path}').TargetPath"
                    )
                    result = subprocess.run(
                        ["powershell", "-NoProfile", "-Command", ps_cmd],
                        capture_output=True, text=True, timeout=5,
                    )
                    if result.returncode == 0:
                        target = result.stdout.strip()
                        if target and target.lower().endswith(".exe"):
                            return target
                except Exception:
                    pass
                return str(f_path)  # return the .lnk itself as fallback
        except PermissionError:
            continue

    return None


# ── Main tools ────────────────────────────────────────────────────────


def launch_app(app_name: str) -> str:
    """Launch an application or URL by name.

    First checks config.APPS (static), then checks librarian memory
    (previously learned paths), then searches Windows automatically.
    Newly discovered paths are saved to memory for future use.
    """
    if not app_name or not app_name.strip():
        return "Please provide an app name."

    app_name = app_name.strip()
    name_lower = app_name.lower()
    app_path = None

    # 1. Check static config.APPS
    import config
    app_path = config.APPS.get(name_lower)
    if app_path:
        logger.info("Launch from config.APPS: %s → %s", app_name, app_path)

    # 2. Check librarian memory for previously learned paths
    if not app_path:
        learned = _load_app_paths()
        app_path = learned.get(name_lower) or learned.get(app_name)
        if app_path:
            logger.info("Launch from memory: %s → %s", app_name, app_path)

    # 3. Auto-discover if still unknown
    if not app_path:
        logger.info("App '%s' not in config or memory — searching...", app_name)
        discovered = _search_app_path(app_name)
        if discovered:
            app_path = discovered
            logger.info("Discovered: %s → %s", app_name, app_path)
            # Save to memory for next time
            _save_app_path_to_memory(name_lower, app_path)

    # 4. Launch
    try:
        if app_path:
            if app_path.startswith("http"):
                webbrowser.open(app_path)
                return f"Opened {app_name} in browser."
            if _CS_SHELL:
                CsShell.Launch(app_path)
            else:
                subprocess.Popen([app_path])
            return f"Launched {app_name}."
        else:
            # Last resort — try as direct command
            if _CS_SHELL:
                CsShell.Launch(app_name)
            else:
                subprocess.Popen([app_name])
            return f"Attempted to launch {app_name}."
    except Exception as e:
        return f"Failed to launch {app_name}: {e}"


def open_url(url: str) -> str:
    """Open a URL in the default web browser."""
    webbrowser.open(url)
    return f"Opened {url} in the default browser."


def run_command(command: str) -> str:
    """Run a system command with timeout and process tree cleanup."""
    try:
        import shlex as _shlex
        cmd_args = _shlex.split(command)
        if not cmd_args:
            return "Empty command."
        proc = subprocess.Popen(
            cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        try:
            stdout, stderr = proc.communicate(timeout=25)
            output = stdout or stderr
            return output[:2000] if output else "Command completed with no output."
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            else:
                proc.kill()
            return "Command timed out after 25 seconds."
    except Exception as e:
        return f"Command failed: {e}"


def get_system_volume() -> str:
    """Get Windows system master volume level via pycaw."""
    try:
        from pycaw.pycaw import AudioUtilities

        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        scalar = volume.GetMasterVolumeLevelScalar()  # 0.0–1.0
        pct = round(scalar * 100)
        return f"System volume: {pct}%"
    except ImportError:
        return "pycaw not available — cannot read system volume"
    except Exception as e:
        return f"Failed to read system volume: {e}"


def set_system_volume(level: int) -> str:
    """Set Windows system master volume level via pycaw (0–100)."""
    level = max(0, min(100, level))
    try:
        from pycaw.pycaw import AudioUtilities

        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"System volume set to {level}%"
    except ImportError:
        return "pycaw not available — cannot set system volume"
    except Exception as e:
        return f"Failed to set system volume: {e}"
