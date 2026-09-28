"""The fixed screen: with one external monitor attached, one screen shows only
workspace FIXED_WS and never changes, the other holds desktops 1-10.

Which screen is fixed (the "role": "panel" = laptop, "external"):
  1. a temporary swap (`hypr-screens swap`), until the monitor is unplugged,
  2. the "one_desktop" setting of either screen (the laptop wins a tie),
  3. the global default, unless the screen it would pick says "no".
Without a role, desktops behave like stock Hyprland.
"""
import json
import os
from dataclasses import dataclass, field

from hypr_screens import config, hypr

FIXED_WS = int(os.environ.get("HYPR_SCREENS_FIXED_WS", "99"))
DESKTOPS = range(1, 11)


def override_file():
    return config.runtime_dir() / "fixed.json"


def load_override() -> dict:
    try:
        override = json.loads(override_file().read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return override if isinstance(override, dict) else {}


def save_override(external_id: str, role: str) -> None:
    override_file().write_text(json.dumps({"external": external_id, "role": role}) + "\n")


def clear_override() -> None:
    override_file().unlink(missing_ok=True)


@dataclass
class Screens:
    monitors: list[dict] = field(default_factory=list)
    panel: str = ""
    external: str = ""
    panel_id: str = ""
    external_id: str = ""
    role: str | None = None

    @property
    def fixed(self) -> str:
        return self.external if self.role == "external" else self.panel

    @property
    def desk(self) -> str:
        return self.panel if self.role == "external" else self.external

    def workspace_on(self, name: str) -> int:
        for monitor in self.monitors:
            if monitor.get("name") == name:
                return int((monitor.get("activeWorkspace") or {}).get("id") or 0)
        return 0

    @property
    def focused(self) -> dict:
        return next((monitor for monitor in self.monitors if monitor.get("focused")), {})


def decide_role(cfg: dict, panel_id: str, external_id: str, ids: set[str]) -> str | None:
    override = load_override()
    if override.get("external") == external_id and override.get("role") in ("panel", "external"):
        return override["role"]
    panel = config.active_value(cfg, panel_id, "one_desktop", ids)
    external = config.active_value(cfg, external_id, "one_desktop", ids)
    if panel is True:
        return "panel"
    if external is True:
        return "external"
    default = cfg.get("default_fixed", "off")
    if default == "panel" and panel is None:
        return "panel"
    if default == "external" and external is None:
        return "external"
    return None


def resolve(cfg: dict, monitors: list[dict] | None = None) -> Screens:
    monitors = [m for m in (monitors if monitors is not None else hypr.monitors()) if not m.get("disabled")]
    screens = Screens(monitors=monitors)
    panel = next((m for m in monitors if config.is_internal(m)), None)
    external = next((m for m in monitors if not config.is_internal(m)), None)
    if panel:
        screens.panel, screens.panel_id = str(panel["name"]), config.screen_id(panel)
    if external:
        screens.external, screens.external_id = str(external["name"]), config.screen_id(external)
    if panel and external:
        ids = set(config.connected(monitors))
        screens.role = decide_role(cfg, screens.panel_id, screens.external_id, ids)
    return screens


# --- building blocks -----------------------------------------------------------


def move_windows(source: int, target: int) -> None:
    """Move every window of workspace `source` to `target` without following."""
    for client in hypr.query_list("clients"):
        if (client.get("workspace") or {}).get("id") == source:
            hypr.dispatch(
                f'hl.dsp.window.move({{ workspace = "{target}", follow = false, window = "address:{client["address"]}" }})'
            )


def pin(workspace: int, monitor: str) -> None:
    """The rule covers a workspace that does not exist yet; the move pulls over
    one that already sits elsewhere -- without it, focusing it would just jump
    to whichever monitor owns it."""
    hypr.eval_lua(f'hl.workspace_rule({{ workspace = "{workspace}", monitor = {hypr.lua_string(monitor)} }})')
    hypr.dispatch(f'hl.dsp.workspace.move({{ workspace = "{workspace}", monitor = {hypr.lua_string(monitor)} }})')


def hold_fixed(screens: Screens) -> None:
    """Keep the fixed screen on its workspace, without stealing focus."""
    fresh = resolve_names(screens)
    if fresh.workspace_on(screens.fixed) == FIXED_WS:
        return
    pin(FIXED_WS, screens.fixed)
    refocus = fresh.focused.get("name", "")
    hypr.dispatch(f"hl.dsp.focus({{ monitor = {hypr.lua_string(screens.fixed)} }})")
    hypr.dispatch(f'hl.dsp.focus({{ workspace = "{FIXED_WS}" }})')
    if refocus and refocus != screens.fixed:
        hypr.dispatch(f"hl.dsp.focus({{ monitor = {hypr.lua_string(refocus)} }})")


def resolve_names(screens: Screens) -> Screens:
    """Same roles, fresh monitor data."""
    return Screens(
        monitors=[m for m in hypr.monitors() if not m.get("disabled")],
        panel=screens.panel,
        external=screens.external,
        panel_id=screens.panel_id,
        external_id=screens.external_id,
        role=screens.role,
    )


def cursor() -> tuple[int, int] | None:
    try:
        x, y = hypr.hyprctl("cursorpos").replace(",", " ").split()[:2]
        return int(float(x)), int(float(y))
    except ValueError:
        return None


def mark_rules(active: bool) -> None:
    marker = config.runtime_dir() / "rules"
    if active:
        marker.touch()
    else:
        marker.unlink(missing_ok=True)


def rules_marked() -> bool:
    return (config.runtime_dir() / "rules").exists()


# --- actions ---------------------------------------------------------------------


def arrange(screens: Screens, docking: bool = False) -> None:
    """Put the fixed workspace and desktops 1-10 where the role wants them.

    On docking, the laptop's visible windows stay on the laptop when it becomes
    the fixed screen, and focus goes to the desk screen (the pointer stays put).
    """
    if not screens.role:
        return
    if docking and screens.role == "panel":
        showing = screens.workspace_on(screens.fixed)
        if showing in DESKTOPS:
            pin(FIXED_WS, screens.fixed)
            move_windows(showing, FIXED_WS)
    position = cursor() if docking else None
    pin(FIXED_WS, screens.fixed)
    for workspace in DESKTOPS:
        pin(workspace, screens.desk)
    mark_rules(True)
    hold_fixed(screens)
    if docking:
        hypr.dispatch(f"hl.dsp.focus({{ monitor = {hypr.lua_string(screens.desk)} }})")
        if position:
            hypr.dispatch(f"hl.dsp.cursor.move({{ x = {position[0]}, y = {position[1]} }})")


def fold_fixed(screens: Screens) -> None:
    """Without a fixed screen its workspace means nothing: move its windows to
    the desktop the laptop shows, or desktop 1."""
    workspaces = {w.get("id") for w in hypr.query_list("workspaces")}
    if FIXED_WS not in workspaces:
        return
    target = screens.workspace_on(screens.panel)
    if target not in DESKTOPS:
        target = 1
    move_windows(FIXED_WS, target)
    hypr.dispatch(f'hl.dsp.focus({{ workspace = "{target}" }})')


def undock(screens: Screens) -> None:
    clear_override()
    fold_fixed(screens)


def swap(cfg: dict, want: str | None = None) -> Screens:
    """Make `want` ("panel"/"external") the fixed screen, or toggle; lasts until
    the monitor is unplugged. Windows and layouts travel with their workspaces."""
    screens = resolve(cfg)
    if not screens.external:
        raise RuntimeError("no external monitor")
    current = screens.role or "panel"
    want = want or ("external" if current == "panel" else "panel")
    if want != screens.role:
        if screens.role:
            hypr.dispatch(
                f"hl.dsp.workspace.swap_monitors({{ monitor1 = {hypr.lua_string(screens.panel)}, "
                f"monitor2 = {hypr.lua_string(screens.external)} }})"
            )
        save_override(screens.external_id, want)
        screens.role = want
    arrange(resolve_names(screens), docking=screens.role is not None)
    return screens


def switch(cfg: dict, action: str, index: int) -> None:
    if index not in DESKTOPS:
        raise ValueError("desktop must be 1-10")
    screens = resolve(cfg)
    if screens.role:
        pin(index, screens.desk)
    if action == "switch":
        hypr.dispatch(f'hl.dsp.focus({{ workspace = "{index}" }})')
    elif action == "move":
        hypr.dispatch(f'hl.dsp.window.move({{ workspace = "{index}" }})')
    else:
        hypr.dispatch(f'hl.dsp.window.move({{ workspace = "{index}", follow = false }})')
    if screens.role:
        hold_fixed(screens)


def step(cfg: dict, direction: int) -> None:
    """Switch to the next/previous desktop that has windows."""
    screens = resolve(cfg)
    current = screens.workspace_on(screens.desk) if screens.role else int(
        (screens.focused.get("activeWorkspace") or {}).get("id") or 0
    )
    used = sorted(
        {w["id"] for w in hypr.query_list("workspaces") if w.get("id") in DESKTOPS and w.get("windows", 0) > 0}
        | ({current} if current in DESKTOPS else set())
    )
    if not used:
        return
    target = used[0] if current not in used else used[(used.index(current) + direction) % len(used)]
    switch(cfg, "switch", target)


def cycle(direction: int) -> None:
    """Focus the next visible window in screen order (left to right)."""
    monitors = [m for m in hypr.monitors() if not m.get("disabled")]
    visible = {(m.get("activeWorkspace") or {}).get("id") for m in monitors}
    focused_id = next((m.get("id") for m in monitors if m.get("focused")), None)
    active = str((hypr.query("activewindow") or {}).get("address") or "")
    windows = sorted(
        (
            c
            for c in hypr.query_list("clients")
            if c.get("mapped") and (c.get("workspace") or {}).get("id") in visible
        ),
        key=lambda c: (c["at"][0], c["at"][1], c["address"]),
    )
    if not windows:
        return
    addresses = [c["address"] for c in windows]
    target = windows[0] if active not in addresses else windows[(addresses.index(active) + direction) % len(windows)]
    # Focusing a window on another monitor makes Hyprland focus that monitor
    # first, which briefly activates its last window -- a border flicker.
    # Warping the pointer onto the target focuses it in one step (follow_mouse).
    if target.get("monitor") != focused_id:
        x = target["at"][0] + target["size"][0] // 2
        y = target["at"][1] + target["size"][1] // 2
        hypr.dispatch(f"hl.dsp.cursor.move({{ x = {x}, y = {y} }})")
    hypr.dispatch(f'hl.dsp.focus({{ window = "address:{target["address"]}" }})')


def status(cfg: dict) -> dict:
    screens = resolve(cfg)
    override = load_override()
    return {
        "panel": screens.panel or None,
        "external": screens.external or None,
        "panel_id": screens.panel_id or None,
        "external_id": screens.external_id or None,
        "fixed": screens.role,
        "swapped": bool(screens.external_id and override.get("external") == screens.external_id),
        "fixed_workspace": FIXED_WS,
    }
