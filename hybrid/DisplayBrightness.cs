using System.Runtime.InteropServices;

namespace RaphaelHybrid;

/// <summary>
/// Monitor DPI (shcore GetDpiForMonitor) and brightness (dxva2) control.
/// Brightness requires a monitor that supports DDC/CI.
/// </summary>
public static class DisplayBrightness
{
    [StructLayout(LayoutKind.Sequential)]
    private struct POINT { public int X; public int Y; }

    [DllImport("user32.dll")]
    private static extern IntPtr MonitorFromPoint(POINT pt, uint dwFlags);

    [DllImport("shcore.dll")]
    private static extern int GetDpiForMonitor(IntPtr hmonitor, int dpiType, out uint dpiX, out uint dpiY);

    private const uint MONITOR_DEFAULTTOPRIMARY = 0x00000001;
    private const int MDT_EFFECTIVE_DPI = 0;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct PHYSICAL_MONITOR
    {
        public IntPtr hPhysicalMonitor;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string szPhysicalMonitorDescription;
    }

    [DllImport("dxva2.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetNumberOfPhysicalMonitorsFromHMONITOR(IntPtr hMonitor, out uint pdwNumberOfPhysicalMonitors);

    [DllImport("dxva2.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetPhysicalMonitorsFromHMONITOR(IntPtr hMonitor, uint dwPhysicalMonitorArraySize, [Out] PHYSICAL_MONITOR[] pPhysicalMonitorArray);

    [DllImport("dxva2.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetMonitorBrightness(IntPtr hMonitor, out uint pdwMinimumBrightness, out uint pdwCurrentBrightness, out uint pdwMaximumBrightness);

    [DllImport("dxva2.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetMonitorBrightness(IntPtr hMonitor, uint dwNewBrightness);

    [DllImport("dxva2.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DestroyPhysicalMonitors(uint dwPhysicalMonitorArraySize, PHYSICAL_MONITOR[] pPhysicalMonitorArray);

    private static IntPtr PrimaryMonitor()
    {
        return MonitorFromPoint(new POINT { X = 0, Y = 0 }, MONITOR_DEFAULTTOPRIMARY);
    }

    /// <summary>
    /// Get the effective DPI of the primary monitor (both axes).
    /// </summary>
    public static Dictionary<string, object?> GetDpi()
    {
        try
        {
            IntPtr hmon = PrimaryMonitor();
            if (hmon == IntPtr.Zero)
                return new Dictionary<string, object?> { ["error"] = "No primary monitor found." };
            int hr = GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI, out uint dpiX, out uint dpiY);
            if (hr != 0)
                return new Dictionary<string, object?> { ["error"] = $"GetDpiForMonitor failed with HRESULT 0x{hr:X8}." };
            return new Dictionary<string, object?> { ["dpi_x"] = dpiX, ["dpi_y"] = dpiY };
        }
        catch (Exception ex)
        {
            return new Dictionary<string, object?> { ["error"] = ex.Message };
        }
    }

    /// <summary>
    /// Get the current brightness range (min/current/max) of the primary monitor via dxva2.
    /// </summary>
    public static Dictionary<string, object?> GetBrightness()
    {
        try
        {
            IntPtr hmon = PrimaryMonitor();
            if (hmon == IntPtr.Zero)
                return new Dictionary<string, object?> { ["error"] = "No primary monitor found." };

            if (!GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, out uint count) || count == 0)
                return new Dictionary<string, object?> { ["error"] = "Monitor does not expose physical monitors (no DDC/CI brightness support)." };

            var monitors = new PHYSICAL_MONITOR[count];
            if (!GetPhysicalMonitorsFromHMONITOR(hmon, count, monitors))
                return new Dictionary<string, object?> { ["error"] = "GetPhysicalMonitorsFromHMONITOR failed." };
            try
            {
                if (!GetMonitorBrightness(monitors[0].hPhysicalMonitor, out uint minB, out uint curB, out uint maxB))
                    return new Dictionary<string, object?> { ["error"] = "GetMonitorBrightness failed (unsupported on this display)." };
                return new Dictionary<string, object?>
                {
                    ["min"] = minB,
                    ["current"] = curB,
                    ["max"] = maxB,
                };
            }
            finally
            {
                DestroyPhysicalMonitors(count, monitors);
            }
        }
        catch (Exception ex)
        {
            return new Dictionary<string, object?> { ["error"] = ex.Message };
        }
    }

    /// <summary>
    /// Set the primary monitor's brightness to a level in [0,100].
    /// The level is scaled into the monitor's reported min/max range.
    /// </summary>
    public static Dictionary<string, object?> SetBrightness(uint level)
    {
        try
        {
            IntPtr hmon = PrimaryMonitor();
            if (hmon == IntPtr.Zero)
                return new Dictionary<string, object?> { ["error"] = "No primary monitor found." };

            if (!GetNumberOfPhysicalMonitorsFromHMONITOR(hmon, out uint count) || count == 0)
                return new Dictionary<string, object?> { ["error"] = "Monitor does not expose physical monitors (no DDC/CI brightness support)." };

            var monitors = new PHYSICAL_MONITOR[count];
            if (!GetPhysicalMonitorsFromHMONITOR(hmon, count, monitors))
                return new Dictionary<string, object?> { ["error"] = "GetPhysicalMonitorsFromHMONITOR failed." };
            try
            {
                if (!GetMonitorBrightness(monitors[0].hPhysicalMonitor, out uint minB, out _, out uint maxB))
                    return new Dictionary<string, object?> { ["error"] = "GetMonitorBrightness failed (unsupported on this display)." };
                uint clamped = Math.Clamp(level, 0u, 100u);
                ulong target = minB + (ulong)(maxB - minB) * clamped / 100u;
                if (!SetMonitorBrightness(monitors[0].hPhysicalMonitor, (uint)target))
                    return new Dictionary<string, object?> { ["error"] = "SetMonitorBrightness failed." };
                return new Dictionary<string, object?> { ["level"] = clamped };
            }
            finally
            {
                DestroyPhysicalMonitors(count, monitors);
            }
        }
        catch (Exception ex)
        {
            return new Dictionary<string, object?> { ["error"] = ex.Message };
        }
    }
}
