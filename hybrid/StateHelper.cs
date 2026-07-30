using System.Diagnostics;
using System.Runtime.InteropServices;

namespace RaphaelHybrid;

/// <summary>
/// User and system state: idle time, foreground process, full-screen detection, power info.
/// </summary>
public static class StateHelper
{
    // ── Win32 API ──

    [DllImport("user32.dll")]
    private static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);

    [StructLayout(LayoutKind.Sequential)]
    private struct LASTINPUTINFO
    {
        public uint cbSize;
        public uint dwTime;
    }

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT { public int Left; public int Top; public int Right; public int Bottom; }

    // ── Public API ──

    /// <summary>Seconds since last user input (keyboard/mouse).</summary>
    public static double GetIdleSeconds()
    {
        var lii = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf<LASTINPUTINFO>() };
        if (!GetLastInputInfo(ref lii)) return 0;
        return (Environment.TickCount - lii.dwTime) / 1000.0;
    }

    /// <summary>Information about the foreground process.</summary>
    public record ForegroundProcessInfo(
        long Handle,
        uint Pid,
        string ProcessName,
        string ExecutablePath,
        bool Responding,
        long MemoryBytes
    );

    /// <summary>Get details about the currently focused window's process.</summary>
    public static ForegroundProcessInfo? GetForegroundProcess()
    {
        try
        {
            var hWnd = GetForegroundWindow();
            if (hWnd == IntPtr.Zero) return null;

            uint pid = 0;
            GetWindowThreadProcessId(hWnd, out pid);
            var proc = Process.GetProcessById((int)pid);

            return new ForegroundProcessInfo(
                (long)hWnd,
                pid,
                proc.ProcessName,
                proc.MainModule?.FileName ?? "",
                proc.Responding,
                proc.WorkingSet64
            );
        }
        catch
        {
            return null;
        }
    }

    /// <summary>Check whether the foreground window is full-screen on its monitor.</summary>
    public static bool IsForegroundFullScreen()
    {
        try
        {
            var hWnd = GetForegroundWindow();
            if (hWnd == IntPtr.Zero) return false;
            if (!GetWindowRect(hWnd, out var rect)) return false;

            var screen = System.Windows.Forms.Screen.FromHandle(hWnd);
            var bounds = screen.Bounds;
            return rect.Left == bounds.Left && rect.Top == bounds.Top &&
                   rect.Right == bounds.Right && rect.Bottom == bounds.Bottom;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>Battery and power status.</summary>
    public static object GetPowerInfo()
    {
        var power = System.Windows.Forms.SystemInformation.PowerStatus;
        return new
        {
            battery_remaining = System.Math.Round(power.BatteryLifePercent * 100, 0),
            power_line_status = power.PowerLineStatus.ToString(),
            battery_charge_status = power.BatteryChargeStatus.ToString(),
            battery_life_seconds = power.BatteryLifeRemaining
        };
    }

    /// <summary>Combined snapshot of all user/system state.</summary>
    public static object GetSnapshot()
    {
        return new
        {
            idle_seconds = GetIdleSeconds(),
            foreground_process = GetForegroundProcess(),
            full_screen = IsForegroundFullScreen(),
            power = GetPowerInfo()
        };
    }
}
