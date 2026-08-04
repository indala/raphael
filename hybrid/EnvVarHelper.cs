namespace RaphaelHybrid;

/// <summary>
/// User environment variable read/write via the .NET BCL (no P/Invoke).
/// </summary>
public static class EnvVarHelper
{
    /// <summary>
    /// Read an environment variable. Checks the User scope first, then
    /// falls back to the process/machine scope so the value is always found.
    /// </summary>
    public static string? Get(string name)
    {
        return Environment.GetEnvironmentVariable(name, EnvironmentVariableTarget.User)
            ?? Environment.GetEnvironmentVariable(name, EnvironmentVariableTarget.Process)
            ?? Environment.GetEnvironmentVariable(name, EnvironmentVariableTarget.Machine);
    }

    /// <summary>
    /// Write a user-scope environment variable. An empty/null value deletes it.
    /// Returns null on success or an error message.
    /// </summary>
    public static string? Set(string name, string value)
    {
        try
        {
            Environment.SetEnvironmentVariable(
                name,
                string.IsNullOrEmpty(value) ? null : value,
                EnvironmentVariableTarget.User);
            return null;
        }
        catch (Exception ex)
        {
            return ex.Message;
        }
    }
}
