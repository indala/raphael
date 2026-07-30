using System.Speech.Recognition;

namespace RaphaelHybrid;

/// <summary>
/// Speech-to-text via System.Speech (Windows built-in speech recognition engine).
/// Uses the in-process SpeechRecognitionEngine for continuous dictation.
/// </summary>
public class SpeechRecognition : IDisposable
{
    private SpeechRecognitionEngine? _engine;
    private bool _running;

    // Event-based results — subscribe from Python
    public event Action<string>? OnResult;
    public event Action<string>? OnStateChanged;

    /// <summary>Whether the engine is currently listening.</summary>
    public bool IsListening => _running;

    /// <summary>Start continuous dictation.</summary>
    public bool Start()
    {
        if (_running) return true;

        try
        {
            if (_engine == null)
            {
                _engine = new SpeechRecognitionEngine();
                _engine.SetInputToDefaultAudioDevice();
                _engine.LoadGrammar(new DictationGrammar());
                _engine.SpeechRecognized += OnSpeechRecognized;
                _engine.RecognizeCompleted += OnRecognizeCompleted;
                _engine.AudioStateChanged += OnAudioStateChanged;
            }

            _engine.RecognizeAsync(RecognizeMode.Multiple);
            _running = true;
            OnStateChanged?.Invoke("LISTENING");
            return true;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[C# SpeechRecognition] Start failed: {ex.Message}");
            return false;
        }
    }

    /// <summary>Stop listening.</summary>
    public void Stop()
    {
        if (!_running) return;

        try
        {
            _engine?.RecognizeAsyncCancel();
        }
        catch { }

        _running = false;
        OnStateChanged?.Invoke("IDLE");
    }

    private void OnSpeechRecognized(object? sender, SpeechRecognizedEventArgs e)
    {
        if (e.Result == null) return;
        var text = e.Result.Text?.Trim();
        if (!string.IsNullOrEmpty(text))
        {
            OnResult?.Invoke(text);
        }
    }

    private void OnRecognizeCompleted(object? sender, RecognizeCompletedEventArgs e)
    {
        // Recognition session ended — may restart if needed
    }

    private void OnAudioStateChanged(object? sender, AudioStateChangedEventArgs e)
    {
        var state = e.AudioState switch
        {
            AudioState.Stopped => "IDLE",
            AudioState.Speech => "SPEECHING",
            AudioState.Silence => "LISTENING",
            _ => "UNKNOWN"
        };
        OnStateChanged?.Invoke(state);
    }

    public void Dispose()
    {
        Stop();
        if (_engine != null)
        {
            _engine.SpeechRecognized -= OnSpeechRecognized;
            _engine.RecognizeCompleted -= OnRecognizeCompleted;
            _engine.AudioStateChanged -= OnAudioStateChanged;
            _engine.Dispose();
            _engine = null;
        }
    }
}
