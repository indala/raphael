using System.Runtime.InteropServices;

namespace RaphaelHybrid;

/// <summary>
/// Creates Windows .lnk shortcuts via the WScript.Shell COM object.
/// </summary>
public static class ShortcutHelper
{
    /// <summary>
    /// Create a .lnk shortcut at linkPath pointing at target.
    /// Returns null on success or an error message.
    /// </summary>
    public static string? Create(string linkPath, string target, string arguments, string workingDirectory, string description)
    {
        object? shell = null;
        object? shortcut = null;
        try
        {
            var shellType = Type.GetTypeFromProgID("WScript.Shell");
            if (shellType is null)
                return "WScript.Shell COM object is not available on this system.";
            shell = Activator.CreateInstance(shellType);
            if (shell is null)
                return "Failed to create WScript.Shell instance.";

            dynamic sh = shell;
            shortcut = sh.CreateShortcut(linkPath);
            dynamic sc = shortcut;
            sc.TargetPath = target;
            sc.Arguments = arguments ?? "";
            sc.WorkingDirectory = workingDirectory ?? "";
            sc.Description = description ?? "";
            sc.Save();
            return null;
        }
        catch (Exception ex)
        {
            return ex.Message;
        }
        finally
        {
            if (shortcut is not null) Marshal.FinalReleaseComObject(shortcut);
            if (shell is not null) Marshal.FinalReleaseComObject(shell);
        }
    }
}
