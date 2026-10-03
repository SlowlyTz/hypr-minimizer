"""The settings file: known screens, their settings and the keybinds.

Lives at $XDG_CONFIG_HOME/hypr-screens/config.json. Every setting of a screen
is {"value": ..., "when": <screen id> | null}; with "when" set it only applies
while that other screen is connected. A setting that is not stored leaves the
screen as Hyprland's own config has it.
"""
import json
import os
import tempfile
import time
from pathlib import Path

VERSION = 1
INTERNAL_PREFIXES = ("eDP", "LVDS", "DSI")

ROTATIONS = [0, 90, 180, 270]
SCALES = ["auto", 1, 1.25, 1.5, 2]
POSITIONS = ["left", "right", "above", "below"]
FIXED_DEFAULTS = ["off", "external", "panel"]
SETTING_KEYS = ["rotation", "scale", "mode", "position", "one_desktop"]
LANGUAGE_CODES = ["en", "de", "es", "fr", "it"]

# (key, label, command) -- two keys each, see DEFAULT_KEYBINDS.
ACTIONS = [
    ("minimizer_menu", "Minimizer menu", "hypr-minimizer menu"),
    ("stash", "Minimize window", "hypr-minimizer stash"),
    ("stash_others", "Minimize other windows", "hypr-minimizer stash_others"),
    ("pop", "Restore last minimized", "hypr-minimizer pop"),
    ("pop_all", "Restore all minimized", "hypr-minimizer pop_all"),
    ("undo", "Undo minimize/restore", "hypr-minimizer undo"),
]
DEFAULT_KEYBINDS = {
    "minimizer_menu": ["SUPER + PERIOD", ""],
    "stash": ["SUPER + M", ""],
    "stash_others": ["", ""],
    "pop": ["SUPER + I", ""],
    "pop_all": ["SUPER + SHIFT + I", ""],
    "undo": ["SUPER + U", ""],
}


def config_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "hypr-screens" / "config.json"


def runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    path = Path(base) / "hypr-screens"
    path.mkdir(parents=True, exist_ok=True)
    return path


def exists() -> bool:
    return config_file().exists()


def default_config() -> dict:
    return {
        "version": VERSION,
        "keybinds": {action: list(keys) for action, keys in DEFAULT_KEYBINDS.items()},
        "desktop_keys": False,
        "default_fixed": "off",
        "screens": {},
        "sound": {"force_mute": {}},
        "samsung": {"limit": None, "mode": None, "full_once": False},
        "language": "en",
        "look": {},
    }


def normalize(raw: object) -> dict:
    cfg = default_config()
    if not isinstance(raw, dict):
        return cfg

    keybinds = raw.get("keybinds")
    if isinstance(keybinds, dict):
        for action in cfg["keybinds"]:
            keys = keybinds.get(action)
            if isinstance(keys, list):
                keys = [str(key or "") for key in keys[:2]]
                cfg["keybinds"][action] = keys + [""] * (2 - len(keys))
    cfg["desktop_keys"] = bool(raw.get("desktop_keys", False))
    if raw.get("default_fixed") in FIXED_DEFAULTS:
        cfg["default_fixed"] = raw["default_fixed"]

    screens = raw.get("screens")
    if isinstance(screens, dict):
        for screen_id, screen in screens.items():
            if isinstance(screen, dict):
                screen = dict(screen)
                settings = screen.get("settings")
                screen["settings"] = {
                    key: {"value": value.get("value"), "when": value.get("when")}
                    for key, value in (settings or {}).items()
                    if key in SETTING_KEYS and isinstance(value, dict)
                }
                cfg["screens"][str(screen_id)] = screen

    force_mute = (raw.get("sound") or {}).get("force_mute") if isinstance(raw.get("sound"), dict) else None
    if isinstance(force_mute, dict):
        for key, entry in force_mute.items():
            if isinstance(entry, dict) and entry.get("kind") in ("sink", "source"):
                volume = entry.get("volume")
                cfg["sound"]["force_mute"][str(key)] = {
                    "kind": entry["kind"],
                    "label": str(entry.get("label") or key),
                    "volume": int(volume) if isinstance(volume, (int, float)) else 0,
                    "mute": bool(entry.get("mute")),
                }

    samsung = raw.get("samsung") if isinstance(raw.get("samsung"), dict) else {}
    limit = samsung.get("limit")
    if isinstance(limit, (int, float)) and not isinstance(limit, bool) and 1 <= limit <= 100:
        cfg["samsung"]["limit"] = int(limit)
    if isinstance(samsung.get("mode"), str) and samsung["mode"]:
        cfg["samsung"]["mode"] = samsung["mode"]
    cfg["samsung"]["full_once"] = bool(samsung.get("full_once"))
    if raw.get("language") in LANGUAGE_CODES:
        cfg["language"] = raw["language"]
    from hypr_screens import look  # look imports hypr only; kept local to stay light

    cfg["look"] = look.normalize(raw.get("look"))
    return cfg


