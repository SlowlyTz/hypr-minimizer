# Hypr Minimizer

A small Python minimizer for Hyprland.

It stores minimized windows in a per-workspace LIFO stack. When you stash a
window, it is moved to `special:minimized` and its address is saved under the
active workspace ID. When you pop, the most recently stashed live window for the
current workspace is restored first.

Closed windows are pruned from the state when listing or restoring windows.

## Commands

```bash
python3 minimizer.py stash
python3 minimizer.py stash_others
python3 minimizer.py pop
python3 minimizer.py pop_all
python3 minimizer.py list
python3 minimizer.py list --json
python3 minimizer.py restore 0xabc
python3 minimizer.py clear-missing
python3 minimizer.py menu
```

`menu` opens a dmenu-style picker with `wofi` first, then `rofi`, then `walker`
as a fallback. Selecting an entry restores that window to its original
workspace. Brave web apps are resolved through their `.desktop` files, so the
menu shows names like `Notion` or `Discord` instead of `brave-...`.

## State

Runtime state is stored at:

```text
$XDG_RUNTIME_DIR/hypr-minimizer/state.json
```

If `XDG_RUNTIME_DIR` is not set, it falls back to:

```text
$XDG_STATE_HOME/hypr-minimizer/state.json
~/.local/state/hypr-minimizer/state.json
```

The old `/tmp/hypr_minimizer_state.json` path is still read as a legacy fallback
when the new state file does not exist.

## Hyprland Binds

Example:

```text
bindd = SUPER, RETURN, Minimize other windows, exec, python3 ~/Documents/dev/hypr-minimizer/minimizer.py stash_others
bindd = SUPER, M, Minimize active window, exec, python3 ~/Documents/dev/hypr-minimizer/minimizer.py stash
bindd = SUPER, I, Restore minimized window, exec, python3 ~/Documents/dev/hypr-minimizer/minimizer.py pop
bindd = SUPER, U, Undo last minimize/restore step, exec, python3 ~/Documents/dev/hypr-minimizer/minimizer.py undo
bindd = SUPER SHIFT, I, Restore all minimized windows, exec, python3 ~/Documents/dev/hypr-minimizer/minimizer.py pop_all
bindd = SUPER SHIFT, M, Pick minimized window, exec, python3 ~/Documents/dev/hypr-minimizer/minimizer.py menu
```

## Test

```bash
.venv/bin/python -m pytest test_minimizer.py
```
