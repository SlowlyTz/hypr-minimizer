"""Personalization → Widgets: switch the desktop widgets on, set them up and
arrange them (move, resize and turn them on the desktop, then save).

The Widgets page is an overview: arranging, one row per widget with its
switch and a short summary, and the layouts. A row opens the widget's own
page (under Widgets, with a back button) with its settings in parts:
Placement, Visibility, Content and Look; its colors have a page under it.

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
VISIBILITY = ("Visibility", ["desktops", "only_empty", "hide_on_battery", "above"])
SECTIONS = {
    "visualizer": [("Placement", ["where", "screens", "same_place", "arrange"]), VISIBILITY, ("Content", ["player", "bars", "style", "gap", "motion"]),
                   ("Look", LOOK)],
    "lyrics": [("Placement", ["screens", "same_place", "arrange"]), VISIBILITY, ("Content", ["player", "highlight", "lines", "hide_paused"]),
               ("Look", ["align", "current_size", "scroll_ms", *LOOK])],
    "clock": [("Placement", ["screens", "same_place", "arrange"]), VISIBILITY, ("Content", ["clock_style", "hours", "seconds", "date_group", "zone2"]),
              ("Look", LOOK)],
    "system": [("Placement", ["screens", "same_place", "arrange"]), VISIBILITY,
               ("Content", ["cpu", "memory", "temperature", "curves"]), ("Look", LOOK)],
    "nowplaying": [("Placement", ["screens", "same_place", "arrange"]), VISIBILITY,
                   ("Content", ["player", "np_layout", "np_parts", "hide_idle"]), ("Look", LOOK)],
    "weather": [("Placement", ["screens", "same_place", "arrange"]), VISIBILITY,
                ("Content", ["units", "show_place", "show_details", "show_forecast"]), ("Look", LOOK)],
    "calendar": [("Placement", ["screens", "same_place", "arrange"]), VISIBILITY,
                 ("Content", ["week_start", "show_month", "show_weeks"]), ("Look", LOOK)],
    "battery": [("Placement", ["screens", "same_place", "arrange"]), VISIBILITY,
                ("Content", ["show_percent", "show_remaining", "low"]), ("Look", LOOK)],
    "network": [("Placement", ["screens", "same_place", "arrange"]), VISIBILITY, ("Content", ["curves"]),
                ("Look", LOOK)],
    "disk": [("Placement", ["screens", "same_place", "arrange"]), VISIBILITY, ("Content", ["show_free"]),
             ("Look", LOOK)],
}
# Rows that fold out: key: (title, the settings inside, the setting its own
# switch turns on and off, if any).
EXPANDERS = {"font": ("Font", ["font_family", "font_weight", "letter_spacing"], None),
             "effect": ("Effect", ["effect", "effect_strength"], None),
             "card": ("Background card", ["card_radius", "card_padding", "card_opacity", "card_blur"], "card"),
             "date_group": ("Date", ["weekday", "date_format", "date_pattern"], "date"),
             "motion": ("Motion", ["sensitivity", "smoothing", "peaks"], None),
             "np_parts": ("Parts", ["show_cover", "show_title", "show_artist", "show_album", "show_progress",
                                    "show_time", "show_controls"], None)}
# Choices that change which rows there are.
REBUILDS = {"where", "date_format", "clock_style"}
ICONS = {"visualizer": "audio-volume-high-symbolic", "lyrics": "format-justify-center-symbolic",
         "clock": "alarm-symbolic", "system": "computer-symbolic", "nowplaying": "media-playback-start-symbolic",
         "weather": "weather-few-clouds-symbolic", "calendar": "x-office-calendar-symbolic",
         "battery": "battery-good-symbolic", "network": "network-transmit-receive-symbolic",
         "disk": "drive-harddisk-symbolic"}
# The setting a widget's summary in the overview names after its screens.
SUMMARY = {"visualizer": "where", "lyrics": "highlight", "clock": "clock_style", "nowplaying": "np_layout",
           "weather": "units", "calendar": "week_start"}
# Settings picked from a list (widgets.CHOICES): their title and labels.
CHOICE_TITLES = {"where": "Where", "style": "Style", "highlight": "Highlight", "align": "Alignment",
                 "hours": "Time format", "color": "Accent color", "font_weight": "Weight", "effect": "Effect",
                 "clock_style": "Style", "date_format": "Date format", "np_layout": "Layout", "units": "Units",
                 "week_start": "Week starts on"}
CHOICE_LABELS = {
    "where": {"bar": "In the bar", "desktop": "On the desktop", "both": "Bar and desktop"},
    "style": {"bottom": "Bars from the bottom", "mirrored": "Mirrored from the middle", "wave": "Wave",
              "dots": "Dots", "circle": "Circle"},
    "highlight": {"line": "Current line", "word": "Word by word", "off": "Off"},
    "align": {"center": "Centered", "left": "Left", "right": "Right"},
    "hours": {"24": "24-hour", "12": "12-hour"},
    "color": {"accent": "Theme accent", "gradient": "Gradient", "foreground": "Theme text", "white": "White"},
    "font_weight": {"light": "Light", "regular": "Regular", "medium": "Medium", "bold": "Bold", "black": "Black"},
    "effect": {"outline": "Outline", "shadow": "Shadow", "glow": "Glow", "none": "None"},
    "clock_style": {"digital": "Digital", "analog": "Analog", "flip": "Flip cards", "words": "In words"},
    "np_layout": {"row": "Cover beside the text", "column": "Cover above the text"},
    "units": {"c": "Celsius", "f": "Fahrenheit"},
    "week_start": {"monday": "Monday", "sunday": "Sunday"},
    "date_format": {"long": "Long (3 October)", "medium": "Medium (3 Oct 2026)", "short": "Short (as the language writes it)",
                    "iso": "ISO (2026-10-03)", "custom": "Own pattern"},
}
SWITCH_TITLES = {"hide_paused": "Hide while paused", "date": "Show the date", "seconds": "Show seconds",
                 "cpu": "CPU usage", "memory": "Memory", "temperature": "Temperature", "curves": "Show the curves",
                 "card_blur": "Blur behind the card", "only_empty": "Only on an empty desktop",
                 "hide_on_battery": "Hide on battery", "above": "Above the windows",
                 "same_place": "Same place on every screen", "weekday": "Show the weekday",
                 "peaks": "Peak marks", "show_cover": "Cover", "show_title": "Title",
                 "show_artist": "Artist", "show_album": "Album", "show_progress": "Progress bar", "show_time": "Time",
                 "show_controls": "Buttons", "hide_idle": "Hide while nothing plays", "show_place": "Place",
                 "show_details": "Details", "show_forecast": "Next days", "show_month": "Month name",
                 "show_weeks": "Week numbers", "show_percent": "Percent", "show_remaining": "Time left",
                 "show_free": "Free space instead of used"}
# key: (title, step, unit); the range is widgets.RANGES.
SLIDER_ROWS = {"bars": ("Bars", 1, ""), "opacity": ("Opacity", 5, " %"),
               "letter_spacing": ("Letter spacing", 1, " px"), "effect_strength": ("Strength", 5, " %"),
               "card_radius": ("Corners", 2, " px"), "card_padding": ("Room around", 2, " px"),
               "card_opacity": ("Card opacity", 5, " %"), "scroll_ms": ("Scroll time", 50, " ms"),
               "current_size": ("Size of the line being sung", 5, " %"), "gap": ("Room between bars", 5, " %"),
               "sensitivity": ("Sensitivity", 10, " %"), "smoothing": ("Smoothing", 5, " %"),
               "low": ("Low at", 5, " %")}
# Whole numbers typed in (or stepped with − and +): key: title; the range is widgets.RANGES.
NUMBER_ROWS = {"lines": "Lines"}
HINTS = {
    "highlight": "Word by word follows the singing; most songs only have times per line, "
                 "then the words are spread over the line.",
    "same_place": "Off: arrange it on each screen on its own.",
    "player": "With an app picked, only its music counts – the visualizer then hears only that app.",
}
# Hints shown under their own row instead of over the section.
ROW_HINTS = {"same_place"}
DESCRIPTIONS = {
    "visualizer": "Bars that move with the sound playing right now.",
    "lyrics": "The words of the song playing, in time with the music (from lrclib.net).",
    "clock": "A big clock with the date.",
    "system": "CPU, memory and temperature with a curve of the last two minutes.",
    "nowplaying": "The song playing with its cover, a progress bar and buttons.",
    "weather": "The weather at the place set in Omarchy's weather panel.",
    "calendar": "This month with today marked.",
    "battery": "The battery's charge as a ring, with the time left.",
    "network": "Download and upload right now, with curves.",
    "disk": "How full every disk is.",
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
    def __init__(self, window, tab: Gtk.Box):
        """tab: the Widgets page. Each widget gets a page under it,
        "widget-<kind>", and that one a page for its colors,
        "widget-<kind>-colors" (window.add_destination)."""
        self.window = window
        self.tab = tab
        self.pages, self.color_pages = {}, {}
        for kind in widgets.KINDS:
            self.pages[kind] = window.add_destination(f"widget-{kind}", t(widgets.TITLES[kind]), parent="widgets",
                                                      icon=ICONS[kind], intro=t(DESCRIPTIONS[kind]))
            self.color_pages[kind] = window.add_destination(f"widget-{kind}-colors", t("Colors"),
                                                            parent=f"widget-{kind}")
        self.colors = widget_colors.ColorsPage(window, self.change)
        self.open_page = window.navigate
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
        self.tab.append(self.arrange_group(state))
        group = Adw.PreferencesGroup()
        for kind in widgets.KINDS:
            group.add(self.overview_row(kind, state[kind]))
        self.tab.append(group)
        self.tab.append(self.layouts_group())

    # --- layouts ---------------------------------------------------------------------------

    def screen_names(self, sids: list[str]) -> str:
        screens = config.load()["screens"]
        return " + ".join(screens.get(sid, {}).get("name", sid) for sid in sids)

    def layouts_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=t("Layouts"),
                                     description=t("Keep all widgets as they are now and bring them back later – by "
                                                   "hand, or by themselves when certain screens are connected."))
        cfg = config.load()
        connected = widgets.connected_screens()
        for layout in cfg["widget_layouts"]:
            name = layout["name"]
            subtitle = (t("Loads by itself with: {screens}", screens=self.screen_names(layout["screens"]))
                        if layout["screens"] else t("Loaded by hand"))
            row = Adw.ExpanderRow(title=name, subtitle=subtitle)
            load = Gtk.Button(label=t("Load"), valign=Gtk.Align.CENTER, css_classes=["flat"])
            load.connect("clicked", lambda _b, n=name: self.on_layout(widgets.load_layout, n, loads=True,
                                                                     toast=t("Layout “{name}” loaded", name=n)))
            row.add_suffix(load)
            auto = Adw.SwitchRow(title=t("Load with the screens connected now"), subtitle=self.screen_names(connected))
            auto.set_active(bool(layout["screens"]) and layout["screens"] == connected)
            auto.connect("notify::active", lambda r, _p, n=name: self.on_layout(
                widgets.set_layout_screens, n, connected if r.get_active() else []))
            row.add_row(auto)
            keep = Adw.ActionRow(title=t("Keep the widgets as they are now in it"))
            button = Gtk.Button(label=t("Save"), valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda _b, n=name: self.on_layout(widgets.save_layout, n,
                                                                       toast=t("Layout “{name}” saved", name=n)))
            keep.add_suffix(button)
            row.add_row(keep)
            rename = Adw.EntryRow(title=t("Name"), text=name, show_apply_button=True)
            rename.connect("apply", lambda e, n=name: self.on_layout(widgets.rename_layout, n, e.get_text()))
            row.add_row(rename)
            delete = Adw.ActionRow(title=t("Delete this layout"))
            button = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                                css_classes=["flat", "destructive-action"])
            button.connect("clicked", lambda _b, n=name: self.on_layout(widgets.delete_layout, n))
            delete.add_suffix(button)
            row.add_row(delete)
            group.add(row)
        new = Adw.EntryRow(title=t("Save as a new layout – type a name"), show_apply_button=True)
        new.connect("apply", lambda e: e.get_text().strip() and self.on_layout(
            widgets.save_layout, e.get_text(), toast=t("Layout “{name}” saved", name=e.get_text().strip())))
        group.add(new)
        return group

    def on_layout(self, action, *args, loads: bool = False, toast: str = "") -> None:
        if self.updating:
            return
        cfg = action(config.load(), *args)
        config.save(cfg)
        self.window.cfg = cfg
        if loads:
            widgets.apply(cfg)
        if toast:
            self.window.toast(toast)
        GLib.idle_add(lambda: self.build() and False)

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
            hints = [t(HINTS[key]) for key in keys if key in HINTS and key not in ROW_HINTS]
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
            title, keys, switch = EXPANDERS[key]
            row = Adw.ExpanderRow(title=t(title), subtitle=self.expander_summary(key, widget))
            if switch:
                row.set_show_enable_switch(True)
                row.set_enable_expansion(widget[switch])
                row.connect("notify::enable-expansion", self.on_expander_switch, kind, switch)
            for inner in keys:
                if inner == "date_pattern" and widget["date_format"] != "custom":
                    continue
                row.add_row(self.row(kind, inner, widget, inside=True))
            return row
        if key == "date_pattern":
            row = Adw.EntryRow(title=t("Own pattern, e.g. dd.MM.yyyy or dddd d MMMM"), text=widget["date_pattern"],
                               show_apply_button=True)
            row.connect("apply", lambda e: self.change(kind, lambda w: w.__setitem__("date_pattern", e.get_text())))
            return row
        if key == "player":
            values = ["", *widgets.players()]
            if widget["player"] and widget["player"] not in values:
                values.append(widget["player"])
            row = combo(t("React to"), [t("Whatever plays") if not v else v.replace("_", " ").title() for v in values],
                        values.index(widget["player"]))
            row.connect("notify::selected", self.on_choice, kind, "player", values)
            return row
        if key == "zone2":
            zones = ["", *sorted(widgets.time_zones())]
            row = Adw.ComboRow(title=t("Second time zone"),
                               model=Gtk.StringList.new([t("Off"), *[z.replace("_", " ") for z in zones[1:]]]))
            row.set_enable_search(True)
            row.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
            row.set_selected(zones.index(widget["zone2"]) if widget["zone2"] in zones else 0)
            row.connect("notify::selected", self.on_choice, kind, "zone2", zones)
            return row
        if key == "desktops":
            return self.desktops_row(kind, widget)
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
        row = Adw.SwitchRow(title=t(SWITCH_TITLES[key]), subtitle=t(HINTS[key]) if key in ROW_HINTS else "")
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
        self.change(kind, lambda widget: widget.__setitem__(key, value), rebuild=key in REBUILDS)

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

    def desktops_row(self, kind: str, widget: dict) -> Adw.ExpanderRow:
        chosen = widget["desktops"]
        row = Adw.ExpanderRow(title=t("Desktops"), subtitle=self.desktops_summary(chosen))
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=11, column_spacing=4,
                           row_spacing=4, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        for desktop in [*range(1, 11), widgets.FIXED_DESKTOP]:
            text = t("Fixed screen") if desktop == widgets.FIXED_DESKTOP else str(desktop)
            button = Gtk.ToggleButton(label=text, active=desktop in chosen)
            button.connect("toggled", self.on_desktop, kind, desktop)
            flow.append(button)
        holder = Gtk.ListBoxRow(activatable=False, selectable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(label(t("None picked: on every desktop."), "hint"))
        box.get_first_child().set_margin_start(8)
        box.get_first_child().set_margin_top(6)
        box.append(flow)
        holder.set_child(box)
        row.add_row(holder)
        return row

    @staticmethod
    def desktops_summary(chosen: list[int]) -> str:
        if not chosen:
            return t("Every desktop")
        names = [t("Fixed screen") if d == widgets.FIXED_DESKTOP else str(d) for d in chosen]
        return ", ".join(names)

    def on_desktop(self, button: Gtk.ToggleButton, kind: str, desktop: int) -> None:
        if self.updating:
            return
        on = button.get_active()

        def mutate(widget):
            chosen = set(widget["desktops"])
            (chosen.add if on else chosen.discard)(desktop)
            widget["desktops"] = sorted(chosen)
        self.change(kind, mutate)
        row = button.get_ancestor(Adw.ExpanderRow)
        if row is not None:
            row.set_subtitle(self.desktops_summary(self.current()[kind]["desktops"]))

    def expander_summary(self, key: str, widget: dict) -> str:
        if key == "font":
            return f"{widget['font_family'] or t('The Omarchy font')} · {t(CHOICE_LABELS['font_weight'][widget['font_weight']])}"
        if key == "np_parts":
            keys = EXPANDERS["np_parts"][1]
            return t("{shown} of {all}", shown=sum(1 for k in keys if widget[k]), all=len(keys))
        if key == "motion":
            return f"{widget['sensitivity']} % · {widget['smoothing']} %" + (f" · {t('Peak marks')}" if widget["peaks"] else "")
        if key == "date_group":
            return t(CHOICE_LABELS["date_format"][widget["date_format"]]) if widget["date"] else t("Off")
        if key == "effect":
            name = t(CHOICE_LABELS["effect"][widget["effect"]])
            return name if widget["effect"] == "none" else f"{name} · {widget['effect_strength']} %"
        if not widget["card"]:
            return t("Off")
        return t("Blurred") if widget["card_blur"] else t("On")

    def on_expander_switch(self, row: Adw.ExpanderRow, _param, kind: str, key: str) -> None:
        if self.updating:
            return
        on = row.get_enable_expansion()
        self.change(kind, lambda widget: widget.__setitem__(key, on), True)

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
