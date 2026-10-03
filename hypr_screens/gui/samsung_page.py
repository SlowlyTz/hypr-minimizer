"""The "Samsung" page: charge limit, a one-time
full charge, battery facts, the four performance modes and the firmware
switches. Only built on a Galaxy Book with the samsung-galaxybook driver.

Values refresh every 2 seconds while the page is shown; the page is rebuilt
only when its shape changes (setup done, charger in or out, full charge on/off).
"""
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk, Pango  # noqa: E402

from hypr_screens import config, install, samsung  # noqa: E402
from hypr_screens.gui.texts import BATTERY_ROWS, MODE_HINTS  # noqa: E402
from hypr_screens.i18n import t  # noqa: E402

POLL_MS = 2000
MODE_ICONS = {
    "low-power": "battery-level-90-symbolic",
    "quiet": "weather-clear-night-symbolic",
    "balanced": "power-profile-balanced-symbolic",
    "performance": "power-profile-performance-symbolic",
}


def label(text: str, *classes: str) -> Gtk.Label:
    widget = Gtk.Label(label=text, xalign=0, wrap=True, css_classes=list(classes))
    widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return widget


def clear(box: Gtk.Widget) -> None:
    child = box.get_first_child()
    while child is not None:
        following = child.get_next_sibling()
        box.remove(child)
        child = following


def info_row(title: str) -> tuple[Adw.ActionRow, Gtk.Label]:
    row = Adw.ActionRow(title=title)
    value = Gtk.Label(css_classes=["dim-label"])
    row.add_suffix(value)
    return row, value


