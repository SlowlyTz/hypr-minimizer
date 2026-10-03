"""Desktop widgets (Personalization → Widgets): visualizer, lyrics, clock and
system, drawn by the Omarchy shell plugin in omarchy-widgets/
(hypr-screens.widgets) on a layer behind the windows; the visualizer can also
sit in the bar, right of the desktops.

The settings live in config["widgets"]. export() writes what the plugin reads:
~/.config/hypr-screens/widgets.json (it watches that file) and the cava config
for the visualizer. Placement is a point on the screen as a fraction of its
size plus a rotation, the same on every chosen monitor; the size is set by
pulling the edges and corners while arranging ("width" 0: from the size).
"""
import json
import re
import shutil
import subprocess
from pathlib import Path

from hypr_screens import config, i18n, install
from hypr_screens.i18n import t
from hypr_screens.root import run_as_root

PLUGIN = "hypr-screens.widgets"
WORKSPACES_IDS = ("hypr-screens.workspaces", "omarchy.workspaces")
KINDS = ["visualizer", "lyrics", "clock", "system"]
WHERE = ["bar", "desktop", "both"]
MONITOR_MODES = ["laptop", "external", "all", "screen"]
# Accent colors: the theme's accent or text color, or white; the visualizer
# can also use a gradient of the accent.
COLORS = ["accent", "gradient", "foreground", "white"]
TEXT_COLORS = ["accent", "foreground", "white"]
# The theme's colors a part can take (from colors.toml, so they follow a theme
# change); "accent" alone is the widget's own accent color (above).
THEME_COLORS = ["accent", "foreground", "muted", "background", "red", "orange", "yellow", "green", "cyan",
                "blue", "magenta"]
COLOR_VALUE = re.compile(r"^(accent|theme:(" + "|".join(THEME_COLORS) + r")|#[0-9a-f]{6}([0-9a-f]{2})?)$")
# Every widget's font, effect and background card. font_family "": the
# Omarchy font. The effect: an outline on the text, a shadow or a glow
# around everything, or none.
STYLE = {"font_family": "", "font_weight": "bold", "letter_spacing": 0, "effect": "outline", "effect_strength": 35,
         "card": False, "card_radius": 16, "card_padding": 16, "card_opacity": 45, "card_blur": False, "colors": {}}
