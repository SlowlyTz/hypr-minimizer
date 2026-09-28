"""Glue: sync everything, step settings, and the state the menu shows."""
import sys
from pathlib import Path

from hypr_screens import apply, config, desktops, hypr

LAUNCHER = Path(__file__).resolve().parent.parent / "hypr-screens"


def command_prefix() -> list[str]:
    """How the menu calls us back, independent of $PATH."""
    return [sys.executable, str(LAUNCHER)]


def sync(event: str = "") -> list[str]:
    """Record connected screens, apply their settings, arrange desktops.

    event: "added" (a monitor was plugged in), "removed", "reload" or "".
    """
    with apply.locked("sync"):
        cfg = config.load()
        if config.record(cfg, hypr.monitors(include_disabled=True)):
            config.save(cfg)
        done = apply.apply(cfg)
        screens = desktops.resolve(cfg)
        if not screens.external:
            desktops.undock(screens)
            desktops.mark_rules(False)
        elif screens.role:
            desktops.arrange(screens, docking=event == "added")
        else:
            desktops.fold_fixed(screens)
            if desktops.rules_marked():
                # Workspace rules pinning desktops to one screen only go away
                # with a reload; the monitor settings are applied again after.
                desktops.mark_rules(False)
                hypr.hyprctl("reload")
                done += apply.apply(cfg)
        return done


# --- stepping values (menu ←/→ and c) ----------------------------------------------


def options(cfg: dict, sid: str, key: str) -> list[object]:
    """Choices for a setting; None means "not set"."""
    screen = cfg["screens"].get(sid, {})
    if key == "rotation":
        return [None, *config.ROTATIONS]
    if key == "scale":
        return [None, *config.SCALES]
    if key == "mode":
        return [None, "preferred", *screen.get("modes", [])]
    if key == "position":
        return [] if screen.get("internal") else [None, *config.POSITIONS]
    if key == "one_desktop":
        return [None, True, False]
    raise ValueError(f"unknown setting: {key}")


def step_value(cfg: dict, sid: str, key: str, direction: int) -> None:
    choices = options(cfg, sid, key)
    if not choices:
        return
    current = (config.get_setting(cfg, sid, key) or {}).get("value")
    index = choices.index(current) if current in choices else 0
    config.set_setting(cfg, sid, key, choices[(index + direction) % len(choices)])


def step_condition(cfg: dict, sid: str, key: str, direction: int) -> bool:
    setting = config.get_setting(cfg, sid, key)
    if setting is None:
        return False
    choices = [None, *sorted(other for other in cfg["screens"] if other != sid)]
    current = setting.get("when")
    index = choices.index(current) if current in choices else 0
    config.set_condition(cfg, sid, key, choices[(index + direction) % len(choices)])
    return True


# --- state for the menu -------------------------------------------------------------

SETTING_LABELS = {
    "rotation": "Rotation",
    "scale": "Scale",
    "mode": "Resolution",
    "position": "Position",
    "one_desktop": "One desktop",
}


def screen_rows(cfg: dict, connected_ids: set[str]) -> list[dict]:
    def order(item):
        sid, screen = item
        section = 0 if screen.get("internal") else 1 if screen.get("favorite") else 2
        return (section, sid not in connected_ids, screen.get("name", ""))

    rows = []
    for sid, screen in sorted(cfg["screens"].items(), key=order):
        section = "Laptop" if screen.get("internal") else "Favorites" if screen.get("favorite") else "Known screens"
        settings = []
        for key in config.SETTING_KEYS:
            if key == "position" and screen.get("internal"):
                continue
            setting = config.get_setting(cfg, sid, key) or {}
            value = setting.get("value")
            when = setting.get("when")
            label = config.value_label(key, value)
            if key == "one_desktop" and value is None:
                label = f"default ({cfg.get('default_fixed', 'off')})"
            settings.append({
                "key": key,
                "label": SETTING_LABELS[key],
                "value": label,
                "set": value is not None,
                "when": "always" if not when else f"if {cfg['screens'].get(when, {}).get('name', '?')} connected",
                "active": value is not None and (not when or when in connected_ids),
            })
        rows.append({
            "id": sid,
            "name": screen.get("name", sid),
            "description": screen.get("description", ""),
            "connector": screen.get("connector", ""),
            "internal": bool(screen.get("internal")),
            "favorite": bool(screen.get("favorite")),
            "connected": sid in connected_ids,
            "section": section,
            "summary": config.summary(cfg, sid),
            "settings": settings,
        })
    return rows


def state(cfg: dict | None = None, message: str = "") -> dict:
    from hypr_screens import keybinds

    cfg = cfg or config.load()
    monitors = hypr.monitors()
    if config.record(cfg, hypr.monitors(include_disabled=True)):
        config.save(cfg)
    connected_ids = set(config.connected(monitors))
    return {
        "command": command_prefix(),
        "message": message,
        "status": desktops.status(cfg),
        "screens": screen_rows(cfg, connected_ids),
        "keybinds": [
            {"action": action, "label": label, "keys": cfg["keybinds"][action]}
            for action, label, _command in config.ACTIONS
        ],
        "options": [
            {"key": "desktop_keys", "label": "Desktop keys",
             "value": "on" if cfg["desktop_keys"] else "off"},
            {"key": "default_fixed", "label": "One desktop on new screens",
             "value": {"off": "off", "external": "external screen", "panel": "laptop"}[cfg["default_fixed"]]},
        ],
        "recordSubmap": keybinds.RECORD_SUBMAP,
    }
