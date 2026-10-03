"""Window look: gaps, rounding, border, blur and opacity (Personalization →
Window). Values the user set are kept in config["look"] and written into the
generated Lua file (keybinds.render), which loads after Omarchy's theme and so
wins; an empty look leaves everything to Omarchy.

Beyond Hyprland's plain options:
- border_colors + border_angle: the active border as a gradient of two colors,
- anim_speed: Omarchy's animations faster or slower (2 = twice as fast),
- apps: see-through apps, [{"class", "active", "inactive"}] as window rules.
"""
import json
import re
from pathlib import Path

from hypr_screens import hypr

# key: (Hyprland option, Lua path, kind, minimum, maximum, step)
OPTIONS = {
    "gaps_in": ("general:gaps_in", ("general", "gaps_in"), "int", 0, 30, 1),
    "gaps_out": ("general:gaps_out", ("general", "gaps_out"), "int", 0, 60, 1),
    "rounding": ("decoration:rounding", ("decoration", "rounding"), "int", 0, 30, 1),
    "border_size": ("general:border_size", ("general", "border_size"), "int", 0, 8, 1),
    "blur": ("decoration:blur:enabled", ("decoration", "blur", "enabled"), "bool", 0, 1, 1),
    "blur_size": ("decoration:blur:size", ("decoration", "blur", "size"), "int", 1, 20, 1),
    "blur_passes": ("decoration:blur:passes", ("decoration", "blur", "passes"), "int", 1, 4, 1),
    "active_opacity": ("decoration:active_opacity", ("decoration", "active_opacity"), "float", 0.3, 1.0, 0.01),
    "inactive_opacity": ("decoration:inactive_opacity", ("decoration", "inactive_opacity"), "float", 0.3, 1.0, 0.01),
}
ANIM_RANGE = (0.25, 3.0)
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
# Where Omarchy's animations are defined; the user's file wins per animation.
ANIMATION_FILES = [Path("/usr/share/omarchy/default/hypr/looknfeel.lua"),
                   Path.home() / ".config" / "hypr" / "looknfeel.lua"]
PRESETS = {
    "Clean": {"gaps_in": 0, "gaps_out": 0, "rounding": 0, "border_size": 1, "blur": False,
              "blur_size": 8, "blur_passes": 1, "active_opacity": 1.0, "inactive_opacity": 1.0},
    "Soft": {"gaps_in": 5, "gaps_out": 12, "rounding": 12, "border_size": 2, "blur": True,
             "blur_size": 6, "blur_passes": 2, "active_opacity": 1.0, "inactive_opacity": 0.95},
    "Glass": {"gaps_in": 6, "gaps_out": 14, "rounding": 14, "border_size": 1, "blur": True,
              "blur_size": 10, "blur_passes": 3, "active_opacity": 0.9, "inactive_opacity": 0.8},
}


def clean(key: str, value: object) -> object:
    """A value of the right kind inside its range, or None."""
    _option, _path, kind, low, high, _step = OPTIONS[key]
    if kind == "bool":
        return bool(value) if isinstance(value, (bool, int)) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = max(low, min(high, value))
    return int(round(value)) if kind == "int" else round(float(value), 2)


def normalize(raw: object) -> dict:
    if not isinstance(raw, dict):
        return {}
    look = {}
    for key, value in raw.items():
        if key in OPTIONS and (value := clean(key, value)) is not None:
            look[key] = value
    colors = raw.get("border_colors")
    if isinstance(colors, list) and len(colors) == 2 and all(isinstance(c, str) and HEX_COLOR.match(c) for c in colors):
        look["border_colors"] = [c.lower() for c in colors]
        angle = raw.get("border_angle", 0)
        look["border_angle"] = int(angle) % 360 if isinstance(angle, (int, float)) and not isinstance(angle, bool) else 0
    speed = raw.get("anim_speed")
    if isinstance(speed, (int, float)) and not isinstance(speed, bool) and round(float(speed), 2) != 1.0:
        look["anim_speed"] = round(max(ANIM_RANGE[0], min(ANIM_RANGE[1], float(speed))), 2)
    apps = []
    for rule in raw.get("apps") if isinstance(raw.get("apps"), list) else []:
        if not isinstance(rule, dict) or not str(rule.get("class") or "").strip():
            continue
        name = str(rule["class"]).strip()
        if any(other["class"] == name for other in apps):
            continue
        active, inactive = (clean("active_opacity", rule.get(k, 1.0)) for k in ("active", "inactive"))
        apps.append({"class": name, "active": active if active is not None else 1.0,
                     "inactive": inactive if inactive is not None else 1.0})
    if apps:
        look["apps"] = apps
    return look


def parse_option(reply: dict, kind: str) -> object:
    if "css" in reply:  # gaps: "top right bottom left"; the sliders set all four
        value = int(str(reply["css"]).split()[0]) if str(reply["css"]).split() else 0
    else:
        value = reply.get("int", reply.get("float", reply.get("bool")))
    if kind == "bool":
        return bool(value)
    if kind == "float":
        return round(float(value or 0), 2)
    return int(value or 0)


