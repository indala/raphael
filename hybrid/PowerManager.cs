using System.Runtime.InteropServices;

namespace RaphaelHybrid;

/// <summary>
/// System power control via PowrProf (suspend/hibernate) and User32
/// (lock, shutdown, reboot). Shutdown/reboot are destructive and therefore
/// require an explicit confirm flag before taking effect.
/// </summary>
public static class PowerManager
{
    [DllImport("powrprof.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetSuspendState(bool hibernate, bool forceCritical, bool disableWakeEvent);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool LockWorkStation();

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool ExitWindowsEx(uint uFlags, uint dwReason);

    private const uint EWX_SHUTDOWN = 0x00000001;
    private const uint EWX_REBOOT = 0x00000002;
    private const uint EWX_FORCE = 0x00000004;

    private const uint TOKEN_ADJUST_PRIVILEGES = 0x00000020;
    private const uint TOKEN_QUERY = 0x00000008;
    private const uint SE_PRIVILEGE_ENABLED = 0x00000002;

    [StructLayout(LayoutKind.Sequential)]
    private struct LUID { public uint LowPart; public int HighPart; }

    [StructLayout(LayoutKind.Sequential)]
    private struct LUID_AND_ATTRIBUTES { public LUID Luid; public uint Attributes; }

    [StructLayout(LayoutKind.Sequential)]
    private struct TOKEN_PRIVILEGES
    {
        public uint PrivilegeCount;
        public LUID_AND_ATTRIBUTES Privileges;
    }

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(IntPtr processHandle, uint desiredAccess, out IntPtr tokenHandle);

    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool LookupPrivilegeValue(string? systemName, string name, ref LUID luid);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AdjustTokenPrivileges(IntPtr tokenHandle, bool disableAllPrivileges, ref TOKEN_PRIVILEGES newState, uint bufferLength, IntPtr previousState, IntPtr returnLength);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CloseHandle(IntPtr handle);

    /// <summary>
    /// Put the machine into sleep (suspend-to-RAM).
    /// </summary>
    public static bool Sleep() => SetSuspendState(false, false, false);

    /// <summary>
    /// Hibernate the machine (suspend-to-disk).
    /// </summary>
    public static bool Hibernate() => SetSuspendState(true, false, false);

    /// <summary>
    /// Lock the workstation.
    /// </summary>
    public static bool Lock() => LockWorkStation();

    /// <summary>
    /// Shut down the machine. Requires confirm == true; otherwise no-op and returns false.
    /// </summary>
    public static bool Shutdown(bool confirm)
    {
        if (!confirm) return false;
        try
        {
            EnableShutdownPrivilege();
            return ExitWindowsEx(EWX_SHUTDOWN | EWX_FORCE, 0);
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Restart the machine. Requires confirm == true; otherwise no-op and returns false.
    /// </summary>
    public static bool Reboot(bool confirm)
    {
        if (!confirm) return false;
        try
        {
            EnableShutdownPrivilege();
            return ExitWindowsEx(EWX_REBOOT | EWX_FORCE, 0);
        }
        catch
        {
            return false;
        }
    }

    private static bool EnableShutdownPrivilege()
    {
        using var process = System.Diagnostics.Process.GetCurrentProcess();
        if (!OpenProcessToken(process.Handle, TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY, out IntPtr hToken))
            return false;
        try
        {
            var luid = new LUID();
            if (!LookupPrivilegeValue(null, "SeShutdownPrivilege", ref luid))
                return false;
            var tp = new TOKEN_PRIVILEGES
            {
                PrivilegeCount = 1,
                Privileges = new LUID_AND_ATTRIBUTES { Luid = luid, Attributes = SE_PRIVILEGE_ENABLED }
            };
            return AdjustTokenPrivileges(hToken, false, ref tp, 0, IntPtr.Zero, IntPtr.Zero);
        }
        finally
        {
            CloseHandle(hToken);
        }
    }
}