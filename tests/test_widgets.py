"""Desktop widgets: settings, what the shell plugin reads, and wiring the bar."""
import json

import pytest

from hypr_screens import config, install, widgets


def test_defaults_and_limits():
    all_off = widgets.normalize({})
    assert set(all_off) == set(widgets.KINDS) and not any(w["enabled"] for w in all_off.values())
    visualizer = widgets.normalize({"visualizer": {"enabled": True, "bars": 500, "where": "moon", "x": 3,
                                                    "monitors": {"mode": "screen", "screen": "HP|32f|1"}}})["visualizer"]
    assert visualizer["bars"] == 64 and visualizer["where"] == "both" and visualizer["x"] == 1.0
    assert visualizer["monitors"] == {"mode": "screen", "screen": "HP|32f|1"}
    assert widgets.normalize({"clock": {"size": 10}})["clock"]["size"] == 30


def test_choices_switches_and_opacity():
    state = widgets.normalize({"lyrics": {"highlight": "word", "align": "middle", "opacity": 5, "hide_paused": True},
                               "clock": {"hours": "12", "color": "gradient"},
                               "system": {"cpu": False, "curves": False},
                               "visualizer": {"style": "mirrored", "color": "white"}})
    assert (state["lyrics"]["highlight"], state["lyrics"]["align"]) == ("word", "center")
    assert state["lyrics"]["opacity"] == 20 and state["lyrics"]["hide_paused"] is True
    assert widgets.normalize({"lyrics": {"lines": 10}})["lyrics"]["lines"] == 10
    assert widgets.normalize({"lyrics": {"lines": 0}})["lyrics"]["lines"] == 1
    assert (state["clock"]["hours"], state["clock"]["color"]) == ("12", "accent")
    assert state["system"]["cpu"] is False and state["system"]["memory"] is True and not state["system"]["curves"]
    assert (state["visualizer"]["style"], state["visualizer"]["color"]) == ("mirrored", "white")


def test_width_is_free_or_follows_the_size():
    state = widgets.normalize({"lyrics": {"width": 50}, "system": {"width": 0}, "visualizer": {"width": True},
                               "clock": {"width": 500}})
    assert state["lyrics"]["width"] == 200 and state["system"]["width"] == 0
    assert state["visualizer"]["width"] == 0 and "width" not in state["clock"]


def test_arranging_saves_places_and_sizes():
    cfg = config.default_config()
    cfg["widgets"] = widgets.normalize({"visualizer": {"enabled": True}})
    cfg = widgets.save_placements(cfg, {"visualizer": {"x": 0.2, "y": 0.8, "rotation": 90, "size": 240,
                                                       "width": 9999, "enabled": False},
                                        "moon": {"x": 0.1}})
    visualizer = cfg["widgets"]["visualizer"]
    assert (visualizer["x"], visualizer["y"], visualizer["rotation"]) == (0.2, 0.8, 90)
    assert (visualizer["size"], visualizer["width"]) == (240, 2000)
    assert visualizer["enabled"] and visualizer["placed"] and "moon" not in cfg["widgets"]


def test_new_widgets_start_in_the_middle():
    for widget in widgets.normalize({}).values():
        assert (widget["x"], widget["y"], widget["rotation"], widget["placed"]) == (0.5, 0.5, 0, False)


def test_where_the_visualizer_shows():
    state = widgets.normalize({"visualizer": {"enabled": True, "where": "bar"}})
    assert widgets.in_bar(state) and not widgets.on_desktop(state["visualizer"], "visualizer")
    state = widgets.normalize({"visualizer": {"enabled": True, "where": "desktop"}})
    assert not widgets.in_bar(state) and widgets.on_desktop(state["visualizer"], "visualizer")


def test_cava_prints_raw_bars_and_sleeps_when_quiet():
    text = widgets.cava_config(24)
    for line in ("bars = 24", "method = raw", "data_format = ascii", "bar_delimiter = 59",
                 "sleep_timer = 2", "method = pipewire"):
        assert line in text


def test_export_writes_what_the_plugin_reads(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr(widgets, "font", lambda: "Mono")
    cfg = config.default_config()
    cfg["language"] = "de"
    cfg["widgets"] = widgets.normalize({"clock": {"enabled": True}})
    widgets.export(cfg)
    data = json.loads(widgets.settings_file().read_text())
    assert data["widgets"]["clock"]["enabled"] is True
    assert data["cava"] == str(widgets.cava_file()) and widgets.cava_file().exists()
    assert data["font"] == "Mono" and data["locale"] == "de_DE"
    assert data["texts"]["clock"] == "Uhr"
    from hypr_screens import i18n

    i18n.set_language("en")


@pytest.fixture()
def shell(tmp_path, monkeypatch):
    path = tmp_path / "shell.json"
    path.write_text(json.dumps({"plugins": [{"id": "hypr-minimizer.picker"}], "bar": {"layout": {
        "left": [{"id": "omarchy.menu"}, {"id": "hypr-screens.workspaces"}], "right": [{"id": "omarchy.clock"}]}}}))
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / widgets.PLUGIN).symlink_to(install.PLUGINS[widgets.PLUGIN])
    monkeypatch.setattr(install, "shell_json", lambda: path)
    monkeypatch.setattr(install, "plugins_dir", lambda: plugins)
    monkeypatch.setattr(install, "has_omarchy_shell", lambda: True)
    return path


