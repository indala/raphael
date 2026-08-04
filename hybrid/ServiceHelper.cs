using System.Management;

namespace RaphaelHybrid;

/// <summary>
/// Windows service enumeration and control via WMI (Win32_Service).
/// Uses System.Management (already referenced); avoids the separate
/// System.ServiceProcess.ServiceController package.
/// </summary>
public static class ServiceHelper
{
    /// <summary>
    /// List all services with name, display name, state, and start mode.
    /// </summary>
    public static List<Dictionary<string, object?>> List()
    {
        var result = new List<Dictionary<string, object?>>();
        using var searcher = new ManagementObjectSearcher(
            "SELECT Name, DisplayName, State, StartMode FROM Win32_Service");
        foreach (var obj in searcher.Get())
        {
            result.Add(new Dictionary<string, object?>
            {
                ["name"] = obj["Name"],
                ["display_name"] = obj["DisplayName"],
                ["state"] = obj["State"],
                ["start_mode"] = obj["StartMode"],
            });
        }
        return result;
    }

    /// <summary>
    /// Start a service by name. Returns null on success or an error message.
    /// </summary>
    public static string? Start(string name)
    {
        return Describe(svc(name).InvokeMethod("StartService", null));
    }

    /// <summary>
    /// Stop a service by name. Returns null on success or an error message.
    /// </summary>
    public static string? Stop(string name)
    {
        return Describe(svc(name).InvokeMethod("StopService", null));
    }

    private static ManagementObject svc(string name)
    {
        string escaped = name.Replace("'", "''");
        return new ManagementObject($"Win32_Service.Name='{escaped}'");
    }

    private static string? Describe(object? methodResult)
    {
        if (methodResult is ManagementBaseObject mo && mo["ReturnValue"] is uint code)
        {
            return code == 0
                ? null
                : $"Service control failed with WMI return value {code} (0 = success; access denied is common without elevation).";
        }
        return "Service control returned no status.";
    }
}
