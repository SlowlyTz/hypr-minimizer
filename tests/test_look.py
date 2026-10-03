"""Window look: values kept in range, rendered as Lua, read back from Hyprland."""
from hypr_screens import config, keybinds, look


def test_values_are_kept_in_range_and_unknown_ones_dropped():
    assert look.normalize({"gaps_in": 99, "rounding": -3, "active_opacity": 0.123, "blur": 1,
                           "nonsense": 5, "border_size": "2"}) == {
        "gaps_in": 30, "rounding": 0, "active_opacity": 0.3, "blur": True}
    assert look.normalize("garbage") == {}


def test_lua_nests_values_like_hyprland_options():
    lua = look.lua_table({"gaps_in": 5, "blur": True, "blur_size": 6, "inactive_opacity": 0.9})
    assert lua == ("hl.config({ general = { gaps_in = 5 }, decoration = { blur = { enabled = true, size = 6 }, "
                   "inactive_opacity = 0.9 } })")
    assert look.lua_table({}) == ""


def test_hyprland_replies_are_read():
    assert look.parse_option({"css": "5 5 5 5"}, "int") == 5
    assert look.parse_option({"int": 2}, "int") == 2
    assert look.parse_option({"bool": False}, "bool") is False
    assert look.parse_option({"float": 0.949999}, "float") == 0.95


def test_presets_are_complete_and_valid():
    for values in look.PRESETS.values():
        assert set(values) == set(look.OPTIONS)
        assert look.normalize(values) == values


def test_a_saved_look_goes_into_the_lua_file():
    cfg = config.default_config()
    assert "Window look" not in keybinds.render(cfg)
    cfg["look"] = {"rounding": 12}
    assert "hl.config({ decoration = { rounding = 12 } })" in keybinds.render(cfg)
    assert config.normalize({"look": {"rounding": 12, "x": 1}})["look"] == {"rounding": 12}


def test_border_gradient_animation_speed_and_app_rules():
    raw = {"border_colors": ["#FF0000", "#00ff00cc"], "border_angle": 405, "anim_speed": 9,
           "apps": [{"class": "foot", "active": 0.1, "inactive": 0.8}, {"class": "foot"}, {"class": " "}]}
    clean = look.normalize(raw)
    assert clean["border_colors"] == ["#ff0000", "#00ff00cc"] and clean["border_angle"] == 45
    assert clean["anim_speed"] == 3.0
    assert clean["apps"] == [{"class": "foot", "active": 0.3, "inactive": 0.8}]
    assert "anim_speed" not in look.normalize({"anim_speed": 1.0})
    lua = look.lua_table(clean)
    assert 'active_border = { colors = { "rgba(ff0000ff)", "rgba(00ff00cc)" }, angle = 45 }' in lua
    assert 'match = { class = "^(foot)$" }, opacity = "0.3 0.8"' in lua


def test_animations_are_scaled_from_omarchys(tmp_path, monkeypatch):
    path = tmp_path / "looknfeel.lua"
    path.write_text('hl.animation({ leaf = "windows", enabled = true, speed = 4, bezier = "q", style = "popin 87%" })\n'
                    'hl.animation({ leaf = "workspaces", enabled = false })\n')
    monkeypatch.setattr(look, "ANIMATION_FILES", [path])
    assert look.animation_lua(2.0) == [
        'hl.animation({ leaf = "windows", enabled = true, speed = 2.0, bezier = "q", style = "popin 87%" })']


def test_taking_rules_or_the_own_border_back_needs_a_reload():
    rule = {"apps": [{"class": "foot", "active": 0.9, "inactive": 0.8}]}
    assert look.needs_reload(rule, {}) and look.needs_reload({}, rule)
    assert look.needs_reload({"border_colors": ["#000000", "#ffffff"]}, {})
    assert not look.needs_reload({}, {"border_colors": ["#000000", "#ffffff"]})
    assert not look.needs_reload({"rounding": 3}, {"rounding": 9, "anim_speed": 2})
