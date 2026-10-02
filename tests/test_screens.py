import json
import re

import pytest

from hypr_screens import apply, config, desktops, engine, hypr, keybinds, watch

LAPTOP_ID = "Samsung Display Corp.|0x4159|"
HP_ID = "HP Inc.|HP 32f|3CM1230QVW"
FUJITSU_ID = "Fujitsu Siemens Computers GmbH|B27-9 TS QHD|YVEB021757"


def monitor(name, make, model, serial="", workspace=1, x=0, y=0, width=1920, height=1080,
            focused=False, transform=0, scale=1.0, modes=None, number=0):
    return {
        "id": number, "name": name, "make": make, "model": model, "serial": serial,
        "description": f"{make} {model} {serial}".strip(),
        "x": x, "y": y, "width": width, "height": height, "refreshRate": 60.0,
        "scale": scale, "transform": transform, "focused": focused, "disabled": False,
        "activeWorkspace": {"id": workspace, "name": str(workspace)},
        "availableModes": modes or [f"{width}x{height}@60.00Hz"],
    }


def laptop(**kw):
    return monitor("eDP-1", "Samsung Display Corp.", "0x4159", **kw)


def hp(**kw):
    kw.setdefault("x", 1920)
    return monitor("DP-3", "HP Inc.", "HP 32f", "3CM1230QVW   ", width=2560, height=1440, number=1, **kw)


def fujitsu(**kw):
    kw.setdefault("x", 1920)
    return monitor("HDMI-A-1", "Fujitsu Siemens Computers GmbH", "B27-9 TS QHD", "YVEB021757",
                   width=2560, height=1440, number=1, **kw)


class FakeHyprland:
    """Answers hyprctl like Hyprland would and records what was sent."""

    def __init__(self, monitors, clients=(), workspaces=(), binds=(), active=""):
        self.monitors = list(monitors)
        self.clients = list(clients)
        self.workspaces = list(workspaces)
        self.binds = list(binds)
        self.active = active
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        answers = {
            ("-j", "monitors"): self.monitors,
            ("-j", "monitors", "all"): self.monitors,
            ("-j", "clients"): self.clients,
            ("-j", "workspaces"): self.workspaces,
            ("-j", "binds"): self.binds,
            ("-j", "activewindow"): {"address": self.active},
        }
        if args in answers:
            return json.dumps(answers[args])
        if args == ("cursorpos",):
            return "100, 200"
        if args[0] == "eval" and args[1].startswith("hl.monitor("):
            # Like Hyprland: the rule takes effect on the output.
            output = re.search(r'output = "([^"]+)"', args[1]).group(1)
            transform = int(re.search(r"transform = (\d)", args[1]).group(1))
            for monitor in self.monitors:
                if monitor["name"] == output:
                    monitor["transform"] = transform
        return "ok"

    @property
    def dispatched(self):
        return [call[1] for call in self.calls if call[0] == "dispatch"]

    @property
    def evaluated(self):
        return [call[1] for call in self.calls if call[0] == "eval"]

    @property
    def reloads(self):
        return self.calls.count(("reload",))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setattr(apply.time, "sleep", lambda seconds: None)


@pytest.fixture()
def fake(monkeypatch):
    def install(*monitors, **kw):
        hyprland = FakeHyprland(monitors, **kw)
        monkeypatch.setattr(hypr, "hyprctl", hyprland)
        return hyprland
    return install


def recorded(*monitors):
    cfg = config.default_config()
    config.record(cfg, list(monitors))
    return cfg


# --- config ---------------------------------------------------------------------------


def test_screens_are_identified_by_edid_not_connector():
    assert config.screen_id(hp()) == HP_ID
    assert config.screen_id(hp(**{"x": 0}) | {"name": "HDMI-A-2"}) == HP_ID
    assert config.screen_name(hp()) == "HP 32f"
    assert config.screen_name(fujitsu()) == "Fujitsu B27-9 TS QHD"
    assert config.screen_name(laptop()) == "Laptop"


def test_record_adds_new_screens_and_keeps_settings():
    monitors = [laptop(), hp(modes=["2560x1440@59.95Hz", "1920x1080@60.00Hz"])]
    cfg = recorded(*monitors)
    assert set(cfg["screens"]) == {LAPTOP_ID, HP_ID}
    assert cfg["screens"][LAPTOP_ID]["internal"] is True
    assert cfg["screens"][HP_ID]["modes"] == ["2560x1440@59.95", "1920x1080@60.00"]

    config.set_setting(cfg, LAPTOP_ID, "rotation", 180)
    assert config.record(cfg, monitors) is False
    assert config.get_setting(cfg, LAPTOP_ID, "rotation") == {"value": 180, "when": None}


