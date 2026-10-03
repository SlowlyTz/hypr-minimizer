"""The "Personalization" page: first just two big buttons, "Window" (gaps,
rounding, border, blur, opacity) and "Widgets" (gui/widgets_tab.py); each
opens its own page with a back button (a widget's page goes back to Widgets).
Window's Apply and Reset sit in the
window's footer, so they stay in reach while scrolling.

Window: the sliders change nothing until "Apply"; then a dialog asks to keep
the look and puts the old one back after KEEP_SECONDS without an answer.
"""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango  # noqa: E402

from hypr_screens import config, hypr, keybinds, look, widgets  # noqa: E402
from hypr_screens.gui.widgets_tab import WidgetsTab  # noqa: E402
from hypr_screens.i18n import t  # noqa: E402

KEEP_SECONDS = 15
# key: (title, subtitle, shown as percent)
SLIDERS = {
    "gaps_in": ("Gaps between windows", "", False),
    "gaps_out": ("Gaps at the screen edge", "", False),
    "rounding": ("Corner rounding", "", False),
    "border_size": ("Border width", "", False),
    "blur_size": ("Blur strength", "", False),
    "blur_passes": ("Blur quality", "More passes look smoother and cost a little more power.", False),
    "active_opacity": ("Active window", "", True),
    "inactive_opacity": ("Other windows", "", True),
}
# The two buttons the page starts with: (page, title, text, icon).
CARDS = [
    ("window", "Window", "Gaps, corners, borders, blur and transparency.", "window-new-symbolic"),
    ("widgets", "Widgets", "Visualizer, lyrics, clock and system on the desktop.", "view-grid-symbolic"),
]
GROUPS = [
    ("Gaps", ["gaps_in", "gaps_out"]),
    ("Shape", ["rounding", "border_size"]),
    ("Blur", ["blur", "blur_size", "blur_passes"]),
    ("Transparency", ["active_opacity", "inactive_opacity"]),
]


def label(text: str, *classes: str) -> Gtk.Label:
    widget = Gtk.Label(label=text, xalign=0, wrap=True, css_classes=list(classes))
    widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return widget


def shown(key: str, value: object) -> str:
    if SLIDERS.get(key, ("", "", False))[2]:
        return f"{round(float(value) * 100)} %"
    return f"{value} px" if key in ("gaps_in", "gaps_out", "rounding", "border_size") else str(value)