def test_the_bar_visualizer_sits_right_of_the_desktops(shell):
    widgets.wire_shell(widgets.normalize({"visualizer": {"enabled": True, "where": "both"}}))
    data = json.loads(shell.read_text())
    assert [w["id"] for w in data["bar"]["layout"]["left"]] == ["omarchy.menu", "hypr-screens.workspaces",
                                                                widgets.PLUGIN]
    assert {"id": widgets.PLUGIN} in data["plugins"]
    assert widgets.wire_shell(widgets.normalize({"visualizer": {"enabled": True, "where": "both"}})) == []


def test_only_desktop_widgets_keep_the_service_but_leave_the_bar(shell):
    widgets.wire_shell(widgets.normalize({"visualizer": {"enabled": True, "where": "both"}}))
    widgets.wire_shell(widgets.normalize({"clock": {"enabled": True}}))
    data = json.loads(shell.read_text())
    assert widgets.PLUGIN not in [w["id"] for w in data["bar"]["layout"]["left"]]
    assert {"id": widgets.PLUGIN} in data["plugins"]
    widgets.wire_shell(widgets.normalize({}))
    assert json.loads(shell.read_text())["plugins"] == [{"id": "hypr-minimizer.picker"}]


def test_widget_settings_survive_the_config_file():
    cfg = config.normalize({"widgets": {"lyrics": {"enabled": True, "lines": 5, "x": 0.2}}})
    assert cfg["widgets"]["lyrics"]["lines"] == 5 and cfg["widgets"]["lyrics"]["x"] == 0.2


def test_visibility_rules_are_kept_clean():
    clock = widgets.normalize({"clock": {"desktops": [3, 1, 99, 11, True, "x", 3], "only_empty": True,
                                         "above": True}})["clock"]
    assert clock["desktops"] == [1, 3, 99] and clock["only_empty"] and clock["above"]
    assert not clock["hide_on_battery"] and widgets.normalize({})["clock"]["desktops"] == []


def test_places_per_screen():
    clock = widgets.normalize({"clock": {"same_place": False, "x": 0.2, "spots": {
        "HP|32f|1": {"x": 0.9, "size": 9999}, "bad": "x"}}})["clock"]
    assert clock["same_place"] is False
    assert clock["spots"] == {"HP|32f|1": {"x": 0.9, "y": 0.5, "rotation": 0, "size": 400}}
    cfg = config.default_config()
    cfg["widgets"] = widgets.normalize({})
    cfg = widgets.save_placements(cfg, {"lyrics": {"spots": {"A|B|C": {"x": 0.1, "width": 50}},
                                                   "colors": {"current": "#FF0000", "nope": "#000000"}}})
    assert cfg["widgets"]["lyrics"]["spots"]["A|B|C"]["width"] == 200
    assert cfg["widgets"]["lyrics"]["colors"] == {"current": "#ff0000"}


def test_layouts_save_load_and_follow_the_screens():
    cfg = config.default_config()
    cfg["widgets"] = widgets.normalize({"clock": {"enabled": True}})
    cfg = widgets.save_layout(cfg, " Work ")
    cfg["widgets"] = widgets.normalize({"lyrics": {"enabled": True}})
    cfg = widgets.save_layout(cfg, "Music")
    assert [layout["name"] for layout in cfg["widget_layouts"]] == ["Work", "Music"]
    cfg = widgets.load_layout(cfg, "Work")
    assert cfg["widgets"]["clock"]["enabled"] and not cfg["widgets"]["lyrics"]["enabled"]
    cfg = widgets.set_layout_screens(cfg, "Work", ["B", "A"])
    cfg = widgets.set_layout_screens(cfg, "Music", ["A", "B"])
    assert cfg["widget_layouts"][0]["screens"] == [] and widgets.matching_layout(cfg, ["B", "A"])["name"] == "Music"
    cfg = widgets.rename_layout(cfg, "Music", "Work")  # taken: stays
    cfg = widgets.rename_layout(cfg, "Music", "Party")
    cfg = widgets.delete_layout(cfg, "Work")
    assert [layout["name"] for layout in config.normalize(cfg)["widget_layouts"]] == ["Party"]


def test_clock_styles_dates_and_zones():
    clock = widgets.normalize({"clock": {"clock_style": "flip", "date_format": "custom", "date_pattern": "x" * 99,
                                         "zone2": "Europe/Rome", "weekday": False}})["clock"]
    assert (clock["clock_style"], clock["date_format"], clock["zone2"], clock["weekday"]) == ("flip", "custom",
                                                                                             "Europe/Rome", False)
    assert len(clock["date_pattern"]) == 60
    assert widgets.normalize({"clock": {"clock_style": "sundial", "zone2": "Nowhere/Land"}})["clock"]["zone2"] == ""
