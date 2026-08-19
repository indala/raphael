"""Desktop state tools — taskbar, processes, system info, network, environment.

Gives Raphael full awareness of the desktop environment beyond visible windows.
All tools are read-only — they observe state, never modify it.
"""

import json
import logging
import os
import platform
import socket
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Suppress console windows when spawning console subprocesses (PowerShell, etc.)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Optional psutil
try:
    import psutil as _psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False
    _psutil = None  # type: ignore[assignment]

# Optional C# bridge
try:
    from hybrid.bridge import LazyBridge as _LazyBridge
    from hybrid.bridge import is_available as _bridge_available
    _BRIDGE_OK = _bridge_available()
except ImportError:
    _BRIDGE_OK = False
    _LazyBridge: type | None = None  # type: ignore[valid-type,misc,no-redef]


def _clean(text: str, max_len: int = 0) -> str:
    """Strip control chars and non-ASCII chars that break console output.

    Removes zero-width spaces, bidirectional text markers, and other
    invisible Unicode control characters. Keeps valid UTF-8 visible text.
    """
    cleaned = []
    for ch in text:
        # Keep printable chars, newlines, tabs
        if ch == "\n" or ch == "\t":
            cleaned.append(ch)
        elif ch.isprintable() and (ord(ch) < 127 or ord(ch) > 0x200B):
            # Skip zero-width space (U+200B) and similar invisible chars
            if ord(ch) not in (0x200B, 0x200C, 0x200D, 0xFEFF, 0x200E, 0x200F):
                cleaned.append(ch)
        elif ord(ch) < 32 and ch not in ("\n", "\t", "\r"):
            continue  # strip other control chars
    result = "".join(cleaned)
    if max_len and len(result) > max_len:
        result = result[:max_len] + "..."
    return result


def get_schemas() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "desktop_processes",
                "description": "List running processes sorted by CPU usage (top 30). Returns PID, process name, CPU%, memory MB, command line. Use this to discover what's actually running beyond visible windows.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_system_info",
                "description": "Get system specs and health: OS version, CPU cores, RAM (total/available/used%), disk (total/free/used%), uptime, boot time.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_network",
                "description": "Get network state: hostname, IP addresses per interface, connected WiFi SSID, internet connectivity status.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_environment",
                "description": "Get user environment: username, computer name, OS version, architecture, session type, key environment variables (PATH, TEMP, USERPROFILE, APPDATA, LOCALAPPDATA).",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_taskbar",
                "description": "Get running taskbar applications and pinned apps. Returns all visible application windows (what appears in the taskbar) with process name, window title, PID. Also shows pinned but not running apps if available.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_tray",
                "description": "Get notification area (system tray) icons and tooltips. Returns background app icons visible in the tray near the clock. Helps identify apps running silently in the background like OneDrive, antivirus, VPNs, sync clients.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "desktop_snapshot_v2",
                "description": "COMPREHENSIVE desktop snapshot in a single call. Combines: visible windows (with PIDs, process names, protected flags), system state (idle time, foreground process, power), system info (OS, RAM, disk), network state, environment, and mouse position. Use this at task start instead of multiple individual calls.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_active_window_info",
                "description": "Get rich information about the user's currently active (focused) foreground window: process name, window title, PID, position, and active Explorer path if applicable.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


# ── Process info ─────────────────────────────────────────────────────


