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
# Where a widget first appears: the middle, so it can be dragged from there.
CENTER = {"x": 0.5, "y": 0.5, "rotation": 0}
ALL_SCREENS = {"mode": "all", "screen": ""}
DEFAULTS = {
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
# The values a setting can take; the first-listed default is in DEFAULTS.
CHOICES = {
    "visualizer": {"where": WHERE, "style": ["bottom", "mirrored"], "color": COLORS},
    # line: the line being sung in the accent color, word: each word as it is
    # sung, off: no color, only the size sets it apart.
    "lyrics": {"highlight": ["line", "word", "off"], "align": ["center", "left", "right"], "color": TEXT_COLORS},
    "clock": {"hours": ["24", "12"], "color": TEXT_COLORS},
    "system": {"color": TEXT_COLORS},
}
TITLES = {"visualizer": "Visualizer", "lyrics": "Lyrics", "clock": "Clock", "system": "System"}
LOCALES = {"en": "en_US", "de": "de_DE", "es": "es_ES", "fr": "fr_FR", "it": "it_IT"}
# key: (minimum, maximum)
RANGES = {"bars": (8, 64), "lines": (1, 10), "opacity": (20, 100), "rotation": (-360, 360)}
# The visualizer's and the lyrics' size is their height in pixels (the lyrics'
# font fills it), the others' a scale in percent.
SIZE_RANGES = {"visualizer": (30, 600), "lyrics": (40, 1200), "clock": (30, 400), "system": (50, 300)}
# Width in pixels for the widgets that can be made wider on their own.
WIDTH_RANGES = {"visualizer": (60, 2000), "lyrics": (200, 2400), "system": (150, 1200)}
# What arranging may change.
PLACEMENT_KEYS = ("x", "y", "rotation", "size", "width")


def settings_file() -> Path:
    return config.config_file().parent / "widgets.json"


def cava_file() -> Path:
    return config.config_file().parent / "cava.conf"


def number(value: object, low: float, high: float, fallback: float, whole: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return fallback
    value = max(low, min(high, value))
    return int(round(value)) if whole else round(float(value), 4)


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


def apply(cfg: dict) -> None:
    export(cfg)
    wire_shell(normalize(cfg.get("widgets")))


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
