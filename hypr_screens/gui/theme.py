"""Omarchy look for the settings window: colors, font and corners of the menu.

Reads the active Omarchy theme ($XDG_STATE_HOME/omarchy/current/theme) and
turns it into GTK CSS that recolors libadwaita through its named colors.
Falls back to a neutral dark palette without Omarchy.
"""
import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

FALLBACK = {
    "background": "#1e1e2e",
    "foreground": "#cdd6f4",
    "accent": "#89b4fa",
    "selection": "#45475a",
    "lighter_background": "#313244",
    "dark_foreground": "#6c7086",
    "red": "#f38ba8",
    "green": "#a6e3a1",
}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def theme_dir() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "omarchy" / "current" / "theme"


def read_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def palette(directory: Path | None = None) -> dict:
    """Theme colors; the [menu] section of shell.toml wins where it has plain hex values."""
    directory = directory or theme_dir()
    colors = dict(FALLBACK)
    colors.update({k: v for k, v in read_toml(directory / "colors.toml").items() if isinstance(v, str) and HEX.match(v)})
    colors["mode"] = read_toml(directory / "colors.toml").get("mode", "dark")
    menu = read_toml(directory / "shell.toml").get("menu", {})
    colors["menu_background"] = menu.get("background") if HEX.match(str(menu.get("background", ""))) else colors["background"]
    colors["menu_text"] = menu.get("text") if HEX.match(str(menu.get("text", ""))) else colors["foreground"]
    return colors


def rounding() -> int:
    try:
        option = json.loads(subprocess.run(
            ["hyprctl", "-j", "getoption", "decoration:rounding"], capture_output=True, text=True, check=False
        ).stdout)
        return int(option.get("int", 0))
    except (ValueError, json.JSONDecodeError, AttributeError):
        return 0


def font() -> str:
    try:
        family = subprocess.run(
            ["fc-match", "-f", "%{family[0]}", "monospace"], capture_output=True, text=True, check=False
        ).stdout.strip()
    except OSError:
        family = ""
    return family or "monospace"


def css(colors: dict, radius: int = 0, family: str = "monospace") -> str:
    bg = colors["menu_background"]
    fg = colors["menu_text"]
    accent = colors["accent"]
    raised = colors["lighter_background"]
    muted = colors["dark_foreground"]
    return f"""
@define-color window_bg_color {bg};
@define-color window_fg_color {fg};
@define-color view_bg_color {bg};
@define-color view_fg_color {fg};
@define-color headerbar_bg_color {bg};
@define-color headerbar_fg_color {fg};
@define-color sidebar_bg_color {bg};
@define-color sidebar_fg_color {fg};
@define-color card_bg_color {raised};
@define-color card_fg_color {fg};
@define-color dialog_bg_color {bg};
@define-color dialog_fg_color {fg};
@define-color popover_bg_color {raised};
@define-color popover_fg_color {fg};
@define-color accent_bg_color {accent};
@define-color accent_fg_color {bg};
@define-color accent_color {accent};
@define-color destructive_bg_color {colors["red"]};
@define-color destructive_color {colors["red"]};
@define-color success_color {colors["green"]};

window, dialog, popover, .card, button, entry, row, list, .navigation-sidebar {{
  font-family: "{family}";
}}
.card, list.boxed-list, button, popover > contents, dialog .dialog-contents {{
  border-radius: {radius}px;
}}
list.boxed-list {{ border: 1px solid alpha({fg}, 0.15); }}
.navigation-sidebar row {{ border-radius: {radius}px; padding: 10px 12px; }}
.navigation-sidebar row:selected {{ background: alpha({fg}, 0.08); color: {accent}; }}
.page-title {{ font-size: 1.4em; font-weight: bold; }}
.hint {{ color: {muted}; }}
.page-footer {{ padding: 2px 0; }}
.sidebar-section {{ font-size: 0.8em; font-weight: bold; color: {muted}; padding: 16px 14px 4px 14px; }}
.sidebar-separator {{ margin: 10px 12px; background: alpha({fg}, 0.1); }}
.result-path {{ font-size: 0.82em; }}
.search-results row {{ padding: 8px 12px; }}
.search-hit {{ background: alpha({accent}, 0.18); box-shadow: inset 0 0 0 2px alpha({accent}, 0.7);
              transition: background 300ms, box-shadow 300ms; }}
.status-on {{ color: {colors["green"]}; }}
.status-off {{ color: {muted}; }}
.keycap {{ padding: 4px 10px; min-width: 150px; }}
.capture {{ font-size: 1.3em; padding: 18px; }}
"""
