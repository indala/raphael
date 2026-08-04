using System.Diagnostics;

namespace RaphaelHybrid;

/// <summary>
/// Process lifecycle helpers via System.Diagnostics (no P/Invoke).
/// </summary>
public static class ProcessHelper
{
    /// <summary>
    /// Kill a process by PID, including its child process tree.
    /// Returns null on success or an error message.
    /// </summary>
    public static string? Kill(int pid)
    {
        try
        {
            using var proc = Process.GetProcessById(pid);
            proc.Kill(entireProcessTree: true);
            return null;
        }
        catch (Exception ex)
        {
            return ex.Message;
        }
    }

    /// <summary>
    /// Wait for a process to exit. Returns exited flag (true = exited within
    /// timeout) and an error message on failure.
    /// </summary>
    public static Dictionary<string, object?> Wait(int pid, int timeoutMs)
    {
        try
        {
            using var proc = Process.GetProcessById(pid);
            bool exited = proc.WaitForExit(timeoutMs);
            return new Dictionary<string, object?>
            {
                ["exited"] = exited,
                ["error"] = null,
            };
        }
        catch (Exception ex)
        {
            return new Dictionary<string, object?>
            {
                ["exited"] = false,
                ["error"] = ex.Message,
            };
        }
    }
}
