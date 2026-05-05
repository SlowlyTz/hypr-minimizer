# hypr-minimizer

A workspace-aware LIFO window minimizer for [Hyprland](https://hyprland.org/).

Stashes windows into a hidden scratchpad (`special:minimized`) and restores them in last-in-first-out order, scoped per workspace. Includes undo support, a dmenu-style picker, and automatic pruning of closed windows.

## Features

- **Per-workspace LIFO stacks** — minimized windows on workspace 2 are never touched when you're on workspace 3
- **Undo** (up to 5 steps) — revert stash, pop, or restore operations per workspace
- **Stash others** — minimize all windows on the current workspace except the active one
- **Menu picker** — browse and restore minimized windows via `walker`, `wofi`, or `rofi`
- **Brave PWA name resolution** — shows human-readable names (e.g. "Notion") instead of `brave-<appid>-Default`
- **Automatic pruning** — closed windows are detected and removed from state automatically
- **Zero Python dependencies** — uses only the standard library

## Requirements

- **Hyprland** (with `hyprctl` available in `$PATH`)
- **Python 3.10+**
- Optional, for the `menu` command:
  - [walker](https://github.com/abenz1267/walker) (preferred)
  - [wofi](https://hg.sr.ht/~scoopta/wofi)
  - [rofi](https://github.com/davatorium/rofi)
- Optional, for notifications: `notify-send` (libnotify)

## Installation

### From source

```bash
git clone https://github.com/GhostTz/hypr-workspace-manager.git
cd hypr-workspace-manager
pip install .
```

This installs the `hypr-minimizer` command system-wide.

### Manual (no install)

```bash
git clone https://github.com/GhostTz/hypr-workspace-manager.git
# Run directly with Python:
python3 ~/path/to/hypr-workspace-manager/minimizer.py stash
```

### Arch Linux (AUR)

Not yet available. Contributions welcome.

## Usage

```bash
# Install via pip:
hypr-minimizer stash

# Or run directly:
python3 minimizer.py stash
```

### Commands

| Command | Description |
|---|---|
| `stash` | Minimize (hide) the currently focused window |
| `stash_others` | Minimize all windows on the current workspace except the active one |
| `pop` | Restore the most recently minimized window (LIFO) |
| `pop_all` | Restore all minimized windows on the current workspace |
| `undo` | Undo the last stash/pop/restore operation on this workspace |
| `restore <address>` | Restore a specific window by its address (e.g. `0xabc123`) |
| `list` | Print all minimized windows |
| `list --json` | Print all minimized windows as JSON |
| `clear-missing` | Remove references to windows that no longer exist |
| `menu` | Open a dmenu-style picker to select and restore a window |

## Hyprland Keybindings

Add these to your `~/.config/hypr/hyprland.conf`:

```ini
bindd = SUPER, RETURN, Minimize other windows, exec, hypr-minimizer stash_others
bindd = SUPER, M, Minimize active window, exec, hypr-minimizer stash
bindd = SUPER, I, Restore last minimized window, exec, hypr-minimizer pop
bindd = SUPER, U, Undo last minimize/restore, exec, hypr-minimizer undo
bindd = SUPER SHIFT, I, Restore all minimized windows, exec, hypr-minimizer pop_all
bindd = SUPER SHIFT, M, Pick minimized window, exec, hypr-minimizer menu
```

If you installed manually without pip, replace `hypr-minimizer` with the full path to `minimizer.py`.

## State File

Runtime state is stored in JSON format:

**Primary location:**
```
$XDG_RUNTIME_DIR/hypr-minimizer/state.json
```
(typically `/run/user/1000/hypr-minimizer/state.json`)

**Fallback chain** (if `XDG_RUNTIME_DIR` is unset):
1. `$XDG_STATE_HOME/hypr-minimizer/state.json`
2. `~/.local/state/hypr-minimizer/state.json`

Legacy state at `/tmp/hypr_minimizer_state.json` is read as a one-time migration fallback.

## Development

```bash
git clone https://github.com/GhostTz/hypr-workspace-manager.git
cd hypr-workspace-manager

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run tests
python -m pytest test_minimizer.py -v
```

## License

MIT — see [LICENSE](LICENSE) for details.