def test_condition_limits_a_setting_to_another_screen_being_connected():
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, LAPTOP_ID, "rotation", 180)
    config.set_condition(cfg, LAPTOP_ID, "rotation", HP_ID)

    assert config.active_value(cfg, LAPTOP_ID, "rotation", {LAPTOP_ID, HP_ID}) == 180
    assert config.active_value(cfg, LAPTOP_ID, "rotation", {LAPTOP_ID}) is None
    assert config.summary(cfg, LAPTOP_ID) == "180° if HP 32f"


def test_config_round_trips_and_ignores_junk(tmp_path):
    cfg = recorded(laptop())
    cfg["keybinds"]["pop"] = ["SUPER + I", "SUPER + O"]
    config.save(cfg)
    loaded = config.load()
    assert loaded["keybinds"]["pop"] == ["SUPER + I", "SUPER + O"]
    assert config.normalize({"screens": {"x": {"settings": {"bogus": {"value": 1}}}}})["screens"]["x"]["settings"] == {}


# --- apply ------------------------------------------------------------------------------


def test_apply_sets_rotation_and_keeps_the_rest_as_it_is(fake):
    hyprland = fake(laptop(), hp())
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, LAPTOP_ID, "rotation", 180)
    config.set_condition(cfg, LAPTOP_ID, "rotation", HP_ID)

    assert apply.apply(cfg) == ["eDP-1"]
    assert hyprland.evaluated == [
        'hl.monitor({ output = "eDP-1", mode = "1920x1080@60.00", position = "0x0", scale = 1.0, transform = 2 })'
    ]

    # Hyprland now reports the rotation; nothing to do the second time.
    assert hyprland.monitors[0]["transform"] == 2
    hyprland.calls.clear()
    apply.apply(cfg)
    assert hyprland.evaluated == []


def test_apply_skips_monitors_already_in_the_wanted_state(fake):
    hyprland = fake(laptop(transform=2), hp())
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, LAPTOP_ID, "rotation", 180)

    assert apply.apply(cfg) == []
    assert hyprland.evaluated == []


def test_apply_reloads_once_when_a_condition_stops_holding(fake):
    hyprland = fake(laptop(), hp())
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, LAPTOP_ID, "rotation", 180)
    config.set_condition(cfg, LAPTOP_ID, "rotation", HP_ID)
    apply.apply(cfg)

    hyprland.monitors = [laptop(transform=2)]   # HP unplugged
    assert apply.apply(cfg) == ["reload"]
    assert hyprland.reloads == 1
    assert apply.load_applied() == {}


def test_position_scale_and_mode_of_an_external_screen(fake):
    hyprland = fake(laptop(), hp())
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, HP_ID, "position", "left")
    config.set_setting(cfg, HP_ID, "scale", 1.25)
    config.set_setting(cfg, HP_ID, "mode", "1920x1080@60.00")
    config.set_setting(cfg, LAPTOP_ID, "position", "left")   # ignored: laptop is the anchor

    apply.apply(cfg)
    assert hyprland.evaluated == [
        'hl.monitor({ output = "DP-3", mode = "1920x1080@60.00", position = "auto-left", scale = 1.25, transform = 0 })'
    ]


def test_quarter_turn_lets_hyprland_place_the_screen(fake):
    hyprland = fake(laptop(), hp())
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, HP_ID, "rotation", 90)
    apply.apply(cfg)
    assert 'position = "auto"' in hyprland.evaluated[0]


# --- desktops -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("laptop_value", "external_value", "default", "role"),
    [
        (True, None, "off", "panel"),
        (None, True, "off", "external"),
        (True, True, "off", "panel"),
        (None, None, "external", "external"),
        (None, False, "external", None),
        (None, None, "off", None),
        (False, None, "panel", None),
    ],
)
def test_role_comes_from_settings_then_default(laptop_value, external_value, default, role):
    cfg = recorded(laptop(), hp())
    cfg["default_fixed"] = default
    if laptop_value is not None:
        config.set_setting(cfg, LAPTOP_ID, "one_desktop", laptop_value)
    if external_value is not None:
        config.set_setting(cfg, HP_ID, "one_desktop", external_value)
    assert desktops.decide_role(cfg, LAPTOP_ID, HP_ID, {LAPTOP_ID, HP_ID}) == role


def test_swap_override_wins_until_unplugged():
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, LAPTOP_ID, "one_desktop", True)
    desktops.save_override(HP_ID, "external")
    assert desktops.decide_role(cfg, LAPTOP_ID, HP_ID, {LAPTOP_ID, HP_ID}) == "external"
    assert desktops.decide_role(cfg, LAPTOP_ID, FUJITSU_ID, {LAPTOP_ID, FUJITSU_ID}) == "panel"


