using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace RaphaelHybrid;

/// <summary>
/// Window management via User32 P/Invoke.
/// More reliable than pygetwindow for finding, focusing, and enumerating windows.
/// </summary>
public static class WindowManager
{
    // ── Win32 API declarations ──

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern IntPtr FindWindow(string? lpClassName, string? lpWindowName);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern IntPtr FindWindowEx(IntPtr hwndParent, IntPtr hwndChildAfter, string? lpszClass, string? lpszWindow);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    private static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    private delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

    [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

    private const uint WM_CLOSE = 0x0010;

    [StructLayout(LayoutKind.Sequential)]
    private struct RECT
    {
        public int Left; public int Top; public int Right; public int Bottom;
    }

    /// <summary>
    /// Structured window info returned by GetAllWindows.
    /// </summary>
    public record WindowInfo(
        long Handle,
        string Title,
        uint Pid,
        string ProcessName,
        bool IsForeground,
        int RectLeft,
        int RectTop,
        int RectRight,
        int RectBottom
    );

    private const int SW_RESTORE = 9;
    private const int SW_MINIMIZE = 6;
    private const int SW_MAXIMIZE = 3;

    // ── Public API ──

    /// <summary>
    /// Find a window handle by partial title match.
    /// </summary>
    public static IntPtr FindWindowByTitle(string title)
    {
        if (string.IsNullOrWhiteSpace(title)) return IntPtr.Zero;

        // First, try exact match
        var hWnd = FindWindow(null, title);
        if (hWnd != IntPtr.Zero) return hWnd;

        // Fallback: enumerate all windows for partial match
        IntPtr found = IntPtr.Zero;
        EnumWindows((hWnd, _) =>
        {
            var sb = new StringBuilder(256);
            GetWindowText(hWnd, sb, sb.Capacity);
            var windowTitle = sb.ToString();

            if (windowTitle.Contains(title, StringComparison.OrdinalIgnoreCase) && IsWindowVisible(hWnd))
            {
                found = hWnd;
                return false; // stop enumeration
            }
            return true;
        }, IntPtr.Zero);

        return found;
    }

    /// <summary>
    /// Bring a window to the foreground by title (partial match).
    /// </summary>
    public static bool FocusWindow(string title)
    {
        try
        {
            var hWnd = FindWindowByTitle(title);
            if (hWnd == IntPtr.Zero) return false;

            // If minimized, restore first
            ShowWindow(hWnd, SW_RESTORE);
            return SetForegroundWindow(hWnd);
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Get the title of the currently focused window.
    /// </summary>
    public static string GetActiveWindowTitle()
    {
        try
        {
            var hWnd = GetForegroundWindow();
            if (hWnd == IntPtr.Zero) return "";

            var sb = new StringBuilder(256);
            GetWindowText(hWnd, sb, sb.Capacity);
            return sb.ToString();
        }
        catch
        {
            return "";
        }
    }

    /// <summary>
    /// Enumerate all visible window titles.
    /// </summary>
    public static string[] GetAllWindowTitles()
    {
        var titles = new List<string>();
        EnumWindows((hWnd, _) =>
        {
            if (!IsWindowVisible(hWnd)) return true;
            var sb = new StringBuilder(256);
            GetWindowText(hWnd, sb, sb.Capacity);
            var title = sb.ToString();
            if (!string.IsNullOrWhiteSpace(title))
                titles.Add(title);
            return true;
        }, IntPtr.Zero);
        return [.. titles];
    }

    /// <summary>
    /// Safely close a window by sending WM_CLOSE. Respects any "are you sure?" prompts inside the app.
    /// Returns false if the window is not found.
    /// </summary>
    public static bool CloseWindow(string title)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return false;
        PostMessage(hWnd, WM_CLOSE, IntPtr.Zero, IntPtr.Zero);
        return true;
    }

    /// <summary>
    /// Enumerate all visible windows with full details (handle, title, PID, process name, rect, foreground).
    /// </summary>
    public static WindowInfo[] GetAllWindows()
    {
        var foreground = GetForegroundWindow();
        var list = new List<WindowInfo>();
        EnumWindows((hWnd, _) =>
        {
            if (!IsWindowVisible(hWnd)) return true;
            var sb = new StringBuilder(256);
            GetWindowText(hWnd, sb, sb.Capacity);
            var title = sb.ToString();
            if (string.IsNullOrWhiteSpace(title)) return true;

            uint pid = 0;
            GetWindowThreadProcessId(hWnd, out pid);
            var procName = "";
            try { procName = Process.GetProcessById((int)pid).ProcessName; } catch { }

            var rect = default(RECT);
            GetWindowRect(hWnd, out rect);

            list.Add(new WindowInfo(
                (long)hWnd,
                title,
                pid,
                procName,
                hWnd == foreground,
                rect.Left, rect.Top, rect.Right, rect.Bottom
            ));
            return true;
        }, IntPtr.Zero);
        return [.. list];
    }

    /// <summary>
    /// Minimize a window by title.
    /// </summary>
    public static bool MinimizeWindow(string title)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return false;
        return ShowWindow(hWnd, SW_MINIMIZE);
    }

    /// <summary>
    /// Maximize a window by title.
    /// </summary>
    public static bool MaximizeWindow(string title)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return false;
        return ShowWindow(hWnd, SW_MAXIMIZE);
    }

    /// <summary>
    /// Get window position and size as (left, top, right, bottom).
    /// </summary>
    public static int[]? GetWindowRect(string title)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return null;

        if (GetWindowRect(hWnd, out RECT rect))
            return [rect.Left, rect.Top, rect.Right, rect.Bottom];
        return null;
    }
}