# When a widget shows: on these desktops only ([]: all; 1-10, FIXED_DESKTOP:
# the fixed screen), only while its desktop has no window, not on battery;
# above the windows instead of behind them.
FIXED_DESKTOP = 99
VISIBILITY = {"desktops": [], "only_empty": False, "hide_on_battery": False, "above": False}
# One place on every screen, or (same_place off) a place per screen id in
# "spots"; a screen without one uses the widget's own place.
PLACES = {"same_place": True, "spots": {}}
FONT_WEIGHTS = ["light", "regular", "medium", "bold", "black"]
EFFECTS = ["outline", "shadow", "glow", "none"]
# Each widget's parts that have a color, in groups: (group title, [(part,
# title, default)]). Defaults: "accent", "theme:<name>", "#rrggbbaa", or
# "auto" (worked out by the widget, e.g. the effect's color by its kind).
LOOK_PARTS = ("Card and effect", [("card", "Card", "theme:background"), ("effect", "Effect", "auto")])
PARTS = {
    "visualizer": [("Bars", [("bars", "Bars", "accent"), ("bars_end", "Bar tips", "auto")])],
    "lyrics": [("Lines", [("current", "Line being sung", "accent"), ("sung", "Words already sung", "accent"),
                          ("waiting", "Words still to sing", "theme:foreground"),
                          ("upcoming", "Coming lines", "theme:foreground"), ("past", "Lines sung", "theme:foreground")])],
    "clock": [("Time", [("hours", "Hours", "theme:foreground"), ("colon", "Colon", "theme:foreground"),
                        ("minutes", "Minutes", "theme:foreground"), ("seconds", "Seconds", "theme:foreground"),
                        ("ampm", "AM/PM", "theme:foreground")]),
              ("Date", [("weekday", "Weekday", "accent"), ("date", "Date", "accent")])],
    "system": [(group, [(f"{gauge}_label", "Label", "theme:foreground"), (f"{gauge}_value", "Value", "accent"),
                        (f"{gauge}_line", "Curve", "accent"), (f"{gauge}_fill", "Area under the curve", "auto")])
               for gauge, group in (("cpu", "CPU usage"), ("memory", "Memory"), ("temperature", "Temperature"))],
}
# Where a widget first appears: the middle, so it can be dragged from there.
CENTER = {"x": 0.5, "y": 0.5, "rotation": 0}
ALL_SCREENS = {"mode": "all", "screen": ""}
BASE = {
    "visualizer": {"enabled": False, "where": "both", "monitors": ALL_SCREENS, "bars": 32, "style": "bottom",
                   "color": "accent", "opacity": 100, "size": 160, "width": 0, "placed": False, **CENTER},
    "lyrics": {"enabled": False, "monitors": ALL_SCREENS, "highlight": "line", "align": "center", "lines": 3,
               "hide_paused": False, "color": "accent", "opacity": 100, "size": 200, "width": 0,
               "placed": False, **CENTER},
    "clock": {"enabled": False, "monitors": ALL_SCREENS, "hours": "24", "date": True, "seconds": False,
              "color": "accent", "opacity": 100, "size": 100, "placed": False, **CENTER},
    "system": {"enabled": False, "monitors": ALL_SCREENS, "cpu": True, "memory": True, "temperature": True,
               "curves": True, "color": "accent", "opacity": 100, "size": 100, "width": 0,
               "placed": False, **CENTER},
}
DEFAULTS = {kind: {**base, **STYLE, **VISIBILITY, **PLACES} for kind, base in BASE.items()}
# The values a setting can take; the first-listed default is in DEFAULTS.
STYLE_CHOICES = {"font_weight": FONT_WEIGHTS, "effect": EFFECTS}
CHOICES = {
    "visualizer": {"where": WHERE, "style": ["bottom", "mirrored"], "color": COLORS, **STYLE_CHOICES},
    # line: the line being sung in the accent color, word: each word as it is
    # sung, off: no color, only the size sets it apart.
    "lyrics": {"highlight": ["line", "word", "off"], "align": ["center", "left", "right"], "color": TEXT_COLORS,
               **STYLE_CHOICES},
    "clock": {"hours": ["24", "12"], "color": TEXT_COLORS, **STYLE_CHOICES},
    "system": {"color": TEXT_COLORS, **STYLE_CHOICES},
}
TITLES = {"visualizer": "Visualizer", "lyrics": "Lyrics", "clock": "Clock", "system": "System"}
LOCALES = {"en": "en_US", "de": "de_DE", "es": "es_ES", "fr": "fr_FR", "it": "it_IT"}
# key: (minimum, maximum)
RANGES = {"bars": (8, 64), "lines": (1, 10), "opacity": (20, 100), "rotation": (-360, 360),
          "letter_spacing": (-2, 20), "effect_strength": (0, 100), "card_radius": (0, 60), "card_padding": (0, 80),
          "card_opacity": (5, 100)}
# The visualizer's and the lyrics' size is their height in pixels (the lyrics'
# font fills it), the others' a scale in percent.
SIZE_RANGES = {"visualizer": (30, 600), "lyrics": (40, 1200), "clock": (30, 400), "system": (50, 300)}
# Width in pixels for the widgets that can be made wider on their own.
WIDTH_RANGES = {"visualizer": (60, 2000), "lyrics": (200, 2400), "system": (150, 1200)}
# What arranging may change.
PLACEMENT_KEYS = ("x", "y", "rotation", "size", "width", "colors", "spots")
SPOT_KEYS = ("x", "y", "rotation", "size", "width")
MAX_SPOTS = 20
MAX_LAYOUTS = 30


def settings_file() -> Path:
    return config.config_file().parent / "widgets.json"


def cava_file() -> Path:
    return config.config_file().parent / "cava.conf"