def desktop_processes() -> str:
    """Top processes by CPU usage."""
    if not _HAS_PSUTIL:
        return _processes_fallback()

    try:
        procs = []
        for p in _psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_info", "cmdline", "status"]
        ):
            try:
                info = p.info
                info["cpu_percent"] = info["cpu_percent"] or 0.0
                mem = info.get("memory_info")
                if info["cpu_percent"] > 1.0 or (
                    mem is not None and mem.rss > 20 * 1024 * 1024
                ):
                    procs.append(info)
            except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                pass

        procs.sort(key=lambda p: p["cpu_percent"], reverse=True)
        top = procs[:30]

        lines = [f"Running processes (top {len(top)} by CPU):"]
        for p in top:
            mem_mb = (
                (p.get("memory_info") or _psutil._common.svmem(0, 0, 0, 0, 0, 0)).rss
                / 1024
                / 1024
            )
            cmd = (p.get("cmdline") or [""])[0] if p.get("cmdline") else ""
            name = p["name"] or "?"
            status = p.get("status", "")
            status_tag = f" [{status}]" if status and status != "running" else ""
            lines.append(
                f"  pid={p['pid']:>6}  cpu={p['cpu_percent']:>5.1f}%  "
                f"mem={mem_mb:>6.0f}MB{status_tag}  "
                f"{name}{'  ' + cmd[:80] if cmd else ''}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.error("desktop_processes error: %s", e)
        return f"Error: {e}"


def _processes_fallback() -> str:
    """Fallback via tasklist command."""
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_NO_WINDOW,
        )
        result.check_returncode()
        lines = ["Running processes (from tasklist):"]
        # tasklist CSV has: "name","pid","session","session#","mem"
        for line in result.stdout.strip().split("\n")[:30]:
            parts = line.strip().strip('"').split('","')
            if len(parts) >= 2:
                name, pid = parts[0], parts[1]
                lines.append(f"  pid={pid}  {name}")
        return "\n".join(lines)
    except Exception as e:
        return f"Process info unavailable: {e}"


# ── System info ─────────────────────────────────────────────────────


def desktop_system_info() -> str:
    """System specs and health."""
    parts = []

    # OS
    parts.append(
        f"OS: {platform.system()} {platform.release()} "
        f"(build {platform.version()})"
    )
    parts.append(f"Hostname: {platform.node()}")
    parts.append(f"Architecture: {platform.machine()}")
    parts.append(f"Processor: {platform.processor() or 'N/A'}")

    if _HAS_PSUTIL:
        try:
            # CPU
            parts.append(
                f"CPU cores: {_psutil.cpu_count(logical=True)} logical, "
                f"{_psutil.cpu_count(logical=False)} physical"
            )

            # RAM
            mem = _psutil.virtual_memory()
            parts.append(
                f"RAM: {mem.total / 1024**3:.1f}GB total, "
                f"{mem.available / 1024**3:.1f}GB available "
                f"({mem.percent:.0f}% used)"
            )

            # Disk
            for disk in _psutil.disk_partitions():
                try:
                    usage = _psutil.disk_usage(disk.mountpoint)
                    parts.append(
                        f"Disk {disk.device} ({disk.mountpoint}): "
                        f"{usage.total / 1024**3:.1f}GB total, "
                        f"{usage.free / 1024**3:.1f}GB free "
                        f"({usage.percent:.0f}% used)  "
                        f"fs={disk.fstype}"
                    )
                except (PermissionError, OSError):
                    pass

            # Uptime
            boot = _psutil.boot_time()
            uptime_s = time.time() - boot
            days, rem = divmod(int(uptime_s), 86400)
            hours, rem = divmod(rem, 3600)
            minutes = rem // 60
            parts.append(
                f"Uptime: {days}d {hours}h {minutes}m "
                f"(booted {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(boot))})"
            )
        except Exception as e:
            parts.append(f"(query error: {e})")

    return "\n".join(parts)


# ── Network ──────────────────────────────────────────────────────────


def desktop_network() -> str:
    """Network interfaces, WiFi, internet."""
    parts = []

    # Hostname + primary IP
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        parts.append(f"Hostname: {hostname}")
        parts.append(f"Primary IP: {ip}")
    except Exception as e:
        parts.append(f"Hostname/IP: {e}")

    # Interfaces via psutil
    if _HAS_PSUTIL:
        try:
            addrs = _psutil.net_if_addrs()
            stats = _psutil.net_if_stats()
            for iface, addr_list in addrs.items():
                if iface == "lo" or iface.startswith("Loopback"):
                    continue
                is_up = stats.get(iface, _psutil._common.snicstats(isup=False)).isup
                for a in addr_list:
                    if a.family == socket.AF_INET:
                        parts.append(
                            f"  {iface}: IP={a.address} "
                            f"netmask={a.netmask or '?'} "
                            f"{'UP' if is_up else 'DOWN'}"
                        )
        except Exception as e:
            logger.debug("Network interfaces query: %s", e)

    # WiFi SSID + internet (Windows)
    if os.name == "nt":
        try:
            r = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-NetConnectionProfile).Name",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=_NO_WINDOW,
            )
            ssid = r.stdout.strip()
            if ssid:
                parts.append(f"WiFi: {ssid}")

            try:
                # Fast TCP connection check — no subprocess
                sock = socket.create_connection(("8.8.8.8", 53), timeout=3)
                sock.close()
                parts.append("Internet: Connected")
            except (TimeoutError, OSError):
                parts.append("Internet: No connection")
        except Exception as e:
            logger.debug("WiFi/internet query: %s", e)

    return "\n".join(parts) if parts else "Network info unavailable."


