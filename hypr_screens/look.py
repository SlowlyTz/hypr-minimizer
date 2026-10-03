"""Window look: gaps, rounding, border, blur and opacity (Personalization →
Window). Values the user set are kept in config["look"] and written into the
generated Lua file (keybinds.render), which loads after Omarchy's theme and so
wins; an empty look leaves everything to Omarchy.
"""
import json

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
    """hl.config({...}) for these values, nested like Hyprland's options."""
    tree: dict = {}
    for key, value in normalize(look).items():
        node = tree
        *parents, leaf = OPTIONS[key][1]
        for name in parents:
            node = node.setdefault(name, {})
        node[leaf] = value

    def render(node: dict) -> str:
        parts = [f"{name} = {render(child) if isinstance(child, dict) else lua_value(child)}"
                 for name, child in node.items()]
        return "{ " + ", ".join(parts) + " }"

    return f"hl.config({render(tree)})" if tree else ""


def apply(look: dict) -> None:
    """Show these values now (without saving them)."""
    code = lua_table(look)
    if code:
        hypr.eval_lua(code)


def reset_to_omarchy() -> None:
    """Back to Omarchy's own values: reload the config (with no look in our file)."""
    hypr.hyprctl("reload")
