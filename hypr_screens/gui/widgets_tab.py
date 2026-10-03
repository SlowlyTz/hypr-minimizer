"""Personalization → Widgets: switch the desktop widgets on, set them up and
arrange them (move, resize and turn them on the desktop, then save).

The tab is an overview: arranging, then one row per widget with its switch
and a short summary. A row opens the widget's own page (a page of the
Personalization stack) with its settings in three parts: Placement, Content
and Look.

Every change goes live at once (widgets.apply writes what the shell plugin
reads). A widget switched on for the first time appears in the middle of the
screen and arranging starts, so it can be dragged where it belongs.
"""
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from hypr_screens import config, widgets  # noqa: E402
from hypr_screens.gui import widget_colors  # noqa: E402
from hypr_screens.i18n import t  # noqa: E402

DEBOUNCE_MS = 300
# A widget's page: (section title, settings), top to bottom. The size is set
# by arranging; "arrange" is the row that starts it.
LOOK = ["color", "colors", "font", "effect", "card", "opacity"]
SECTIONS = {
    "visualizer": [("Placement", ["where", "screens", "arrange"]), ("Content", ["bars", "style"]), ("Look", LOOK)],
    "lyrics": [("Placement", ["screens", "arrange"]), ("Content", ["highlight", "lines", "hide_paused"]),
               ("Look", ["align", *LOOK])],
    "clock": [("Placement", ["screens", "arrange"]), ("Content", ["hours", "date", "seconds"]), ("Look", LOOK)],
    "system": [("Placement", ["screens", "arrange"]), ("Content", ["cpu", "memory", "temperature", "curves"]),
               ("Look", LOOK)],
}
# Rows that fold out: key: (title, the settings inside). "card" has its own switch.
EXPANDERS = {"font": ("Font", ["font_family", "font_weight", "letter_spacing"]),
             "effect": ("Effect", ["effect", "effect_strength"]),
             "card": ("Background card", ["card_radius", "card_padding", "card_opacity", "card_blur"])}
ICONS = {"visualizer": "audio-volume-high-symbolic", "lyrics": "format-justify-center-symbolic",
         "clock": "alarm-symbolic", "system": "computer-symbolic"}
# The setting a widget's summary in the overview names after its screens.
SUMMARY = {"visualizer": "where", "lyrics": "highlight", "clock": "hours"}
# Settings picked from a list (widgets.CHOICES): their title and labels.
CHOICE_TITLES = {"where": "Where", "style": "Style", "highlight": "Highlight", "align": "Alignment",
                 "hours": "Time format", "color": "Accent color", "font_weight": "Weight", "effect": "Effect"}
CHOICE_LABELS = {
    "where": {"bar": "In the bar", "desktop": "On the desktop", "both": "Bar and desktop"},
    "style": {"bottom": "Bars from the bottom", "mirrored": "Mirrored from the middle"},
    "highlight": {"line": "Current line", "word": "Word by word", "off": "Off"},
    "align": {"center": "Centered", "left": "Left", "right": "Right"},
    "hours": {"24": "24-hour", "12": "12-hour"},
    "color": {"accent": "Theme accent", "gradient": "Gradient", "foreground": "Theme text", "white": "White"},
    "font_weight": {"light": "Light", "regular": "Regular", "medium": "Medium", "bold": "Bold", "black": "Black"},
    "effect": {"outline": "Outline", "shadow": "Shadow", "glow": "Glow", "none": "None"},
}
SWITCH_TITLES = {"hide_paused": "Hide while paused", "date": "Show the date", "seconds": "Show seconds",
                 "cpu": "CPU usage", "memory": "Memory", "temperature": "Temperature", "curves": "Show the curves",
                 "card_blur": "Blur behind the card"}
# key: (title, step, unit); the range is widgets.RANGES.
SLIDER_ROWS = {"bars": ("Bars", 1, ""), "opacity": ("Opacity", 5, " %"),
               "letter_spacing": ("Letter spacing", 1, " px"), "effect_strength": ("Strength", 5, " %"),
               "card_radius": ("Corners", 2, " px"), "card_padding": ("Room around", 2, " px"),
               "card_opacity": ("Card opacity", 5, " %")}
