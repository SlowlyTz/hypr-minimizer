# Keys

Only **window keys** live on the keyboard (minimize, restore, window list, desktops). Everything else is in the settings window (tray icon). Every action has **two** key slots.

## Change a key in the window

1. Tray icon → **Tasten**
2. Click the key you want to change
3. Press the new combination (`Backspace` = remove the key, `Esc` = cancel)
4. If the key is already used by something else, the window tells you what and asks before replacing it.

While you press the new keys, Hyprland's own shortcuts are paused, so even taken combinations get recorded.

## Change a key in the terminal

```bash
hypr-screens bind minimizer_menu 1 "SUPER + PERIOD"
hypr-screens bind minimizer_menu 2 "SUPER + SHIFT + F23"   # Copilot key
hypr-screens bind stash_others 1 ""                         # clear
```

Actions: `minimizer_menu` `stash` `stash_others` `pop` `pop_all` `undo`

```bash
hypr-screens option desktop_keys on    # SUPER + 1…0, SUPER + TAB (see one-desktop.md)
```

## Where they live

- `~/.config/hypr/hypr_screens.lua` is **generated**. Don't edit it; change keys as above.
- It unbinds whatever else sits on your keys first, so nothing fires twice.
- New keys work immediately. A key you gave up gets its old meaning back after the next `hyprctl reload`.

## See what is bound

```bash
hyprctl binds -j | jq -r '.[] | "\(.modmask) \(.key) \(.keycode) \(.description)"' | sort
```
