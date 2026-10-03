"""Wording for the settings window, kept apart from the widgets.

Every setting gets a plain-language title, one explaining sentence and
human-readable choices. (value, label) lists map straight onto dropdowns;
None always means "not set: Hyprland's own config decides". Texts are English
and go through i18n.t(), so they are looked up again whenever they are shown.
"""
from hypr_screens import config
from hypr_screens.i18n import t

# (key, title, icon). "samsung" only on a Samsung Galaxy Book (samsung.present()).
PAGE_LIST = [
    ("screens", "Screens", "video-display-symbolic"),
    ("desktop", "One desktop", "view-dual-symbolic"),
    ("keys", "Keys", "input-keyboard-symbolic"),
    ("sound", "Sound", "audio-volume-high-symbolic"),
    ("samsung", "Samsung", "computer-symbolic"),
    ("camera", "Camera", "camera-web-symbolic"),
    ("personalization", "Personalization", "applications-graphics-symbolic"),
    ("settings", "Settings", "preferences-system-symbolic"),
    ("help", "Help", "help-about-symbolic"),
]


def pages() -> list[tuple[str, str, str]]:
    return [(key, t(title), icon) for key, title, icon in PAGE_LIST]


def as_configured() -> str:
    return t("Default")


SETTINGS = {
    "rotation": (
        "Rotation",
        "Turns the picture, e.g. when the screen stands upright or upside down.",
    ),
    "scale": (
        "Size (scaling)",
        "Makes text and windows bigger or smaller. Bigger is easier on high-resolution screens.",
    ),
    "mode": (
        "Resolution",
        "How many pixels the screen shows and how often per second the picture is refreshed.",
    ),
    "position": (
        "Place next to the laptop",
        "Where the screen stands on the desk. Decides at which edge the mouse moves across.",
    ),
    "one_desktop": (
        "Only one desktop on this screen",
        "The screen always shows the same desktop; desktops 1–10 live on the other one. See “One desktop”.",
    ),
}


def setting_text(key: str) -> tuple[str, str]:
    title, explanation = SETTINGS[key]
    return t(title), t(explanation)


ACTION_HELP = {
    "minimizer_menu": "Opens the list of minimized windows (there: Enter, Shift+Enter, “-” to peek).",
    "stash": "Hides the active window.",
    "stash_others": "Hides all other windows on this desktop.",
    "pop": "Brings back the window hidden last.",
    "pop_all": "Brings back all hidden windows of this desktop.",
    "undo": "Undoes the last hiding or bringing back.",
}

ACTION_LABELS = {
    "minimizer_menu": "Open window list",
    "stash": "Hide window",
    "stash_others": "Hide all others",
    "pop": "Bring back last",
    "pop_all": "Bring back all",
    "undo": "Undo",
}


def action_label(action: str) -> str:
    return t(ACTION_LABELS[action])


def action_help(action: str) -> str:
    return t(ACTION_HELP[action])


# Samsung page.
BATTERY_ROWS = {"level": "Level", "health": "Health", "cycles": "Charge cycles", "power": "Power"}
MODE_HINTS = {
    "low-power": "Longest battery life, slowest and silent.",
    "quiet": "Keeps the fan quiet; a little slower.",
    "balanced": "Samsung's default: speed and fan noise in balance.",
    "performance": "Fastest; the fan gets loud under load.",
}


def default_fixed_choices() -> list[tuple[str, str]]:
    return [
        ("off", t("Off – both screens have desktops")),
        ("external", t("The external monitor")),
        ("panel", t("The laptop")),
    ]


def choices(key: str, screen: dict, default_fixed: str = "off") -> list[tuple[object, str]]:
    """(value, label) for a setting's dropdown; the first entry is "not set"."""
    default = as_configured()
    if key == "rotation":
        return [(None, default), (0, t("Normal (0°)")), (90, t("90° – upright, to the right")),
                (180, t("180° – upside down")), (270, t("270° – upright, to the left"))]
    if key == "scale":
        return [(None, default), ("auto", t("Automatic")), (1, t("100 % – normal")),
                (1.25, "125 %"), (1.5, "150 %"), (2, t("200 % – twice as big"))]
    if key == "mode":
        modes = [(mode, mode_label(mode)) for mode in screen.get("modes", [])]
        return [(None, default), ("preferred", t("Recommended (by the screen)")), *modes]
    if key == "position":
        return [(None, default), ("left", t("Left of the laptop")), ("right", t("Right of the laptop")),
                ("above", t("Above the laptop")), ("below", t("Below the laptop"))]
    if key == "one_desktop":
        yes_no = {"off": False, "external": not screen.get("internal"), "panel": bool(screen.get("internal"))}
        fixed = yes_no[default_fixed]
        return [(None, t("Default (yes)") if fixed else t("Default (no)")), (True, t("Yes")), (False, t("No"))]
    raise ValueError(key)


def mode_label(mode: str) -> str:
    """"2560x1440@59.95" -> "2560 × 1440 · 60 Hz"."""
    size, _, rate = str(mode).partition("@")
    size = size.replace("x", " × ")
    try:
        return f"{size} · {round(float(rate))} Hz" if rate else size
    except ValueError:
        return str(mode)