# ── Environment ────────────────────────────────────────────────────


def desktop_environment() -> str:
    """User environment variables and session info."""
    parts = []
    parts.append(f"User: {os.environ.get('USERNAME', 'N/A')}")
    parts.append(f"Computer: {os.environ.get('COMPUTERNAME', platform.node())}")
    parts.append(f"OS: {platform.system()} {platform.release()} ({platform.version()})")
    parts.append(f"Arch: {platform.machine()}")

    # Session type
    session = "Remote Desktop" if os.environ.get("REMOTE_SESSION") else "Console"
    parts.append(f"Session: {session}")

    # Key env vars
    env_keys = [
        ("PATH", "[truncated to 300 chars]" if len(os.environ.get("PATH", "")) > 300 else ""),
        "TEMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "HOMEDRIVE",
        "SYSTEMROOT",
        "USERDOMAIN",
    ]
    for key in env_keys:
        if isinstance(key, tuple):
            key, trunc_label = key
        else:
            trunc_label = ""
        val = os.environ.get(str(key), "")
        if val and trunc_label and len(val) > 300:
            val = val[:300] + f"... ({trunc_label})"
        if val:
            parts.append(f"  {key}={val}")

    return "\n".join(parts)


# ── Taskbar ──────────────────────────────────────────────────────────


