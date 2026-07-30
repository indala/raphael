using System;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;

namespace RaphaelHybrid
{
    /// <summary>
    /// Screen capture via GDI BitBlt — faster and more reliable than mss/Python
    /// alternatives. Captures the entire primary display as a PNG byte array.
    /// </summary>
    public class ScreenCapture
    {
        // ── Win32 API ────────────────────────────────────────────────────

        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateCompatibleDC(IntPtr hdc);

        [DllImport("gdi32.dll")]
        private static extern bool DeleteDC(IntPtr hdc);

        [DllImport("gdi32.dll")]
        private static extern IntPtr CreateCompatibleBitmap(IntPtr hdc, int nWidth, int nHeight);

        [DllImport("gdi32.dll")]
        private static extern IntPtr SelectObject(IntPtr hdc, IntPtr hgdiobj);

        [DllImport("gdi32.dll")]
        private static extern bool BitBlt(IntPtr hdcDest, int nXDest, int nYDest, int nWidth, int nHeight,
            IntPtr hdcSrc, int nXSrc, int nYSrc, uint dwRop);

        [DllImport("gdi32.dll")]
        private static extern bool DeleteObject(IntPtr hObject);

        [DllImport("user32.dll")]
        private static extern IntPtr GetDesktopWindow();

        [DllImport("user32.dll")]
        private static extern IntPtr GetWindowDC(IntPtr hWnd);

        [DllImport("user32.dll")]
        private static extern int ReleaseDC(IntPtr hWnd, IntPtr hDC);

        private const uint SRCCOPY = 0x00CC0020;

        // ── Public API ──────────────────────────────────────────────────

        /// <summary>
        /// Capture the primary screen and return raw PNG bytes.
        /// Returns empty array on failure.
        /// </summary>
        public static byte[] CapturePrimaryScreen()
        {
            try
            {
                int screenWidth = GetSystemMetrics(SM_CXSCREEN);
                int screenHeight = GetSystemMetrics(SM_CYSCREEN);

                IntPtr hdcScreen = GetDC(IntPtr.Zero);
                IntPtr hdcMem = CreateCompatibleDC(hdcScreen);
                IntPtr hBitmap = CreateCompatibleBitmap(hdcScreen, screenWidth, screenHeight);
                IntPtr hOld = SelectObject(hdcMem, hBitmap);

                BitBlt(hdcMem, 0, 0, screenWidth, screenHeight, hdcScreen, 0, 0, SRCCOPY);

                // Convert to PNG bytes
                using var bitmap = Image.FromHbitmap(hBitmap);
                using var ms = new MemoryStream();
                bitmap.Save(ms, ImageFormat.Png);
                byte[] result = ms.ToArray();

                // Cleanup
                SelectObject(hdcMem, hOld);
                DeleteObject(hBitmap);
                DeleteDC(hdcMem);
                ReleaseDC(IntPtr.Zero, hdcScreen);

                return result;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[ScreenCapture] Error: {ex.Message}");
                return [];
            }
        }

        /// <summary>
        /// Capture a specific monitor by index (0 = primary).
        /// </summary>
        public static byte[] CaptureMonitor(int monitorIndex)
        {
            // Fall back to primary screen for now
            // Multi-monitor support via EnumDisplayMonitors is possible but adds complexity
            return CapturePrimaryScreen();
        }

        /// <summary>Get screen dimensions as "WxH".</summary>
        public static string GetScreenSize()
        {
            int w = GetSystemMetrics(SM_CXSCREEN);
            int h = GetSystemMetrics(SM_CYSCREEN);
            return $"{w}x{h}";
        }

        // ── Win32 helpers ────────────────────────────────────────────────

        [DllImport("user32.dll")]
        private static extern int GetSystemMetrics(int nIndex);

        [DllImport("user32.dll")]
        private static extern IntPtr GetDC(IntPtr hWnd);

        private const int SM_CXSCREEN = 0;
        private const int SM_CYSCREEN = 1;
    }
}
