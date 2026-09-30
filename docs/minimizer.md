# Minimizer

Hides windows in a hidden workspace (`special:minimized`) and brings them back, last in first out, **per desktop**.

## Commands

```bash
hypr-minimizer stash          # minimize the active window
hypr-minimizer stash_others   # minimize everything else on this desktop
hypr-minimizer pop            # bring back the last one (this desktop)
hypr-minimizer pop_all        # bring back all (this desktop)
hypr-minimizer undo           # undo last stash/pop/restore (5 steps)
hypr-minimizer menu           # window menu
hypr-minimizer list           # print minimized windows (--json)
hypr-minimizer restore 0xabc  # restore by address (--here: onto this desktop)
hypr-minimizer peek 0xabc     # peek by address
```

## Window menu

Keyboard only (the mouse does nothing inside it; clicking outside closes it).

| Key | Does |
|---|---|
| `Enter` | bring it to this desktop |
| `Shift+Enter` | back to the desktop it was minimized on |
| `-` | **peek** |
| typing | filter; the first match is always selected |
| `Esc` | clear filter, then close |

## Peek

- The window slides in from the bottom, over everything, in the space a single tiled window would take (bar and gaps stay free).
- Your tiled windows underneath don't move.
- `SUPER + M` slides it out again. Switching desktop hides it too.
- It goes back to its old place in the list.

## Scratchpad

While the scratchpad (`SUPER + S`) is open, it counts as the current desktop: `SUPER + M` there minimizes into its own list, `SUPER + I` puts the window back into the scratchpad, and `Enter` in the window menu brings any window into it. Opened from a desktop, `Enter` brings a scratchpad window to that desktop; `Shift+Enter` sends it back to the scratchpad. If minimizing empties the scratchpad, Hyprland closes it — open it again with `SUPER + S` and press `SUPER + I`. The menu shows these windows as `ws scratchpad`.

## Apps that ask to be shown

Starting an app again from the launcher (`SUPER + SPACE`) when it already runs brings its window **to this desktop** — also when it is minimized or on another desktop. Hyprland would otherwise switch to its desktop, or open `special:minimized` and show every minimized window. Same for notifications and links that bring an app forward. Set up by `~/.config/hypr/hypr_screens.lua`.

## Bar counter (optional)

Shows `-3` when 3 windows are minimized.

**Omarchy bar**: add this to a workspaces widget (e.g. `omarchy-workspaces/Workspaces.qml`), inside its `GridLayout` (give `columns` one more slot while it is visible):

```qml
readonly property int minimizedCount: {
  var values = Hyprland.workspaces.values
  for (var i = 0; i < values.length; i++)
    if (String(values[i].name || "") === "special:minimized") return values[i].toplevels.values.length
  return 0
}

WidgetButton {
  visible: root.minimizedCount > 0
  bar: root.bar
  text: "-" + root.minimizedCount
  opacity: 0.5
  horizontalMargin: 4
  fixedHeight: root.barSize
  onPressed: function() { if (root.bar) root.bar.run("hypr-minimizer menu") }
}
```

**Waybar**:

```jsonc
"custom/minimized": {
  "exec": "n=$(hypr-minimizer list --json | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))'); [ \"$n\" -gt 0 ] && echo \"-$n\" || echo",
  "interval": 2,
  "on-click": "hypr-minimizer menu"
}
```

## Where things live

| What | Where |
|---|---|
| minimized windows + undo | `$XDG_RUNTIME_DIR/hypr-minimizer/state.json` |
| menu plugin | `omarchy-plugin/` → `~/.config/omarchy/plugins/hypr-minimizer.picker` |

Without Omarchy the menu falls back to `walker`, `wofi` or `rofi` (only `Enter`: brings it here).