def current_border() -> tuple[list[str], int]:
    """The active border's colors (two) and angle as Hyprland shows them now."""
    try:
        reply = json.loads(hypr.hyprctl("-j", "getoption", "general:col.active_border") or "{}")
    except json.JSONDecodeError:
        reply = {}
    words = str(reply.get("gradient") or "").split()
    colors = [f"#{w[2:8]}{w[0:2]}".lower() for w in words if re.fullmatch(r"[0-9a-fA-F]{8}", w)]
    angle = next((int(w[:-3]) for w in words if re.fullmatch(r"\d+deg", w)), 0)
    colors = (colors + colors)[:2] if colors else ["#89b4faff", "#89b4faff"]
    return colors, angle


def animations() -> list[dict]:
    """Omarchy's animations (the user's looknfeel.lua wins per animation)."""
    found: dict[str, dict] = {}
    for path in ANIMATION_FILES:
        try:
            text = path.read_text()
        except OSError:
            continue
        for body in re.findall(r"hl\.animation\(\{(.*?)\}\)", text):
            fields = dict(re.findall(r'(\w+)\s*=\s*("[^"]*"|[\w.]+)', body))
            leaf = fields.get("leaf", "").strip('"')
            if leaf:
                found[leaf] = fields
    return list(found.values())


def animation_lua(speed: float) -> list[str]:
    """Omarchy's animations, each running `speed` times as fast."""
    lines = []
    for fields in animations():
        if "speed" not in fields:
            continue
        try:
            fields = {**fields, "speed": str(round(float(fields["speed"]) / speed, 2))}
        except ValueError:
            continue
        lines.append("hl.animation({ " + ", ".join(f"{k} = {v}" for k, v in fields.items()) + " })")
    return lines


def rgba(color: str) -> str:
    hexa = color.lstrip("#")
    return f"rgba({hexa}{'' if len(hexa) == 8 else 'ff'})"


def app_rule(rule: dict) -> str:
    pattern = "^(" + re.escape(rule["class"]) + ")$"
    return (f"hl.window_rule({{ name = {hypr.lua_string('hypr-screens-opacity-' + rule['class'])}, "
            f"match = {{ class = {hypr.lua_string(pattern)} }}, "
            f"opacity = \"{rule['active']} {rule['inactive']}\" }})")


def current() -> dict:
    """What Hyprland uses right now."""
    values = {}
    for key, (option, _path, kind, *_rest) in OPTIONS.items():
        try:
            reply = json.loads(hypr.hyprctl("-j", "getoption", option) or "{}")
        except json.JSONDecodeError:
            continue
        values[key] = parse_option(reply, kind)
    return values


def lua_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return repr(value)


def lua_table(look: dict) -> str:
    """hl.config({...}) for these values, nested like Hyprland's options, then
    the border gradient, the animations and the app rules (one per line)."""
    tree: dict = {}
    for key, value in normalize(look).items():
        if key not in OPTIONS:
            continue
        node = tree
        *parents, leaf = OPTIONS[key][1]
        for name in parents:
            node = node.setdefault(name, {})
        node[leaf] = value

    def render(node: dict) -> str:
        parts = [f"{name} = {render(child) if isinstance(child, dict) else lua_value(child)}"
                 for name, child in node.items()]
        return "{ " + ", ".join(parts) + " }"

    lines = [f"hl.config({render(tree)})"] if tree else []
    look = normalize(look)
    if "border_colors" in look:
        colors = ", ".join(f'"{rgba(c)}"' for c in look["border_colors"])
        lines.append(f"hl.config({{ general = {{ col = {{ active_border = {{ colors = {{ {colors} }}, "
                     f"angle = {look['border_angle']} }} }} }} }})")
    if "anim_speed" in look:
        lines += animation_lua(look["anim_speed"])
    lines += [app_rule(rule) for rule in look.get("apps", [])]
    return "\n".join(lines)


def apply(look: dict) -> None:
    """Show these values now (without saving them). Animations are always
    written, so a speed of 1 puts Omarchy's back."""
    code = lua_table(look)
    if "anim_speed" not in normalize(look):
        code = "\n".join([code, *animation_lua(1.0)]).strip()
    for line in code.splitlines():
        hypr.eval_lua(line)


def needs_reload(shown: dict, target: dict) -> bool:
    """Going from `shown` to `target` takes a reload: window rules cannot be
    taken back live, nor can the theme's own border."""
    shown, target = normalize(shown), normalize(target)
    return (shown.get("apps") != target.get("apps")
            or ("border_colors" in shown and "border_colors" not in target))


def show_by_reload(cfg: dict, target: dict) -> None:
    """Show `target` by writing it into the Lua file and reloading (the caller
    writes the saved look back the same way, or keeps it)."""
    from hypr_screens import keybinds

    keybinds.write({**cfg, "look": normalize(target)})
    hypr.hyprctl("reload")


def reset_to_omarchy() -> None:
    """Back to Omarchy's own values: reload the config (with no look in our file)."""
    hypr.hyprctl("reload")
