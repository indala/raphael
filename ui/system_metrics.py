"""
System metrics monitor for Raphael HUD.
Polls CPU%, memory, and other system stats in a background thread.

Can use C# PerformanceCounters (via pythonnet) when available,
falling back to psutil.
"""

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

# Optional C# hybrid bridge — JSON subprocess (RaphaelBridge.exe)
try:
    from hybrid.bridge import CSystemMonitor as CsMonitor, is_available
    _CS_MONITOR = is_available() and CsMonitor is not None
except ImportError:
    _CS_MONITOR = False

import psutil


class SystemMonitor(threading.Thread):
    """Background thread that polls system metrics every interval_ms."""

    def __init__(self, interval_ms: float = 1500):
        super().__init__(daemon=True)
        self.interval = interval_ms / 1000.0
        self._lock = threading.Lock()
        self._running = True
        self._stop_event = threading.Event()

        # Latest readings
        self.cpu_percent = 0.0
        self.mem_percent = 0.0
        self.net_speed = 0.0  # KB/s
        self.gpu_percent = 0.0
        self.cpu_temp = 0.0

        # Net tracking
        self._last_net = 0
        self._last_net_time = time.time()

        # Callbacks for UI thread
        self._on_update: Callable[[float, float, float, float, float], object] | None = None

    def set_callback(self, cb: Callable[[float, float, float, float, float], object]) -> None:
        """Register a callback fn(cpu, mem, net, gpu, temp) called on each poll."""
        self._on_update = cb

    def stop(self):
        self._running = False
        self._stop_event.set()

    def read(self) -> dict:
        """Thread-safe snapshot of current readings."""
        with self._lock:
            return {
                "cpu": self.cpu_percent,
                "mem": self.mem_percent,
                "net": self.net_speed,
                "gpu": self.gpu_percent,
                "temp": self.cpu_temp,
            }

    def _poll_gpu(self) -> float:
        """Attempt to read GPU utilization via WMI or nvidia-smi."""
        # 1. NVIDIA fallback
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=1,
            )
            if result.returncode == 0:
                return float(result.stdout.strip().split("\n")[0])
        except Exception:
            pass

        # 2. General Windows WMI GPU Performance Counters (Intel, AMD, NVIDIA)
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine", "get", "UtilizationPercentage"],
                capture_output=True, text=True, timeout=1,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                total = 0.0
                for line in lines[1:]:
                    val = line.strip()
                    if val.isdigit():
                        total += float(val)
                return min(100.0, total)
        except Exception:
            pass

        return 0.0

    def _poll_temp(self) -> float:
        """Read CPU temperature via psutil, WMI, or ThermalZoneInformation."""
        # 1. psutil fallback (if platform supports it)
        sensors_temps = getattr(psutil, "sensors_temperatures", None)
        if sensors_temps:
            try:
                temps = sensors_temps()
                for _name, entries in temps.items():
                    if entries:
                        return float(entries[0].current)
            except Exception:
                pass

        # 2. Windows WMI ThermalZoneInformation (no Admin required)
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "Win32_PerfFormattedData_Counters_ThermalZoneInformation", "get", "HighPrecisionTemperature"],
                capture_output=True, text=True, timeout=1,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                temps = []
                for line in lines[1:]:
                    val = line.strip()
                    if val.isdigit():
                        temp_k = float(val) / 10.0
                        temp_c = temp_k - 273.15
                        if 0 <= temp_c <= 150:
                            temps.append(temp_c)
                if temps:
                    return max(temps)
        except Exception:
            pass

        # 3. Windows WMI fallback (requires Admin)
        try:
            import subprocess
            result = subprocess.run(
                ["wmic", "path", "Win32_TemperatureProbe", "get", "CurrentReading"],
                capture_output=True, text=True, timeout=1,
            )
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                val = lines[1].strip()
                if val and val.isdigit():
                    return float(val) / 10.0
        except Exception:
            pass

        return 0.0

    def run(self):
        # Initialize net tracking inside the background thread so it doesn't block the GUI thread during creation
        try:
            self._last_net = psutil.net_io_counters().bytes_recv
        except Exception:
            self._last_net = 0
        self._last_net_time = time.time()

        # If C# bridge available, use .NET PerformanceCounters
        if _CS_MONITOR:
            self._run_cs()
        else:
            self._run_python()

    def _run_cs(self):
        """Poll using C# SystemMonitor (.NET PerformanceCounters via bridge)."""
        consecutive_failures = 0
        while self._running:
            try:
                snap = CsMonitor.GetSnapshot()
                if snap is None:
                    consecutive_failures += 1
                    if consecutive_failures >= 3:
                        logger.debug("Bridge dead — stopping C# system monitor")
                        break
                    continue
                consecutive_failures = 0
                with self._lock:
                    self.cpu_percent = snap.get("cpu_percent", 0.0)
                    self.mem_percent = snap.get("mem_percent", 0.0)
                    self.net_speed = snap.get("net_speed_kbps", 0.0)
                    self.gpu_percent = snap.get("gpu_percent", 0.0)
                    self.cpu_temp = snap.get("cpu_temp", 0.0)

                if self._on_update:
                    self._on_update(
                        self.cpu_percent, self.mem_percent,
                        self.net_speed, self.gpu_percent, self.cpu_temp,
                    )
            except Exception:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    logger.debug("Bridge dead after failures — stopping C# system monitor")
                    break
            self._stop_event.wait(self.interval)

    def _run_python(self):
        """Poll using psutil (pure Python fallback)."""
        while self._running:
            try:
                cpu = psutil.cpu_percent(interval=0.3)
                mem = psutil.virtual_memory().percent

                # Network speed
                now = time.time()
                net = psutil.net_io_counters().bytes_recv
                elapsed = now - self._last_net_time
                net_speed = ((net - self._last_net) / elapsed) / 1024 if elapsed > 0 else 0
                self._last_net = net
                self._last_net_time = now

                gpu = self._poll_gpu()
                temp = self._poll_temp()

                with self._lock:
                    self.cpu_percent = cpu
                    self.mem_percent = mem
                    self.net_speed = net_speed
                    self.gpu_percent = gpu
                    self.cpu_temp = temp

                if self._on_update:
                    self._on_update(cpu, mem, net_speed, gpu, temp)

            except Exception:
                pass

            self._stop_event.wait(self.interval)