def test_switch_pins_the_desktop_to_the_desk_screen(fake):
    hyprland = fake(laptop(workspace=99), hp(workspace=2, focused=True))
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, LAPTOP_ID, "one_desktop", True)

    desktops.switch(cfg, "switch", 3)
    assert hyprland.evaluated == ['hl.workspace_rule({ workspace = "3", monitor = "DP-3" })']
    assert hyprland.dispatched == [
        'hl.dsp.workspace.move({ workspace = "3", monitor = "DP-3" })',
        'hl.dsp.focus({ workspace = "3" })',
    ]


def test_switch_without_fixed_screen_is_plain_hyprland(fake):
    hyprland = fake(laptop(focused=True))
    desktops.switch(config.default_config(), "move", 4)
    assert hyprland.dispatched == ['hl.dsp.window.move({ workspace = "4" })']
    assert hyprland.evaluated == []


def test_docking_keeps_the_laptops_windows_on_the_laptop(fake):
    hyprland = fake(
        laptop(workspace=1, focused=True), hp(workspace=5),
        clients=[{"address": "0xa", "workspace": {"id": 1}}, {"address": "0xb", "workspace": {"id": 2}}],
    )
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, LAPTOP_ID, "one_desktop", True)

    desktops.arrange(desktops.resolve(cfg), docking=True)
    assert 'hl.dsp.window.move({ workspace = "99", follow = false, window = "address:0xa" })' in hyprland.dispatched
    assert not any("0xb" in line for line in hyprland.dispatched)
    assert hyprland.dispatched[-2:] == [
        'hl.dsp.focus({ monitor = "DP-3" })',
        "hl.dsp.cursor.move({ x = 100, y = 200 })",
    ]


def test_swap_trades_the_screens_and_remembers_it(fake):
    hyprland = fake(laptop(workspace=99), hp(workspace=1, focused=True))
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, LAPTOP_ID, "one_desktop", True)

    desktops.swap(cfg)
    assert hyprland.dispatched[0] == 'hl.dsp.workspace.swap_monitors({ monitor1 = "eDP-1", monitor2 = "DP-3" })'
    assert desktops.load_override() == {"external": HP_ID, "role": "external"}


def test_swapping_back_forgets_the_swap(fake):
    fake(laptop(workspace=99), hp(workspace=1, focused=True))
    cfg = recorded(laptop(), hp())
    config.set_setting(cfg, LAPTOP_ID, "one_desktop", True)
    desktops.swap(cfg)
    assert desktops.status(cfg)["swapped"] is False or desktops.load_override()
    desktops.swap(cfg, "panel")
    assert desktops.load_override() == {}
    assert desktops.status(cfg)["swapped"] is False


def test_undock_folds_the_fixed_workspace_into_the_laptops_desktop(fake):
    hyprland = fake(
        laptop(workspace=3, focused=True),
        clients=[{"address": "0xa", "workspace": {"id": 99}}],
        workspaces=[{"id": 3, "windows": 1}, {"id": 99, "windows": 1}],
    )
    desktops.save_override(HP_ID, "external")
    desktops.undock(desktops.resolve(config.default_config()))
    assert hyprland.dispatched == [
        'hl.dsp.window.move({ workspace = "3", follow = false, window = "address:0xa" })',
        'hl.dsp.focus({ workspace = "3" })',
    ]
    assert desktops.load_override() == {}


# --- engine -------------------------------------------------------------------------------


def test_step_value_cycles_through_unset():
    cfg = recorded(laptop(), hp())
    for expected in (0, 90, 180, 270, None):
        engine.step_value(cfg, LAPTOP_ID, "rotation", 1)
        assert (config.get_setting(cfg, LAPTOP_ID, "rotation") or {}).get("value") == expected
    engine.step_value(cfg, LAPTOP_ID, "rotation", -1)
    assert config.get_setting(cfg, LAPTOP_ID, "rotation")["value"] == 270


def test_step_condition_needs_a_value_and_cycles_other_screens():
    cfg = recorded(laptop(), hp(), fujitsu())
    assert engine.step_condition(cfg, LAPTOP_ID, "rotation", 1) is False
    config.set_setting(cfg, LAPTOP_ID, "rotation", 180)
    seen = []
    for _ in range(3):
        engine.step_condition(cfg, LAPTOP_ID, "rotation", 1)
        seen.append(config.get_setting(cfg, LAPTOP_ID, "rotation")["when"])
    assert seen == [FUJITSU_ID, HP_ID, None]


