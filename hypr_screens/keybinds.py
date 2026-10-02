"""Keybinds: two keys per action, conflict checks, and the generated Lua file.

Only window keys live on the keyboard; everything else is in the settings
window (tray icon).

hypr-screens owns ~/.config/hypr/hypr_screens.lua, loaded by one line at the end
of hyprland.lua (REQUIRE_LINE). It unbinds whatever else sits on our keys first,
so nothing fires twice. Changes also go live at once via `hyprctl eval` -- a
reload would reset the monitor settings for a moment.
"""
import os
from pathlib import Path

from hypr_screens import config, hypr

RECORD_SUBMAP = "hypr-screens-record"
# The settings window (gui/app.py APP_ID, gui/window.py WIDTH x HEIGHT).
SETTINGS_CLASS = "^(io\\.github\\.slowlytz\\.HyprScreens)$"
SETTINGS_SIZE = (1000, 720)
# The Omarchy menu (SUPER+SPACE) and how long after it closes an app asking to
# be shown counts as started from it: a running app needs a moment to answer.
LAUNCHER_NAMESPACE = "omarchy-menu"
LAUNCH_WINDOW_MS = 5000
REQUIRE_LINE = 'require("hypr.hypr_screens")'

MODIFIERS = {
    "SHIFT": 1, "CAPS": 2, "CTRL": 4, "CONTROL": 4, "ALT": 8, "MOD2": 16, "MOD3": 32,
    "SUPER": 64, "WIN": 64, "LOGO": 64, "MOD4": 64, "MOD5": 128,
}
MODIFIER_ORDER = ["SUPER", "CTRL", "ALT", "SHIFT"]

# Keys whose keycode does not depend on the layout, so a keysym bind and a
# `code:` bind on the same key are recognised as the same key.
KEYCODES = {
    **{f"F{n}": 66 + n for n in range(1, 11)},
    "F11": 95, "F12": 96,
    **{f"F{n}": 178 + n for n in range(13, 25)},
    **{str(n): 9 + n for n in range(1, 10)}, "0": 19,
}

# Desktop keys: digits by keycode (layout independent), like Omarchy binds them.
DESKTOP_CODES = list(range(10, 20))
DESKTOP_BINDS = [
    ("SUPER", "switch", "Show desktop"),
    ("SUPER + SHIFT", "move", "Move window to desktop"),
    ("SUPER + SHIFT + ALT", "move-silent", "Move window to desktop silently"),
]
CYCLE_BINDS = [
    ("SUPER + TAB", "cycle", "Next visible window"),
    ("SUPER + SHIFT + TAB", "cycle prev", "Previous visible window"),
]


def lua_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "hypr" / "hypr_screens.lua"


def hyprland_file() -> Path:
    return lua_file().with_name("hyprland.lua")


# --- combos ------------------------------------------------------------------------


def parse(combo: str) -> tuple[int, str] | None:
    parts = [part.strip() for part in str(combo or "").split("+") if part.strip()]
    if not parts:
        return None
    *mods, key = parts
    mask = 0
    for mod in mods:
        if mod.upper() not in MODIFIERS:
            return None
        mask |= MODIFIERS[mod.upper()]
    key = key if key.lower().startswith("code:") else key.upper()
    return mask, key


def normalize(combo: str) -> str:
    """Canonical spelling, e.g. "shift+super+period" -> "SUPER + SHIFT + PERIOD"."""
    parsed = parse(combo)
    if parsed is None:
        return ""
    mask, key = parsed
    mods = [mod for mod in MODIFIER_ORDER if mask & MODIFIERS[mod]]
    return " + ".join([*mods, key])


def keycode(key: str) -> int | None:
    if key.lower().startswith("code:"):
        try:
            return int(key[5:])
        except ValueError:
            return None
    return KEYCODES.get(key.upper())


def mods_text(mask: int) -> str:
    return " + ".join(mod for mod in MODIFIER_ORDER if mask & MODIFIERS[mod])


def spellings(combo: str) -> list[str]:
    """The combo plus its `code:` twin, so both forms get unbound."""
    parsed = parse(combo)
    if parsed is None:
        return []
    mask, key = parsed
    result = [normalize(combo)]
    code = keycode(key)
    if code is not None and not key.lower().startswith("code:"):
        mods = mods_text(mask)
        result.append(f"{mods} + code:{code}" if mods else f"code:{code}")
    return result


