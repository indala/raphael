using System;
using System.Runtime.InteropServices;
using System.Threading;

namespace RaphaelHybrid
{
    /// <summary>
    /// Reliable keyboard and mouse input via Win32 SendInput API.
    /// Replaces PyAutoGUI/pywin32 which can crash on COM threading issues.
    /// </summary>
    public class InputSimulator
    {
        // ── Win32 API ────────────────────────────────────────────────────

        [StructLayout(LayoutKind.Sequential)]
        private struct INPUT
        {
            public uint type;
            public InputUnion u;
        }

        [StructLayout(LayoutKind.Explicit)]
        private struct InputUnion
        {
            [FieldOffset(0)] public MOUSEINPUT mi;
            [FieldOffset(0)] public KEYBDINPUT ki;
            [FieldOffset(0)] public HARDWAREINPUT hi;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct MOUSEINPUT
        {
            public int dx;
            public int dy;
            public uint mouseData;
            public uint dwFlags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct KEYBDINPUT
        {
            public ushort wVk;
            public ushort wScan;
            public uint dwFlags;
            public uint time;
            public IntPtr dwExtraInfo;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct HARDWAREINPUT
        {
            public uint uMsg;
            public ushort wParamL;
            public ushort wParamH;
        }

        private const uint INPUT_MOUSE = 0;
        private const uint INPUT_KEYBOARD = 1;

        private const uint MOUSEEVENTF_MOVE = 0x0001;
        private const uint MOUSEEVENTF_LEFTDOWN = 0x0002;
        private const uint MOUSEEVENTF_LEFTUP = 0x0004;
        private const uint MOUSEEVENTF_RIGHTDOWN = 0x0008;
        private const uint MOUSEEVENTF_RIGHTUP = 0x0010;
        private const uint MOUSEEVENTF_MIDDLEDOWN = 0x0020;
        private const uint MOUSEEVENTF_MIDDLEUP = 0x0040;
        private const uint MOUSEEVENTF_ABSOLUTE = 0x8000;
        private const uint MOUSEEVENTF_WHEEL = 0x0800;
        private const uint MOUSEEVENTF_HWHEEL = 0x1000;

        private const int SM_CXSCREEN = 0;
        private const int SM_CYSCREEN = 1;

        private const uint KEYEVENTF_KEYUP = 0x0002;
        private const uint KEYEVENTF_SCANCODE = 0x0008;

        [DllImport("user32.dll", SetLastError = true)]
        private static extern uint SendInput(uint nInputs, INPUT[] pInputs, int cbSize);

        [DllImport("user32.dll")]
        private static extern bool SetCursorPos(int x, int y);

        [DllImport("user32.dll")]
        private static extern bool GetCursorPos(out POINT lpPoint);

        [DllImport("user32.dll")]
        private static extern int GetSystemMetrics(int nIndex);

        [StructLayout(LayoutKind.Sequential)]
        private struct POINT
        {
            public int x;
            public int y;
        }

        [DllImport("user32.dll")]
        private static extern short VkKeyScanA(char ch);

        // ── Virtual key map (subset) ─────────────────────────────────────

        private static readonly Dictionary<string, ushort> KeyMap = new(StringComparer.OrdinalIgnoreCase)
        {
            ["backspace"] = 0x08, ["tab"] = 0x09, ["enter"] = 0x0D,
            ["shift"] = 0x10, ["ctrl"] = 0x11, ["control"] = 0x11, ["alt"] = 0x12,
            ["pause"] = 0x13, ["capslock"] = 0x14, ["esc"] = 0x1B, ["escape"] = 0x1B,
            ["space"] = 0x20, ["pgup"] = 0x21, ["pgdn"] = 0x22, ["end"] = 0x23,
            ["home"] = 0x24, ["left"] = 0x25, ["up"] = 0x26, ["right"] = 0x27,
            ["down"] = 0x28, ["delete"] = 0x2E, ["del"] = 0x2E,
            ["0"] = 0x30, ["1"] = 0x31, ["2"] = 0x32, ["3"] = 0x33, ["4"] = 0x34,
            ["5"] = 0x35, ["6"] = 0x36, ["7"] = 0x37, ["8"] = 0x38, ["9"] = 0x39,
            ["a"] = 0x41, ["b"] = 0x42, ["c"] = 0x43, ["d"] = 0x44, ["e"] = 0x45,
            ["f"] = 0x46, ["g"] = 0x47, ["h"] = 0x48, ["i"] = 0x49, ["j"] = 0x4A,
            ["k"] = 0x4B, ["l"] = 0x4C, ["m"] = 0x4D, ["n"] = 0x4E, ["o"] = 0x4F,
            ["p"] = 0x50, ["q"] = 0x51, ["r"] = 0x52, ["s"] = 0x53, ["t"] = 0x54,
            ["u"] = 0x55, ["v"] = 0x56, ["w"] = 0x57, ["x"] = 0x58, ["y"] = 0x59,
            ["z"] = 0x5A,
            ["f1"] = 0x70, ["f2"] = 0x71, ["f3"] = 0x72, ["f4"] = 0x73,
            ["f5"] = 0x74, ["f6"] = 0x75, ["f7"] = 0x76, ["f8"] = 0x77,
            ["f9"] = 0x78, ["f10"] = 0x79, ["f11"] = 0x7A, ["f12"] = 0x7B,
            ["f13"] = 0x7C, ["f14"] = 0x7D, ["f15"] = 0x7E, ["f16"] = 0x7F,
            ["f17"] = 0x80, ["f18"] = 0x81, ["f19"] = 0x82, ["f20"] = 0x83,
            ["f21"] = 0x84, ["f22"] = 0x85, ["f23"] = 0x86, ["f24"] = 0x87,
            [","] = 0xBC, ["-"] = 0xBD, ["."] = 0xBE, ["/"] = 0xBF,
            [";"] = 0xBA, ["'"] = 0xDE, ["["] = 0xDB, ["]"] = 0xDD,
            ["\\"] = 0xDC, ["`"] = 0xC0, ["="] = 0xBB,
            ["insert"] = 0x2D, ["ins"] = 0x2D,
            ["printscreen"] = 0x2C, ["prtsc"] = 0x2C, ["prtscr"] = 0x2C,
            ["scrolllock"] = 0x91, ["numlock"] = 0x90,
            ["win"] = 0x5B, ["lwin"] = 0x5B, ["winleft"] = 0x5B,
            ["rwin"] = 0x5C, ["winright"] = 0x5C,
            ["apps"] = 0x5D, ["menu"] = 0x5D, ["sleep"] = 0x5F,
            ["numpad0"] = 0x60, ["numpad1"] = 0x61, ["numpad2"] = 0x62,
            ["numpad3"] = 0x63, ["numpad4"] = 0x64, ["numpad5"] = 0x65,
            ["numpad6"] = 0x66, ["numpad7"] = 0x67, ["numpad8"] = 0x68,
            ["numpad9"] = 0x69, ["multiply"] = 0x6A, ["add"] = 0x6B,
            ["separator"] = 0x6C, ["subtract"] = 0x6D, ["decimal"] = 0x6E,
            ["divide"] = 0x6F,
        };

        // ── Public API ──────────────────────────────────────────────────

        /// <summary>Move the mouse cursor to absolute screen coordinates.</summary>
        public static void MoveTo(int x, int y)
        {
            SetCursorPos(x, y);
        }

        /// <summary>Click the specified mouse button at the current position.</summary>
        public static void Click(string button = "left")
        {
            uint downFlag, upFlag;
            switch (button.ToLower())
            {
                case "right":
                    downFlag = MOUSEEVENTF_RIGHTDOWN;
                    upFlag = MOUSEEVENTF_RIGHTUP;
                    break;
                case "middle":
                    downFlag = MOUSEEVENTF_MIDDLEDOWN;
                    upFlag = MOUSEEVENTF_MIDDLEUP;
                    break;
                default:
                    downFlag = MOUSEEVENTF_LEFTDOWN;
                    upFlag = MOUSEEVENTF_LEFTUP;
                    break;
            }

            INPUT[] inputs =
            {
                new() { type = INPUT_MOUSE, u = new InputUnion { mi = new MOUSEINPUT { dwFlags = downFlag } } },
                new() { type = INPUT_MOUSE, u = new InputUnion { mi = new MOUSEINPUT { dwFlags = upFlag } } }
            };
            SendInput(2, inputs, Marshal.SizeOf<INPUT>());
        }

        /// <summary>Move to (x,y) and click.</summary>
        public static void ClickAt(int x, int y, string button = "left")
        {
            MoveTo(x, y);
            Thread.Sleep(15);
            Click(button);
        }

        /// <summary>Get the current cursor position as "x,y".</summary>
        public static string GetCursorPosition()
        {
            if (GetCursorPos(out POINT pt))
                return $"{pt.x},{pt.y}";
            return "0,0";
        }

        /// <summary>Type a string of text at the current focus.</summary>
        public static void TypeText(string text)
        {
            foreach (char c in text)
            {
                ushort vk;
                bool shift = false;

                if (KeyMap.TryGetValue(c.ToString(), out ushort mapped))
                {
                    vk = mapped;
                }
                else
                {
                    // Use VkKeyScan to determine vkey and shift state
                    short scan = VkKeyScanA(c);
                    if (scan == -1) continue;
                    vk = (ushort)(scan & 0xFF);
                    shift = (scan & 0x100) != 0;
                }

                if (shift)
                    PressKey("shift");

                INPUT[] down = { new() { type = INPUT_KEYBOARD, u = new InputUnion { ki = new KEYBDINPUT { wVk = vk } } } };
                SendInput(1, down, Marshal.SizeOf<INPUT>());

                INPUT[] up = { new() { type = INPUT_KEYBOARD, u = new InputUnion { ki = new KEYBDINPUT { wVk = vk, dwFlags = KEYEVENTF_KEYUP } } } };
                SendInput(1, up, Marshal.SizeOf<INPUT>());

                if (shift)
                    ReleaseKey("shift");
            }
        }

        /// <summary>Press and hold a key.</summary>
        public static void PressKey(string key)
        {
            if (!KeyMap.TryGetValue(key, out ushort vk)) return;
            INPUT input = new() { type = INPUT_KEYBOARD, u = new InputUnion { ki = new KEYBDINPUT { wVk = vk } } };
            SendInput(1, new[] { input }, Marshal.SizeOf<INPUT>());
        }

        /// <summary>Release a held key.</summary>
        public static void ReleaseKey(string key)
        {
            if (!KeyMap.TryGetValue(key, out ushort vk)) return;
            INPUT input = new() { type = INPUT_KEYBOARD, u = new InputUnion { ki = new KEYBDINPUT { wVk = vk, dwFlags = KEYEVENTF_KEYUP } } };
            SendInput(1, new[] { input }, Marshal.SizeOf<INPUT>());
        }

        /// <summary>Press and release a key.</summary>
        public static void TapKey(string key)
        {
            if (!KeyMap.TryGetValue(key, out ushort vk)) return;
            INPUT[] inputs =
            {
                new() { type = INPUT_KEYBOARD, u = new InputUnion { ki = new KEYBDINPUT { wVk = vk } } },
                new() { type = INPUT_KEYBOARD, u = new InputUnion { ki = new KEYBDINPUT { wVk = vk, dwFlags = KEYEVENTF_KEYUP } } }
            };
            SendInput(2, inputs, Marshal.SizeOf<INPUT>());
        }

        /// <summary>Send a modifier + key combination (e.g. "ctrl+c").</summary>
        public static void Hotkey(string keys)
        {
            var parts = keys.Split('+');
            // Press modifiers in order
            foreach (var p in parts)
                PressKey(p.Trim());
            // Release in reverse
            for (int i = parts.Length - 1; i >= 0; i--)
                ReleaseKey(parts[i].Trim());
        }

        // ── Mouse Enhancements ──────────────────────────────────────────

        /// <summary>Double-click the specified mouse button at current position.</summary>
        public static void DoubleClick(string button = "left")
        {
            Click(button);
            Thread.Sleep(30);
            Click(button);
        }

        /// <summary>Move to (x,y) and double-click.</summary>
        public static void DoubleClickAt(int x, int y, string button = "left")
        {
            MoveTo(x, y);
            Thread.Sleep(15);
            DoubleClick(button);
        }

        /// <summary>Animate cursor smoothly to (x,y) using linear interpolation.</summary>
        public static void SmoothMoveTo(int x, int y, int durationMs = 200)
        {
            if (!GetCursorPos(out POINT start))
            {
                start.x = 0; start.y = 0;
            }
            int steps = Math.Max(10, durationMs / 10);
            int delayPerStep = Math.Max(1, durationMs / steps);
            for (int i = 1; i <= steps; i++)
            {
                float t = (float)i / steps;
                int cx = (int)(start.x + (x - start.x) * t);
                int cy = (int)(start.y + (y - start.y) * t);
                SetCursorPos(cx, cy);
                Thread.Sleep(delayPerStep);
            }
        }

        /// <summary>Drag from (x1,y1) to (x2,y2) holding the specified button.</summary>
        public static void Drag(int x1, int y1, int x2, int y2, string button = "left")
        {
            MoveTo(x1, y1);
            Thread.Sleep(30);
            MouseDown(button);
            Thread.Sleep(15);
            // Smooth move to destination
            int steps = 20;
            for (int i = 1; i <= steps; i++)
            {
                float t = (float)i / steps;
                int cx = (int)(x1 + (x2 - x1) * t);
                int cy = (int)(y1 + (y2 - y1) * t);
                SetCursorPos(cx, cy);
                Thread.Sleep(10);
            }
            Thread.Sleep(15);
            MouseUp(button);
        }

        /// <summary>Scroll the mouse wheel (positive clicks = down, negative = up).</summary>
        public static void Scroll(int clicks)
        {
            int delta = -clicks * 120; // positive = scroll down (negative WHEEL_DELTA)
            INPUT input = new()
            {
                type = INPUT_MOUSE,
                u = new InputUnion
                {
                    mi = new MOUSEINPUT
                    {
                        dwFlags = MOUSEEVENTF_WHEEL,
                        mouseData = unchecked((uint)delta)
                    }
                }
            };
            SendInput(1, new[] { input }, Marshal.SizeOf<INPUT>());
        }

        /// <summary>Move to (x,y) then scroll.</summary>
        public static void ScrollAt(int x, int y, int clicks)
        {
            MoveTo(x, y);
            Thread.Sleep(15);
            Scroll(clicks);
        }

        /// <summary>Move cursor relative to current position.</summary>
        public static void MoveRelative(int dx, int dy)
        {
            if (GetCursorPos(out POINT current))
            {
                SetCursorPos(current.x + dx, current.y + dy);
            }
        }

        /// <summary>Press and hold the specified mouse button.</summary>
        public static void MouseDown(string button = "left")
        {
            uint flag = button.ToLower() switch
            {
                "right" => MOUSEEVENTF_RIGHTDOWN,
                "middle" => MOUSEEVENTF_MIDDLEDOWN,
                _ => MOUSEEVENTF_LEFTDOWN
            };
            INPUT input = new() { type = INPUT_MOUSE, u = new InputUnion { mi = new MOUSEINPUT { dwFlags = flag } } };
            SendInput(1, new[] { input }, Marshal.SizeOf<INPUT>());
        }

        /// <summary>Release the specified mouse button.</summary>
        public static void MouseUp(string button = "left")
        {
            uint flag = button.ToLower() switch
            {
                "right" => MOUSEEVENTF_RIGHTUP,
                "middle" => MOUSEEVENTF_MIDDLEUP,
                _ => MOUSEEVENTF_LEFTUP
            };
            INPUT input = new() { type = INPUT_MOUSE, u = new InputUnion { mi = new MOUSEINPUT { dwFlags = flag } } };
            SendInput(1, new[] { input }, Marshal.SizeOf<INPUT>());
        }

        /// <summary>Get screen dimensions as "width,height".</summary>
        public static string GetScreenSize()
        {
            int w = GetSystemMetrics(SM_CXSCREEN);
            int h = GetSystemMetrics(SM_CYSCREEN);
            return $"{w},{h}";
        }
    }
}
