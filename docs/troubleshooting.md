# Troubleshooting

## Settings are not applied after plugging in

```bash
pgrep -af "hypr-screens watch" || (hypr-screens watch &)   # watcher running?
hypr-screens apply
```

Watcher log: run it in a terminal to see what it does:

```bash
pkill -f "hypr-screens watch"; hypr-screens watch
```

## A key does nothing / fires twice

```bash
grep -n hypr_screens ~/.config/hypr/hyprland.lua   # must show the require line
hyprctl configerrors
hypr-screens setup                                  # rewrites the Lua file
```

## A menu opens with the old look / a new key in the menu does nothing

The shell caches the menus:

```bash
omarchy-restart-shell
```

## Desktops end up on the wrong screen

```bash
hypr-screens status
hypr-screens apply
```

Forget a swap: unplug and plug in again, or

```bash
rm "$XDG_RUNTIME_DIR/hypr-screens/fixed.json" && hypr-screens apply
```

## Stuck in "press the new shortcut"

Press `Esc`. Still stuck:

```bash
hyprctl dispatch 'hl.dsp.submap("reset")'
```

## A peeked window does not go away

```bash
hypr-minimizer stash   # or SUPER + M on it
```

## Start over

```bash
cp ~/.config/hypr-screens/config.json ~/hypr-screens-config.backup.json
rm ~/.config/hypr-screens/config.json && hypr-screens setup
```