def same_key(combo: str, bind: dict) -> bool:
    parsed = parse(combo)
    if parsed is None or bind.get("submap"):
        return False
    mask, key = parsed
    if int(bind.get("modmask") or 0) != mask:
        return False
    if str(bind.get("key") or "").upper() == key.upper() and bind.get("key"):
        return True
    code = keycode(key)
    return code is not None and int(bind.get("keycode") or 0) == code


def own_descriptions() -> set[str]:
    labels = {label for _action, label, _command in config.ACTIONS}
    labels |= {label for _mods, _command, label in DESKTOP_BINDS}
    labels |= {label for _combo, _command, label in CYCLE_BINDS}
    return labels


def conflicts(combo: str, binds: list[dict] | None = None, ignore: set[str] | None = None) -> list[str]:
    """What else is bound to `combo` right now (by description)."""
    binds = hypr.query_list("binds") if binds is None else binds
    ignore = own_descriptions() if ignore is None else ignore
    return [
        str(bind.get("description") or bind.get("arg") or "?")
        for bind in binds
        if same_key(combo, bind) and str(bind.get("description") or "") not in ignore
    ]


def taken_by_us(cfg: dict, combo: str, except_slot: tuple[str, int] | None = None) -> str | None:
    target = normalize(combo)
    for action, label, _command in config.ACTIONS:
        for slot, other in enumerate(cfg["keybinds"][action]):
            if (action, slot) != except_slot and normalize(other) == target and target:
                return label
    return None


# --- the Lua file ------------------------------------------------------------------------


def lua_quote(value: str) -> str:
    return hypr.lua_string(value)


def bind_line(combo: str, command: str, description: str) -> list[str]:
    lines = [f"hl.unbind({lua_quote(spelling)})" for spelling in spellings(combo)]
    lines.append(
        f"hl.bind({lua_quote(normalize(combo))}, hl.dsp.exec_cmd({lua_quote(command)}), "
        f"{{ description = {lua_quote(description)} }})"
    )
    return lines


def render(cfg: dict, runtime: bool = False) -> str:
    lines = [
        "-- Generated by hypr-screens. Do not edit: change keys in the settings window",
        "-- (tray icon) or with `hypr-screens bind`. Loaded by this line in hyprland.lua:",
        f"--   {REQUIRE_LINE}",
        "",
    ]
    for action, label, command in config.ACTIONS:
        for combo in cfg["keybinds"][action]:
            if parse(combo):
                lines += bind_line(combo, command, label)
    if cfg.get("desktop_keys"):
        lines.append("")
        lines.append("-- Desktop keys: desktops 1-10 stay on the non-fixed screen.")
        for index, code in enumerate(DESKTOP_CODES, start=1):
            for mods, command, label in DESKTOP_BINDS:
                lines.append(f"hl.unbind({lua_quote(f'{mods} + {index % 10}')})")
                lines += bind_line(f"{mods} + code:{code}", f"hypr-screens {command} {index}", label)
        for combo, command, label in CYCLE_BINDS:
            lines += bind_line(combo, f"hypr-screens {command}", label)
    lines += [
        "",
        "-- Empty keymap used while the menu records a new shortcut, so keys that are",
        "-- already bound reach the menu instead of firing. Escape always gets out.",
        f"hl.define_submap({lua_quote(RECORD_SUBMAP)}, function()",
        '  hl.bind("escape", hl.dsp.submap("reset"))',
        "end)",
    ]
    if not runtime:
        lines += [
            "",
            "-- The settings window floats, sized and centred, from its first frame.",
            f"hl.window_rule({{ match = {{ class = {lua_quote(SETTINGS_CLASS)} }}, "
            f"float = true, size = {{ {SETTINGS_SIZE[0]}, {SETTINGS_SIZE[1]} }}, center = true }})",
            "",
            "-- Watcher: applies monitor settings on hotplug and config reloads.",
            "-- Tray: the icon that opens the settings window.",
            'hl.on("hyprland.start", function()',
            '  hl.exec_cmd("hypr-screens watch")',
            '  hl.exec_cmd("hypr-screens tray")',
            "end)",
            "",
            "-- An app started again from the Omarchy menu while it already runs asks to be",
            "-- shown; it comes to the current desktop instead of Hyprland switching to its",
            "-- desktop -- or opening special:minimized and showing every minimized window.",
            "-- Any app can ask that at any time, though (Chromium/Electron apps do on new",
            "-- messages), so only a request shortly after the menu closed counts; others",
            "-- are ignored (focus_on_activate off) and nothing moves.",
            "hl.config({ misc = { focus_on_activate = false } })",
            "local launched, launches = false, 0",
            'hl.on("layer.closed", function(layer)',
            f"  if not layer or layer.namespace ~= {lua_quote(LAUNCHER_NAMESPACE)} then return end",
            "  launches = launches + 1",
            "  local this = launches",
            "  launched = true",
            f"  hl.timer(function() if launches == this then launched = false end end, "
            f'{{ timeout = {LAUNCH_WINDOW_MS}, type = "oneshot" }})',
            "end)",
            "-- Switching desktop ends it: Electron apps ask for focus back when a switch",
            "-- takes it from them, which would drag them along.",
            'hl.on("workspace.active", function() launched = false end)',
            'hl.on("window.urgent", function(window)',
            "  if not launched or not window or not window.mapped then return end",
            "  launched = false  -- one window per launch",
            "  local here = hl.get_active_workspace()",
            "  local there = window.workspace",
            "  if not here or not there then return end",
            '  local target = "address:" .. window.address',
            "  if not window.pinned and there.id ~= here.id and not (there.special and there.visible) then",
            "    hl.dispatch(hl.dsp.window.move({ workspace = tostring(here.id), follow = false, window = target }))",
            "  end",
            "  hl.dispatch(hl.dsp.focus({ window = target }))",
            "end)",
        ]
    return "\n".join(lines) + "\n"


