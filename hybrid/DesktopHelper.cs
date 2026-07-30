using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace RaphaelHybrid;

/// <summary>
/// Desktop state queries — taskbar, notification tray, and system-level info.
/// Provides C# P/Invoke implementations for queries that are unreliable in Python.
/// </summary>
public static class DesktopHelper
{
    // ── Win32 P/Invoke for tray query ──────────────────────────────

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr FindWindow(string lpClassName, string? lpWindowName);

    [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    private static extern IntPtr FindWindowEx(IntPtr hWndParent, IntPtr hWndChildAfter,
        string lpszClass, string? lpszWindow);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam,
        [Out] StringBuilder? lParam);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam,
        ref IntPtr lParam);

    private const uint TB_BUTTONCOUNT = 0x0418;
    private const uint TB_GETBUTTONTEXTW = 0x044D;

    // ── Taskbar info ───────────────────────────────────────────────

    /// <summary>
    /// Get taskbar info: running apps (visible windows) and pinned shortcut names.
    /// Pinned apps are read from the shell TaskBar shortcuts folder
    /// (%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\),
    /// which is more reliable than parsing binary registry data.
    /// </summary>
    public static object GetTaskbarInfo()
    {
        // Running apps = visible windows with process names
        var windows = WindowManager.GetAllWindows();
        var running = new List<object>();
        foreach (var w in windows)
        {
            if (string.IsNullOrWhiteSpace(w.Title))
                continue;
            if (w.RectLeft <= -32000 && w.RectTop <= -32000)
                continue;

            running.Add(new
            {
                name = w.ProcessName,
                title = w.Title,
                pid = w.Pid,
                handle = (long)w.Handle,
            });
        }

        // Pinned apps — read from the shortcuts folder
        var pinned = new List<string>();
        try
        {
            var pinnedFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
                @"Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar"
            );
            if (Directory.Exists(pinnedFolder))
            {
                foreach (var lnk in Directory.GetFiles(pinnedFolder, "*.lnk"))
                {
                    string name = Path.GetFileNameWithoutExtension(lnk);
                    if (!string.IsNullOrEmpty(name) && name != "File Explorer")
                        pinned.Add(name);
                }
            }
        }
        catch
        {
            // Folder may not exist (e.g., clean Windows install without shell pins)
        }

        return new { running_apps = running, pinned_apps = pinned };
    }

    /// <summary>
    /// Get notification area (system tray) icon tooltips.
    /// Enumerates toolbar buttons in the notification area toolbar window.
    /// </summary>
    public static List<object> GetTrayIcons()
    {
        var icons = new List<object>();

        try
        {
            IntPtr trayWnd = FindWindow("Shell_TrayWnd", null);
            if (trayWnd == IntPtr.Zero) return icons;

            IntPtr notifyWnd = FindWindowEx(trayWnd, IntPtr.Zero, "TrayNotifyWnd", null);
            if (notifyWnd == IntPtr.Zero)
            {
                // Windows 11 may use a different hierarchy
                notifyWnd = FindWindowEx(trayWnd, IntPtr.Zero, "NotifyIconOverflowWindow", null);
                if (notifyWnd == IntPtr.Zero) return icons;
            }

            // Find the toolbar that hosts the notification icons
            IntPtr toolbar = FindWindowEx(notifyWnd, IntPtr.Zero, "ToolbarWindow32", null);
            if (toolbar == IntPtr.Zero) return icons;

            // Get button count
            int count = (int)SendMessage(toolbar, TB_BUTTONCOUNT, IntPtr.Zero, (StringBuilder?)null);
            if (count <= 0 || count > 100) return icons;

            var seen = new HashSet<string>();

            for (int i = 0; i < count; i++)
            {
                var sb = new StringBuilder(512);
                SendMessage(toolbar, TB_GETBUTTONTEXTW, (IntPtr)i, sb);
                string text = sb.ToString().Trim();

                if (string.IsNullOrEmpty(text)) continue;
                if (seen.Contains(text)) continue;
                seen.Add(text);

                icons.Add(new { tooltip = text });
            }
        }
        catch
        {
            // Best-effort; tray queries may fail in some Windows versions
        }

        return icons;
    }
}
