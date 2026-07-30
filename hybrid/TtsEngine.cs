using System.Speech.Synthesis;

namespace RaphaelHybrid;

/// <summary>
/// Text-to-speech via System.Speech.Synthesis (SAPI5).
/// Clean, fast, offline TTS without COM interop overhead.
/// </summary>
public class TtsEngine : IDisposable
{
    private readonly SpeechSynthesizer _synthesizer = new();

    public TtsEngine()
    {
        // Default rate and volume
        _synthesizer.Rate = 0;     // -10 to 10
        _synthesizer.Volume = 100; // 0 to 100
    }

    /// <summary>Speak text synchronously (blocks until done).</summary>
    public void Speak(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        try
        {
            _synthesizer.Speak(text);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[C# TTS] Speak failed: {ex.Message}");
        }
    }

    /// <summary>Speak text asynchronously.</summary>
    public void SpeakAsync(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        try
        {
            _synthesizer.SpeakAsync(text);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[C# TTS] SpeakAsync failed: {ex.Message}");
        }
    }

    /// <summary>Stop speaking immediately.</summary>
    public void Stop()
    {
        try
        {
            _synthesizer.SpeakAsyncCancelAll();
        }
        catch { }
    }

    /// <summary>Set speaking rate (-10 to 10).</summary>
    public void SetRate(int rate)
    {
        _synthesizer.Rate = Math.Clamp(rate, -10, 10);
    }

    /// <summary>Set volume (0 to 100).</summary>
    public void SetVolume(int volume)
    {
        _synthesizer.Volume = Math.Clamp(volume, 0, 100);
    }

    /// <summary>Select voice by partial name match.</summary>
    public bool SetVoice(string name)
    {
        if (string.IsNullOrWhiteSpace(name)) return false;
        try
        {
            foreach (var voice in _synthesizer.GetInstalledVoices())
            {
                if (voice.VoiceInfo?.Name != null &&
                    voice.VoiceInfo.Name.Contains(name, StringComparison.OrdinalIgnoreCase))
                {
                    _synthesizer.SelectVoice(voice.VoiceInfo.Name);
                    return true;
                }
            }
        }
        catch { }
        return false;
    }

    /// <summary>List installed voice names.</summary>
    public string[] GetVoices()
    {
        try
        {
            return _synthesizer.GetInstalledVoices()
                .Where(v => v.VoiceInfo?.Name != null)
                .Select(v => v.VoiceInfo!.Name!)
                .ToArray();
        }
        catch
        {
            return [];
        }
    }

    /// <summary>Whether audio is currently playing.</summary>
    public bool IsSpeaking
    {
        get
        {
            try { return _synthesizer.State == SynthesizerState.Speaking; }
            catch { return false; }
        }
    }

    public void Dispose()
    {
        try
        {
            _synthesizer.SpeakAsyncCancelAll();
            _synthesizer.Dispose();
        }
        catch { }
    }
}
