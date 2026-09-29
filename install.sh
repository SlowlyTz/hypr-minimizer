#!/bin/sh
# Install hypr-minimizer + hypr-screens from this checkout, then run the setup wizard.
set -e
cd "$(dirname "$0")"
REPO=$(pwd)

command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
command -v hyprctl >/dev/null || { echo "Hyprland (hyprctl) is required"; exit 1; }
python3 -c 'import gi; gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")' 2>/dev/null ||
  echo "Note: the settings window needs GTK 4 + libadwaita + PyGObject (Arch: sudo pacman -S python-gobject libadwaita)"

mkdir -p "$HOME/.local/bin"
ln -sfn "$REPO/minimizer.py" "$HOME/.local/bin/hypr-minimizer"
ln -sfn "$REPO/hypr-screens" "$HOME/.local/bin/hypr-screens"
echo "Linked hypr-minimizer and hypr-screens into ~/.local/bin"
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) echo "Note: ~/.local/bin is not on your PATH yet" ;;
esac

exec "$REPO/hypr-screens" setup
