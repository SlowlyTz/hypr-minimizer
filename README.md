# hypr-minimizer

A workspace-aware LIFO window minimizer for [Hyprland](https://hyprland.org/).

Stashes windows into a hidden scratchpad (`special:minimized`) and restores them in last-in-first-out order, scoped per workspace. Comes with undo, a picker with app icons for [Omarchy](https://omarchy.org/) (with a dmenu fallback elsewhere), and automatic cleanup of stale entries.

## Features

- **Per-workspace LIFO stacks** — minimized windows on workspace 2 are never touched when you're on workspace 3
- **Undo** (up to 5 steps) — revert stash, pop, or restore operations per workspace
- **Stash others** — minimize all windows on the current workspace except the active one
- **Picker** — browse minimized windows with app icons; `Enter` restores a window to its own workspace, `Shift+Enter` brings it to the one you're on
- **Monitor page** (optional) — with an external monitor and a [monitor manager](#monitor-page) installed, `→` in the picker switches to choosing which screen keeps a single desktop
- **Peek** — `-` in the picker slides a window in from the bottom, full-size over the current workspace without touching its layout; `SUPER + M` slides it out again, and leaving the workspace minimizes it too
- **Readable names** — resolves app names and icons from desktop files, including Brave/Chromium web apps (e.g. "Notion" instead of `brave-<appid>-Default`)
- **Self-healing state** — windows that were closed, or pulled out of the scratchpad by other means, are dropped automatically
- **Zero Python dependencies** — uses only the standard library

## Requirements

- **Hyprland** with `hyprctl` in `$PATH` (both the 0.56+ Lua dispatchers and the older string dispatchers work)
- **Python 3.10+**
- For the `menu` command, one of:
  - [Omarchy](https://omarchy.org/) 4 with the bundled picker plugin (recommended — app icons and `Shift+Enter`)
  - `omarchy-menu-select`, [walker](https://github.com/abenz1267/walker), [wofi](https://hg.sr.ht/~scoopta/wofi) or [rofi](https://github.com/davatorium/rofi) as a plain-text fallback
- Optional: `notify-send` (libnotify) for notifications

## Installation

### From source

```bash
git clone https://github.com/SlowlyTz/hypr-minimizer.git
cd hypr-minimizer
pip install .
```

This installs the `hypr-minimizer` command.

### Without installing

Put a small wrapper on your `$PATH`, e.g. `~/.local/bin/hypr-minimizer`:

```sh
#!/bin/sh
exec python3 "$HOME/path/to/hypr-minimizer/minimizer.py" "$@"
```

### Omarchy picker plugin

The picker lives in [`omarchy-plugin/`](omarchy-plugin/) as an `omarchy-shell` overlay plugin. Link it into your plugin directory, then enable it:

```bash
ln -s "$PWD/omarchy-plugin" ~/.config/omarchy/plugins/hypr-minimizer.picker
omarchy-shell shell rescanPlugins
omarchy plugin enable hypr-minimizer.picker
```

`hypr-minimizer menu` uses the plugin whenever it is enabled and falls back to the plain menus otherwise. After editing the plugin's QML, run `omarchy-restart-shell`: the shell caches components it has already loaded.

## Usage

### Commands

| Command | Description |
|---|---|
| `stash` | Minimize (hide) the currently focused window |
| `stash_others` | Minimize all windows on the current workspace except the active one |
| `pop` | Restore the most recently minimized window of this workspace (LIFO) |
| `pop_all` | Restore all minimized windows of this workspace |
| `undo` | Undo the last stash/pop/restore on this workspace |
| `menu` | Pick a minimized window to restore |
| `restore <address>` | Restore a window by address (e.g. `0xabc123`) to its original workspace |
| `restore <address> --here` | Restore a window by address onto the current workspace |
| `peek <address>` | Show a minimized window full-size over the current workspace until it is minimized again |
| `list` | Print all minimized windows |
| `list --json` | Print all minimized windows as JSON |
| `clear-missing` | Drop entries for windows that are gone or no longer minimized |

### Picker keys

| Key | Action |
|---|---|
| `Enter` | Restore the window to the workspace it was minimized from |
| `Shift+Enter` | Bring the window to the current workspace |
| `-` | Peek: show the window full-size over the current workspace |
| `→` / `←` | Switch between the window list and the [monitor page](#monitor-page) |
| `↑` `↓` / `Tab` | Move the selection |
| Typing | Filter by app name or window title |
| `Esc` | Clear the filter, then close |

A window brought to another workspace belongs there afterwards: `undo` on that workspace minimizes it again. The plain-text fallback menus only support `Enter`.

The picker is keyboard only: the mouse does not hover or click inside it (so a resting pointer cannot steal the selection while you type), and clicking outside closes it. Typing always selects the first match.

A peeked window floats above the tiled windows in the same box a lone tiled window would fill (bar, `gaps_out` and border stay free), so the layout underneath does not change. On Hyprland 0.56+ it slides in from below the screen edge and slides back out when minimized with `SUPER + M`, using Hyprland's own window-move animation (`windowsMove`, inherited from `windows`). A window that was already floating gets its old position and size back afterwards. It is minimized again, back into its old place in the list, when you press `SUPER + M` (`stash`), switch to another workspace, or run any other minimizer command. A small `hypr-minimizer watch-peek` process listens to Hyprland's event socket while a peek is open and exits with it. Moving a peeked window to another workspace by hand keeps it there.

### Monitor page

The picker can host a second page for setups where, with an external monitor attached, one screen keeps a single fixed workspace and the other one holds the desktops. The minimizer does not manage monitors itself; it talks to an executable named `hypr-workspace` on `$PATH` (the page stays hidden without one, or without an external monitor):

| Call | Expected behavior |
|---|---|
| `hypr-workspace status` | Print JSON: `{"panel": "eDP-1", "external": "HDMI-A-1", "description": "...", "fixed": "panel"}`, with `"external": null` when no external monitor is attached |
| `hypr-workspace fixed panel\|external` | Make that screen the one with a single desktop |

With the page available, `hypr-minimizer menu` opens the picker even when nothing is minimized.

## Keybindings

### Omarchy (`~/.config/hypr/bindings.lua`)

```lua
o.bind("SUPER + M", "Minimize active window", "hypr-minimizer stash")
o.bind("SUPER + RETURN", "Minimize other windows", "hypr-minimizer stash_others")
o.bind("SUPER + I", "Restore last minimized window", "hypr-minimizer pop")
o.bind("SUPER + SHIFT + I", "Restore all minimized windows", "hypr-minimizer pop_all")
o.bind("SUPER + U", "Undo last minimize/restore", "hypr-minimizer undo")
o.bind("SUPER + PERIOD", "Pick minimized window", "hypr-minimizer menu")
```

Omarchy opens the terminal on `SUPER + RETURN`; release it first with `hl.unbind("SUPER + RETURN")`, or pick another key.

### Plain Hyprland (`hyprland.conf`)

```ini
bindd = SUPER, M, Minimize active window, exec, hypr-minimizer stash
bindd = SUPER, RETURN, Minimize other windows, exec, hypr-minimizer stash_others
bindd = SUPER, I, Restore last minimized window, exec, hypr-minimizer pop
bindd = SUPER SHIFT, I, Restore all minimized windows, exec, hypr-minimizer pop_all
bindd = SUPER, U, Undo last minimize/restore, exec, hypr-minimizer undo
bindd = SUPER, PERIOD, Pick minimized window, exec, hypr-minimizer menu
```

## Bar counter

Show how many windows are minimized, e.g. `-3`, hidden when there are none.

**omarchy-shell** — a bar widget can read the count straight from Hyprland, without polling. Clone the workspaces widget with `omarchy plugin clone omarchy.workspaces` and add this inside it (the new button goes into the widget's `GridLayout`, whose `columns` needs one more slot while the counter is visible):

```qml
readonly property int minimizedCount: {
  var values = Hyprland.workspaces.values
  for (var i = 0; i < values.length; i++) {
    if (String(values[i].name || "") === "special:minimized") return values[i].toplevels.values.length
  }
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

**Waybar** — a polling custom module:

```jsonc
"custom/minimized": {
  "exec": "n=$(hypr-minimizer list --json | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))'); [ \"$n\" -gt 0 ] && echo \"-$n\" || echo",
  "interval": 2,
  "on-click": "hypr-minimizer menu"
}
```

## State file

State (stacks and undo history) is stored as JSON at:

```
$XDG_RUNTIME_DIR/hypr-minimizer/state.json
```

(typically `/run/user/1000/hypr-minimizer/state.json`). If `XDG_RUNTIME_DIR` is unset, it falls back to `$XDG_STATE_HOME/hypr-minimizer/state.json`, then `~/.local/state/hypr-minimizer/state.json`. Legacy state at `/tmp/hypr_minimizer_state.json` is read once as a migration fallback.

## Development

```bash
git clone https://github.com/SlowlyTz/hypr-minimizer.git
cd hypr-minimizer
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest test_minimizer.py -v
```

The tests mock `hyprctl` and pin the classic string dispatchers; the Lua path has its own test.

## License

MIT — see [LICENSE](LICENSE) for details.
