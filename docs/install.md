# Install

**Needs:** Hyprland ≥ 0.56 (Lua config), Python ≥ 3.10, GTK 4 + libadwaita + PyGObject (settings window).
**Nice to have:** Omarchy (window menu with icons, bar widget).

```bash
sudo pacman -S python-gobject libadwaita   # Arch, if missing
```

## 1. Get it and run the installer

```bash
git clone https://github.com/SlowlyTz/hypr-minimizer.git ~/hypr-minimizer
~/hypr-minimizer/install.sh
```

The installer:

1. links `hypr-minimizer` and `hypr-screens` into `~/.local/bin`
2. starts the **setup wizard**, which:
   - lets you pick the shortcuts (Enter = keep the suggestion)
   - asks if you want "one desktop" (see [one-desktop.md](one-desktop.md))
   - writes `~/.config/hypr/hypr_screens.lua`
   - adds **one line** to `~/.config/hypr/hyprland.lua` (asks first):
     ```lua
     require("hypr.hypr_screens")
     ```
   - sets up the Omarchy window menu and, if you want, the bar widget
   - starts the background watcher and the **tray icon** (both also start with Hyprland from then on)

No monitor settings in the wizard. Those come later, in the settings window (tray icon).

## 2. Check it

```bash
hypr-screens list          # your screens
hyprctl configerrors       # should print nothing
pgrep -af "hypr-screens (watch|tray)"
```

## Run the wizard again

```bash
hypr-screens setup
```

It also starts by itself the first time you run either command in a terminal.

## Uninstall

```bash
sed -i '/hypr.hypr_screens/d' ~/.config/hypr/hyprland.lua
rm ~/.config/hypr/hypr_screens.lua ~/.local/bin/hypr-minimizer ~/.local/bin/hypr-screens
rm -r ~/.config/hypr-screens
omarchy plugin disable hypr-minimizer.picker
hyprctl reload
```

Bar widget back to stock (the installer kept a backup):

```bash
sed -i 's/"hypr-screens.workspaces"/"omarchy.workspaces"/' ~/.config/omarchy/shell.json
# or: cp ~/.config/omarchy/shell.json.bak-hypr-screens ~/.config/omarchy/shell.json
```
