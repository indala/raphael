using System.IO;
using System.Runtime.InteropServices;
using Windows.Data.Xml.Dom;
using Windows.UI.Notifications;

namespace RaphaelHybrid;

/// <summary>
/// Desktop toast notifications via WinRT ToastNotificationManager.
/// Unpackaged apps need a registered AppUserModelID to show toasts, so on
/// first use we best-effort create a Start Menu shortcut for the bridge
/// carrying the AppUserModelID. Failures are swallowed — the tool reports
/// the result instead of crashing the bridge.
/// </summary>
public static class ToastNotifier
{
    private const string AppId = "Raphael.Hybrid";

    private static readonly string ShortcutPath =
        Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Raphael.lnk");

    /// <summary>
    /// Show a desktop toast with the given title and message.
    /// </summary>
    public static bool Show(string title, string message)
    {
        try
        {
            EnsureShortcut();

            var doc = new XmlDocument();
            var toast = doc.CreateElement("toast");
            doc.AppendChild(toast);
            var visual = doc.CreateElement("visual");
            toast.AppendChild(visual);
            var binding = doc.CreateElement("binding");
            binding.SetAttribute("template", "ToastGeneric");
            visual.AppendChild(binding);

            var titleNode = doc.CreateElement("text");
            titleNode.AppendChild(doc.CreateTextNode(title ?? ""));
            binding.AppendChild(titleNode);

            var messageNode = doc.CreateElement("text");
            messageNode.AppendChild(doc.CreateTextNode(message ?? ""));
            binding.AppendChild(messageNode);

            ToastNotificationManager.CreateToastNotifier(AppId).Show(new ToastNotification(doc));
            return true;
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Register the bridge's AppUserModelID via a Start Menu shortcut.
    /// No-op once the shortcut exists.
    /// </summary>
    private static void EnsureShortcut()
    {
        if (File.Exists(ShortcutPath)) return;

        var shellType = Type.GetTypeFromProgID("WScript.Shell");
        if (shellType is null) return;

        dynamic? shell = null;
        dynamic? shortcut = null;
        try
        {
            shell = Activator.CreateInstance(shellType);
            shortcut = shell!.CreateShortcut(ShortcutPath);
            shortcut.TargetPath = Environment.ProcessPath ?? "";
            shortcut.WorkingDirectory = AppContext.BaseDirectory;
            shortcut.IconLocation = shortcut.TargetPath;
            shortcut.AppUserModelID = AppId;
            shortcut.Save();
        }
        finally
        {
            if (shortcut is not null)
            {
                try { Marshal.FinalReleaseComObject(shortcut); } catch { }
            }
            if (shell is not null)
            {
                try { Marshal.FinalReleaseComObject(shell); } catch { }
            }
        }
    }
}