def desktop_taskbar() -> str:
    """Running taskbar apps and pinned items, cross-referenced."""
    # ── Gather pinned app names (folder + registry for Store apps) ──
    pinned_names = _get_pinned_apps_folder() | _get_pinned_apps_registry()

    # ── Gather running process names (for cross-ref) ──
    running_process_names: set[str] = set()
    if _HAS_PSUTIL:
        try:
            for p in _psutil.process_iter(["pid", "name"]):
                try:
                    nm = (p.info["name"] or "").lower()
                    if nm.endswith(".exe"):
                        nm = nm[:-4]
                    running_process_names.add(nm)
                except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                    pass
        except Exception:
            pass

    # AUMID-based app names → friendly display names
    AUMID_DISPLAY = {  # noqa: N806
        "windowsstore": "Microsoft Store",
        "microsoft.outlookforwindows": "Outlook (New)",
        "microsoft.bingweather": "Weather",
        "microsoft.windowsphotos": "Photos",
        "microsoft.windowsalarms": "Alarms & Clock",
        "microsoft.windowscalculator": "Calculator",
    }

    # Known app name ↔ process name mappings
    APP_NAME_MAP = {  # noqa: N806
        "microsoft edge": "msedge",
        "google chrome": "chrome",
        "microsoft excel": "excel",
        "microsoft word": "winword",
        "microsoft powerpoint": "powerpnt",
        "microsoft outlook": "outlook",
        "microsoft teams": "teams",
        "file explorer": "explorer",
        "windows terminal": "windowsterminal",
        "visual studio code": "code",
        "visual studio": "devenv",
        "powerToys": "powertoys",
    }

    # Infrastructure process names that don't have taskbar entries
    INFRA_PROCS = frozenset({  # noqa: N806
        "textinputhost", "applicationframehost", "microsoft.cmdpal.ui",
        "calculatorapp", "shellexperiencehost", "windowswindowmanager",
        "searchapp", "searchui", "startmenuexperiencehost",
        "svchost", "runtimebroker", "powertoys.quickaccess",
    })

    # ── Try C# bridge first ──
    if _BRIDGE_OK:
        try:
            data = _LazyBridge.call("taskbar_get_info")
            if data and isinstance(data, dict):
                lines = []
                running = data.get("running_apps", [])
                # Filter out infra processes and deduplicate by process name
                seen_running: set[str] = set()
                filtered = []
                for app in running:
                    pname = (app.get("name") or "").lower()
                    if pname in INFRA_PROCS:
                        continue
                    if pname in seen_running:
                        continue
                    seen_running.add(pname)
                    filtered.append(app)
                if filtered:
                    lines.append(f"Running taskbar apps ({len(filtered)}):")
                    for app in filtered:
                        lines.append(
                            f"  • {_clean(app.get('name', '?'))}  "
                            f"\"{_clean(app.get('title', ''), 120)}\"  "
                            f"pid={app.get('pid', 0)}"
                        )

                # Cross-reference pinned apps: running vs not running
                # Merge bridge pins + registry-detected pins (Store apps)
                bridge_pinned = data.get("pinned_apps", [])
                all_pinned = list(pinned_names)
                for p in bridge_pinned:
                    if p not in all_pinned:
                        all_pinned.append(p)

                pinned_running = []
                pinned_idle = []
                for app_name in all_pinned:
                    an = app_name.lower()
                    mapped = APP_NAME_MAP.get(an)
                    is_running = any(
                        (mapped and mapped in pn)
                        or (len(an) > 3 and an in pn)
                        or (len(pn) > 3 and pn in an)
                        for pn in running_process_names
                    )
                    if is_running:
                        pinned_running.append(app_name)
                    else:
                        pinned_idle.append(app_name)

                if pinned_running:
                    lines.append(f"\nPinned + running ({len(pinned_running)}):")
                    for app in sorted(pinned_running):
                        an = app.lower()
                        mapped = APP_NAME_MAP.get(an, an.replace(" ", ""))
                        display = AUMID_DISPLAY.get(an, app)
                        pids = []
                        if _HAS_PSUTIL:
                            for p in _psutil.process_iter(["pid", "name"]):
                                try:
                                    nm = ((p.info["name"] or "").lower()
                                          .replace(".exe", ""))
                                    if nm == mapped:
                                        pids.append(p.info["pid"])
                                except Exception:
                                    pass
                        pid_tag = f"  pid={','.join(str(x) for x in pids[:5])}" if pids else ""
                        lines.append(f"  • {display}{pid_tag}")
                if pinned_idle:
                    lines.append(f"\nPinned but not running ({len(pinned_idle)}):")
                    for app in sorted(pinned_idle):
                        display = AUMID_DISPLAY.get(app.lower(), app)
                        lines.append(f"  • {display}")

                if lines:
                    return "\n".join(lines)
        except Exception as e:
            logger.debug("Bridge taskbar_get_info failed: %s", e)

    # ── Fallback: visible windows + pinned folder ──
    from modules import ui_control
    windows = ui_control.enum_windows()
    lines = []
    seen_fb: set[str] = set()
    if windows:
        for w in windows:
            rect_left = w.get("rect_left", 0)
            if rect_left <= -32000:
                continue
            pname = (w.get("process_name") or "").lower()
            if pname in INFRA_PROCS:
                continue
            if pname in seen_fb:
                continue
            seen_fb.add(pname)
            fg = " [fg]" if w.get("is_foreground") else ""
            prot = " [protected]" if w.get("protected") else ""
            lines.append(
                f"  • {_clean(w.get('process_name', '?'))}  "
                f"\"{_clean(w.get('title', ''), 120)}\"  "
                f"pid={w.get('pid', 0)}{fg}{prot}"
            )
        if lines:
            lines.insert(0, f"Running taskbar apps ({len(lines)}):")

    if pinned_names:
        pinned_running = []
        pinned_idle = []
        for name in pinned_names:
            an = name.lower()
            mapped = APP_NAME_MAP.get(an)
            is_running = any(
                (mapped and mapped in pn) or (len(an) > 3 and an in pn) or (len(pn) > 3 and pn in an)
                for pn in running_process_names
            )
            if is_running:
                pinned_running.append(name)
            else:
                pinned_idle.append(name)
        if pinned_running:
            lines.append(f"\nPinned + running ({len(pinned_running)}):")
            for app in sorted(pinned_running):
                lines.append(f"  • {AUMID_DISPLAY.get(app.lower(), app)}")
        if pinned_idle:
            lines.append(f"\nPinned but not running ({len(pinned_idle)}):")
            for app in sorted(pinned_idle):
                lines.append(f"  • {AUMID_DISPLAY.get(app.lower(), app)}")

    return "\n".join(lines) if lines else "No taskbar apps found."



