using System.Runtime.InteropServices;

namespace RaphaelHybrid;

/// <summary>
/// Keyboard key state queries via User32 GetAsyncKeyState / GetKeyState.
/// </summary>
public static class KeyboardState
{
    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int vKey);

    [DllImport("user32.dll")]
    private static extern short GetKeyState(int nVirtKey);

    private const int VK_CAPITAL = 0x14;
    private const int VK_NUMLOCK = 0x90;

    private static readonly Dictionary<string, int> KeyMap = new(StringComparer.OrdinalIgnoreCase)
    {
        ["a"] = 0x41, ["b"] = 0x42, ["c"] = 0x43, ["d"] = 0x44, ["e"] = 0x45,
        ["f"] = 0x46, ["g"] = 0x47, ["h"] = 0x48, ["i"] = 0x49, ["j"] = 0x4A,
        ["k"] = 0x4B, ["l"] = 0x4C, ["m"] = 0x4D, ["n"] = 0x4E, ["o"] = 0x4F,
        ["p"] = 0x50, ["q"] = 0x51, ["r"] = 0x52, ["s"] = 0x53, ["t"] = 0x54,
        ["u"] = 0x55, ["v"] = 0x56, ["w"] = 0x57, ["x"] = 0x58, ["y"] = 0x59,
        ["z"] = 0x5A,
        ["0"] = 0x30, ["1"] = 0x31, ["2"] = 0x32, ["3"] = 0x33, ["4"] = 0x34,
        ["5"] = 0x35, ["6"] = 0x36, ["7"] = 0x37, ["8"] = 0x38, ["9"] = 0x39,
        ["enter"] = 0x0D, ["return"] = 0x0D, ["escape"] = 0x1B, ["esc"] = 0x1B,
        ["tab"] = 0x09, ["space"] = 0x20, ["backspace"] = 0x08, ["delete"] = 0x2E,
        ["del"] = 0x2E, ["insert"] = 0x2D, ["home"] = 0x24, ["end"] = 0x23,
        ["pageup"] = 0x21, ["pgup"] = 0x21, ["pagedown"] = 0x22, ["pgdn"] = 0x22,
        ["up"] = 0x26, ["down"] = 0x28, ["left"] = 0x25, ["right"] = 0x27,
        ["shift"] = 0x10, ["ctrl"] = 0x11, ["control"] = 0x11, ["alt"] = 0x12,
        ["win"] = 0x5B, ["lwin"] = 0x5B, ["rwin"] = 0x5C,
        ["capslock"] = 0x14, ["numlock"] = 0x90, ["scrolllock"] = 0x91,
        ["menu"] = 0x5D, ["apps"] = 0x5D, ["printscreen"] = 0x2C, ["pause"] = 0x13,
        ["f1"] = 0x70, ["f2"] = 0x71, ["f3"] = 0x72, ["f4"] = 0x73, ["f5"] = 0x74,
        ["f6"] = 0x75, ["f7"] = 0x76, ["f8"] = 0x77, ["f9"] = 0x78, ["f10"] = 0x79,
        ["f11"] = 0x7A, ["f12"] = 0x7B, ["f13"] = 0x7C, ["f14"] = 0x7D,
        ["f15"] = 0x7E, ["f16"] = 0x7F, ["f17"] = 0x80, ["f18"] = 0x81,
        ["f19"] = 0x82, ["f20"] = 0x83, ["f21"] = 0x84, ["f22"] = 0x85,
        ["f23"] = 0x86, ["f24"] = 0x87,
        ["semicolon"] = 0xBA, ["quote"] = 0xDE, ["comma"] = 0xBC,
        ["period"] = 0xBE, ["slash"] = 0xBF, ["backslash"] = 0xDC,
        ["backquote"] = 0xC0, ["minus"] = 0xBD, ["equals"] = 0xBB,
        ["lbracket"] = 0xDB, ["rbracket"] = 0xDD,
    };

    /// <summary>
    /// Check whether a key is currently held down (GetAsyncKeyState high bit).
    /// </summary>
    public static Dictionary<string, object?> IsPressed(string key)
    {
        if (!KeyMap.TryGetValue(key, out int vk))
        {
            return new Dictionary<string, object?>
            {
                ["pressed"] = false,
                ["error"] = $"Unknown key name: {key}",
            };
        }
        bool pressed = (GetAsyncKeyState(vk) & 0x8000) != 0;
        return new Dictionary<string, object?>
        {
            ["pressed"] = pressed,
            ["error"] = null,
        };
    }

    /// <summary>
    /// Caps Lock toggle state (true when the indicator is on).
    /// </summary>
    public static bool CapsLock() => (GetKeyState(VK_CAPITAL) & 1) != 0;

    /// <summary>
    /// Num Lock toggle state (true when the indicator is on).
    /// </summary>
    public static bool NumLock() => (GetKeyState(VK_NUMLOCK) & 1) != 0;
}
