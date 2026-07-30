# Windows GUI & Desktop Control Reference

Use this guide to look up window management, hotkeys, and coordinate operations when using desktop automation tools.

---

## 1. Keyboard Shortcuts & Hotkeys
Use these shortcuts to perform system-level window management via the `ui_hotkey` tool.

| Action | Shortcut (Keys) | Description |
| :--- | :--- | :--- |
| **Show Desktop** | `win`, `d` | Toggles showing/hiding all open windows. |
| **Task Manager** | `ctrl`, `shift`, `esc` | Launches Windows Task Manager. |
| **Switch Windows** | `alt`, `tab` | Focuses the previously active window. |
| **Virtual Desktop Left** | `win`, `ctrl`, `left` | Switches to the virtual desktop on the left. |
| **Virtual Desktop Right**| `win`, `ctrl`, `right` | Switches to the virtual desktop on the right. |
| **New Virtual Desktop**  | `win`, `ctrl`, `d` | Creates a new virtual desktop. |
| **Close Virtual Desktop**| `win`, `ctrl`, `f4` | Closes the current virtual desktop. |
| **Snap Window Left**     | `win`, `left` | Snaps the active window to the left side. |
| **Snap Window Right**    | `win`, `right` | Snaps the active window to the right side. |

---

## 2. Desktop Coordinates & Scaling
Windows coordinates are represented by primary monitor pixels (0,0 is the top-left).
* **DPI Scaling**: Playwright and coordinate clicks are DPI-dependent.
* **Get Position**: Call `ui_get_mouse_position` to check where the cursor is currently located before calculating offsets.

---

## 3. Window Management (via Bridge / User32)
* **Focusing a Window**: Call `ui_focus_window(title="...")` to bring a window to the foreground before typing or clicking.
* **Typing Text**: Call `ui_type_text(text="...")` to simulate keyboard entry into the focused input field.
