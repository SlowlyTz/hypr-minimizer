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
