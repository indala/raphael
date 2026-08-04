using System.Runtime.InteropServices;

namespace RaphaelHybrid;

/// <summary>
/// Recycle Bin query and empty via Shell32 P/Invoke
/// (SHQueryRecycleBinW / SHEmptyRecycleBinW).
/// </summary>
public static class RecycleBin
{
    [StructLayout(LayoutKind.Sequential)]
    private struct SHQUERYRBINFO
    {
        public int cbSize;
        public long i64Size;
        public long i64NumItems;
    }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SHQueryRecycleBinW(string? pszRootPath, ref SHQUERYRBINFO pSHQueryRBInfo);

    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SHEmptyRecycleBinW(IntPtr hwnd, string? pszRootPath, uint dwFlags);

    private const uint SHERB_NOCONFIRMATION = 0x00000001;
    private const uint SHERB_NOPROGRESSUI = 0x00000002;
    private const uint SHERB_NOSOUND = 0x00000004;

    /// <summary>
    /// Query recycle bin contents across all drives.
    /// </summary>
    public static Dictionary<string, object?> Get()
    {
        var info = new SHQUERYRBINFO { cbSize = Marshal.SizeOf<SHQUERYRBINFO>() };
        int hr = SHQueryRecycleBinW(null, ref info);
        return new Dictionary<string, object?>
        {
            ["hr"] = hr,
            ["item_count"] = info.i64NumItems,
            ["size_bytes"] = info.i64Size,
        };
    }

    /// <summary>
    /// Empty the recycle bin. Requires confirm == true; otherwise no-op.
    /// </summary>
    public static Dictionary<string, object?> Empty(bool confirm)
    {
        if (!confirm)
        {
            return new Dictionary<string, object?>
            {
                ["hr"] = -1,
                ["message"] = "Empty requires confirm=true (destructive operation).",
            };
        }
        int hr = SHEmptyRecycleBinW(
            IntPtr.Zero,
            null,
            SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND);
        return new Dictionary<string, object?>
        {
            ["hr"] = hr,
            ["message"] = hr == 0
                ? "Recycle bin emptied."
                : $"Shell32 returned HRESULT 0x{hr:X8} (no trash on this system?).",
        };
    }
}