def write(cfg: dict) -> Path:
    path = lua_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(cfg))
    return path


def go_live(old: dict | None, new: dict) -> None:
    """Make the new keys work now: drop keys that are gone, rebind the rest."""
    lines = []
    if old is not None:
        kept = {normalize(combo) for keys in new["keybinds"].values() for combo in keys}
        for keys in old["keybinds"].values():
            for combo in keys:
                if parse(combo) and normalize(combo) not in kept:
                    lines += [f"hl.unbind({lua_quote(spelling)})" for spelling in spellings(combo)]
        if old.get("desktop_keys") and not new.get("desktop_keys"):
            for code in DESKTOP_CODES:
                for mods, _command, _label in DESKTOP_BINDS:
                    lines.append(f"hl.unbind({lua_quote(f'{mods} + code:{code}')})")
            for combo, _command, _label in CYCLE_BINDS:
                lines.append(f"hl.unbind({lua_quote(combo)})")
    code = "\n".join(lines) + "\n" + render(new, runtime=True)
    hypr.eval_lua(code)


def is_required() -> bool:
    try:
        return REQUIRE_LINE in hyprland_file().read_text()
    except OSError:
        return False


def add_require() -> Path:
    """Append the require line to hyprland.lua (keeps a backup next to it)."""
    path = hyprland_file()
    text = path.read_text()
    backup = path.with_suffix(".lua.bak-hypr-screens")
    if not backup.exists():
        backup.write_text(text)
    if REQUIRE_LINE not in text:
        path.write_text(text.rstrip("\n") + f"\n\n-- hypr-screens: keys, desktop keys, monitor watcher\n{REQUIRE_LINE}\n")
    return path


def set_key(cfg: dict, action: str, slot: int, combo: str) -> str:
    """Store a key; returns a note about what it replaces (or "")."""
    if action not in cfg["keybinds"] or slot not in (0, 1):
        raise ValueError("unknown action or slot")
    combo = normalize(combo) if combo else ""
    if combo and parse(combo) is None:
        raise ValueError(f"not a key combination: {combo}")
    notes = []
    if combo:
        mine = taken_by_us(cfg, combo, except_slot=(action, slot))
        if mine:
            raise ValueError(f"{combo} is already used for {mine}")
        others = conflicts(combo)
        if others:
            notes.append(f"{combo} replaces: {', '.join(others)}")
    cfg["keybinds"][action][slot] = combo
    return "; ".join(notes)