def _is_valid_app_name(name: str) -> bool:
    """Check if app name extracted from binary data is valid (not garbage)."""
    if not name or len(name) < 2 or len(name) > 50:
        return False
    lower = name.lower()
    if lower in ("desktop", "file explorer", "tombstones", "app"):
        return False
    if any(lower.startswith(p) for p in ("com-", "clsid-")):
        return False
    # All chars must be printable ASCII
    if not all(32 <= ord(c) <= 126 for c in name):
        return False
    # Must start with a letter
    if not name[0].isalpha():
        return False
    # Must not end with punctuation
    return name[-1] not in ('.', '-', '_', ' ')


def _get_pinned_apps_registry() -> set[str]:
    """Parse pinned apps from Taskband registry (handles both .lnk paths and AUMIDs)."""
    apps: set = set()
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Taskband"
        )
        data, _ = winreg.QueryValueEx(key, "Favorites")
        key.Close()
    except Exception:
        return apps

    try:
        # Scan for null-terminated Unicode strings containing known patterns
        i = 0
        while i < len(data) - 8:
            # Look for ".lnk\0" in Unicode
            if (data[i:i+2] == b'\x2e\x00' and  # '.'
                i + 6 < len(data) and
                data[i+2:i+4] == b'\x6c\x00' and  # 'l'
                data[i+4:i+6] == b'\x6e\x00' and  # 'n'
                data[i+6:i+8] == b'\x6b\x00'):   # 'k'
                j = i
                while j > 0 and data[j-2:j] != b'\x00\x00':
                    j -= 2
                if i > j:
                    path = data[j:i].decode('utf-16-le', errors='replace')
                    name = Path(path).stem if path.endswith('.lnk') else path
                    if name and len(name) > 1 and _is_valid_app_name(name):
                        apps.add(name)
                i += 8
                continue

            # Look for AUMID patterns (contains '!')
            if data[i] == ord('!') and i > 4:
                j = i - 2
                while j > 0 and data[j:j+2] != b'\x00\x00':
                    j -= 2
                k = i + 2
                while k < len(data) - 1 and data[k:k+2] != b'\x00\x00':
                    k += 2
                if i - j > 4 and k - i > 4:
                    aumid = data[j:k].decode('utf-16-le', errors='replace').strip('\x00')
                    if '!' in aumid:
                        parts = aumid.split('!')
                        if parts[1] and parts[1] != 'App' and _is_valid_app_name(parts[1]):
                            apps.add(parts[1])
                        elif '_' in parts[0]:
                            family = parts[0].split('_')[0]
                            base = family.split('.')[-1] if '.' in family else family
                            if _is_valid_app_name(base):
                                apps.add(base)
                i += 2
                continue
            i += 2
    except Exception:
        pass

    return apps


def _get_pinned_apps_folder() -> set[str]:
    """Read pinned app names from the shortcuts folder."""
    apps = set()
    try:
        folder = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"
        )
        if os.path.isdir(folder):
            for f in os.listdir(folder):
                if f.lower().endswith(".lnk"):
                    name = Path(f).stem
                    if name and name.lower() not in ("desktop", "file explorer"):
                        apps.add(name)
    except Exception:
        pass
    return apps


# ── Tray icons ───────────────────────────────────────────────────────


