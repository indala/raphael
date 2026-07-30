using System.Runtime.InteropServices;
using System.Text;

namespace RaphaelHybrid;

/// <summary>
/// Audio playback via Windows MCI (winmm.dll).
/// Replaces ctypes.windll.winmm in Python which risks process crashes.
/// </summary>
public static class AudioPlayer
{
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    private static extern int mciSendString(string command, StringBuilder? returnString, int returnLength, IntPtr hWndCallback);

    private static int _counter;
    private static readonly object _lock = new();

    /// <summary>Play an MP3 file synchronously (blocks until done).</summary>
    public static void PlayMp3(string filePath)
    {
        lock (_lock)
        {
            int id = Interlocked.Increment(ref _counter);
            string alias = $"raphael_{id}";
            string path = filePath.Replace("/", "\\");
            int ret;

            ret = mciSendString($"open \"{path}\" type mpegvideo alias {alias}", null, 0, IntPtr.Zero);
            if (ret != 0) return;

            try
            {
                mciSendString($"play {alias} wait", null, 0, IntPtr.Zero);
            }
            finally
            {
                mciSendString($"close {alias}", null, 0, IntPtr.Zero);
            }
        }
    }

    /// <summary>Stop all MCI playback immediately.</summary>
    public static void StopAll()
    {
        lock (_lock)
        {
            mciSendString("close all", null, 0, IntPtr.Zero);
        }
    }
}
