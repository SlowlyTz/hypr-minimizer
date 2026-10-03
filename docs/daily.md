# Daily cheat sheet

Default keys. Yours may differ: see them in the settings window (tray icon → Shortcuts) or with `hypr-screens state | jq .keybinds`.

## Windows

| Key | Does |
|---|---|
| `SUPER + M` | minimize this window |
| `SUPER + I` | bring back the last minimized one |
| `SUPER + SHIFT + I` | bring back all |
| `SUPER + U` | undo |
| `SUPER + .` | window menu |

In the window menu: `Enter` here · `Shift+Enter` back to its desktop · `-` peek · type to filter · `Esc` close.

## Screens

| Key | Does |
|---|---|
| tray icon (click) | settings window |
| tray icon (right-click) | swap the fixed screen, quit |
| `SUPER + Y` | move window to the other screen (Hyprland, not ours) |

## Desktops (if "one desktop" is on)

| Key | Does |
|---|---|
| `SUPER + 1…0` | show desktop 1–10 |
| `SUPER + SHIFT + 1…0` | move window there, follow |
| `SUPER + SHIFT + ALT + 1…0` | move window there, stay |
| `SUPER + TAB` / `+ SHIFT` | next / previous visible window |

## Commands

```bash
hypr-screens list                              # screens, ● connected, ★ favorite
hypr-screens set Laptop rotation 180           # set a value (unset = remove)
hypr-screens when Laptop rotation "HP 32f"     # only while HP 32f is connected
hypr-screens when Laptop rotation always
hypr-screens swap                              # swap the fixed screen until unplugged
hypr-screens settings                          # open the settings window
hypr-screens apply                             # apply everything now
hypr-minimizer list                            # minimized windows
```