# Whole numbers typed in (or stepped with − and +): key: title; the range is widgets.RANGES.
NUMBER_ROWS = {"lines": "Lines"}
HINTS = {
    "highlight": "Word by word follows the singing; most songs only have times per line, "
                 "then the words are spread over the line.",
}
DESCRIPTIONS = {
    "visualizer": "Bars that move with the sound playing right now.",
    "lyrics": "The words of the song playing, in time with the music (from lrclib.net).",
    "clock": "A big clock with the date.",
    "system": "CPU, memory and temperature with a curve of the last two minutes.",
}


def label(text: str, *classes: str) -> Gtk.Label:
    widget = Gtk.Label(label=text, xalign=0, wrap=True, css_classes=list(classes))
    widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return widget


def combo(title: str, labels: list[str], selected: int) -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels))
    row.set_selected(max(0, selected))
    return row


class WidgetsTab:
    def __init__(self, window, tab: Gtk.Box, pages: dict[str, Gtk.Box], color_pages: dict[str, Gtk.Box], open_page):
        """tab: the overview; pages: each widget's page, color_pages its colors;
        open_page(name) shows "widget-<kind>", "widget-<kind>-colors" (or
        "widgets") in the Personalization stack."""
        self.window = window
        self.tab = tab
        self.pages = pages
        self.color_pages = color_pages
        self.colors = widget_colors.ColorsPage(window, self.change)
        self.open_page = open_page
        self.editing = False
        self.updating = False
        self.pending: dict[str, int] = {}
        self.build()

    # --- data ------------------------------------------------------------------------------

    def current(self) -> dict:
        return config.load()["widgets"]

    def change(self, kind: str, mutate, rebuild: bool = False) -> None:
        cfg = config.load()
        mutate(cfg["widgets"][kind])
        cfg["widgets"] = widgets.normalize(cfg["widgets"])
        config.save(cfg)
        self.window.cfg = cfg
        widgets.apply(cfg)
        if rebuild:
            GLib.idle_add(lambda: self.build() and False)
        else:
            GLib.idle_add(lambda: self.build_overview() and False)

    def screen_choices(self) -> list[tuple[str, str, str]]:
        """(mode, screen id, label): laptop, externals, all, then each known external screen."""
        choices = [("laptop", "", t("Laptop screen")), ("external", "", t("All external screens")),
                   ("all", "", t("All screens"))]
        for sid, screen in sorted(config.load()["screens"].items(), key=lambda item: item[1].get("name", "")):
            if not screen.get("internal"):
                choices.append(("screen", sid, t("Only “{name}”", name=screen.get("name", sid))))
        return choices

    # --- building ------------------------------------------------------------------------

    @staticmethod
    def clear(box: Gtk.Box) -> None:
        child = box.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            box.remove(child)
            child = following

    def build(self) -> None:
        self.updating = True
        self.build_overview()
        state = self.current()
        for kind in widgets.KINDS:
            self.build_page(kind, state[kind])
            self.clear(self.color_pages[kind])
            self.colors.build(self.color_pages[kind], kind, state[kind])
        GLib.idle_add(self.end_update)

    def build_overview(self) -> None:
        self.clear(self.tab)
        state = self.current()
        self.tab.append(label(t("Widgets sit on the desktop behind the windows. Open one to set it up."), "hint"))
        self.tab.append(self.arrange_group(state))
        group = Adw.PreferencesGroup()
        for kind in widgets.KINDS:
            group.add(self.overview_row(kind, state[kind]))
        self.tab.append(group)

    def overview_row(self, kind: str, widget: dict) -> Adw.ActionRow:
        row = Adw.ActionRow(title=t(widgets.TITLES[kind]), subtitle=self.summary(kind, widget), activatable=True)
        row.add_prefix(Gtk.Image.new_from_icon_name(ICONS[kind]))
        switch = Gtk.Switch(active=widget["enabled"], valign=Gtk.Align.CENTER)
        switch.connect("notify::active", self.on_enabled, kind)
        row.add_suffix(switch)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect("activated", lambda _r: self.open_page(f"widget-{kind}"))
        return row

    def summary(self, kind: str, widget: dict) -> str:
        if not widget["enabled"]:
            return t(DESCRIPTIONS[kind])
        monitors = widget["monitors"]
        parts = [next((text for mode, sid, text in self.screen_choices()
                       if mode == monitors["mode"] and (mode != "screen" or sid == monitors["screen"])), "")]
        if kind in SUMMARY:
            key = SUMMARY[kind]
            parts.append(t(CHOICE_LABELS[key][widget[key]]))
        return " · ".join(part for part in parts if part)

    def build_page(self, kind: str, widget: dict) -> None:
        page = self.pages[kind]
        self.clear(page)
        page.append(label(t(DESCRIPTIONS[kind]), "hint"))
        group = Adw.PreferencesGroup()
        shown = Adw.SwitchRow(title=t("Show this widget"))
        shown.add_prefix(Gtk.Image.new_from_icon_name(ICONS[kind]))
        shown.set_active(widget["enabled"])
        shown.connect("notify::active", self.on_enabled, kind)
        group.add(shown)
        if kind == "visualizer" and widget["enabled"] and not widgets.has_cava():
            row = Adw.ActionRow(title=t("cava is missing"),
                                subtitle=t("The visualizer needs the program cava. Needs your password."))
            button = Gtk.Button(label=t("Install…"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
            button.connect("clicked", self.on_install_cava)
            row.add_suffix(button)
            group.add(row)
        page.append(group)
        if not widget["enabled"]:
            return
        for title, keys in SECTIONS[kind]:
            section = Adw.PreferencesGroup(title=t(title))
            hints = [t(HINTS[key]) for key in keys if key in HINTS]
            if hints:
                section.set_description(" ".join(hints))
            for key in keys:
                section.add(self.row(kind, key, widget))
            page.append(section)

    def end_update(self) -> bool:
        self.updating = False
        return False

    def arrange_group(self, state: dict) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup()
        row = Adw.ActionRow(title=t("Arrange on the desktop"),
                            subtitle=t("Drag to move, pull the edges and corners to resize, scroll to turn. "
                                       "Save keeps them.")
                            if not self.editing else t("Arranging – drag the widgets on the desktop now."))
        row.add_prefix(Gtk.Image.new_from_icon_name("view-grid-symbolic"))
        buttons = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        if self.editing:
            cancel = Gtk.Button(label=t("Cancel"))
            cancel.connect("clicked", self.on_cancel)
            save = Gtk.Button(label=t("Save"), css_classes=["suggested-action"])
            save.connect("clicked", self.on_save)
            buttons.append(cancel)
            buttons.append(save)
        else:
            arrange = Gtk.Button(label=t("Arrange"))
            arrange.set_sensitive(any(widgets.on_desktop(state[k], k) for k in widgets.KINDS))
            arrange.connect("clicked", lambda _b: self.start_arranging())
            buttons.append(arrange)
        row.add_suffix(buttons)
        group.add(row)
        return group

    def row(self, kind: str, key: str, widget: dict, inside: bool = False) -> Gtk.Widget:
        if key == "colors":
            row = Adw.ActionRow(title=t("Colors"), subtitle=t("Every part on its own."), activatable=True)
            row.add_suffix(widget_colors.preview(widget, kind))
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.connect("activated", lambda _r: self.open_page(f"widget-{kind}-colors"))
            return row
        if key in EXPANDERS and not inside:
            title, keys = EXPANDERS[key]
            row = Adw.ExpanderRow(title=t(title), subtitle=self.expander_summary(key, widget))
            if key == "card":
                row.set_show_enable_switch(True)
                row.set_enable_expansion(widget["card"])
                row.connect("notify::enable-expansion", self.on_card, kind)
            for inner in keys:
                row.add_row(self.row(kind, inner, widget, inside=True))
            return row
        if key == "font_family":
            row = Adw.ActionRow(title=t("Font"), subtitle=widget["font_family"] or t("The Omarchy font"))
            button = Gtk.FontDialogButton(dialog=Gtk.FontDialog(title=t("Font")), level=Gtk.FontLevel.FAMILY,
                                          valign=Gtk.Align.CENTER)
            button.set_font_desc(Pango.FontDescription.from_string(widget["font_family"] or widgets.font() or "monospace"))
            button.connect("notify::font-desc", self.on_font, kind)
            row.add_suffix(button)
            if widget["font_family"]:
                reset = Gtk.Button(icon_name="edit-undo-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER)
                reset.set_tooltip_text(t("Back to the Omarchy font"))
                reset.connect("clicked", lambda _b: self.change(kind, lambda w: w.__setitem__("font_family", ""), True))
                row.add_suffix(reset)
            return row
        if key == "arrange":
            row = Adw.ActionRow(title=t("Size and place"),
                                subtitle=t("Arranging – drag the widgets on the desktop now.") if self.editing
                                else t("Move, resize and turn it on the desktop."))
            button = Gtk.Button(label=t("Arrange"), valign=Gtk.Align.CENTER)
            button.set_sensitive(not self.editing and widgets.on_desktop(widget, kind))
            button.connect("clicked", lambda _b: self.start_arranging())
            row.add_suffix(button)
            return row
        if key == "screens":
            choices = self.screen_choices()
            monitors = widget["monitors"]
            index = next((i for i, (mode, sid, _l) in enumerate(choices)
                          if mode == monitors["mode"] and (mode != "screen" or sid == monitors["screen"])), 2)
            row = combo(t("Screens"), [text for _m, _s, text in choices], index)
            row.connect("notify::selected", self.on_screens, kind, choices)
            return row
        if key in widgets.CHOICES[kind]:
            values = widgets.CHOICES[kind][key]
            row = combo(t(CHOICE_TITLES[key]), [t(CHOICE_LABELS[key][v]) for v in values],
                        values.index(widget[key]))
            row.connect("notify::selected", self.on_choice, kind, key, values)
            return row
        if key in NUMBER_ROWS:
            low, high = widgets.RANGES[key]
            row = Adw.SpinRow.new_with_range(low, high, 1)
            row.set_title(t(NUMBER_ROWS[key]))
            row.set_numeric(True)
            row.set_value(widget[key])
            row.connect("notify::value", self.on_number, kind, key)
            return row
        if key in SLIDER_ROWS:
            title, step, unit = SLIDER_ROWS[key]
            low, high = widgets.RANGES[key]
            return self.slider(kind, key, t(title), low, high, step, widget[key], unit)
        row = Adw.SwitchRow(title=t(SWITCH_TITLES[key]))
        row.set_active(bool(widget[key]))
        row.connect("notify::active", self.on_switch, kind, key)
        return row

    def slider(self, kind: str, key: str, title: str, low: int, high: int, step: int, value: int,
               unit: str) -> Adw.ActionRow:
        row = Adw.ActionRow(title=title)
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, step)
        scale.set_size_request(240, -1)
        scale.set_draw_value(False)
        scale.set_valign(Gtk.Align.CENTER)
        scale.set_value(value)
        shown = Gtk.Label(label=f"{value}{unit}", width_chars=7, xalign=1)
        scale.connect("value-changed", self.on_slider, kind, key, step, unit, shown)
        row.add_suffix(scale)
        row.add_suffix(shown)
        return row

    # --- input ------------------------------------------------------------------------------

    def on_enabled(self, switch: Gtk.Switch, _param, kind: str) -> None:
        if self.updating:
            return
        on = switch.get_active()
        first_time = on and not self.current()[kind]["placed"]

        def mutate(widget):
            widget["enabled"] = on
            if first_time:
                widget.update(widgets.CENTER)
        self.change(kind, mutate, rebuild=True)
        if first_time and widgets.on_desktop(self.current()[kind], kind):
            self.window.toast(t("Drag it where you want it, then Save."))
            self.start_arranging()

    def on_choice(self, row: Adw.ComboRow, _param, kind: str, key: str, values: list[str]) -> None:
        if self.updating:
            return
        value = values[row.get_selected()]
        self.change(kind, lambda widget: widget.__setitem__(key, value), rebuild=key == "where")

    def on_screens(self, row: Adw.ComboRow, _param, kind: str, choices) -> None:
        if self.updating:
            return
        mode, sid, _label = choices[row.get_selected()]
        self.change(kind, lambda widget: widget.__setitem__("monitors", {"mode": mode, "screen": sid}))

    def on_switch(self, row: Adw.SwitchRow, _param, kind: str, key: str) -> None:
        if self.updating:
            return
        active = row.get_active()
        self.change(kind, lambda widget: widget.__setitem__(key, active))

    def expander_summary(self, key: str, widget: dict) -> str:
        if key == "font":
            return f"{widget['font_family'] or t('The Omarchy font')} · {t(CHOICE_LABELS['font_weight'][widget['font_weight']])}"
        if key == "effect":
            name = t(CHOICE_LABELS["effect"][widget["effect"]])
            return name if widget["effect"] == "none" else f"{name} · {widget['effect_strength']} %"
        if not widget["card"]:
            return t("Off")
        return t("Blurred") if widget["card_blur"] else t("On")

    def on_card(self, row: Adw.ExpanderRow, _param, kind: str) -> None:
        if self.updating:
            return
        on = row.get_enable_expansion()
        self.change(kind, lambda widget: widget.__setitem__("card", on), True)

    def on_font(self, button: Gtk.FontDialogButton, _param, kind: str) -> None:
        if self.updating:
            return
        desc = button.get_font_desc()
        family = desc.get_family() if desc else ""
        self.change(kind, lambda widget: widget.__setitem__("font_family", family or ""), True)

    def on_number(self, row: Adw.SpinRow, _param, kind: str, key: str) -> None:
        if self.updating:
            return
        value = int(row.get_value())
        self.change(kind, lambda widget: widget.__setitem__(key, value))

    def on_slider(self, scale: Gtk.Scale, kind: str, key: str, step: int, unit: str, shown: Gtk.Label) -> None:
        low = scale.get_adjustment().get_lower()
        value = int(low + round((scale.get_value() - low) / step) * step)
        shown.set_label(f"{value}{unit}")
        if self.updating:
            return
        # Wait until the slider rests: one write, one reload of the plugin.
        source = self.pending.pop(f"{kind}.{key}", None)
        if source:
            GLib.source_remove(source)

        def apply():
            self.pending.pop(f"{kind}.{key}", None)
            self.change(kind, lambda widget: widget.__setitem__(key, value))
            return False
        self.pending[f"{kind}.{key}"] = GLib.timeout_add(DEBOUNCE_MS, apply)

    def on_install_cava(self, button: Gtk.Button) -> None:
        button.set_sensitive(False)

        def job():
            done = widgets.install_cava(graphical=True)
            GLib.idle_add(self.after_cava, done)
        threading.Thread(target=job, daemon=True).start()

    def after_cava(self, done: bool) -> bool:
        if done and widgets.has_cava():
            widgets.apply(config.load())
            # The plugin starts cava when its settings change: nudge it.
            widgets.shell_ipc("reload")
            self.window.toast(t("cava installed"))
        else:
            self.window.toast(t("Installing cava was cancelled or failed"))
        self.build()
        return False

    # --- arranging ---------------------------------------------------------------------------

    def start_arranging(self) -> None:
        def job():
            # A plugin that was just switched on needs a moment to load.
            for _ in range(20):
                if widgets.start_editing():
                    GLib.idle_add(self.arranging, True)
                    return
                time.sleep(0.25)
            GLib.idle_add(self.window.toast, t("The widgets are not ready yet – try again in a moment."))
        threading.Thread(target=job, daemon=True).start()

    def arranging(self, on: bool) -> bool:
        self.editing = on
        self.build()
        if on:
            GLib.timeout_add(1000, self.watch_overlay)
        return False

    def watch_overlay(self) -> bool:
        """The overlay has its own Save/Cancel (and Esc): notice when it closed."""
        if not self.editing:
            return False

        def job():
            if not widgets.editing():
                GLib.idle_add(self.overlay_closed)
        threading.Thread(target=job, daemon=True).start()
        return True

    def overlay_closed(self) -> bool:
        if self.editing:
            self.editing = False
            self.build()
        return False

    def on_save(self, _button) -> None:
        cfg = widgets.save_placements(config.load(), widgets.placements())
        config.save(cfg)
        self.window.cfg = cfg
        widgets.apply(cfg)
        widgets.stop_editing()
        self.arranging(False)
        self.window.toast(t("Places saved"))

    def on_cancel(self, _button) -> None:
        widgets.shell_ipc("cancel")
        self.arranging(False)
