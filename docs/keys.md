# Keys

Every action has **two** key slots.

## Change a key in the menu

1. `SUPER + SHIFT + .` → `Tab` (Keys & options)
2. `↑↓` pick the action, `←→` pick slot 1 or 2
3. `Enter`, then press the new combination
4. `Esc` cancels, `Del` clears a slot

While you press the new keys, Hyprland's own shortcuts are paused, so even taken combinations get recorded. If the key is taken by something else, the menu says what it replaces.

## Change a key in the terminal

```bash
hypr-screens bind screens_menu 1 "SUPER + SHIFT + PERIOD"
hypr-screens bind minimizer_menu 2 "SUPER + SHIFT + F23"   # Copilot key
hypr-screens bind stash_others 1 ""                         # clear
```

Actions: `minimizer_menu` `screens_menu` `stash` `stash_others` `pop` `pop_all` `undo`

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