class PersonalizationPage:
    def __init__(self, window, page: Gtk.Box):
        self.window = window
        self.page = page
        self.values: dict = {}
        self.live: dict = {}
        self.controls: dict = {}
        self.updating = False
        self.build()

    def build(self) -> None:
        self.nav = Gtk.Stack(transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, vhomogeneous=False,
                             interpolate_size=True)
        self.page.append(self.nav)

        home = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        home.append(label(t("Personalization"), "page-title"))
        home.append(label(t("Pick what to change."), "hint"))
        cards = Gtk.Box(spacing=14, homogeneous=True)
        for key, title, text, icon in CARDS:
            button = Gtk.Button(css_classes=["nav-card"])
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=18, margin_bottom=18,
                          margin_start=12, margin_end=12)
            image = Gtk.Image.new_from_icon_name(icon)
            image.set_pixel_size(48)
            box.append(image)
            box.append(Gtk.Label(label=t(title), css_classes=["nav-card-title"]))
            caption = label(t(text), "hint")
            caption.set_xalign(0.5)
            caption.set_justify(Gtk.Justification.CENTER)
            box.append(caption)
            button.set_child(box)
            button.connect("clicked", lambda _b, page=key: self.open(page))
            cards.append(button)
        home.append(cards)
        self.nav.add_named(home, "home")

        self.window_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.widgets_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.nav.add_named(self.subpage(t("Window"), self.window_tab), "window")
        self.nav.add_named(self.subpage(t("Widgets"), self.widgets_tab), "widgets")
        widget_pages = {}
        for kind in widgets.KINDS:
            widget_pages[kind] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
            self.nav.add_named(self.subpage(t(widgets.TITLES[kind]), widget_pages[kind], back="widgets"),
                               f"widget-{kind}")

        # The dock: Apply and Reset stay visible while the sliders scroll.
        footer = self.window.footers["personalization"]
        self.reset_button = Gtk.Button(label=t("Reset to Omarchy default"))
        self.reset_button.set_tooltip_text(t("Forgets this look; the Omarchy theme decides again."))
        self.reset_button.connect("clicked", self.on_reset)
        footer.append(self.reset_button)
        footer.append(Gtk.Box(hexpand=True))
        self.apply_button = Gtk.Button(label=t("Apply"), css_classes=["suggested-action"])
        self.apply_button.connect("clicked", self.on_apply)
        footer.append(self.apply_button)

        self.build_window_tab()
        self.widgets = WidgetsTab(self.window, self.widgets_tab, widget_pages, self.open)
        self.open("home")

    def subpage(self, title: str, body: Gtk.Box, back: str = "home") -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        header = Gtk.Box(spacing=8)
        button = Gtk.Button(icon_name="go-previous-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER)
        button.set_tooltip_text(t("Back"))
        button.connect("clicked", lambda _b: self.open(back))
        header.append(button)
        header.append(label(title, "page-title"))
        box.append(header)
        box.append(body)
        return box

    def open(self, name: str) -> None:
        self.nav.set_visible_child_name(name)
        self.window.footers["personalization"].set_visible(name == "window")
        adjustment = self.window.scrollers["personalization"].get_vadjustment()
        adjustment.set_value(adjustment.get_lower())

    # --- tab: window -----------------------------------------------------------------

    def build_window_tab(self, values: dict | None = None, live: dict | None = None) -> None:
        tab = self.window_tab
        child = tab.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            tab.remove(child)
            child = following
        self.updating = True
        saved = config.load().get("look", {})
        if live is not None:
            self.live, self.values = live, values
        else:
            # Hyprland can tell gaps or blur, not our animation speed or app
            # rules: those count as shown as they are saved.
            self.live = {**look.current(), **{k: v for k, v in saved.items() if k in ("anim_speed", "apps")}}
            if "border_colors" in saved:
                self.live["border_colors"], self.live["border_angle"] = look.current_border()
            self.values = {**self.live, **saved}
        self.controls.clear()
        tab.append(label(t("Nothing changes until “Apply”. Without “Keep” the old look comes back after "
                           "{seconds} s.", seconds=KEEP_SECONDS), "hint"))

        presets = Adw.PreferencesGroup()
        row = Adw.ActionRow(title=t("Presets"), subtitle=t("Fill in the sliders; “Apply” shows them."))
        buttons = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        for name in look.PRESETS:
            button = Gtk.Button(label=t(name), css_classes=["flat"])
            button.connect("clicked", self.on_preset, name)
            buttons.append(button)
        row.add_suffix(buttons)
        presets.add(row)
        tab.append(presets)

        for title, keys in GROUPS:
            group = Adw.PreferencesGroup(title=t(title))
            for key in keys:
                group.add(self.switch_row() if key == "blur" else self.slider_row(key))
            tab.append(group)
        tab.append(self.border_group())
        tab.append(self.animation_group())
        tab.append(self.apps_group())

        self.sync_apply()
        GLib.idle_add(self.end_update)

    def end_update(self) -> bool:
        self.updating = False
        return False

    def slider_row(self, key: str) -> Adw.ActionRow:
        title, subtitle, _percent = SLIDERS[key]
        _option, _path, kind, low, high, step = look.OPTIONS[key]
        row = Adw.ActionRow(title=t(title), subtitle=t(subtitle) if subtitle else "")
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, step)
        scale.set_size_request(240, -1)
        scale.set_draw_value(False)
        scale.set_valign(Gtk.Align.CENTER)
        scale.set_value(self.values.get(key, low))
        value = Gtk.Label(label=shown(key, self.values.get(key, low)), width_chars=6, xalign=1)
        scale.connect("value-changed", self.on_slider, key, value)
        row.add_suffix(scale)
        row.add_suffix(value)
        self.controls[key] = scale
        return row

    # --- border, animations, apps ------------------------------------------------------

    def border_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=t("Border colors"))
        own = Adw.SwitchRow(title=t("Own border colors"),
                            subtitle=t("A gradient of two colors around the active window; off: the theme's."))
        own.set_active("border_colors" in self.values)
        own.connect("notify::active", self.on_own_border)
        group.add(own)
        if "border_colors" not in self.values:
            return group
        colors = self.values["border_colors"]
        for index, title in enumerate((t("First color"), t("Second color"))):
            row = Adw.ActionRow(title=title)
            button = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=True), valign=Gtk.Align.CENTER)
            button.set_rgba(self.rgba(colors[index]))
            button.connect("notify::rgba", self.on_border_color, index)
            row.add_suffix(button)
            group.add(row)
        row = Adw.ActionRow(title=t("Angle"))
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 355, 5)
        scale.set_size_request(240, -1)
        scale.set_draw_value(False)
        scale.set_valign(Gtk.Align.CENTER)
        scale.set_value(self.values.get("border_angle", 0))
        shown_angle = Gtk.Label(label=f"{self.values.get('border_angle', 0)}°", width_chars=6, xalign=1)
        scale.connect("value-changed", self.on_border_angle, shown_angle)
        row.add_suffix(scale)
        row.add_suffix(shown_angle)
        group.add(row)
        return group

    @staticmethod
    def rgba(color: str) -> Gdk.RGBA:
        rgba = Gdk.RGBA()
        hexa = color.lstrip("#")
        rgba.parse("#" + hexa[:6])
        rgba.alpha = int(hexa[6:8], 16) / 255 if len(hexa) == 8 else 1.0
        return rgba

    @staticmethod
    def hex_color(rgba: Gdk.RGBA) -> str:
        return "#" + "".join(f"{round(v * 255):02x}" for v in (rgba.red, rgba.green, rgba.blue, rgba.alpha))

    def animation_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=t("Animations"))
        row = Adw.ActionRow(title=t("Animation speed"), subtitle=t("Omarchy's animations, faster or slower."))
        low, high = look.ANIM_RANGE
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, 0.05)
        scale.set_size_request(240, -1)
        scale.set_draw_value(False)
        scale.set_valign(Gtk.Align.CENTER)
        scale.add_mark(1.0, Gtk.PositionType.BOTTOM, None)
        speed = self.values.get("anim_speed", 1.0)
        scale.set_value(speed)
        shown_speed = Gtk.Label(label=f"{speed:.2f}×", width_chars=6, xalign=1)
        scale.connect("value-changed", self.on_anim_speed, shown_speed)
        row.add_suffix(scale)
        row.add_suffix(shown_speed)
        group.add(row)
        return group

    def apps_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=t("See-through apps"),
                                     description=t("Own transparency for single apps, by their window class."))
        for index, rule in enumerate(self.values.get("apps", [])):
            row = Adw.ExpanderRow(title=rule["class"],
                                  subtitle=t("Active {active} · other {inactive}",
                                             active=f"{round(rule['active'] * 100)} %",
                                             inactive=f"{round(rule['inactive'] * 100)} %"))
            remove = Gtk.Button(icon_name="user-trash-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER)
            remove.set_tooltip_text(t("Remove"))
            remove.connect("clicked", self.on_remove_app, index)
            row.add_suffix(remove)
            for key, title in (("active", t("Active window")), ("inactive", t("Other windows"))):
                inner = Adw.ActionRow(title=title)
                scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.3, 1.0, 0.01)
                scale.set_size_request(240, -1)
                scale.set_draw_value(False)
                scale.set_valign(Gtk.Align.CENTER)
                scale.set_value(rule[key])
                value = Gtk.Label(label=f"{round(rule[key] * 100)} %", width_chars=6, xalign=1)
                scale.connect("value-changed", self.on_app_opacity, index, key, value, row)
                inner.add_suffix(scale)
                inner.add_suffix(value)
                row.add_row(inner)
            group.add(row)
        taken = {rule["class"] for rule in self.values.get("apps", [])}
        classes = sorted({c.get("class") for c in (hypr.query("clients") or [])
                          if c.get("class") and c.get("class") not in taken})
        if classes:
            add = Adw.ComboRow(title=t("Add an open app"), model=Gtk.StringList.new(classes))
            button = Gtk.Button(icon_name="list-add-symbolic", css_classes=["flat"], valign=Gtk.Align.CENTER)
            button.set_tooltip_text(t("Add"))
            button.connect("clicked", self.on_add_app, add, classes)
            add.add_suffix(button)
            group.add(add)
        return group

    def switch_row(self) -> Adw.SwitchRow:
        row = Adw.SwitchRow(title=t("Blur behind windows"),
                            subtitle=t("Blurs what is behind see-through windows and the bar."))
        row.set_active(bool(self.values.get("blur")))
        row.connect("notify::active", self.on_blur)
        self.controls["blur"] = row
        return row

    def sync_apply(self) -> None:
        """Apply only lights up when the sliders differ from what is shown now."""
        self.apply_button.set_sensitive(look.normalize(self.values) != look.normalize(self.live))
        blur = bool(self.values.get("blur"))
        for key in ("blur_size", "blur_passes"):
            if key in self.controls:
                self.controls[key].set_sensitive(blur)

    # --- input ---------------------------------------------------------------------------

    def on_slider(self, scale: Gtk.Scale, key: str, value: Gtk.Label) -> None:
        number = look.clean(key, scale.get_value())
        value.set_label(shown(key, number))
        if self.updating:
            return
        self.values[key] = number
        self.sync_apply()

    def on_own_border(self, row: Adw.SwitchRow, _param) -> None:
        if self.updating:
            return
        if row.get_active():
            self.values["border_colors"], self.values["border_angle"] = look.current_border()
        else:
            self.values.pop("border_colors", None)
            self.values.pop("border_angle", None)
        self.rebuild_keeping_values()

    def on_border_color(self, button: Gtk.ColorDialogButton, _param, index: int) -> None:
        if self.updating:
            return
        colors = list(self.values["border_colors"])
        colors[index] = self.hex_color(button.get_rgba())
        self.values["border_colors"] = colors
        self.sync_apply()

    def on_border_angle(self, scale: Gtk.Scale, shown_angle: Gtk.Label) -> None:
        angle = int(round(scale.get_value() / 5) * 5)
        shown_angle.set_label(f"{angle}°")
        if not self.updating:
            self.values["border_angle"] = angle
            self.sync_apply()

    def on_anim_speed(self, scale: Gtk.Scale, shown_speed: Gtk.Label) -> None:
        speed = round(scale.get_value() / 0.05) * 0.05
        shown_speed.set_label(f"{speed:.2f}×")
        if not self.updating:
            self.values["anim_speed"] = round(speed, 2)
            self.sync_apply()

    def on_app_opacity(self, scale: Gtk.Scale, index: int, key: str, value: Gtk.Label, row: Adw.ExpanderRow) -> None:
        number = round(scale.get_value(), 2)
        value.set_label(f"{round(number * 100)} %")
        if self.updating:
            return
        apps = [dict(rule) for rule in self.values.get("apps", [])]
        apps[index][key] = number
        self.values["apps"] = apps
        row.set_subtitle(t("Active {active} · other {inactive}", active=f"{round(apps[index]['active'] * 100)} %",
                           inactive=f"{round(apps[index]['inactive'] * 100)} %"))
        self.sync_apply()

    def on_add_app(self, _button, combo: Adw.ComboRow, classes: list[str]) -> None:
        apps = [dict(rule) for rule in self.values.get("apps", [])]
        apps.append({"class": classes[combo.get_selected()], "active": 0.9, "inactive": 0.8})
        self.values["apps"] = apps
        self.rebuild_keeping_values()

    def on_remove_app(self, _button, index: int) -> None:
        apps = [dict(rule) for rule in self.values.get("apps", [])]
        del apps[index]
        self.values["apps"] = apps
        self.rebuild_keeping_values()

    def rebuild_keeping_values(self) -> None:
        """Rebuild the tab (rows come and go) without losing what is not applied yet."""
        values = dict(self.values)
        live = dict(self.live)
        GLib.idle_add(lambda: (self.build_window_tab(values, live), False)[1])

    def on_blur(self, row: Adw.SwitchRow, _param) -> None:
        if self.updating:
            return
        self.values["blur"] = row.get_active()
        self.sync_apply()

    def on_preset(self, _button, name: str) -> None:
        self.updating = True
        self.values.update(look.PRESETS[name])
        for key, control in self.controls.items():
            if key == "blur":
                control.set_active(bool(self.values["blur"]))
            elif key in look.OPTIONS:
                control.set_value(self.values[key])
        self.updating = False
        self.sync_apply()

    def on_apply(self, _button) -> None:
        before, wanted = dict(self.live), look.normalize(self.values)
        if look.needs_reload(before, wanted):
            look.show_by_reload(config.load(), wanted)
        else:
            look.apply(wanted)
        self.ask_to_keep(before, wanted)

    def ask_to_keep(self, before: dict, wanted: dict) -> None:
        dialog = Adw.AlertDialog(heading=t("Keep this look?"))
        dialog.add_response("revert", t("Revert"))
        dialog.add_response("keep", t("Keep"))
        dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("keep")
        dialog.set_close_response("revert")
        state = {"left": KEEP_SECONDS, "answered": False}

        def body():
            dialog.set_body(t("Without “Keep” the old look comes back in {seconds} s.", seconds=state["left"]))

        def tick():
            if state["answered"]:
                return False
            state["left"] -= 1
            if state["left"] <= 0:
                dialog.close()
                return False
            body()
            return True

        def answered(_dialog, response):
            if state["answered"]:
                return
            state["answered"] = True
            if response == "keep":
                cfg = config.load()
                cfg["look"] = wanted
                config.save(cfg)
                keybinds.write(cfg)
                self.window.cfg = cfg
                self.live = look.current()
                self.window.toast(t("Look saved"))
            else:
                if look.needs_reload(wanted, before) or look.needs_reload(before, wanted):
                    look.show_by_reload(config.load(), config.load().get("look", {}))
                else:
                    look.apply(before)
                self.values = {**before}
                self.window.toast(t("Old look back"))
            self.build_window_tab()

        body()
        dialog.connect("response", answered)
        GLib.timeout_add_seconds(1, tick)
        dialog.present(self.window)

    def on_reset(self, _button) -> None:
        cfg = config.load()
        cfg["look"] = {}
        config.save(cfg)
        keybinds.write(cfg)
        self.window.cfg = cfg
        look.reset_to_omarchy()
        self.window.toast(t("Omarchy's look is back"))
        # The reload needs a moment before Hyprland reports the theme's values.
        GLib.timeout_add(800, lambda: self.build_window_tab() and False)
