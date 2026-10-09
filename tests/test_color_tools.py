"""omarchy-widgets/ColorTools.js (the arrange tool's color schemes, carrying
colors to other widgets, the wallpaper's colors), run in node."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parent.parent / "omarchy-widgets" / "ColorTools.js"
CLOCK = {"hours": "theme:foreground", "colon": "theme:foreground", "date": "theme:muted", "ring": "accent",
         "card": "theme:background", "effect": "auto"}
LYRICS = {"current": "accent", "sung": "accent", "waiting": "theme:foreground", "past": "theme:foreground"}
BLUE = {"r": 0.2, "g": 0.4, "b": 1.0, "a": 1}

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def run(expression: str):
    """The value of `expression` with ColorTools' functions in scope."""
    code = SOURCE.read_text().replace(".pragma library", "") + f"\nconsole.log(JSON.stringify({expression}))\n"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_hex_round_trip_through_hsv():
    assert run('hex(fromHsv(toHsv({r: 0, g: 0, b: 1, a: 1}).h, 1, 1, 0.6))') == "#0000ff99"
    assert run('hex(fromHsv(1 / 6, 1, 1))') == "#ffff00"
    assert run('hex({r: 0, g: 0, b: 0, a: 1})') == "#000000"


def test_theme_scheme_gives_the_defaults_back():
    assert run(f'scheme("theme", "#3366ff", {json.dumps(BLUE)}, {json.dumps(CLOCK)})') == {}


def test_schemes_keep_main_parts_on_the_base_and_leave_auto_alone():
    for scheme in ["mono", "contrast", "pastel", "colorful", "muted"]:
        colors = run(f'scheme("{scheme}", "theme:blue", {json.dumps(BLUE)}, {json.dumps(CLOCK)})')
        assert colors["ring"] == "accent"
        assert "effect" not in colors
        assert colors["base"].startswith("#") if scheme in ("pastel", "muted") else colors["base"] == "theme:blue"
    mono = run(f'scheme("mono", "theme:blue", {json.dumps(BLUE)}, {json.dumps(CLOCK)})')
    assert mono["hours"] == "theme:blue" and mono["date"].endswith("99")  # 60 % see-through
    contrast = run(f'scheme("contrast", "", {json.dumps(BLUE)}, {json.dumps(CLOCK)})')
    assert (contrast["hours"], contrast["card"]) == ("#ffffff", "#000000") and "base" not in contrast


def test_carry_takes_the_base_and_each_kind_of_part():
    clock_colors = {"base": "#ff0000", "hours": "#eeeeee", "date": "#888888"}
    carried = run(f'carry({json.dumps(clock_colors)}, {json.dumps(CLOCK)}, {json.dumps(LYRICS)})')
    assert carried == {"base": "#ff0000", "waiting": "#eeeeee", "past": "#eeeeee"}


def test_main_colors_of_an_image():
    red, green = [230, 30, 30, 255], [40, 200, 60, 255]
    pixels = red * 60 + green * 30 + [128, 128, 128, 255] * 10
    colors = run(f"mainColors({json.dumps(pixels)}, 4)")
    assert colors[:2] == ["#e61e1e", "#28c83c"]
    assert len(colors) <= 4
