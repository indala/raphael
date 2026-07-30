using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace RaphaelHybrid;

/// <summary>
/// Shell.Application COM interop for active Explorer window folder path and selection.
/// </summary>
public static class ExplorerHelper
{
    /// <summary>Selected item within an Explorer window.</summary>
    public record ExplorerSelectedItem(
        string Name,
        string Path,
        bool IsFolder
    );

    /// <summary>Active Explorer window state.</summary>
    public record ExplorerSelection(
        string FolderPath,
        ExplorerSelectedItem[]? Selected
    );

    /// <summary>
    /// Find the active (foreground) Explorer window and return its folder path and selected items.
    /// Returns null if no Explorer window is active or no selection is available.
    /// </summary>
    public static ExplorerSelection? GetActiveExplorerSelection()
    {
        try
        {
            var shellType = Type.GetTypeFromProgID("Shell.Application");
            if (shellType == null) return null;

            dynamic? shell = null;
            try
            {
                shell = Activator.CreateInstance(shellType);
                if (shell == null) return null;

                dynamic? windows = null;
                try { windows = shell.Windows(); }
                catch { return null; }

                if (windows == null) return null;

                foreach (dynamic? win in windows)
                {
                    if (win == null) continue;

                    try
                    {
                        // Skip if no document (not an Explorer/IE window)
                        dynamic? doc = null;
                        try { doc = win.Document; }
                        catch { continue; }

                        if (doc == null) continue;

                        // Verify it's a file system folder (not a web browser)
                        dynamic? folder = null;
                        try { folder = doc.Folder; }
                        catch { continue; }

                        if (folder == null) continue;

                        string? folderPath = null;
                        try { folderPath = folder.Self?.Path; }
                        catch { /* not a filesystem folder */ }

                        if (string.IsNullOrEmpty(folderPath)) continue;

                        // Collect selected items
                        var selected = new List<ExplorerSelectedItem>();
                        try
                        {
                            dynamic? items = doc.SelectedItems();
                            if (items != null)
                            {
                                foreach (dynamic? item in items)
                                {
                                    if (item == null) continue;
                                    selected.Add(new ExplorerSelectedItem(
                                        (string)item.Name,
                                        (string)item.Path,
                                        (bool)item.IsFolder
                                    ));
                                }
                            }
                        }
                        catch { /* no selection or access denied */ }

                        Marshal.FinalReleaseComObject(doc);
                        Marshal.FinalReleaseComObject(folder);
                        Marshal.FinalReleaseComObject(win);

                        return new ExplorerSelection(
                            folderPath,
                            selected.Count > 0 ? [.. selected] : null
                        );
                    }
                    catch
                    {
                        try { Marshal.FinalReleaseComObject(win); }
                        catch { }
                        continue;
                    }
                }

                return null;
            }
            finally
            {
                if (shell != null)
                    try { Marshal.FinalReleaseComObject(shell); }
                    catch { }
            }
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// Get Explorer selection for ALL open Explorer windows (not just foreground).
    /// Returns null if no Explorer windows are open.
    /// </summary>
    public static ExplorerSelection[] GetAllExplorerSelections()
    {
        try
        {
            var shellType = Type.GetTypeFromProgID("Shell.Application");
            if (shellType == null) return [];

            dynamic? shell = null;
            try
            {
                shell = Activator.CreateInstance(shellType);
                if (shell == null) return [];

                dynamic? windows = null;
                try { windows = shell.Windows(); }
                catch { return []; }

                if (windows == null) return [];

                var results = new List<ExplorerSelection>();

                foreach (dynamic? win in windows)
                {
                    if (win == null) continue;

                    try
                    {
                        dynamic? doc = null;
                        try { doc = win.Document; }
                        catch { continue; }

                        if (doc == null) continue;

                        dynamic? folder = null;
                        try { folder = doc.Folder; }
                        catch { continue; }

                        if (folder == null) continue;

                        string? folderPath = null;
                        try { folderPath = folder.Self?.Path; }
                        catch { }

                        if (string.IsNullOrEmpty(folderPath))
                        {
                            try { Marshal.FinalReleaseComObject(doc); }
                            catch { }
                            try { Marshal.FinalReleaseComObject(folder); }
                            catch { }
                            continue;
                        }

                        var selected = new List<ExplorerSelectedItem>();
                        try
                        {
                            dynamic? items = doc.SelectedItems();
                            if (items != null)
                            {
                                foreach (dynamic? item in items)
                                {
                                    if (item == null) continue;
                                    selected.Add(new ExplorerSelectedItem(
                                        (string)item.Name,
                                        (string)item.Path,
                                        (bool)item.IsFolder
                                    ));
                                }
                            }
                        }
                        catch { }

                        results.Add(new ExplorerSelection(
                            folderPath,
                            selected.Count > 0 ? [.. selected] : null
                        ));

                        try { Marshal.FinalReleaseComObject(doc); }
                        catch { }
                        try { Marshal.FinalReleaseComObject(folder); }
                        catch { }
                    }
                    finally
                    {
                        try { Marshal.FinalReleaseComObject(win); }
                        catch { }
                    }
                }

                return [.. results];
            }
            finally
            {
                if (shell != null)
                    try { Marshal.FinalReleaseComObject(shell); }
                    catch { }
            }
        }
        catch
        {
            return [];
        }
    }
}