def test_screen_list_puts_laptop_then_favorites_then_known():
    cfg = recorded(laptop(), hp(), fujitsu())
    cfg["screens"][FUJITSU_ID]["favorite"] = True
    rows = engine.screen_rows(cfg, {LAPTOP_ID, HP_ID})
    assert [(row["section"], row["name"]) for row in rows] == [
        ("Laptop", "Laptop"),
        ("Favorites", "Fujitsu B27-9 TS QHD"),
        ("Known screens", "HP 32f"),
    ]
    assert not [s for s in rows[0]["settings"] if s["key"] == "position"]


# --- keybinds -----------------------------------------------------------------------------


def test_combos_are_normalized_and_get_their_keycode_twin():
    assert keybinds.normalize("shift + super + period") == "SUPER + SHIFT + PERIOD"
    assert keybinds.normalize("SUPER + NOPE + X") == ""
    assert keybinds.spellings("SUPER + SHIFT + F23") == ["SUPER + SHIFT + F23", "SUPER + SHIFT + code:201"]
    assert keybinds.spellings("SUPER + 3") == ["SUPER + 3", "SUPER + code:12"]


def test_conflicts_see_keycode_binds_and_skip_our_own():
    binds = [
        {"modmask": 65, "key": "", "keycode": 201, "description": "Omarchy menu", "submap": ""},
        {"modmask": 64, "key": "PERIOD", "keycode": 0, "description": "Minimizer menu", "submap": ""},
        {"modmask": 64, "key": "PERIOD", "keycode": 0, "description": "Emoji picker", "submap": ""},
    ]
    assert keybinds.conflicts("SUPER + SHIFT + F23", binds) == ["Omarchy menu"]
    assert keybinds.conflicts("SUPER + PERIOD", binds) == ["Emoji picker"]


def test_set_key_rejects_a_combo_we_already_use(fake):
    fake(laptop())
    cfg = config.default_config()
    with pytest.raises(ValueError, match="Minimize window"):
        keybinds.set_key(cfg, "pop", 1, "super + m")
    assert keybinds.set_key(cfg, "pop", 1, "SUPER + O") == ""
    assert cfg["keybinds"]["pop"] == ["SUPER + I", "SUPER + O"]


def test_rendered_lua_unbinds_before_binding():
    cfg = config.default_config()
    cfg["keybinds"]["minimizer_menu"] = ["SUPER + PERIOD", "SUPER + SHIFT + F23"]
    cfg["desktop_keys"] = True
    lua = keybinds.render(cfg)
    assert 'hl.unbind("SUPER + SHIFT + code:201")' in lua
    assert (
        'hl.bind("SUPER + SHIFT + F23", hl.dsp.exec_cmd("hypr-minimizer menu"), '
        '{ description = "Minimizer menu" })' in lua
    )
    assert 'hl.bind("SUPER + code:12", hl.dsp.exec_cmd("hypr-screens switch 3")' in lua
    assert 'hl.unbind("SUPER + 3")' in lua
    assert 'hl.define_submap("hypr-screens-record"' in lua
    assert 'hl.exec_cmd("hypr-screens watch")' in lua
    assert 'hl.exec_cmd("hypr-screens tray")' in lua
    assert 'hl.on("window.urgent"' in lua
    assert "focus_on_activate = false" in lua
    assert 'hl.window_rule({ match = { class = "^(io\\\\.github\\\\.slowlytz\\\\.HyprScreens)$" }, float = true' in lua
    assert 'layer.namespace ~= "omarchy-menu"' in lua
    assert "monitor.focused" in lua and "workspace_swipe_create_new" in lua
    assert "hypr-screens watch" not in keybinds.render(cfg, runtime=True)
    assert "window.urgent" not in keybinds.render(cfg, runtime=True)
    assert "screens menu" not in lua.lower()


def test_add_require_appends_once_and_keeps_a_backup(tmp_path):
    hyprland = keybinds.hyprland_file()
    hyprland.parent.mkdir(parents=True)
    hyprland.write_text('require("hypr.bindings")\n')
    keybinds.add_require()
    keybinds.add_require()
    assert hyprland.read_text().count(keybinds.REQUIRE_LINE) == 1
    assert hyprland.with_suffix(".lua.bak-hypr-screens").read_text() == 'require("hypr.bindings")\n'
    assert keybinds.is_required()


# --- watch --------------------------------------------------------------------------------


def test_watch_folds_a_burst_into_one_kind():
    lines = [b"monitoraddedv2>>2,DP-3,HP", b"activewindow>>x", b"configreloaded>>"]
    assert watch.kinds(lines) == {"added", "reload"}
    assert watch.strongest({"reload", "removed"}) == "removed"
    assert watch.strongest(set()) == ""
