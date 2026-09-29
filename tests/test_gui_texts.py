"""The settings window's wording and key recording, without GTK."""
from hypr_screens.gui import texts, theme


def test_keys_are_spelled_like_hyprland():
    assert texts.combo_from_event("m", 58, texts.SUPER) == "SUPER + M"
    assert texts.combo_from_event("period", 60, texts.SUPER | texts.SHIFT) == "SUPER + SHIFT + PERIOD"
    assert texts.combo_from_event("F23", 201, texts.SUPER | texts.SHIFT) == "SUPER + SHIFT + F23"
    # Layout-specific keys go by keycode.
    assert texts.combo_from_event("ssharp", 20, texts.SUPER) == "SUPER + code:20"
    assert texts.combo_from_event("Return", 36, texts.CONTROL | texts.ALT) == "CTRL + ALT + RETURN"


def test_combo_labels_read_like_keys():
    assert texts.combo_label("SUPER + SHIFT + PERIOD") == "Super + Shift + ."
    assert texts.combo_label("SUPER + SHIFT + F23") == "Copilot-Taste"
    assert texts.combo_label("") == "—"


def test_choices_start_with_not_set_and_keep_types_apart():
    screen = {"modes": ["2560x1440@59.95"], "internal": False}
    rotation = texts.choices("rotation", screen)
    assert rotation[0] == (None, texts.AS_CONFIGURED)
    assert texts.index_of(rotation, 180) == 3
    assert texts.choices("mode", screen)[2] == ("2560x1440@59.95", "2560 × 1440 · 60 Hz")
    scale = texts.choices("scale", screen)
    assert texts.index_of(scale, 1.0) == 2
    one = texts.choices("one_desktop", screen, "external")
    assert one[0][1] == "Standard (ja)"
    assert texts.index_of(one, True) == 1 and texts.index_of(one, False) == 2


def test_conditions_list_only_connected_screens_plus_the_current_one():
    cfg = {"screens": {"a": {"name": "Laptop"}, "b": {"name": "HP 32f"}, "c": {"name": "Fujitsu"}}}
    assert texts.condition_choices(cfg, "a", {"a", "b"}) == [(None, "Immer"), ("b", "Nur mit „HP 32f“")]
    assert texts.condition_choices(cfg, "a", {"a", "b"}, current="c") == [
        (None, "Immer"),
        ("c", "Nur mit „Fujitsu“ (nicht angeschlossen)"),
        ("b", "Nur mit „HP 32f“"),
    ]


def test_theme_uses_omarchy_colors(tmp_path):
    (tmp_path / "colors.toml").write_text('mode = "dark"\naccent = "#123456"\nbackground = "#000000"\n')
    (tmp_path / "shell.toml").write_text('[menu]\nbackground = "#111111"\ntext = "#eeeeee"\nborder = "hyprland.x"\n')
    colors = theme.palette(tmp_path)
    assert colors["menu_background"] == "#111111" and colors["accent"] == "#123456"
    css = theme.css(colors, radius=0, family="JetBrainsMono Nerd Font")
    assert "@define-color window_bg_color #111111;" in css
    assert "@define-color accent_bg_color #123456;" in css
    assert 'font-family: "JetBrainsMono Nerd Font"' in css
