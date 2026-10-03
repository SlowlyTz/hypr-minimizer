"""A widget's "Colors" page (Personalization → Widgets → a widget → Colors):
every part with a color, in groups, each with a swatch that opens a small
popover: the widget's accent, the theme's colors, an own color or the default.

Values (widgets.clean_colors): "accent" (the widget's accent color),
"theme:<name>" (follows a theme change) or "#rrggbb[aa]" (stays).
"""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk, Pango  # noqa: E402

from hypr_screens import widgets  # noqa: E402
from hypr_screens.gui import theme  # noqa: E402
from hypr_screens.i18n import t  # noqa: E402

THEME_NAMES = {"accent": "Theme accent", "foreground": "Theme text", "muted": "Muted", "background": "Background",
               "red": "Red", "orange": "Orange", "yellow": "Yellow", "green": "Green", "cyan": "Cyan", "blue": "Blue",
               "magenta": "Magenta"}
ACCENTS = {"accent": "accent", "gradient": "accent", "foreground": "foreground"}


def rgba(hex_color: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    hexa = hex_color.lstrip("#")
    color.parse("#" + hexa[:6])
    color.alpha = int(hexa[6:8], 16) / 255 if len(hexa) == 8 else 1.0
    return color


def hex_color(color: Gdk.RGBA) -> str:
    alpha = round(color.alpha * 255)
    channels = [color.red, color.green, color.blue]
    return "#" + "".join(f"{round(v * 255):02x}" for v in channels) + ("" if alpha == 255 else f"{alpha:02x}")


def resolve(widget: dict, value: str, palette: dict) -> Gdk.RGBA | None:
    """What a value looks like now (None: worked out by the widget)."""
    if value == "accent":
        choice = widget.get("color", "accent")
        return rgba("#ffffff") if choice == "white" else rgba(palette.get(ACCENTS.get(choice, "accent"), "#89b4fa"))
    if value.startswith("theme:"):
        return rgba(palette.get(value[6:], palette.get("foreground", "#cdd6f4")))
    if value.startswith("#"):
        return rgba(value)
    return None


def describe(value: str) -> str:
    if value == "accent":
        return t("Widget accent")
    if value == "auto":
        return t("Automatic")
    if value.startswith("theme:"):
        return t(THEME_NAMES.get(value[6:], value[6:]))
    return value


def swatch(color: Gdk.RGBA | None, size: int = 22) -> Gtk.DrawingArea:
    """A round color sample (striped when the widget works it out itself)."""
    area = Gtk.DrawingArea(content_width=size, content_height=size, valign=Gtk.Align.CENTER)

    def draw(_area, cr, width, height):
        radius = min(width, height) / 2 - 1
        cr.arc(width / 2, height / 2, radius, 0, 6.2832)
        if color is None:
            cr.set_source_rgba(0.5, 0.5, 0.5, 0.25)
            cr.fill_preserve()
            cr.set_source_rgba(0.5, 0.5, 0.5, 0.8)
            cr.set_line_width(1.5)
            cr.stroke()
            cr.move_to(width / 2 - radius * 0.6, height / 2 + radius * 0.6)
            cr.line_to(width / 2 + radius * 0.6, height / 2 - radius * 0.6)
            cr.stroke()
            return
        # A checkerboard shows through see-through colors.
        cr.save()
        cr.clip()
        for i in range(0, width, 5):
            for j in range(0, height, 5):
                shade = 0.85 if (i // 5 + j // 5) % 2 else 0.6
                cr.set_source_rgb(shade, shade, shade)
                cr.rectangle(i, j, 5, 5)
                cr.fill()
        cr.restore()
        cr.arc(width / 2, height / 2, radius, 0, 6.2832)
        cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        cr.fill_preserve()
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.set_line_width(1)
        cr.stroke()

    area.set_draw_func(draw)
    return area


def preview(widget: dict, kind: str, count: int = 5) -> Gtk.Box:
    """A few of the widget's colors side by side (for the "Colors" row)."""
    palette = theme.palette()
    defaults = widgets.part_defaults(kind)
    box = Gtk.Box(spacing=3, valign=Gtk.Align.CENTER)
    shown = 0
    for part, default in defaults.items():
        color = resolve(widget, widget["colors"].get(part, default), palette)
        if color is None:
            continue
        box.append(swatch(color, 14))
        shown += 1
        if shown >= count:
            break
    return box


class ColorsPage:
    """Fills `page` with the parts of `kind`; `change(kind, mutate)` saves."""

    def __init__(self, window, change):
        self.window = window
        self.change = change

    def build(self, page: Gtk.Box, kind: str, widget: dict) -> None:
        palette = theme.palette()
        hint = Gtk.Label(label=t("Theme colors change with the theme; an own color stays. "
                                 "Parts left on their default follow the widget."),
                         xalign=0, wrap=True, css_classes=["hint"])
        hint.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        page.append(hint)
        for title, parts in [*widgets.PARTS[kind], widgets.LOOK_PARTS]:
            group = Adw.PreferencesGroup(title=t(title))
            for part, part_title, default in parts:
                group.add(self.part_row(kind, widget, part, t(part_title), default, palette))
            page.append(group)
        if widget["colors"]:
            group = Adw.PreferencesGroup()
            row = Adw.ActionRow(title=t("All colors back to their defaults"))
            button = Gtk.Button(label=t("Reset"), valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
            button.connect("clicked", lambda _b: self.change(kind, lambda w: w.__setitem__("colors", {}), True))
            row.add_suffix(button)
            group.add(row)
            page.append(group)

    def part_row(self, kind: str, widget: dict, part: str, title: str, default: str, palette: dict) -> Adw.ActionRow:
        own = widget["colors"].get(part)
        value = own or default
        subtitle = describe(value) if own else t("Default: {color}", color=describe(default))
        row = Adw.ActionRow(title=title, subtitle=subtitle)
        button = Gtk.MenuButton(valign=Gtk.Align.CENTER, css_classes=["flat"])
        button.set_child(swatch(resolve(widget, value, palette)))
        button.set_tooltip_text(t("Pick a color"))
        button.set_popover(self.popover(kind, widget, part, value, palette, button))
        row.add_suffix(button)
        row.set_activatable_widget(button)
        return row

    def popover(self, kind: str, widget: dict, part: str, value: str, palette: dict,
                button: Gtk.MenuButton) -> Gtk.Popover:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=10, margin_bottom=10,
                      margin_start=10, margin_end=10)
        grid = Gtk.FlowBox(max_children_per_line=6, min_children_per_line=6, selection_mode=Gtk.SelectionMode.NONE,
                           column_spacing=4, row_spacing=4)
        for choice in ["accent", *(f"theme:{name}" for name in widgets.THEME_COLORS)]:
            chip = Gtk.Button(css_classes=["flat", "circular"])
            chip.set_child(swatch(resolve(widget, choice, palette), 24))
            chip.set_tooltip_text(describe(choice))
            if choice == value:
                chip.add_css_class("suggested-action")
            chip.connect("clicked", self.on_pick, kind, part, choice, popover)
            grid.append(chip)
        box.append(grid)
        actions = Gtk.Box(spacing=6, homogeneous=True)
        custom = Gtk.Button(label=t("Own color…"))
        custom.connect("clicked", self.on_custom, kind, widget, part, value, palette, popover)
        actions.append(custom)
        reset = Gtk.Button(label=t("Default"))
        reset.set_sensitive(part in widget["colors"])
        reset.connect("clicked", self.on_pick, kind, part, None, popover)
        actions.append(reset)
        box.append(actions)
        popover.set_child(box)
        return popover

    def on_pick(self, _button, kind: str, part: str, value: str | None, popover: Gtk.Popover) -> None:
        popover.popdown()

        def mutate(widget):
            colors = dict(widget["colors"])
            if value is None:
                colors.pop(part, None)
            else:
                colors[part] = value
            widget["colors"] = colors
        self.change(kind, mutate, True)

    def on_custom(self, _button, kind: str, widget: dict, part: str, value: str, palette: dict,
                  popover: Gtk.Popover) -> None:
        popover.popdown()
        dialog = Gtk.ColorDialog(with_alpha=True, title=t("Own color"))
        start = resolve(widget, value, palette) or rgba(palette.get("foreground", "#cdd6f4"))

        def done(dialog, result):
            try:
                color = dialog.choose_rgba_finish(result)
            except Exception:
                return  # cancelled
            self.on_pick(None, kind, part, hex_color(color), popover)
        dialog.choose_rgba(self.window, start, None, done)