def load() -> dict:
    try:
        return normalize(json.loads(config_file().read_text()))
    except (OSError, json.JSONDecodeError):
        return default_config()


def save(cfg: dict) -> None:
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(normalize(cfg), indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


# --- screens -----------------------------------------------------------------


def is_internal(monitor: dict) -> bool:
    return str(monitor.get("name", "")).startswith(INTERNAL_PREFIXES)


def screen_id(monitor: dict) -> str:
    """Stable identity from the EDID; the connector name changes between ports."""
    parts = [str(monitor.get(key) or "").strip() for key in ("make", "model", "serial")]
    if not any(parts):
        parts = [str(monitor.get("description") or monitor.get("name") or "").strip()]
    return "|".join(parts)


def screen_name(monitor: dict) -> str:
    if is_internal(monitor):
        return "Laptop"
    make = str(monitor.get("make") or "").strip()
    model = str(monitor.get("model") or "").strip()
    brand = make.split(" ")[0] if make else ""
    if brand and model.lower().startswith(brand.lower()):
        return model
    return " ".join(part for part in (brand, model) if part) or str(monitor.get("name", "?"))


def parse_modes(monitor: dict) -> list[str]:
    modes = []
    for mode in monitor.get("availableModes") or []:
        mode = str(mode).removesuffix("Hz")
        if mode not in modes:
            modes.append(mode)
    return modes


def record(cfg: dict, monitors: list[dict]) -> bool:
    """Add or refresh every connected monitor; True if anything changed."""
    changed = False
    for monitor in monitors:
        sid = screen_id(monitor)
        screen = cfg["screens"].get(sid)
        if screen is None:
            screen = {"favorite": False, "settings": {}}
            cfg["screens"][sid] = screen
            changed = True
        fresh = {
            "name": screen_name(monitor),
            "description": str(monitor.get("description") or ""),
            "internal": is_internal(monitor),
            "connector": str(monitor.get("name") or ""),
            "modes": parse_modes(monitor) or screen.get("modes", []),
        }
        today = time.strftime("%Y-%m-%d")
        if screen.get("last_seen") != today:
            fresh["last_seen"] = today
        if any(screen.get(key) != value for key, value in fresh.items()):
            screen.update(fresh)
            changed = True
    return changed


def connected(monitors: list[dict]) -> dict[str, dict]:
    """Enabled monitors by screen id."""
    return {screen_id(monitor): monitor for monitor in monitors if not monitor.get("disabled")}


def internal_id(cfg: dict) -> str | None:
    return next((sid for sid, screen in cfg["screens"].items() if screen.get("internal")), None)


# --- settings ----------------------------------------------------------------


def get_setting(cfg: dict, sid: str, key: str) -> dict | None:
    return cfg["screens"].get(sid, {}).get("settings", {}).get(key)


def set_setting(cfg: dict, sid: str, key: str, value: object) -> None:
    """Store a value, keeping its condition; None removes the setting."""
    if key not in SETTING_KEYS:
        raise ValueError(f"unknown setting: {key}")
    settings = cfg["screens"].setdefault(sid, {"favorite": False, "settings": {}}).setdefault("settings", {})
    if value is None:
        settings.pop(key, None)
        return
    when = (settings.get(key) or {}).get("when")
    settings[key] = {"value": value, "when": when}


def set_condition(cfg: dict, sid: str, key: str, when: str | None) -> None:
    setting = get_setting(cfg, sid, key)
    if setting is None:
        raise ValueError(f"{key} is not set")
    setting["when"] = when or None


def active_value(cfg: dict, sid: str, key: str, connected_ids: set[str]) -> object:
    """The value in force right now, or None when unset or its condition is unmet."""
    setting = get_setting(cfg, sid, key)
    if setting is None:
        return None
    when = setting.get("when")
    if when and when not in connected_ids:
        return None
    return setting.get("value")


def value_label(key: str, value: object) -> str:
    if value is None:
        return "as configured" if key != "one_desktop" else "default"
    if key == "rotation":
        return f"{value}°"
    if key == "scale":
        return "auto" if value == "auto" else f"{value}×"
    if key == "one_desktop":
        return "yes" if value else "no"
    return str(value)


def summary(cfg: dict, sid: str) -> str:
    """Short text for the screen list, e.g. "180° if HP 32f · one desktop"."""
    parts = []
    for key, setting in cfg["screens"].get(sid, {}).get("settings", {}).items():
        value = setting.get("value")
        if key == "one_desktop":
            text = "one desktop" if value else "no fixed desktop"
        elif key == "position":
            text = f"{value} of laptop"
        else:
            text = value_label(key, value)
        when = setting.get("when")
        if when:
            text += f" if {cfg['screens'].get(when, {}).get('name', '?')}"
        parts.append(text)
    return " · ".join(parts)