def desktop_tray() -> str:
    """Notification area icons — best-effort query."""
    if os.name != "nt":
        return "System tray is not available on this platform."

    if _BRIDGE_OK:
        try:
            icons = _LazyBridge.call("tray_get_icons")
            if icons and isinstance(icons, list):
                lines = [f"Tray icons ({len(icons)}):"]
                for icon in icons:
                    name = icon.get("name", icon.get("tooltip", "?"))
                    tip = icon.get("tooltip", "")
                    if tip and tip != name:
                        lines.append(f"  • {name} — \"{tip}\"")
                    else:
                        lines.append(f"  • {name}")
                return "\n".join(lines)
        except Exception as e:
            logger.debug("Bridge tray_get_icons failed: %s", e)

    # PowerShell fallback: query tray window children
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                """
$tray = Add-Type -MemberDefinition '
[DllImport("user32.dll")] public static extern IntPtr FindWindow(string cls, string win);
[DllImport("user32.dll")] public static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string cls, string win);
[DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder sb, int max);
[DllImport("user32.dll")] public static extern int SendMessage(IntPtr h, uint msg, IntPtr wp, System.Text.StringBuilder lp);
' -Name "Tray" -Namespace "Win32" -PassThru;
$trayWnd = [Win32.Tray]::FindWindow("Shell_TrayWnd", $null);
$notify = [Win32.Tray]::FindWindowEx($trayWnd, [IntPtr]::Zero, "TrayNotifyWnd", $null);
$toolbar = [Win32.Tray]::FindWindowEx($notify, [IntPtr]::Zero, "ToolbarWindow32", $null);
if ($toolbar -eq [IntPtr]::Zero) { exit; }
$count = [Win32.Tray]::SendMessage($toolbar, 0x418, [IntPtr]::Zero, [System.Text.StringBuilder]::new());  # TB_BUTTONCOUNT
$results = @();
for ($i = 0; $i -lt $count; $i++) {
    $sb = New-Object System.Text.StringBuilder 256;
    [Win32.Tray]::SendMessage($toolbar, 0x44D, [IntPtr]$i, $sb) | Out-Null;  # TB_GETBUTTONTEXTW
    $text = $sb.ToString().Trim();
    if ($text -ne "") { $results += $text; }
}
if ($results.Count -eq 0) { exit; }
ConvertTo-Json $results
""",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=_NO_WINDOW,
        )
        if r.returncode == 0 and r.stdout.strip() and r.stdout.strip() != "null":
            data = json.loads(r.stdout.strip())
            icons_list = data if isinstance(data, list) else [data]
            lines = [f"Tray icons ({len(icons_list)}):"]
            for icon in icons_list:
                if isinstance(icon, str) and icon.strip():
                    lines.append(f"  • {icon}")
                elif isinstance(icon, dict):
                    lines.append(
                        f"  • {icon.get('name', icon.get('tooltip', '?'))}"
                    )
            if len(lines) > 1:
                return "\n".join(lines)
    except json.JSONDecodeError:
        pass
    except Exception as e:
        logger.debug("Tray PowerShell query: %s", e)

    # Last resort: list background processes as approximate tray apps
    if _HAS_PSUTIL:
        try:
            tray_processes = []
            for p in _psutil.process_iter(["pid", "name"]):
                try:
                    name = (p.info["name"] or "").lower()
                    if any(
                        kw in name
                        for kw in ["one drive", "onedrive", "dropbox", "googledrive",
                                   "googledrivesync", "notify", "systray",
                                   "syncthing", "mega", "teamviewer", "anydesk",
                                   "vpn", "docker", "slack", "discord", "telegram",
                                   "skype", "spotify"]
                    ):
                        tray_processes.append(p.info)
                except (_psutil.NoSuchProcess, _psutil.AccessDenied):
                    pass

            if tray_processes:
                lines = [f"Background tray-like processes ({len(tray_processes)}):"]
                for t in tray_processes:
                    lines.append(f"  • {t['name']}  pid={t['pid']}")
                return "\n".join(lines)
        except Exception as e:
            logger.debug("Tray psutil fallback: %s", e)

    return "Tray icons: unable to query (PowerShell may have limited access)."


# ── Snapshot v2 (all-in-one) ────────────────────────────────────────