class SamsungPage:
    def __init__(self, window, page: Gtk.Box):
        self.window = window
        self.page = page
        self.state: dict = {}
        self.shape = None
        self.updating = False
        self.busy = False
        self.values: dict[str, Gtk.Label] = {}
        self.controls: dict = {}
        GLib.timeout_add(POLL_MS, self.tick)
        self.refresh()

    def shown(self) -> bool:
        return self.window.get_visible() and self.window.stack.get_visible_child_name() == "samsung"

    def tick(self) -> bool:
        if self.shown() and not self.busy:
            self.refresh()
        return True

    def refresh(self) -> None:
        self.state = samsung.status(config.load())
        shape = (self.state["writable"], self.state["ac"], self.state["full_once"],
                 tuple(self.state["modes"]), self.state["keyboard"] is not None)
        if shape != self.shape:
            self.shape = shape
            self.build()
        else:
            self.update()

    def run(self, work, message: str) -> None:
        """Do a change off the GTK thread (writes can take a moment), then refresh."""
        self.busy = True

        def job():
            try:
                work()
                result = message
            except Exception as error:
                result = t("Error: {error}", error=error)
            GLib.idle_add(self.done, result)
        threading.Thread(target=job, daemon=True).start()

    def done(self, message: str) -> bool:
        self.busy = False
        self.refresh()
        self.window.toast(message)
        return False

    def change(self, mutate, message: str) -> None:
        def work():
            cfg = config.load()
            mutate(cfg)
            config.save(cfg)
        self.run(work, message)

    # --- building ----------------------------------------------------------------------

    def build(self) -> None:
        self.updating = True
        clear(self.page)
        self.values.clear()
        self.controls.clear()
        state = self.state
        product = samsung.read(samsung.SYSFS / "class/dmi/id/product_family") or "Galaxy Book"
        self.page.append(label(t("Samsung"), "page-title"))
        self.page.append(label(t("{product}: the settings Samsung Settings has on Windows. "
                                 "Changes apply at once and stay after a restart.", product=product), "hint"))
        if not state["writable"]:
            self.page.append(self.setup_group())
        self.page.append(self.battery_group())
        self.page.append(self.performance_group())
        self.page.append(self.device_group())
        if state["writable"]:
            self.page.append(self.control_group())
        self.update()
        GLib.idle_add(self.end_update)

    def end_update(self) -> bool:
        self.updating = False
        return False

    def setup_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title=t("One-time setup"),
            description=t("Changing these settings needs root once: a rule lets your user write the "
                          "few Samsung files, and power-profiles-daemon leaves the performance mode to "
                          "this app (it keeps tuning the CPU). The battery panel in the bar then gets "
                          "the four modes. You will be asked for your password."))
        row = Adw.ActionRow(title=t("Allow changes"), subtitle=t("Until then, everything here is read-only."))
        button = Gtk.Button(label=t("Set up…"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        button.connect("clicked", lambda _b: self.run(self.do_setup, t("Set up")))
        row.add_suffix(button)
        group.add(row)
        return group

    def do_setup(self) -> None:
        if not samsung.setup(graphical=True):
            raise RuntimeError(t("setup was cancelled or failed"))
        install.sync_power_panel(samsung.active())

    def control_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=t("Samsung control"))
        row = Adw.ActionRow(
            title=t("Turn off"),
            subtitle=t("Gives the battery panel and the performance mode back to Omarchy and stops "
                       "holding the charge limit. Needs your password."))
        button = Gtk.Button(label=t("Turn off…"), valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
        button.connect("clicked", lambda _b: self.run(self.do_teardown, t("Samsung control off")))
        row.add_suffix(button)
        group.add(row)
        return group

    def do_teardown(self) -> None:
        if not samsung.teardown(graphical=True):
            raise RuntimeError(t("turning off was cancelled or failed"))
        install.sync_power_panel(samsung.active())

    def battery_group(self) -> Adw.PreferencesGroup:
        state = self.state
        writable = state["writable"]
        group = Adw.PreferencesGroup(title=t("Battery"))

        limit = Adw.ActionRow(title=t("Charge limit"),
                              subtitle=t("Charging stops here. Below 100 % the battery lasts more years."))
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 50, 100, 5)
        scale.set_size_request(220, -1)
        scale.set_draw_value(False)
        scale.set_valign(Gtk.Align.CENTER)
        for mark in (60, 80, 100):
            scale.add_mark(mark, Gtk.PositionType.BOTTOM, None)
        value = Gtk.Label(width_chars=5, xalign=1)
        scale.set_sensitive(writable and not state["full_once"])
        scale.connect("value-changed", self.on_limit_moved, value)
        limit.add_suffix(scale)
        limit.add_suffix(value)
        group.add(limit)
        self.controls["limit"] = (scale, value)

        if state["full_once"]:
            once = Adw.ActionRow(title=t("Charging to 100 % once"),
                                 subtitle=t("The limit comes back when the battery is full or the charger "
                                            "is unplugged."))
            button = Gtk.Button(label=t("Stop"), valign=Gtk.Align.CENTER)
            button.connect("clicked", lambda _b: self.change(lambda cfg: samsung.full_once(cfg, False),
                                                             t("Charge limit back")))
        else:
            once = Adw.ActionRow(title=t("Charge to 100 % once"),
                                 subtitle=t("For a long day away: one full charge, then the limit is back.")
                                 if state["ac"] else t("Plug in the charger first."))
            button = Gtk.Button(label=t("Charge now"), valign=Gtk.Align.CENTER)
            button.set_sensitive(writable and state["ac"])
            button.connect("clicked", lambda _b: self.change(lambda cfg: samsung.full_once(cfg, True),
                                                             t("Charging to 100 % once")))
        once.add_suffix(button)
        group.add(once)

        for key, title in BATTERY_ROWS.items():
            row, text = info_row(t(title))
            if key == "health":
                row.set_subtitle(t("Capacity now compared to when the battery was new."))
            self.values[key] = text
            group.add(row)
        return group

    def performance_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title=t("Performance mode"),
            description=t("How fast and how loud. Also in the battery panel in the bar and on the "
                          "keyboard's mode key."))
        box = Gtk.Box(spacing=8, homogeneous=True, margin_top=10, margin_bottom=10,
                      margin_start=10, margin_end=10)
        first = None
        self.controls["modes"] = {}
        for mode, text in self.state["modes"]:
            button = Gtk.ToggleButton()
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, margin_top=8, margin_bottom=8)
            content.append(Gtk.Image.new_from_icon_name(MODE_ICONS.get(mode, "computer-symbolic")))
            content.append(Gtk.Label(label=t(text)))
            button.set_child(content)
            button.set_tooltip_text(t(MODE_HINTS[mode]) if mode in MODE_HINTS else "")
            if first is None:
                first = button
            else:
                button.set_group(first)
            button.set_sensitive(self.state["writable"])
            button.connect("toggled", self.on_mode, mode, text)
            box.append(button)
            self.controls["modes"][mode] = button
        # In a list row, so it sits inside the group's card above "Fan".
        holder = Gtk.ListBoxRow(activatable=False, selectable=False)
        holder.set_child(box)
        group.add(holder)
        row, text = info_row(t("Fan"))
        self.values["fan"] = text
        group.add(row)
        row, text = info_row(t("CPU temperature"))
        self.values["cpu"] = text
        group.add(row)
        return group

    def device_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(title=t("Device"))
        self.controls["attributes"] = {}
        for name, title in samsung.ATTRIBUTES.items():
            if self.state["attributes"].get(name) is None:
                continue
            row = Adw.SwitchRow(title=t(title))
            row.set_sensitive(self.state["attributes_writable"])
            row.connect("notify::active", self.on_attribute, name, title)
            group.add(row)
            self.controls["attributes"][name] = row
        if self.state["keyboard"] is not None:
            _level, top = self.state["keyboard"]
            row = Adw.ActionRow(title=t("Keyboard backlight"))
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, top, 1)
            scale.set_size_request(220, -1)
            scale.set_draw_value(False)
            scale.set_valign(Gtk.Align.CENTER)
            for mark in range(top + 1):
                scale.add_mark(mark, Gtk.PositionType.BOTTOM, None)
            scale.connect("value-changed", self.on_keyboard)
            row.add_suffix(scale)
            group.add(row)
            self.controls["keyboard"] = scale
        return group

    # --- values ------------------------------------------------------------------------

    def update(self) -> None:
        self.updating = True
        state, battery = self.state, self.state["battery"]
        scale, value = self.controls["limit"]
        if not self.controls.get("limit_pending") and state["limit"] is not None:
            scale.set_value(state["limit"])
            value.set_label(f"{state['limit']} %")
        level = battery.get("percent")
        self.values["level"].set_label(f"{level} % · {battery.get('status') or '?'}" if level is not None else "—")
        health = battery.get("health")
        self.values["health"].set_label(f"{health} %" if health is not None else "—")
        self.values["cycles"].set_label(str(battery.get("cycles") if battery.get("cycles") is not None else "—"))
        watts = battery.get("watts")
        self.values["power"].set_label(f"{watts} W" if watts else "—")
        fan = state["fan"]
        if fan["running"] is None:
            self.values["fan"].set_label("—")
        elif fan["running"]:
            self.values["fan"].set_label(t("Running · {rpm} rpm", rpm=fan["rpm"]) if fan["rpm"] else t("Running"))
        else:
            self.values["fan"].set_label(t("Off"))
        temperature = state["cpu_temperature"]
        self.values["cpu"].set_label(f"{temperature} °C" if temperature is not None else "—")
        button = self.controls["modes"].get(state["mode"])
        if button is not None and not button.get_active():
            button.set_active(True)
        for name, row in self.controls["attributes"].items():
            if row.get_active() != bool(state["attributes"].get(name)):
                row.set_active(bool(state["attributes"].get(name)))
        if "keyboard" in self.controls and state["keyboard"] is not None:
            self.controls["keyboard"].set_value(state["keyboard"][0])
        self.updating = False

    # --- user input ----------------------------------------------------------------------

    def on_limit_moved(self, scale: Gtk.Scale, value: Gtk.Label) -> None:
        limit = int(round(scale.get_value() / 5) * 5)
        value.set_label(f"{limit} %")
        if self.updating:
            return
        # Wait until the slider rests, so dragging writes the firmware once.
        pending = self.controls.get("limit_pending")
        if pending:
            GLib.source_remove(pending)
        self.controls["limit_pending"] = GLib.timeout_add(400, self.apply_limit, limit)

    def apply_limit(self, limit: int) -> bool:
        self.controls["limit_pending"] = None
        self.change(lambda cfg: samsung.set_limit(cfg, limit), t("Charge limit {limit} %", limit=limit))
        return False

    def on_mode(self, button: Gtk.ToggleButton, mode: str, text: str) -> None:
        if self.updating or not button.get_active() or mode == self.state.get("mode"):
            return
        self.change(lambda cfg: samsung.set_mode(cfg, mode), t("Performance mode: {mode}", mode=t(text)))

    def on_attribute(self, row: Adw.SwitchRow, _param, name: str, title: str) -> None:
        if self.updating:
            return
        on = row.get_active()

        def work():
            if not samsung.set_attribute(name, on):
                raise RuntimeError(t("could not change it (setup done?)"))
        self.run(work, t("{setting}: on", setting=t(title)) if on else t("{setting}: off", setting=t(title)))

    def on_keyboard(self, scale: Gtk.Scale) -> None:
        if self.updating:
            return
        level = int(round(scale.get_value()))
        self.run(lambda: samsung.set_keyboard(level), t("Keyboard backlight {level}", level=level))
