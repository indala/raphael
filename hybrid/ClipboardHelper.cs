using System.Runtime.InteropServices;
using System.Text;

namespace RaphaelHybrid;

/// <summary>
/// Clipboard operations using Win32 API (no WinForms dependency).
/// Text, image, and file clipboard operations.
/// </summary>
public static class ClipboardHelper
{
    // ── Win32 API ──

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool OpenClipboard(IntPtr hWndNewOwner);

    [DllImport("shell32.dll", SetLastError = true)]
    private static extern uint DragQueryFile(IntPtr hDrop, uint iFile,
        [Out] StringBuilder? lpszFile, uint cch);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool CloseClipboard();

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool EmptyClipboard();

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr SetClipboardData(uint uFormat, IntPtr hMem);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern IntPtr GetClipboardData(uint uFormat);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr GlobalAlloc(uint uFlags, IntPtr dwBytes);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr GlobalLock(IntPtr hMem);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GlobalUnlock(IntPtr hMem);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr GlobalFree(IntPtr hMem);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr GlobalSize(IntPtr hMem);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr RtlMoveMemory(IntPtr dest, IntPtr src, IntPtr length);

    // ── Clipboard format constants ──
    private const uint CF_UNICODETEXT = 13;
    private const uint CF_DIB = 8;
    private const uint CF_HDROP = 15;
    private const uint GMEM_MOVEABLE = 0x0002;
    private const uint GMEM_ZEROINIT = 0x0040;

    // ── Public API ──

    /// <summary>Copy text to clipboard.</summary>
    public static bool CopyText(string text)
    {
        if (text == null) return false;
        try
        {
            if (!OpenClipboard(IntPtr.Zero)) return false;
            try
            {
                EmptyClipboard();

                // Write Unicode text (CF_UNICODETEXT = UTF-16)
                var bytes = Encoding.Unicode.GetBytes(text + "\0");
                var hMem = GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, (IntPtr)bytes.Length);
                if (hMem == IntPtr.Zero) return false;

                var ptr = GlobalLock(hMem);
                if (ptr == IntPtr.Zero) { GlobalFree(hMem); return false; }

                Marshal.Copy(bytes, 0, ptr, bytes.Length);
                GlobalUnlock(hMem);

                SetClipboardData(CF_UNICODETEXT, hMem);
                return true;
            }
            finally
            {
                CloseClipboard();
            }
        }
        catch
        {
            return false;
        }
    }

    /// <summary>Copy a DIB bitmap to the clipboard (CF_DIB).</summary>
    /// <param name="base64Dib">Base64-encoded DIB data (BMP file header already stripped).</param>
    public static bool CopyImage(string base64Dib)
    {
        if (string.IsNullOrEmpty(base64Dib)) return false;
        try
        {
            var dibBytes = Convert.FromBase64String(base64Dib);
            if (dibBytes.Length == 0) return false;

            if (!OpenClipboard(IntPtr.Zero)) return false;
            try
            {
                EmptyClipboard();

                var hMem = GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, (IntPtr)dibBytes.Length);
                if (hMem == IntPtr.Zero) return false;

                var ptr = GlobalLock(hMem);
                if (ptr == IntPtr.Zero) { GlobalFree(hMem); return false; }

                Marshal.Copy(dibBytes, 0, ptr, dibBytes.Length);
                GlobalUnlock(hMem);

                SetClipboardData(CF_DIB, hMem);
                return true;
            }
            finally
            {
                CloseClipboard();
            }
        }
        catch
        {
            return false;
        }
    }

    /// <summary>Check if clipboard contains an image (CF_DIB).</summary>
    public static bool HasImage()
    {
        try
        {
            if (!OpenClipboard(IntPtr.Zero)) return false;
            try
            {
                return GetClipboardData(CF_DIB) != IntPtr.Zero;
            }
            finally
            {
                CloseClipboard();
            }
        }
        catch
        {
            return false;
        }
    }

    /// <summary>Read text from clipboard.</summary>
    public static string PasteText()
    {
        try
        {
            if (!OpenClipboard(IntPtr.Zero)) return "";
            try
            {
                var hMem = GetClipboardData(CF_UNICODETEXT);
                if (hMem == IntPtr.Zero) return "";

                var ptr = GlobalLock(hMem);
                if (ptr == IntPtr.Zero) return "";

                try
                {
                    var size = (int)GlobalSize(hMem);
                    var bytes = new byte[size];
                    Marshal.Copy(ptr, bytes, 0, size);
                    return Encoding.Unicode.GetString(bytes).TrimEnd('\0');
                }
                finally
                {
                    GlobalUnlock(hMem);
                }
            }
            finally
            {
                CloseClipboard();
            }
        }
        catch
        {
            return "";
        }
    }

    /// <summary>Check if clipboard contains text.</summary>
    public static bool HasText()
    {
        try
        {
            if (!OpenClipboard(IntPtr.Zero)) return false;
            try
            {
                return GetClipboardData(CF_UNICODETEXT) != IntPtr.Zero;
            }
            finally
            {
                CloseClipboard();
            }
        }
        catch
        {
            return false;
        }
    }

    /// <summary>Clear clipboard contents.</summary>
    public static bool Clear()
    {
        try
        {
            if (!OpenClipboard(IntPtr.Zero)) return false;
            try
            {
                EmptyClipboard();
                return true;
            }
            finally
            {
                CloseClipboard();
            }
        }
        catch
        {
            return false;
        }
    }

    // ── File drop list (CF_HDROP) ──

    /// <summary>
    /// Get list of file paths from clipboard (CF_HDROP).
    /// Returns null if no file list is available.
    /// </summary>
    public static string[]? GetFileDropList()
    {
        try
        {
            if (!OpenClipboard(IntPtr.Zero)) return null;
            try
            {
                var hDrop = GetClipboardData(CF_HDROP);
                if (hDrop == IntPtr.Zero) return null;

                // Get file count
                uint count = DragQueryFile(hDrop, 0xFFFFFFFF, null, 0);
                if (count == 0) return [];

                var files = new List<string>((int)count);
                for (uint i = 0; i < count; i++)
                {
                    uint len = DragQueryFile(hDrop, i, null, 0);
                    var sb = new StringBuilder((int)len + 1);
                    DragQueryFile(hDrop, i, sb, (uint)sb.Capacity);
                    files.Add(sb.ToString());
                }
                return [.. files];
            }
            finally
            {
                CloseClipboard();
            }
        }
        catch
        {
            return null;
        }
    }

    /// <summary>Check if clipboard contains file drop list (CF_HDROP).</summary>
    public static bool HasFiles()
    {
        try
        {
            if (!OpenClipboard(IntPtr.Zero)) return false;
            try
            {
                return GetClipboardData(CF_HDROP) != IntPtr.Zero;
            }
            finally
            {
                CloseClipboard();
            }
        }
        catch
        {
            return false;
        }
    }
}
