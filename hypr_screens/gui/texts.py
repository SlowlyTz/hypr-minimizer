"""German wording for the settings window, kept apart from the widgets.

Every setting gets a plain-language title, one explaining sentence and
human-readable choices. (value, label) lists map straight onto dropdowns;
None always means "not set: Hyprland's own config decides".
"""
from hypr_screens import config

PAGES = [
    ("screens", "Bildschirme", "video-display-symbolic"),
    ("desktop", "Ein Desktop", "view-dual-symbolic"),
    ("keys", "Tasten", "input-keyboard-symbolic"),
    ("sound", "Sound", "audio-volume-high-symbolic"),
    # Only on a Samsung Galaxy Book (samsung.present()); English like Samsung Settings.
    ("samsung", "Samsung", "computer-symbolic"),
    ("help", "Hilfe", "help-about-symbolic"),
]

AS_CONFIGURED = "Standard"

SETTINGS = {
    "rotation": (
        "Drehung",
        "Dreht das Bild, z. B. wenn der Bildschirm hochkant oder kopfüber steht.",
    ),
    "scale": (
        "Größe (Skalierung)",
        "Macht Schrift und Fenster größer oder kleiner. Größer ist angenehmer auf hochauflösenden Bildschirmen.",
    ),
    "mode": (
        "Auflösung",
        "Wie viele Bildpunkte der Bildschirm zeigt und wie oft pro Sekunde das Bild erneuert wird.",
    ),
    "position": (
        "Platz neben dem Laptop",
        "Wo der Bildschirm auf dem Schreibtisch steht. Bestimmt, an welchem Rand die Maus hinüberwandert.",
    ),
    "one_desktop": (
        "Nur ein Desktop auf diesem Bildschirm",
        "Der Bildschirm zeigt immer denselben Desktop; die Desktops 1–10 liegen auf dem anderen. Siehe „Ein Desktop“.",
    ),
}

ACTION_HELP = {
    "minimizer_menu": "Öffnet die Liste der minimierten Fenster (dort: Enter, Shift+Enter, „-“ zum Reinschauen).",
    "stash": "Versteckt das aktive Fenster.",
    "stash_others": "Versteckt alle anderen Fenster auf diesem Desktop.",
    "pop": "Holt das zuletzt versteckte Fenster zurück.",
    "pop_all": "Holt alle versteckten Fenster dieses Desktops zurück.",
    "undo": "Macht das letzte Verstecken oder Zurückholen rückgängig.",
}

ACTION_LABELS = {
    "minimizer_menu": "Fenster-Liste öffnen",
    "stash": "Fenster verstecken",
    "stash_others": "Alle anderen verstecken",
    "pop": "Letztes zurückholen",
    "pop_all": "Alle zurückholen",
    "undo": "Rückgängig",
}

DEFAULT_FIXED = [
    ("off", "Aus – beide Bildschirme haben Desktops"),
    ("external", "Der externe Monitor"),
    ("panel", "Der Laptop"),
]


def choices(key: str, screen: dict, default_fixed: str = "off") -> list[tuple[object, str]]:
    """(value, label) for a setting's dropdown; the first entry is "not set"."""
    if key == "rotation":
        return [(None, AS_CONFIGURED), (0, "Normal (0°)"), (90, "90° – hochkant, nach rechts"),
                (180, "180° – kopfüber"), (270, "270° – hochkant, nach links")]
    if key == "scale":
        return [(None, AS_CONFIGURED), ("auto", "Automatisch"), (1, "100 % – normal"),
                (1.25, "125 %"), (1.5, "150 %"), (2, "200 % – doppelt so groß")]
    if key == "mode":
        modes = [(mode, mode_label(mode)) for mode in screen.get("modes", [])]
        return [(None, AS_CONFIGURED), ("preferred", "Empfohlen (vom Bildschirm)"), *modes]
    if key == "position":
        return [(None, AS_CONFIGURED), ("left", "Links vom Laptop"), ("right", "Rechts vom Laptop"),
                ("above", "Über dem Laptop"), ("below", "Unter dem Laptop")]
    if key == "one_desktop":
        default = {"off": "nein", "external": "ja" if not screen.get("internal") else "nein",
                   "panel": "ja" if screen.get("internal") else "nein"}[default_fixed]
        return [(None, f"Standard ({default})"), (True, "Ja"), (False, "Nein")]
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
    return [(None, "Immer")] + [
        (other, f"Nur mit „{name}“" + ("" if other in connected else " (nicht angeschlossen)"))
        for other, name in others
    ]


def status_text(status: dict, cfg: dict) -> str:
    if not status.get("external"):
        return "Kein externer Monitor angeschlossen – alles ist normal."
    if not status.get("fixed"):
        return "Beide Bildschirme haben Desktops (niemand ist fest)."
    who = "Der Laptop" if status["fixed"] == "panel" else "Der externe Monitor"
    extra = " (vorübergehend getauscht, bis zum Abstecken)" if status.get("swapped") else ""
    return f"{who} zeigt gerade nur einen Desktop{extra}."


def combo_label(combo: str) -> str:
    if not combo:
        return "—"
    names = {"PERIOD": ".", "COMMA": ",", "MINUS": "-", "RETURN": "Enter", "SPACE": "Leertaste", "TAB": "Tab"}
    parts = [part.strip() for part in combo.split("+")]
    key = parts[-1]
    if key.upper() == "F23" and parts[:-1] == ["SUPER", "SHIFT"]:
        return "Copilot-Taste"
    return " + ".join([*[p.capitalize() if p != "SUPER" else "Super" for p in parts[:-1]], names.get(key.upper(), key)])


def actions() -> list[str]:
    return [action for action, _label, _command in config.ACTIONS]


def label_for(english: str) -> str:
    """German label for an action given its config label."""
    for action, text, _command in config.ACTIONS:
        if text == english:
            return ACTION_LABELS.get(action, text)
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
    ("Tray-Symbol",
     "Das Bildschirm-Symbol in der Leiste öffnet dieses Fenster. Rechtsklick: tauschen oder beenden. "
     "Es startet mit Hyprland von selbst."),
    ("Tasten auf dem Desktop",
     "Nur die Fenster-Tasten liegen auf der Tastatur (z. B. Super + M zum Verstecken, Super + . für die "
     "Fenster-Liste). Alles andere stellst du hier ein."),
    ("Bildschirme",
     "Jede Einstellung gilt entweder immer oder nur, solange ein bestimmter anderer Bildschirm angeschlossen "
     "ist – z. B. „Laptop kopfüber, aber nur am Schreibtisch-Monitor“."),
    ("Sound",
     "Lautstärke für jedes Gerät und jede App, auch für Geräte, die gerade nicht Standard sind. "
     "„Force Mute“ hält ein Gerät dauerhaft stumm – auch wenn dieses Fenster zu ist."),
    ("Wenn etwas nicht stimmt",
     "Im Terminal hilft oft: hypr-screens apply. Die Einstellungen liegen in ~/.config/hypr-screens/config.json."),
]
