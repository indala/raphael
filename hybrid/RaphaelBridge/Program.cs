/// <summary>
/// RaphaelBridge — JSON stdin/stdout subprocess bridge.
/// Avoids pythonnet compatibility issues by communicating via newline-delimited JSON.
/// </summary>

using System.Text.Json;
using System.Text.Json.Serialization;
using RaphaelHybrid;

using var monitor = new SystemMonitor();
var tts = new TtsEngine();

string? line;
while ((line = Console.In.ReadLine()) is not null)
{
    if (string.IsNullOrWhiteSpace(line)) continue;

    Request? req;
    try
    {
        req = JsonSerializer.Deserialize<Request>(line, JsonOpts.Default);
    }
    catch (Exception ex)
    {
        RespondError(0, $"Parse error: {ex.Message}");
        continue;
    }

    if (req is null)
    {
        RespondError(0, "Empty request");
        continue;
    }

    try
    {
        ProcessRequest(req);
    }
    catch (Exception ex)
    {
        RespondError(req.Id, ex.Message);
    }
}

void ProcessRequest(Request req)
{
    switch (req.Method)
    {
        // ── HybridInfo ──
        case "self_test":
            Respond(req.Id, HybridInfo.SelfTest());
            break;

        // ── InputSimulator (all static) ──
        case "input_move_to":
            InputSimulator.MoveTo(req.GetArg<int>(0), req.GetArg<int>(1));
            RespondNull(req.Id);
            break;
        case "input_click":
            InputSimulator.Click(req.GetArg<string>(0) ?? "left");
            RespondNull(req.Id);
            break;
        case "input_click_at":
            InputSimulator.ClickAt(req.GetArg<int>(0), req.GetArg<int>(1), req.GetArg<string>(2) ?? "left");
            RespondNull(req.Id);
            break;
        case "input_get_cursor":
            {
                var pos = InputSimulator.GetCursorPosition(); // "x,y"
                var parts = pos.Split(',');
                Respond(req.Id, new { x = int.Parse(parts[0]), y = int.Parse(parts[1]) });
                break;
            }
        case "input_type_text":
            InputSimulator.TypeText(req.GetArg<string>(0) ?? "");
            RespondNull(req.Id);
            break;
        case "input_press_key":
            InputSimulator.PressKey(req.GetArg<string>(0) ?? "");
            RespondNull(req.Id);
            break;
        case "input_release_key":
            InputSimulator.ReleaseKey(req.GetArg<string>(0) ?? "");
            RespondNull(req.Id);
            break;
        case "input_tap_key":
            InputSimulator.TapKey(req.GetArg<string>(0) ?? "");
            RespondNull(req.Id);
            break;
        case "input_hotkey":
            InputSimulator.Hotkey(req.GetArg<string>(0) ?? "");
            RespondNull(req.Id);
            break;
        case "input_double_click":
            InputSimulator.DoubleClick(req.GetArg<string>(0) ?? "left");
            RespondNull(req.Id);
            break;
        case "input_double_click_at":
            InputSimulator.DoubleClickAt(req.GetArg<int>(0), req.GetArg<int>(1), req.GetArg<string>(2) ?? "left");
            RespondNull(req.Id);
            break;
        case "input_smooth_move_to":
            InputSimulator.SmoothMoveTo(req.GetArg<int>(0), req.GetArg<int>(1), req.GetArg<int>(2) > 0 ? req.GetArg<int>(2) : 200);
            RespondNull(req.Id);
            break;
        case "input_drag":
            InputSimulator.Drag(req.GetArg<int>(0), req.GetArg<int>(1), req.GetArg<int>(2), req.GetArg<int>(3), req.GetArg<string>(4) ?? "left");
            RespondNull(req.Id);
            break;
        case "input_scroll":
            InputSimulator.Scroll(req.GetArg<int>(0));
            RespondNull(req.Id);
            break;
        case "input_scroll_at":
            InputSimulator.ScrollAt(req.GetArg<int>(0), req.GetArg<int>(1), req.GetArg<int>(2));
            RespondNull(req.Id);
            break;
        case "input_move_relative":
            InputSimulator.MoveRelative(req.GetArg<int>(0), req.GetArg<int>(1));
            RespondNull(req.Id);
            break;
        case "input_mouse_down":
            InputSimulator.MouseDown(req.GetArg<string>(0) ?? "left");
            RespondNull(req.Id);
            break;
        case "input_mouse_up":
            InputSimulator.MouseUp(req.GetArg<string>(0) ?? "left");
            RespondNull(req.Id);
            break;
        case "input_get_screen_size":
            {
                var size = InputSimulator.GetScreenSize(); // "width,height"
                var parts = size.Split(',');
                Respond(req.Id, new { width = int.Parse(parts[0]), height = int.Parse(parts[1]) });
                break;
            }

        // ── ScreenCapture (all static) ──
        case "capture_primary":
            {
                var bytes = ScreenCapture.CapturePrimaryScreen();
                Respond(req.Id, Convert.ToBase64String(bytes));
                break;
            }
        case "capture_monitor":
            {
                var bytes = ScreenCapture.CaptureMonitor(req.GetArg<int>(0));
                Respond(req.Id, Convert.ToBase64String(bytes));
                break;
            }
        case "screen_size":
            {
                var size = ScreenCapture.GetScreenSize(); // "WxH"
                var parts = size.Split('x');
                Respond(req.Id, new { width = int.Parse(parts[0]), height = int.Parse(parts[1]) });
                break;
            }

        // ── TTS ──
        case "tts_speak":
            tts.Speak(req.GetArg<string>(0) ?? "");
            RespondNull(req.Id);
            break;
        case "tts_speak_async":
            tts.SpeakAsync(req.GetArg<string>(0) ?? "");
            RespondNull(req.Id);
            break;
        case "tts_stop":
            tts.Stop();
            RespondNull(req.Id);
            break;
        case "tts_is_speaking":
            Respond(req.Id, tts.IsSpeaking);
            break;
        case "tts_set_rate":
            tts.SetRate(req.GetArg<int>(0));
            RespondNull(req.Id);
            break;
        case "tts_set_volume":
            tts.SetVolume(req.GetArg<int>(0));
            RespondNull(req.Id);
            break;
        case "tts_get_voices":
            Respond(req.Id, tts.GetVoices());
            break;
        case "tts_set_voice":
            tts.SetVoice(req.GetArg<string>(0) ?? "");
            RespondNull(req.Id);
            break;

        // ── WindowManager (all static, takes window titles) ──
        case "window_find":
            Respond(req.Id, (long)WindowManager.FindWindowByTitle(req.GetArg<string>(0) ?? ""));
            break;
        case "window_focus":
            Respond(req.Id, WindowManager.FocusWindow(req.GetArg<string>(0) ?? ""));
            break;
        case "window_get_active_title":
            Respond(req.Id, WindowManager.GetActiveWindowTitle());
            break;
        case "window_get_all_titles":
            Respond(req.Id, WindowManager.GetAllWindowTitles());
            break;
        case "window_get_all":
            Respond(req.Id, WindowManager.GetAllWindows());
            break;
        case "window_close":
            Respond(req.Id, WindowManager.CloseWindow(req.GetArg<string>(0) ?? ""));
            break;
        case "window_minimize":
            Respond(req.Id, WindowManager.MinimizeWindow(req.GetArg<string>(0) ?? ""));
            break;
        case "window_maximize":
            Respond(req.Id, WindowManager.MaximizeWindow(req.GetArg<string>(0) ?? ""));
            break;
        case "window_get_rect":
            {
                var rect = WindowManager.GetWindowRect(req.GetArg<string>(0) ?? "");
                if (rect is null)
                    RespondNull(req.Id);
                else
                    Respond(req.Id, new { left = rect[0], top = rect[1], right = rect[2], bottom = rect[3] });
                break;
            }

        // ── Clipboard (all static) ──
        case "clipboard_copy_text":
            Respond(req.Id, ClipboardHelper.CopyText(req.GetArg<string>(0) ?? ""));
            break;
        case "clipboard_paste_text":
            Respond(req.Id, ClipboardHelper.PasteText());
            break;
        case "clipboard_has_text":
            Respond(req.Id, ClipboardHelper.HasText());
            break;
        case "clipboard_clear":
            Respond(req.Id, ClipboardHelper.Clear());
            break;

        // ── AudioPlayer ──
        case "audio_play_mp3":
            AudioPlayer.PlayMp3(req.GetArg<string>(0) ?? "");
            RespondNull(req.Id);
            break;
        case "audio_stop_all":
            AudioPlayer.StopAll();
            RespondNull(req.Id);
            break;

        // ── RegistryHelper ──
        case "registry_get_browser_progid":
            Respond(req.Id, RegistryHelper.GetDefaultBrowserProgId());
            break;
        case "registry_read_current_user":
            Respond(req.Id, RegistryHelper.ReadCurrentUser(req.GetArg<string>(0) ?? "", req.GetArg<string>(1) ?? ""));
            break;
        case "registry_read_local_machine":
            Respond(req.Id, RegistryHelper.ReadLocalMachine(req.GetArg<string>(0) ?? "", req.GetArg<string>(1) ?? ""));
            break;

        // ── ShellHelper ──
        case "shell_open":
            Respond(req.Id, ShellHelper.Open(req.GetArg<string>(0) ?? ""));
            break;
        case "shell_launch":
            Respond(req.Id, ShellHelper.Launch(req.GetArg<string>(0) ?? ""));
            break;

        // ── Image clipboard (extended) ──
        case "clipboard_copy_image":
            Respond(req.Id, ClipboardHelper.CopyImage(req.GetArg<string>(0) ?? ""));
            break;
        case "clipboard_has_image":
            Respond(req.Id, ClipboardHelper.HasImage());
            break;

        // ── File drop list ──
        case "clipboard_get_file_list":
            Respond(req.Id, ClipboardHelper.GetFileDropList());
            break;
        case "clipboard_has_files":
            Respond(req.Id, ClipboardHelper.HasFiles());
            break;

        // ── AudioDeviceState ──
        case "audio_get_state":
            {
                var state = AudioDeviceState.GetAudioState();
                Respond(req.Id, new
                {
                    playback = state.Playback is not null
                        ? new { muted = state.Playback.Muted, volume_percent = state.Playback.VolumePercent }
                        : null,
                    recording = state.Recording is not null
                        ? new { muted = state.Recording.Muted, volume_percent = state.Recording.VolumePercent }
                        : null
                });
                break;
            }

        // ── SystemMonitor ──
        case "system_snapshot":
            {
                var snap = monitor.GetSnapshot();
                Respond(req.Id, new
                {
                    cpu_percent = snap.CpuPercent,
                    mem_percent = snap.MemPercent,
                    net_speed_kbps = snap.NetSpeedKbps,
                    gpu_percent = snap.GpuPercent,
                    cpu_temp = snap.CpuTemp
                });
                break;
            }

        // ── DisplayHelper ──
        case "monitors_get_all":
            Respond(req.Id, DisplayHelper.GetAllMonitors());
            break;

        // ── StateHelper ──
        case "system_state_get":
            Respond(req.Id, StateHelper.GetSnapshot());
            break;

        // ── ExplorerHelper ──
        case "explorer_get_selection":
            Respond(req.Id, ExplorerHelper.GetActiveExplorerSelection());
            break;

        case "explorer_get_all_selections":
            Respond(req.Id, ExplorerHelper.GetAllExplorerSelections());
            break;

        // ── DesktopHelper ──
        case "taskbar_get_info":
            Respond(req.Id, DesktopHelper.GetTaskbarInfo());
            break;
        case "tray_get_icons":
            Respond(req.Id, DesktopHelper.GetTrayIcons());
            break;

        default:
            RespondError(req.Id, $"Unknown method: {req.Method}");
            break;
    }
}

