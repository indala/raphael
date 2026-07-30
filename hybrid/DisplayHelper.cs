namespace RaphaelHybrid;

/// <summary>
/// Monitor/display information via Screen.AllScreens.
/// </summary>
public static class DisplayHelper
{
    /// <summary>
    /// Per-monitor information returned to Python.
    /// </summary>
    public record MonitorInfo(
        int Index,
        int Left,
        int Top,
        int Right,
        int Bottom,
        int WorkLeft,
        int WorkTop,
        int WorkRight,
        int WorkBottom,
        bool IsPrimary
    );

    /// <summary>
    /// Enumerate all monitors with bounds, work area, and primary flag.
    /// </summary>
    public static MonitorInfo[] GetAllMonitors()
    {
        var screens = System.Windows.Forms.Screen.AllScreens;
        var results = new List<MonitorInfo>();

        for (int i = 0; i < screens.Length; i++)
        {
            var s = screens[i];
            results.Add(new MonitorInfo(
                i,
                s.Bounds.Left, s.Bounds.Top, s.Bounds.Right, s.Bounds.Bottom,
                s.WorkingArea.Left, s.WorkingArea.Top, s.WorkingArea.Right, s.WorkingArea.Bottom,
                s.Primary
            ));
        }

        return [.. results];
    }
}
