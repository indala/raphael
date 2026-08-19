using System.Text.Json;
using System.Text.Json.Serialization;
using RaphaelHybrid;

using var monitor = new SystemMonitor();
var tts = new TtsEngine();
var writeLock = new object();
var monitorLock = new object();
var ttsLock = new object();

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

    ThreadPool.QueueUserWorkItem(_ =>
    {
        try
        {
            ProcessRequest(req);
        }
        catch (Exception ex)
        {
            RespondError(req.Id, ex.Message);
        }
    });
}

void ProcessRequest(Request req)
{
    switch (req.Method)
    {
        // ── Introspection & Liveness ──
        case "ping":
            Respond(req.Id, "pong");
            break;
        case "version":
            Respond(req.Id, new
            {
                version = "1.2.0",
                framework = ".NET 10",
                os = Environment.OSVersion.ToString(),
                process_id = Environment.ProcessId,
            });
            break;
        case "list_methods":
            Respond(req.Id, ProgramMeta.AllMethods);
            break;

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
        case "window_move":
            Respond(req.Id, WindowManager.MoveWindow(req.GetArg<string>(0) ?? "", req.GetArg<int>(1), req.GetArg<int>(2)));
            break;
        case "window_resize":
            Respond(req.Id, WindowManager.ResizeWindow(req.GetArg<string>(0) ?? "", req.GetArg<int>(1), req.GetArg<int>(2)));
            break;
        case "window_set_always_on_top":
            Respond(req.Id, WindowManager.SetAlwaysOnTop(req.GetArg<string>(0) ?? "", req.GetArg<bool>(1)));
            break;
        case "window_set_opacity":
            Respond(req.Id, WindowManager.SetOpacity(req.GetArg<string>(0) ?? "", req.GetArg<double>(1)));
            break;
        case "window_hide":
            Respond(req.Id, WindowManager.HideWindow(req.GetArg<string>(0) ?? ""));
            break;
        case "window_show":
            Respond(req.Id, WindowManager.ShowWindowByTitle(req.GetArg<string>(0) ?? ""));
            break;

        // ── PowerManager ──
        case "power_sleep":
            Respond(req.Id, PowerManager.Sleep());
            break;
        case "power_hibernate":
            Respond(req.Id, PowerManager.Hibernate());
            break;
        case "power_lock":
            Respond(req.Id, PowerManager.Lock());
            break;
        case "power_shutdown":
            Respond(req.Id, PowerManager.Shutdown(req.GetArg<bool>(0)));
            break;
        case "power_reboot":
            Respond(req.Id, PowerManager.Reboot(req.GetArg<bool>(0)));
            break;

        // ── ToastNotifier ──
        case "toast_show":
            Respond(req.Id, ToastNotifier.Show(req.GetArg<string>(0) ?? "", req.GetArg<string>(1) ?? ""));
            break;

        // ── ServiceHelper (WMI) ──
        case "service_list":
            Respond(req.Id, ServiceHelper.List());
            break;
        case "service_start":
            Respond(req.Id, ServiceHelper.Start(req.GetArg<string>(0) ?? ""));
            break;
        case "service_stop":
            Respond(req.Id, ServiceHelper.Stop(req.GetArg<string>(0) ?? ""));
            break;

        // ── EnvVarHelper (BCL) ──
        case "env_get":
            Respond(req.Id, EnvVarHelper.Get(req.GetArg<string>(0) ?? ""));
            break;
        case "env_set":
            Respond(req.Id, EnvVarHelper.Set(req.GetArg<string>(0) ?? "", req.GetArg<string>(1) ?? ""));
            break;

        // ── ProcessHelper (System.Diagnostics) ──
        case "process_kill":
            Respond(req.Id, ProcessHelper.Kill(req.GetArg<int>(0)));
            break;
        case "process_wait":
            Respond(req.Id, ProcessHelper.Wait(req.GetArg<int>(0), req.GetArg<int>(1) > 0 ? req.GetArg<int>(1) : 30000));
            break;

        // ── ShortcutHelper (WScript.Shell COM) ──
        case "shortcut_create":
            Respond(req.Id, ShortcutHelper.Create(
                req.GetArg<string>(0) ?? "", req.GetArg<string>(1) ?? "",
                req.GetArg<string>(2) ?? "", req.GetArg<string>(3) ?? "", req.GetArg<string>(4) ?? ""));
            break;

        // ── RecycleBin (Shell32) ──
        case "recycle_bin_get":
            Respond(req.Id, RecycleBin.Get());
            break;
        case "recycle_bin_empty":
            Respond(req.Id, RecycleBin.Empty(req.GetArg<bool>(0)));
            break;

        // ── KeyboardState (User32) ──
        case "key_is_pressed":
            Respond(req.Id, KeyboardState.IsPressed(req.GetArg<string>(0) ?? ""));
            break;
        case "key_caps_lock":
            Respond(req.Id, KeyboardState.CapsLock());
            break;
        case "key_num_lock":
            Respond(req.Id, KeyboardState.NumLock());
            break;

        // ── DisplayBrightness (shcore + dxva2) ──
        case "monitor_get_dpi":
            Respond(req.Id, DisplayBrightness.GetDpi());
            break;
        case "brightness_get":
            Respond(req.Id, DisplayBrightness.GetBrightness());
            break;
        case "brightness_set":
            Respond(req.Id, DisplayBrightness.SetBrightness(req.GetArg<uint>(0)));
            break;

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
                    cpu_temp = snap.CpuTemp,
                    gpu_temp = snap.GpuTemp
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
    var json = JsonSerializer.Serialize(resp, JsonOpts.Default);
    lock (writeLock)
    {
        Console.Out.WriteLine(json);
        Console.Out.Flush();
    }
}

void RespondNull(long id)
{
    Respond(id, null);
}

void RespondError(long id, string message)
{
    var resp = new Response { Id = id, Error = message };
    var json = JsonSerializer.Serialize(resp, JsonOpts.Default);
    lock (writeLock)
    {
        Console.Out.WriteLine(json);
        Console.Out.Flush();
    }
}

// ── Types & Metadata ──

static class ProgramMeta
{
    public static readonly string[] AllMethods =
    [
        "ping", "version", "list_methods", "self_test",
        "input_move_to", "input_click", "input_click_at", "input_get_cursor",
        "input_type_text", "input_press_key", "input_release_key", "input_tap_key",
        "input_hotkey", "input_double_click", "input_double_click_at",
        "input_smooth_move_to", "input_drag", "input_scroll", "input_scroll_at",
        "input_move_relative", "input_mouse_down", "input_mouse_up", "input_get_screen_size",
        "capture_primary", "capture_monitor", "screen_size",
        "tts_speak", "tts_speak_async", "tts_stop", "tts_is_speaking",
        "tts_set_rate", "tts_set_volume", "tts_get_voices", "tts_set_voice",
        "window_find", "window_focus", "window_get_active_title", "window_get_all_titles",
        "window_get_all", "window_close", "window_minimize", "window_maximize",
        "window_get_rect", "window_move", "window_resize", "window_set_always_on_top",
        "window_set_opacity", "window_hide", "window_show",
        "power_sleep", "power_hibernate", "power_lock", "power_shutdown", "power_reboot",
        "toast_show", "service_list", "service_start", "service_stop",
        "env_get", "env_set", "process_kill", "process_wait",
        "shortcut_create", "recycle_bin_get", "recycle_bin_empty",
        "key_is_pressed", "key_caps_lock", "key_num_lock",
        "monitor_get_dpi", "brightness_get", "brightness_set",
        "clipboard_copy_text", "clipboard_paste_text", "clipboard_has_text", "clipboard_clear",
        "audio_play_mp3", "audio_stop_all",
        "registry_get_browser_progid", "registry_read_current_user", "registry_read_local_machine",
        "shell_open", "shell_launch",
        "clipboard_copy_image", "clipboard_has_image", "clipboard_get_file_list", "clipboard_has_files",
        "audio_get_state", "system_snapshot", "monitors_get_all",
        "system_state_get", "explorer_get_selection", "explorer_get_all_selections",
        "taskbar_get_info", "tray_get_icons"
    ];
}

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
