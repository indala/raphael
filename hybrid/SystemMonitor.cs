using System.Diagnostics;
using System.Management;
using System.Net.NetworkInformation;
using System.Runtime.InteropServices;

namespace RaphaelHybrid;

/// <summary>
/// System metrics via .NET PerformanceCounters and WMI.
/// Replaces psutil with native Windows APIs for better efficiency.
/// </summary>
public class SystemMonitor : IDisposable
{
    private PerformanceCounter? _cpuCounter;
    private PerformanceCounter? _memCounter;
    private PerformanceCounter? _netBytesReceived;
    private PerformanceCounter? _netBytesSent;

    private long _lastBytesReceived;
    private long _lastBytesSent;
    private DateTime _lastNetTime;

    public SystemMonitor()
    {
        InitializeCounters();
        _lastNetTime = DateTime.UtcNow;
        // Seed network counters
        ReadNetworkCounters(out _lastBytesReceived, out _lastBytesSent);
    }

    private void InitializeCounters()
    {
        try { _cpuCounter = new PerformanceCounter("Processor", "% Processor Time", "_Total"); }
        catch { }

        try { _memCounter = new PerformanceCounter("Memory", "% Committed Bytes In Use"); }
        catch { }

        try
        {
            _netBytesReceived = new PerformanceCounter("Network Interface", "Bytes Received/sec", GetFirstNetAdapter());
        }
        catch { }

        try
        {
            _netBytesSent = new PerformanceCounter("Network Interface", "Bytes Sent/sec", GetFirstNetAdapter());
        }
        catch { }
    }

    private static string GetFirstNetAdapter()
    {
        try
        {
            var cat = new PerformanceCounterCategory("Network Interface");
            var instances = cat.GetInstanceNames();
            return instances.Length > 0 ? instances[0] : "";
        }
        catch { return ""; }
    }

    private static void ReadNetworkCounters(out long recv, out long sent)
    {
        recv = 0;
        sent = 0;
        try
        {
            var props = NetworkInterface.GetAllNetworkInterfaces()
                .FirstOrDefault(n => n.OperationalStatus == OperationalStatus.Up);
            if (props != null)
            {
                var stats = props.GetIPv4Statistics();
                recv = stats.BytesReceived;
                sent = stats.BytesSent;
            }
        }
        catch { }
    }

    private bool _cpuInitialized = false;

    /// <summary>CPU usage percentage (0-100).</summary>
    public float GetCpuUsage()
    {
        try
        {
            if (_cpuCounter == null) return 0f;
            if (!_cpuInitialized)
            {
                _cpuCounter.NextValue(); // first call returns 0
                _cpuInitialized = true;
                Thread.Sleep(50); // small initial seed sleep
            }
            return (float)Math.Round(_cpuCounter.NextValue(), 1);
        }
        catch { return 0f; }
    }

    /// <summary>Memory usage percentage (0-100).</summary>
    public float GetMemoryUsage()
    {
        try
        {
            if (_memCounter != null) return (float)Math.Round(_memCounter.NextValue(), 1);
            // Fallback: use GlobalMemoryStatusEx
            MEMORYSTATUSEX mem = new();
            GlobalMemoryStatusEx(mem);
            return (float)Math.Round((double)mem.dwMemoryLoad, 1);
        }
        catch { return 0f; }
    }

    /// <summary>Network speed in KB/s (download).</summary>
    public float GetNetworkSpeed()
    {
        try
        {
            ReadNetworkCounters(out long nowRecv, out long _);
            var now = DateTime.UtcNow;
            var elapsed = (now - _lastNetTime).TotalSeconds;
            if (elapsed <= 0) return 0f;

            var speed = (nowRecv - _lastBytesReceived) / elapsed / 1024.0f;
            _lastBytesReceived = nowRecv;
            _lastNetTime = now;
            return (float)Math.Round(Math.Max(0, speed), 1);
        }
        catch { return 0f; }
    }

    /// <summary>GPU usage percentage via WMI (nvidia/amd).</summary>
    public float GetGpuUsage()
    {
        try
        {
            var query = "SELECT * FROM Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine";
            using var searcher = new ManagementObjectSearcher(query);
            using var results = searcher.Get();
            float maxUtil = 0;
            foreach (ManagementObject obj in results)
            {
                using (obj)
                {
                    var val = obj["PercentOfTime"]?.ToString();
                    if (val != null && float.TryParse(val, out float util))
                        maxUtil = Math.Max(maxUtil, util);
                }
            }
            return maxUtil;
        }
        catch { return 0f; }
    }

    /// <summary>CPU temperature in Celsius via WMI. May return 0 if unavailable.</summary>
    public float GetCpuTemperature()
    {
        try
        {
            var query = "SELECT CurrentTemperature FROM Win32_TemperatureProbe";
            using var searcher = new ManagementObjectSearcher(query);
            using var results = searcher.Get();
            foreach (ManagementObject obj in results)
            {
                using (obj)
                {
                    var val = obj["CurrentTemperature"]?.ToString();
                    if (val != null && float.TryParse(val, out float temp))
                        return (float)Math.Round((temp - 2731.5f) / 10.0f, 1); // Kelvin*10 -> Celsius
                }
            }
        }
        catch { }

        // Fallback: MSAcpi_ThermalZoneTemperature
        try
        {
            var query = "SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature";
            using var searcher = new ManagementObjectSearcher("root\\WMI", query);
            using var results = searcher.Get();
            foreach (ManagementObject obj in results)
            {
                using (obj)
                {
                    var val = obj["CurrentTemperature"]?.ToString();
                    if (val != null && float.TryParse(val, out float temp))
                        return (float)Math.Round((temp - 2731.5f) / 10.0f, 1);
                }
            }
        }
        catch { }

        return 0f;
    }

    /// <summary>Thread-safe snapshot of all metrics.</summary>
    public MetricSnapshot GetSnapshot()
    {
        return new MetricSnapshot
        {
            CpuPercent = GetCpuUsage(),
            MemPercent = GetMemoryUsage(),
            NetSpeedKbps = GetNetworkSpeed(),
            GpuPercent = GetGpuUsage(),
            CpuTemp = GetCpuTemperature()
        };
    }

    public void Dispose()
    {
        _cpuCounter?.Dispose();
        _memCounter?.Dispose();
        _netBytesReceived?.Dispose();
        _netBytesSent?.Dispose();
    }

    // ── Win32 API for memory fallback ──

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    private class MEMORYSTATUSEX
    {
        public uint dwLength;
        public uint dwMemoryLoad;
        public ulong ullTotalPhys;
        public ulong ullAvailPhys;
        public ulong ullTotalPageFile;
        public ulong ullAvailPageFile;
        public ulong ullTotalVirtual;
        public ulong ullAvailVirtual;
        public ulong ullAvailExtendedVirtual;

        public MEMORYSTATUSEX() => dwLength = (uint)Marshal.SizeOf(typeof(MEMORYSTATUSEX));
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GlobalMemoryStatusEx([In, Out] MEMORYSTATUSEX lpBuffer);
}

/// <summary>Snapshot of all system metrics at a point in time.</summary>
public class MetricSnapshot
{
    public float CpuPercent { get; init; }
    public float MemPercent { get; init; }
    public float NetSpeedKbps { get; init; }
    public float GpuPercent { get; init; }
    public float CpuTemp { get; init; }
}
