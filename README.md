# Hypr Minimizer

A small Python minimizer for Hyprland.

It stores minimized windows in a per-workspace LIFO stack. When you stash a window, its address is saved under the active workspace ID and the window is moved to `special:minimized`. When you pop, the most recently stashed window for the current workspace is restored first.

## Commands

```bash
python3 minimizer.py stash
python3 minimizer.py pop
python3 minimizer.py pop_all
```

## State

Runtime state is stored at:

```text
/tmp/hypr_minimizer_state.json
```

The state file maps workspace IDs to lists of Hyprland window addresses.

## Test

```bash
python3 -m pytest test_minimizer.py
```