def condition_choices(cfg: dict, sid: str, connected: set[str], current: str | None = None
                      ) -> list[tuple[str | None, str]]:
    """"Always" plus the screens connected right now; a condition already set on
    an unplugged screen stays listed so it can be seen and changed."""
    others = sorted(
        ((other, screen.get("name", other)) for other, screen in cfg["screens"].items()
         if other != sid and (other in connected or other == current)),
        key=lambda item: item[1],
    )
    return [(None, t("Always"))] + [
        (other, t("Only with “{name}”", name=name) if other in connected
         else t("Only with “{name}” (not connected)", name=name))
        for other, name in others
    ]


def status_text(status: dict, cfg: dict) -> str:
    if not status.get("external"):
        return t("No external monitor connected – everything is normal.")
    if not status.get("fixed"):
        return t("Both screens have desktops (none is fixed).")
    panel = status["fixed"] == "panel"
    if status.get("swapped"):
        return (t("The laptop shows only one desktop right now (swapped for now, until unplugged).") if panel
                else t("The external monitor shows only one desktop right now (swapped for now, until unplugged)."))
    return (t("The laptop shows only one desktop right now.") if panel
            else t("The external monitor shows only one desktop right now."))


def combo_label(combo: str) -> str:
    if not combo:
        return "—"
    names = {"PERIOD": ".", "COMMA": ",", "MINUS": "-", "RETURN": "Enter", "SPACE": t("Space"), "TAB": "Tab"}
    parts = [part.strip() for part in combo.split("+")]
    key = parts[-1]
    if key.upper() == "F23" and parts[:-1] == ["SUPER", "SHIFT"]:
        return t("Copilot key")
    return " + ".join([*[p.capitalize() if p != "SUPER" else "Super" for p in parts[:-1]], names.get(key.upper(), key)])


def actions() -> list[str]:
    return [action for action, _label, _command in config.ACTIONS]


def label_for(english: str) -> str:
    """Shown label for an action given its config label."""
    for action, text, _command in config.ACTIONS:
        if text == english:
            return action_label(action)
    return english


def same(a: object, b: object) -> bool:
    """Equal values, but True is not 1 and 1 equals 1.0."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return a == b


def index_of(pairs: list[tuple[object, str]], value: object) -> int:
    return next((i for i, (option, _text) in enumerate(pairs) if same(option, value)), 0)


# --- recording a shortcut ----------------------------------------------------------

MODIFIER_KEYS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Super_L", "Super_R",
    "Meta_L", "Meta_R", "Hyper_L", "Hyper_R", "ISO_Level3_Shift", "ISO_Level5_Shift", "Caps_Lock",
}
KEY_NAMES = {
    "period": "PERIOD", "comma": "COMMA", "minus": "MINUS", "Return": "RETURN", "KP_Enter": "RETURN",
    "space": "SPACE", "Tab": "TAB", "ISO_Left_Tab": "TAB", "Delete": "DELETE", "Insert": "INSERT",
    "Home": "HOME", "End": "END", "Prior": "PRIOR", "Next": "NEXT", "Left": "LEFT", "Right": "RIGHT",
    "Up": "UP", "Down": "DOWN", "Print": "PRINT",
}
# Gdk.ModifierType bits, kept as numbers so this module needs no GTK.
SHIFT, CONTROL, ALT, SUPER, META = 1, 4, 8, 1 << 26, 1 << 28


def hypr_key(name: str, keycode: int) -> str:
    """Hyprland spelling of a key; odd or layout-specific keys by their keycode."""
    if len(name) == 1 and name.isascii() and name.isalnum():
        return name.upper()
    if name[:1] == "F" and name[1:].isdigit():
        return name
    return KEY_NAMES.get(name) or (f"code:{keycode}" if keycode else "")


def combo_from_event(name: str, keycode: int, state: int) -> str:
    key = hypr_key(name, keycode)
    if not key:
        return ""
    mods = []
    if state & (SUPER | META):
        mods.append("SUPER")
    if state & CONTROL:
        mods.append("CTRL")
    if state & ALT:
        mods.append("ALT")
    if state & SHIFT:
        mods.append("SHIFT")
    return " + ".join([*mods, key])


HELP = [
    ("Tray icon",
     "The screen icon in the bar opens this window. Right click: swap or quit. "
     "It starts with Hyprland by itself."),
    ("Keys on the desktop",
     "Only the window keys are on the keyboard (e.g. Super + M to hide, Super + . for the "
     "window list). Everything else is set here."),
    ("Screens",
     "Each setting applies either always or only while a certain other screen is connected "
     "– e.g. “laptop upside down, but only at the desk monitor”."),
    ("Sound",
     "Volume for every device and every app, also for devices that are not the default right now. "
     "“Force Mute” keeps a device silent for good – even when this window is closed."),
    ("If something is wrong",
     "In a terminal this often helps: hypr-screens apply. The settings are in ~/.config/hypr-screens/config.json."),
]


def help_items() -> list[tuple[str, str]]:
    return [(t(title), t(text)) for title, text in HELP]