def desktop_snapshot_v2() -> str:
    """Comprehensive all-in-one desktop snapshot."""
    parts = []
    separator = "\n" + ("─" * 50) + "\n"

    # ── Environment ──
    try:
        parts.append(desktop_environment())
    except Exception as e:
        parts.append(f"Environment: {e}")

    parts.append(separator)

    # ── System info ──
    try:
        parts.append(desktop_system_info())
    except Exception as e:
        parts.append(f"System info: {e}")

    parts.append(separator)

    # ── Network ──
    try:
        net = desktop_network()
        if net and "unavailable" not in net.lower():
            parts.append(net)
    except Exception as e:
        parts.append(f"Network: {e}")

    parts.append(separator)

    # ── System state (idle, foreground, power) ──
    try:
        from modules import ui_control

        state = ui_control.get_user_state()
        state_lines = [
            f"Idle: {state.get('idle_seconds', 0):.0f}s",
        ]
        fg = state.get("foreground_process")
        if fg:
            state_lines.append(
                f"Foreground: pid={fg['pid']} name={fg['process_name']} "
                f"exe={fg.get('executable_path', '')} "
                f"mem={fg.get('memory_bytes', 0) / 1024 / 1024:.0f}MB"
            )
        else:
            state_lines.append("Foreground: (none)")
        state_lines.append(
            f"Full-screen app: {state.get('full_screen', False)}"
        )
        power = state.get("power") or {}
        if power:
            state_lines.append(
                f"Battery: {power.get('battery_remaining', '?')}% "
                f"charging={power.get('power_line_status', '?')}"
            )
        parts.append("\n".join(state_lines))
    except Exception as e:
        parts.append(f"System state: {e}")

    parts.append(separator)

    # ── Monitors ──
    try:
        from modules import ui_control

        monitors = ui_control.get_monitors()
        if monitors:
            mon_lines = [f"Monitors ({len(monitors)}):"]
            for m in monitors:
                primary = " (PRIMARY)" if m.get("is_primary") else ""
                mon_lines.append(
                    f"  {m.get('index', '?')}{primary}: "
                    f"bounds=({m.get('left', 0)},{m.get('top', 0)})"
                    f"-({m.get('right', 0)},{m.get('bottom', 0)})"
                )
            parts.append("\n".join(mon_lines))
    except Exception as e:
        parts.append(f"Monitors: {e}")

    parts.append(separator)

    # ── Mouse position ──
    try:
        from modules import ui_control

        pos = ui_control.get_mouse_position()
        if pos:
            parts.append(f"Mouse: X={pos[0]}, Y={pos[1]}")
        else:
            parts.append("Mouse: unknown")
    except Exception as e:
        parts.append(f"Mouse: {e}")

    # ── Visible windows ──
    try:
        from modules import ui_control

        windows = ui_control.enum_windows()
        if windows:
            win_lines = [f"Visible windows ({len(windows)}):"]
            for w in windows:
                rect_left = w.get("rect_left", 0)
                if rect_left <= -32000:
                    continue  # skip minimized/hidden
                prot = " PROTECTED" if w.get("protected") else ""
                fg = " [fg]" if w.get("is_foreground") else ""
                title = _clean(w.get("title", ""), 120)
                proc = _clean(w.get("process_name", ""))
                win_lines.append(
                    f"  [{w.get('handle', 0):#x}] \"{title}\"  "
                    f"{proc}  pid={w.get('pid', 0)}{fg}{prot}"
                )
            parts.append("\n".join(win_lines))
        else:
            parts.append("Visible windows: (none)")
    except Exception as e:
        parts.append(f"Windows: {e}")

    # ── Taskbar ──
    try:
        tb = desktop_taskbar()
        if tb and "taskbar" in tb.lower():
            parts.append(separator)
            parts.append(tb)
    except Exception as e:
        parts.append(f"Taskbar: {e}")

    # ── Tray ──
    try:
        tray = desktop_tray()
        if tray and "tray" in tray.lower() and "unable" not in tray.lower():
            parts.append(separator)
            parts.append(tray)
    except Exception as e:
        logger.debug("Tray in snapshot: %s", e)

    return "\n".join(parts)


def get_active_window_info() -> str:
    """Get rich information about the user's currently focused (active foreground) window."""
    from modules import ui_control
    try:
        windows = ui_control.enum_windows()
        fg_win = next((w for w in windows if w.get("is_foreground")), None)
        if not fg_win and windows:
            # First non-minimized window if none explicitly marked
            fg_win = next((w for w in windows if w.get("rect_left", 0) > -32000), None)

        if not fg_win:
            return "No active foreground window detected."

        title = fg_win.get("title", "Untitled")
        pname = fg_win.get("process_name", "Unknown")
        pid = fg_win.get("pid", 0)
        rect = f"{fg_win.get('rect_left', 0)},{fg_win.get('rect_top', 0)} to {fg_win.get('rect_right', 0)},{fg_win.get('rect_bottom', 0)}"

        # Check explorer selection if Explorer is active
        extra = ""
        if "explorer" in pname.lower():
            sel = ui_control.get_explorer_selection()
            if sel:
                folder = sel.get("folder", "")
                selected = sel.get("selected_files", [])
                extra = f"\n  • Explorer Folder: {folder}\n  • Selected Files ({len(selected)}): {', '.join(selected[:5])}"

        return (
            f"Active Foreground Window:\n"
            f"  • Process: {pname} (PID: {pid})\n"
            f"  • Title: \"{_clean(title, 150)}\"\n"
            f"  • Position: [{rect}]{extra}"
        )
    except Exception as e:
        logger.error("get_active_window_info error: %s", e)
        return f"Error detecting active window: {e}"
