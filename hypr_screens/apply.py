"""Put the per-screen settings in force on the connected monitors.

Only settings whose condition holds are applied, through `hl.monitor`; fields a
screen has no setting for keep their current value. A setting that stops
applying (its screen or condition went away) cannot be "unset" at runtime, so
the Hyprland config is reloaded once to get the configured values back, and
the remaining settings are applied on top.
"""
import fcntl
import json
import time
from contextlib import contextmanager

from hypr_screens import config, hypr

TRANSFORMS = {0: 0, 90: 1, 180: 2, 270: 3}
POSITIONS = {"left": "auto-left", "right": "auto-right", "above": "auto-up", "below": "auto-down"}
MONITOR_FIELDS = ("rotation", "scale", "mode", "position")
RELOAD_SETTLE_SECONDS = 0.5


@contextmanager
def locked(name: str = "apply"):
    """Serialize appliers (watcher, menu, CLI) across processes."""
    with open(config.runtime_dir() / f"{name}.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def applied_file():
    return config.runtime_dir() / "applied.json"


def load_applied() -> dict:
    try:
        applied = json.loads(applied_file().read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return applied if isinstance(applied, dict) else {}


def save_applied(applied: dict) -> None:
    applied_file().write_text(json.dumps(applied, indent=2, sort_keys=True) + "\n")


def desired(cfg: dict, monitors: list[dict]) -> dict[str, dict]:
    """{connector: {"id", "fields"}} for every enabled monitor."""
    live = config.connected(monitors)
    ids = set(live)
    result = {}
    for sid, monitor in live.items():
        fields = {}
        for key in MONITOR_FIELDS:
            value = config.active_value(cfg, sid, key, ids)
            if value is None or (key == "position" and config.is_internal(monitor)):
                continue
            fields[key] = value
        result[str(monitor["name"])] = {"id": sid, "fields": fields}
    return result


def snapshot(monitor: dict) -> dict:
    return {
        key: monitor.get(key)
        for key in ("x", "y", "width", "height", "refreshRate", "scale", "transform")
    }


def mode_matches(monitor: dict, mode: str) -> bool:
    try:
        size, _, rate = mode.partition("@")
        width, height = (int(part) for part in size.split("x"))
    except ValueError:
        return False
    if (monitor.get("width"), monitor.get("height")) != (width, height):
        return False
    return not rate or abs(float(monitor.get("refreshRate") or 0) - float(rate)) < 0.5


def already_there(monitor: dict, fields: dict) -> bool:
    """Whether the live monitor shows these fields, as far as that can be read."""
    if "position" in fields or fields.get("scale") == "auto":
        return False
    if "rotation" in fields and monitor.get("transform") != TRANSFORMS[fields["rotation"]]:
        return False
    if "scale" in fields and abs(float(monitor.get("scale") or 1) - float(fields["scale"])) > 0.01:
        return False
    return "mode" not in fields or mode_matches(monitor, str(fields["mode"]))


def monitor_rule(monitor: dict, fields: dict) -> str:
    transform = TRANSFORMS[fields["rotation"]] if "rotation" in fields else int(monitor.get("transform") or 0)
    if "mode" in fields:
        mode = str(fields["mode"])
    else:
        mode = f"{monitor['width']}x{monitor['height']}@{float(monitor.get('refreshRate') or 60):.2f}"
    if "position" in fields:
        position = POSITIONS[fields["position"]]
    elif transform % 2 != int(monitor.get("transform") or 0) % 2:
        # Width and height swap; the old spot could overlap the other screen.
        position = "auto"
    else:
        position = f"{monitor.get('x', 0)}x{monitor.get('y', 0)}"
    scale = fields.get("scale", monitor.get("scale") or 1)
    scale_lua = hypr.lua_string("auto") if scale == "auto" else repr(float(scale))
    return (
        f"hl.monitor({{ output = {hypr.lua_string(monitor['name'])}, mode = {hypr.lua_string(mode)}, "
        f"position = {hypr.lua_string(position)}, scale = {scale_lua}, transform = {transform} }})"
    )


def needs_reset(applied: dict, wanted: dict) -> bool:
    for name, entry in applied.items():
        now = wanted.get(name)
        if now is None or now["id"] != entry.get("id"):
            return True
        if set(entry.get("fields", {})) - set(now["fields"]):
            return True
    return False


def apply(cfg: dict) -> list[str]:
    """Bring the monitors in line with the settings; returns what was done."""
    done = []
    with locked():
        monitors = hypr.monitors()
        wanted = desired(cfg, monitors)
        applied = load_applied()

        if needs_reset(applied, wanted):
            save_applied({})
            applied = {}
            hypr.hyprctl("reload")
            time.sleep(RELOAD_SETTLE_SECONDS)
            done.append("reload")
            monitors = hypr.monitors()

        by_name = {str(monitor.get("name")): monitor for monitor in monitors}
        for name, entry in wanted.items():
            fields = entry["fields"]
            monitor = by_name.get(name)
            if not fields or monitor is None:
                continue
            previous = applied.get(name)
            if previous and previous.get("fields") == fields and previous.get("after") == snapshot(monitor):
                continue
            if previous is None and already_there(monitor, fields):
                applied[name] = {"id": entry["id"], "fields": fields, "after": snapshot(monitor)}
                continue
            hypr.eval_lua(monitor_rule(monitor, fields))
            done.append(name)
            applied[name] = {"id": entry["id"], "fields": fields}

        if any("after" not in entry for entry in applied.values()):
            time.sleep(RELOAD_SETTLE_SECONDS)
            by_name = {str(monitor.get("name")): monitor for monitor in hypr.monitors()}
            for name, entry in applied.items():
                if name in by_name:
                    entry["after"] = snapshot(by_name[name])
        save_applied(applied)
    return done
