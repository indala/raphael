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

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW", SetLastError = true)]
    private static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW", SetLastError = true)]
    private static extern IntPtr GetWindowLongPtr(IntPtr hWnd, int nIndex);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetLayeredWindowAttributes(IntPtr hwnd, uint crKey, byte bAlpha, uint dwFlags);

    private const uint WM_CLOSE = 0x0010;
    private const int SW_HIDE = 0;
    private const int SW_SHOW = 5;
    private const int GWL_EXSTYLE = -20;
    private const long WS_EX_LAYERED = 0x00080000;
    private const uint LWA_ALPHA = 0x2;
    private static readonly IntPtr HWND_TOPMOST = new(-1);
    private static readonly IntPtr HWND_NOTOPMOST = new(-2);
    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOMOVE = 0x0002;
    private const uint SWP_NOZORDER = 0x0004;
    private const uint SWP_NOACTIVATE = 0x0010;

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

    /// <summary>
    /// Move a window to (x, y), preserving its current size.
    /// </summary>
    public static bool MoveWindow(string title, int x, int y)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return false;
        if (!GetWindowRect(hWnd, out RECT rect)) return false;
        return MoveWindow(hWnd, x, y, rect.Right - rect.Left, rect.Bottom - rect.Top, true);
    }

    /// <summary>
    /// Resize a window to (width, height), preserving its current position.
    /// </summary>
    public static bool ResizeWindow(string title, int width, int height)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return false;
        if (!GetWindowRect(hWnd, out RECT rect)) return false;
        return MoveWindow(hWnd, rect.Left, rect.Top, width, height, true);
    }

    /// <summary>
    /// Pin a window to the top of the z-order (always on top) or release it.
    /// </summary>
    public static bool SetAlwaysOnTop(string title, bool onTop)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return false;
        return SetWindowPos(hWnd, onTop ? HWND_TOPMOST : HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
    }

    /// <summary>
    /// Set a window's opacity to a value in [0, 1] by enabling WS_EX_LAYERED + LWA_ALPHA.
    /// </summary>
    public static bool SetOpacity(string title, double opacity)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return false;
        var opacity01 = Math.Clamp(opacity, 0.0, 1.0);
        var exStyle = GetWindowLongPtr(hWnd, GWL_EXSTYLE).ToInt64();
        if ((exStyle & WS_EX_LAYERED) == 0)
            SetWindowLongPtr(hWnd, GWL_EXSTYLE, (IntPtr)(exStyle | WS_EX_LAYERED));
        byte alpha = (byte)Math.Round(opacity01 * 255.0);
        return SetLayeredWindowAttributes(hWnd, 0, alpha, LWA_ALPHA);
    }

    /// <summary>
    /// Hide (or, on some apps, minimize) a window by title.
    /// </summary>
    public static bool HideWindow(string title)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return false;
        return ShowWindow(hWnd, SW_HIDE);
    }

    /// <summary>
    /// Show a hidden window by title.
    /// </summary>
    public static bool ShowWindowByTitle(string title)
    {
        var hWnd = FindWindowByTitle(title);
        if (hWnd == IntPtr.Zero) return false;
        return ShowWindow(hWnd, SW_SHOW);
    }
}