def number(value: object, low: float, high: float, fallback: float, whole: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    value = max(low, min(high, value))
    return int(round(value)) if whole else round(float(value), 4)


def part_defaults(kind: str) -> dict[str, str]:
    return {part: default for _group, parts in [*PARTS[kind], LOOK_PARTS] for part, _title, default in parts}


def clean_colors(kind: str, raw: object) -> dict[str, str]:
    """Only known parts with a valid color ("accent", "theme:<name>", "#rrggbb[aa]")."""
    known = part_defaults(kind)
    colors = {}
    for part, value in (raw.items() if isinstance(raw, dict) else []):
        value = str(value).lower()
        if part in known and COLOR_VALUE.match(value):
            colors[part] = value
    return colors


def clean_spot(kind: str, raw: dict, base: dict) -> dict:
    """A place on one screen; what it lacks comes from the widget's own place."""
    spot = {"x": number(raw.get("x"), 0.0, 1.0, base["x"], whole=False),
            "y": number(raw.get("y"), 0.0, 1.0, base["y"], whole=False),
            "rotation": number(raw.get("rotation"), *RANGES["rotation"], base["rotation"]),
            "size": number(raw.get("size"), *SIZE_RANGES[kind], base["size"])}
    if kind in WIDTH_RANGES:
        width = raw.get("width", base.get("width", 0))
        spot["width"] = (number(width, *WIDTH_RANGES[kind], 0)
                         if isinstance(width, (int, float)) and not isinstance(width, bool) and width > 0 else 0)
    return spot


def normalize(raw: object) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    widgets = {}
    for kind, defaults in DEFAULTS.items():
        given = raw.get(kind) if isinstance(raw.get(kind), dict) else {}
        widget = json.loads(json.dumps(defaults))
        for key, default in defaults.items():
            if key in CHOICES[kind]:
                widget[key] = given[key] if given.get(key) in CHOICES[kind][key] else default
            elif isinstance(default, bool):
                widget[key] = bool(given.get(key, default))
            elif key in RANGES:
                widget[key] = number(given.get(key), *RANGES[key], default)
        widget["font_family"] = str(given.get("font_family") or "")[:100]
        desktops = given.get("desktops") if isinstance(given.get("desktops"), list) else []
        widget["desktops"] = sorted({d for d in desktops if isinstance(d, int) and not isinstance(d, bool)
                                     and (1 <= d <= 10 or d == FIXED_DESKTOP)})
        widget["colors"] = clean_colors(kind, given.get("colors"))
        monitors = given.get("monitors") if isinstance(given.get("monitors"), dict) else {}
        if monitors.get("mode") in MONITOR_MODES:
            widget["monitors"] = {"mode": monitors["mode"], "screen": str(monitors.get("screen") or "")}
        widget["size"] = number(given.get("size"), *SIZE_RANGES[kind], defaults["size"])
        if kind in WIDTH_RANGES:
            width = given.get("width")
            widget["width"] = (number(width, *WIDTH_RANGES[kind], 0)
                               if isinstance(width, (int, float)) and not isinstance(width, bool) and width > 0
                               else 0)
        widget["x"] = number(given.get("x"), 0.0, 1.0, defaults["x"], whole=False)
        widget["y"] = number(given.get("y"), 0.0, 1.0, defaults["y"], whole=False)
        spots = given.get("spots") if isinstance(given.get("spots"), dict) else {}
        widget["spots"] = {str(sid)[:200]: clean_spot(kind, spot, widget) for sid, spot in list(spots.items())[:MAX_SPOTS]
                           if isinstance(spot, dict)}
        widgets[kind] = widget
    return widgets


def on_desktop(widget: dict, kind: str) -> bool:
    return widget["enabled"] and (kind != "visualizer" or widget["where"] in ("desktop", "both"))


def in_bar(widgets: dict) -> bool:
    visualizer = widgets["visualizer"]
    return visualizer["enabled"] and visualizer["where"] in ("bar", "both")


def cpu_temperature_file() -> str:
    """coretemp's package sensor, for the system widget."""
    for hwmon in sorted(Path("/sys/class/hwmon").glob("*")):
        try:
            if (hwmon / "name").read_text().strip() != "coretemp":
                continue
            for label in sorted(hwmon.glob("temp*_label")):
                if label.read_text().startswith("Package"):
                    return str(hwmon / label.name.replace("_label", "_input"))
        except OSError:
            continue
    return ""


def font() -> str:
    try:
        from hypr_screens.gui import theme  # no GTK needed

        return theme.font()
    except Exception:
        return ""


def cava_config(bars: int) -> str:
    """cava prints one line per frame: bar values 0..1000 separated by ';'.
    It sleeps after 2 s of silence, so the visualizer costs nothing then."""
    return "\n".join([
        "[general]",
        f"bars = {bars}",
        "framerate = 60",
        "sleep_timer = 2",
        "autosens = 1",
        "[input]",
        "method = pipewire",
        "source = auto",
        "[output]",
        "method = raw",
        "raw_target = /dev/stdout",
        "data_format = ascii",
        "ascii_max_range = 1000",
        "bar_delimiter = 59",
        "frame_delimiter = 10",
        "[smoothing]",
        "noise_reduction = 77",
        "",
    ])


def export(cfg: dict) -> None:
    """Write what the shell plugin reads (it reloads on change)."""
    widgets = normalize(cfg.get("widgets"))
    directory = settings_file().parent
    directory.mkdir(parents=True, exist_ok=True)
    cava = cava_config(widgets["visualizer"]["bars"])
    if not cava_file().exists() or cava_file().read_text() != cava:
        cava_file().write_text(cava)
    language = i18n.set_language(cfg.get("language"))
    data = {
        "widgets": widgets,
        "cava": str(cava_file()),
        "cpuTemperature": cpu_temperature_file(),
        "font": font(),
        "locale": LOCALES.get(language, "en_US"),
        "ranges": {kind: {"size": SIZE_RANGES[kind], "width": WIDTH_RANGES.get(kind)} for kind in KINDS},
        "kinds": KINDS,
        "parts": {kind: part_defaults(kind) for kind in KINDS},
        "texts": {
            **{kind: t(title) for kind, title in TITLES.items()},
            "hint": t("Drag to move  ·  pull edges and corners to resize  ·  scroll to turn (Shift: fine)"),
            "save": t("Save"),
            "cancel": t("Cancel"),
            "lyricsSample": t("The lyrics show here while a song plays"),
            "cpu": "CPU",
            "memory": t("Memory"),
            "temperature": t("Temperature"),
        },
    }
    text = json.dumps(data, indent=2) + "\n"
    if not settings_file().exists() or settings_file().read_text() != text:
        # Written in place (not replaced): the plugin's file watch keeps working.
        settings_file().write_text(text)


# --- the shell plugin --------------------------------------------------------------------


def shell_ipc(*args: str) -> str:
    try:
        return subprocess.run(["omarchy-shell", PLUGIN, *args], check=False, text=True,
                              capture_output=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def wire_shell(widgets: dict) -> list[str]:
    """Plugin linked; its service on while any widget is on (shell.json
    "plugins"); its bar widget right after the desktops while the visualizer
    is in the bar. shell.json reloads itself."""
    if not install.has_omarchy_shell():
        return ["no omarchy-shell"]
    done = []
    link = install.plugins_dir() / PLUGIN
    if not (link.is_symlink() and link.resolve() == install.PLUGINS[PLUGIN].resolve()):
        done.append(f"plugin {install.link(install.PLUGINS[PLUGIN], link)}")
        subprocess.run(["omarchy-shell", "shell", "rescanPlugins"], capture_output=True, text=True)
    path = install.shell_json()
    try:
        shell = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return done + ["no shell.json"]
    before = json.dumps(shell, sort_keys=True)
    wanted = any(widget["enabled"] for widget in widgets.values())
    plugins = [p for p in shell.get("plugins", []) if not (isinstance(p, dict) and p.get("id") == PLUGIN)]
    if wanted:
        plugins.append({"id": PLUGIN})
    shell["plugins"] = plugins
    layout = (shell.setdefault("bar", {})).setdefault("layout", {})
    for section in layout.values():
        if isinstance(section, list):
            section[:] = [w for w in section if not (isinstance(w, dict) and w.get("id") == PLUGIN)]
    if in_bar(widgets):
        placed = False
        for section in layout.values():
            if not isinstance(section, list):
                continue
            for index, widget in enumerate(section):
                if isinstance(widget, dict) and widget.get("id") in WORKSPACES_IDS:
                    section.insert(index + 1, {"id": PLUGIN})
                    placed = True
                    break
            if placed:
                break
        if not placed:
            layout.setdefault("left", []).append({"id": PLUGIN})
    if json.dumps(shell, sort_keys=True) != before:
        path.write_text(json.dumps(shell, indent=2) + "\n")
        done.append("shell.json")
    return done


_blur_rule_sent = False


def apply(cfg: dict) -> None:
    global _blur_rule_sent
    export(cfg)
    state = normalize(cfg.get("widgets"))
    wire_shell(state)
    if not _blur_rule_sent and any(w["card"] and w["card_blur"] for w in state.values()):
        # In the Lua file too; this makes it live before the next reload.
        from hypr_screens import hypr, keybinds

        for line in keybinds.WIDGETS_BLUR_RULE.splitlines():
            hypr.eval_lua(line)
        _blur_rule_sent = True


def start_editing() -> bool:
    return shell_ipc("edit").strip() == "ok"


def placements() -> dict:
    """Where the widgets are right now while editing: {kind: {x, y, rotation, size, width}}."""
    try:
        data = json.loads(shell_ipc("placements") or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def stop_editing() -> None:
    shell_ipc("done")


def editing() -> bool:
    return shell_ipc("editing").strip() == "yes"


# --- layouts ---------------------------------------------------------------------------------
# cfg["widget_layouts"]: [{"name", "widgets", "screens"}]: every widget as it
# was saved; with "screens" (screen ids) it loads by itself whenever exactly
# those screens are connected.


def normalize_layouts(raw: object) -> list[dict]:
    layouts = []
    for layout in raw if isinstance(raw, list) else []:
        if not isinstance(layout, dict):
            continue
        name = str(layout.get("name") or "").strip()[:60]
        if not name or any(other["name"] == name for other in layouts):
            continue
        screens = layout.get("screens") if isinstance(layout.get("screens"), list) else []
        layouts.append({"name": name, "widgets": normalize(layout.get("widgets")),
                        "screens": sorted({str(sid) for sid in screens if str(sid)})})
    return layouts[:MAX_LAYOUTS]


def save_layout(cfg: dict, name: str) -> dict:
    """Keep the widgets as they are now under this name (replacing one of that name)."""
    name = name.strip()[:60]
    layouts = [layout for layout in cfg["widget_layouts"] if layout["name"] != name]
    old = next((layout for layout in cfg["widget_layouts"] if layout["name"] == name), None)
    layouts.append({"name": name, "widgets": normalize(cfg["widgets"]), "screens": old["screens"] if old else []})
    cfg["widget_layouts"] = normalize_layouts(layouts)
    return cfg


def load_layout(cfg: dict, name: str) -> dict:
    layout = next((layout for layout in cfg["widget_layouts"] if layout["name"] == name), None)
    if layout is not None:
        cfg["widgets"] = normalize(layout["widgets"])
    return cfg


def rename_layout(cfg: dict, name: str, new_name: str) -> dict:
    new_name = new_name.strip()[:60]
    if new_name and not any(layout["name"] == new_name for layout in cfg["widget_layouts"]):
        for layout in cfg["widget_layouts"]:
            if layout["name"] == name:
                layout["name"] = new_name
    return cfg


def delete_layout(cfg: dict, name: str) -> dict:
    cfg["widget_layouts"] = [layout for layout in cfg["widget_layouts"] if layout["name"] != name]
    return cfg


def set_layout_screens(cfg: dict, name: str, screens: list[str]) -> dict:
    """Load this layout by itself with exactly these screens ([]: only by hand).
    Another layout with the same screens gives them up."""
    screens = sorted(set(screens))
    for layout in cfg["widget_layouts"]:
        if layout["name"] == name:
            layout["screens"] = screens
        elif screens and layout["screens"] == screens:
            layout["screens"] = []
    return cfg


def matching_layout(cfg: dict, connected: list[str]) -> dict | None:
    connected = sorted(set(connected))
    return next((layout for layout in cfg["widget_layouts"] if layout["screens"] == connected), None)


def connected_screens() -> list[str]:
    from hypr_screens import hypr

    return sorted(config.connected(hypr.monitors()))


def auto_layout() -> str:
    """Load the layout made for the screens connected now (the watcher calls
    this after a monitor change)."""
    cfg = config.load()
    layout = matching_layout(cfg, connected_screens())
    if layout is None or normalize(layout["widgets"]) == cfg["widgets"]:
        return ""
    cfg = load_layout(cfg, layout["name"])
    config.save(cfg)
    apply(cfg)
    return f"widget layout {layout['name']}"


def save_placements(cfg: dict, placements: dict) -> dict:
    """Take places and sizes from arranging into the settings (only known widgets and keys)."""
    for kind, spot in (placements or {}).items():
        if kind in cfg["widgets"] and isinstance(spot, dict):
            widget = cfg["widgets"][kind]
            widget.update({key: spot[key] for key in PLACEMENT_KEYS if key in spot})
            if widget["enabled"]:
                widget["placed"] = True
    cfg["widgets"] = normalize(cfg["widgets"])
    return cfg


# --- cava ----------------------------------------------------------------------------------


def has_cava() -> bool:
    return shutil.which("cava") is not None


def install_cava(graphical: bool = True) -> bool:
    return run_as_root("set -e\npacman -S --needed --noconfirm cava\n", graphical)
