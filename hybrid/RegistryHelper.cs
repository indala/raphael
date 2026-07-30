using Microsoft.Win32;

namespace RaphaelHybrid;

/// <summary>
/// Windows registry access via Microsoft.Win32.
/// Replaces Python's winreg which bypasses the C# bridge safety layer.
/// </summary>
public static class RegistryHelper
{
    /// <summary>Get the ProgId for the default HTTP handler (browser).</summary>
    public static string GetDefaultBrowserProgId()
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(
                @"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice");
            return key?.GetValue("ProgId")?.ToString() ?? "";
        }
        catch
        {
            return "";
        }
    }

    /// <summary>Read a string value from HKCU registry path.</summary>
    public static string ReadCurrentUser(string subKey, string valueName)
    {
        try
        {
            using var key = Registry.CurrentUser.OpenSubKey(subKey);
            return key?.GetValue(valueName)?.ToString() ?? "";
        }
        catch
        {
            return "";
        }
    }

    /// <summary>Read a string value from HKLM registry path.</summary>
    public static string ReadLocalMachine(string subKey, string valueName)
    {
        try
        {
            using var key = Registry.LocalMachine.OpenSubKey(subKey);
            return key?.GetValue(valueName)?.ToString() ?? "";
        }
        catch
        {
            return "";
        }
    }
}
