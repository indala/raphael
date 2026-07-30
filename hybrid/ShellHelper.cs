using System.Diagnostics;

namespace RaphaelHybrid;

/// <summary>
/// Shell operations (open files, launch apps) via ShellExecute.
/// Replaces Python's os.startfile() and subprocess.Popen(shell=True).
/// </summary>
public static class ShellHelper
{
    /// <summary>Open a file or URL with its associated application.</summary>
    public static bool Open(string path)
    {
        try
        {
            using var process = new Process();
            process.StartInfo = new ProcessStartInfo
            {
                FileName = path,
                UseShellExecute = true
            };
            process.Start();
            return true;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>Launch a Windows application by name or full path.</summary>
    public static bool Launch(string appName)
    {
        try
        {
            using var process = new Process();
            process.StartInfo = new ProcessStartInfo
            {
                FileName = appName,
                UseShellExecute = true
            };
            process.Start();
            return true;
        }
        catch
        {
            return false;
        }
    }
}
