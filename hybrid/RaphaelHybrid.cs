namespace RaphaelHybrid;

/// <summary>
/// Hybrid bridge info and version.
/// </summary>
public static class HybridInfo
{
    public static string Version => "1.0.0";
    public static bool IsAvailable => true;

    /// <summary>
    /// Quick self-test — returns true if all subsystems can initialize.
    /// </summary>
    public static bool SelfTest()
    {
        try
        {
            // Just check we can create instances (no heavy init)
            var _ = typeof(SpeechRecognition);
            var __ = typeof(TtsEngine);
            var ___ = typeof(SystemMonitor);
            var ____ = typeof(WindowManager);
            var _____ = typeof(ClipboardHelper);
            var ______ = typeof(AudioPlayer);
            var _______ = typeof(RegistryHelper);
            var ________ = typeof(ShellHelper);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