void Respond(long id, object? data)
{
    var resp = new Response { Id = id, Result = data };
    Console.Out.WriteLine(JsonSerializer.Serialize(resp, JsonOpts.Default));
    Console.Out.Flush();
}

void RespondNull(long id)
{
    Respond(id, null);
}

void RespondError(long id, string message)
{
    var resp = new Response { Id = id, Error = message };
    Console.Out.WriteLine(JsonSerializer.Serialize(resp, JsonOpts.Default));
    Console.Out.Flush();
}

// ── Types ──

record Request
{
    [JsonPropertyName("id")]
    public long Id { get; set; }

    [JsonPropertyName("method")]
    public string Method { get; set; } = "";

    [JsonPropertyName("args")]
    public JsonElement? Args { get; set; }

    public T? GetArg<T>(int index)
    {
        if (Args is null) return default;
        var arr = Args.Value;
        if (arr.ValueKind != JsonValueKind.Array) return default;
        int i = 0;
        foreach (var el in arr.EnumerateArray())
        {
            if (i == index)
                return JsonSerializer.Deserialize<T>(el.GetRawText(), JsonOpts.Default);
            i++;
        }
        return default;
    }
}

record Response
{
    [JsonPropertyName("id")]
    public long Id { get; set; }

    [JsonPropertyName("result")]
    public object? Result { get; set; }

    [JsonPropertyName("error")]
    public string? Error { get; set; }
}

static class JsonOpts
{
    public static readonly JsonSerializerOptions Default = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = false,
    };
}
