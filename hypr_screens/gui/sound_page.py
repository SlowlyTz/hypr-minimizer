"""The "Sound" page: outputs, inputs and apps, each with volume and mute, plus
force mute for devices. Polls PipeWire once a second while it is shown.

The page is rebuilt only when the set of devices or apps changes; volumes and
mutes are updated in place, except on controls the user just touched.
"""
import queue
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk, Pango  # noqa: E402

from hypr_screens import config, sound  # noqa: E402
from hypr_screens.i18n import t  # noqa: E402

POLL_MS = 1000
APPLY_MS = 50
# External values do not overwrite a control within this time after the user touched it.
TOUCH_SECONDS = 1.5


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


def mute_icon(mute: bool) -> str:
    return "audio-volume-muted-symbolic" if mute else "audio-volume-high-symbolic"


class SoundPage:
    def __init__(self, window, page: Gtk.Box):
        self.window = window
        self.page = page
        self.signature = None
        self.data = None
        self.controls: dict[str, dict] = {}
        self.touched: dict[str, float] = {}
        self.pending: dict[str, tuple] = {}
        self.updating = False
        self.fetching = False
        self.icons: dict[str, Gio.Icon | str] = {}
        self.jobs: queue.Queue = queue.Queue()
        threading.Thread(target=self.worker, daemon=True).start()
        self.page.append(label(t("Sound"), "page-title"))
        self.page.append(label(t("Loading …"), "hint"))
        GLib.timeout_add(POLL_MS, self.tick)
        self.fetch()

    # --- data ----------------------------------------------------------------------------

    def shown(self) -> bool:
        return self.window.get_visible() and self.window.stack.get_visible_child_name() == "sound"

    def tick(self) -> bool:
        if self.shown():
            self.fetch()
        return True

    def fetch(self) -> None:
        if self.fetching:
            return
        self.fetching = True

        def job():
            try:
                data = sound.snapshot()
                data["forced"] = sound.forced(config.load())
            except Exception:  # pactl missing or PipeWire down: show nothing new
                data = None
            GLib.idle_add(self.show, data)
        threading.Thread(target=job, daemon=True).start()

    def worker(self) -> None:
        """Run pactl changes one after another, in order, off the GTK thread."""
        while True:
            work = self.jobs.get()
            try:
                work()
            except Exception as error:
                GLib.idle_add(self.window.toast, t("Error: {error}", error=error))
            if self.jobs.empty():
                GLib.idle_add(lambda: self.fetch() and False)

    def run(self, work) -> None:
        self.jobs.put(work)

    @staticmethod
    def signature_of(data: dict) -> tuple:
        devices = tuple(
            (d["key"], d["name"], d["active"], d["default"], d["label"])
            for d in data["outputs"] + data["inputs"]
        )
        apps = tuple((a["index"], a["label"], a["detail"], a["sink"]) for a in data["apps"])
        return devices, apps, tuple(sorted(data["forced"]))

    def show(self, data: dict | None) -> bool:
        self.fetching = False
        if data is None:
            return False
        self.data = data
        signature = self.signature_of(data)
        if signature != self.signature:
            self.signature = signature
            self.build()
        else:
            self.update()
        return False

    # --- building ----------------------------------------------------------------------

    def build(self) -> None:
        self.updating = True
        clear(self.page)
        self.controls.clear()
        data = self.data
        self.page.append(label(t("Sound"), "page-title"))
        self.page.append(label(t(
            "Volume for every device and every app. “Force Mute” keeps a device silent for good: "
            "it is set back to 0 % and muted at once and every second – even when an app "
            "or a key turns it up."), "hint"))

        present = {d["key"] for d in data["outputs"] + data["inputs"]}
        outputs = Adw.PreferencesGroup(title=t("Output"), description=t("Speakers, headphones, screens."))
        for device in data["outputs"]:
            outputs.add(self.device_row(device))
        self.add_absent(outputs, "sink", present)
        self.page.append(outputs)

        inputs = Adw.PreferencesGroup(title=t("Input"), description=t("Microphones."))
        for device in data["inputs"]:
            inputs.add(self.device_row(device))
        self.add_absent(inputs, "source", present)
        self.page.append(inputs)

        apps = Adw.PreferencesGroup(title=t("Apps"), description=t("Apps playing sound right now."))
        if not data["apps"]:
            apps.add(Adw.ActionRow(title=t("No app is playing sound right now.")))
        targets = [d for d in data["outputs"] if d["active"]]
        for app in data["apps"]:
            apps.add(self.app_row(app, targets))
        self.page.append(apps)
        GLib.idle_add(self.end_update)

    def end_update(self) -> bool:
        self.updating = False
        return False

    def add_absent(self, group: Adw.PreferencesGroup, kind: str, present: set[str]) -> None:
        """Force-muted devices that are not there right now, so it can be switched off."""
        for key, entry in self.data["forced"].items():
            if entry.get("kind") != kind or key in present:
                continue
            row = Adw.ActionRow(title=entry.get("label") or key,
                                subtitle=t("Not connected · stays silent as soon as it shows up"))
            row.add_prefix(Gtk.Image.new_from_icon_name("audio-volume-muted-symbolic"))
            row.add_suffix(self.force_switch({"key": key, "kind": kind, "label": entry.get("label"),
                                              "active": False}, True))
            group.add(row)

    def device_row(self, device: dict) -> Gtk.Widget:
        forced = device["key"] in self.data["forced"]
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                      margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        top = Gtk.Box(spacing=12)
        icon = Gtk.Image.new_from_icon_name(device["icon"])
        icon.set_pixel_size(24)
        top.append(icon)
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        names.append(Gtk.Label(label=device["label"], xalign=0, ellipsize=Pango.EllipsizeMode.END))
        detail = device["detail"]
        if not device["active"]:
            detail = t("Off – the sound card uses another profile")
        elif forced:
            detail = t("Force Mute – stays silent")
        if detail:
            names.append(Gtk.Label(label=detail, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                   css_classes=["dim-label", "caption"]))
        top.append(names)

        if device["active"]:
            default = Gtk.CheckButton(label=t("Default"), valign=Gtk.Align.CENTER)
            default.set_active(device["default"])
            default.set_sensitive(not device["default"])
            default.set_tooltip_text(t("New sounds play on this device."))
            default.connect("toggled", self.on_default, device)
            top.append(default)
        else:
            switch_on = Gtk.Button(label=t("Switch on"), valign=Gtk.Align.CENTER)
            switch_on.set_tooltip_text(t("Switches the sound card to the profile with this device. "
                                         "The default device stays as it is."))
            switch_on.connect("clicked", self.on_switch_on, device)
            top.append(switch_on)

        force = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        force.append(Gtk.Label(label=t("Force Mute"), css_classes=["caption"]))
        force.append(self.force_switch(device, forced))
        top.append(force)
        box.append(top)

        if device["active"]:
            box.append(self.volume_line(device["key"], device["kind"], device["name"],
                                        device["volume"], device["mute"], locked=forced))
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        row.set_child(box)
        return row

    def app_row(self, app: dict, targets: list[dict]) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6,
                      margin_top=10, margin_bottom=10, margin_start=12, margin_end=12)
        top = Gtk.Box(spacing=12)
        top.append(self.app_icon(app))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True, valign=Gtk.Align.CENTER)
        names.append(Gtk.Label(label=app["label"], xalign=0, ellipsize=Pango.EllipsizeMode.END))
        detail = " · ".join(part for part in (app["detail"], t("paused") if app["paused"] else "") if part)
        if detail:
            names.append(Gtk.Label(label=detail, xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                   css_classes=["dim-label", "caption"]))
        top.append(names)

        names_of = [t["name"] for t in targets]
        if app["sink"] in names_of and len(targets) > 1:
            output = Gtk.DropDown.new_from_strings([t["label"] for t in targets])
            output.set_valign(Gtk.Align.CENTER)
            output.set_tooltip_text(t("Which device this app plays on."))
            output.set_selected(names_of.index(app["sink"]))
            output.connect("notify::selected", self.on_app_output, app, names_of)
            top.append(output)
        box.append(top)
        box.append(self.volume_line(f"app:{app['index']}", "sink-input", str(app["index"]),
                                    app["volume"], app["mute"]))
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        row.set_child(box)
        return row

    def volume_line(self, cid: str, kind: str, target: str, volume: int, mute: bool,
                    locked: bool = False) -> Gtk.Widget:
        line = Gtk.Box(spacing=10)
        button = Gtk.ToggleButton(icon_name=mute_icon(mute), css_classes=["flat"], valign=Gtk.Align.CENTER)
        button.set_active(mute)
        button.set_tooltip_text(t("Mute"))
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, sound.VOLUME_MAX, 1)
        scale.set_hexpand(True)
        scale.set_draw_value(False)
        scale.set_value(volume)
        value = Gtk.Label(label=f"{volume} %", width_chars=5, xalign=1)
        for widget in (button, scale):
            widget.set_sensitive(not locked)
        button.connect("toggled", self.on_mute, cid, kind, target)
        scale.connect("value-changed", self.on_volume, cid, kind, target, value)
        line.append(button)
        line.append(scale)
        line.append(value)
        self.controls[cid] = {"scale": scale, "mute": button, "value": value}
        return line

    def force_switch(self, device: dict, forced: bool) -> Gtk.Switch:
        switch = Gtk.Switch(active=forced, valign=Gtk.Align.CENTER)
        switch.set_tooltip_text(t("Keeps the device silent for good, also after a restart or reconnecting."))
        switch.connect("notify::active", self.on_force, device)
        return switch

    def app_icon(self, app: dict) -> Gtk.Image:
        """The app's own icon: from its stream, its binary, or its desktop file."""
        cache_key = app["search"]
        if cache_key not in self.icons:
            theme = Gtk.IconTheme.get_for_display(self.window.get_display())
            found: Gio.Icon | str = next((name for name in app["icons"] if theme.has_icon(name)), "")
            if not found:
                for results in Gio.DesktopAppInfo.search(app["search"]) or []:
                    info = Gio.DesktopAppInfo.new(results[0]) if results else None
                    if info is not None and info.get_icon() is not None:
                        found = info.get_icon()
                        break
            self.icons[cache_key] = found or "application-x-executable-symbolic"
        icon = self.icons[cache_key]
        image = Gtk.Image.new_from_gicon(icon) if isinstance(icon, Gio.Icon) else Gtk.Image.new_from_icon_name(icon)
        image.set_pixel_size(32)
        return image

    # --- updating in place ---------------------------------------------------------------

    def update(self) -> None:
        self.updating = True
        now = time.monotonic()
        items = [(d["key"], d) for d in self.data["outputs"] + self.data["inputs"] if d["active"]]
        items += [(f"app:{a['index']}", a) for a in self.data["apps"]]
        for cid, item in items:
            control = self.controls.get(cid)
            if control is None or now - self.touched.get(cid, 0) < TOUCH_SECONDS or cid in self.pending:
                continue
            if round(control["scale"].get_value()) != item["volume"]:
                control["scale"].set_value(item["volume"])
                control["value"].set_label(f"{item['volume']} %")
            if control["mute"].get_active() != item["mute"]:
                control["mute"].set_active(item["mute"])
                control["mute"].set_icon_name(mute_icon(item["mute"]))
        self.updating = False

    # --- user input ----------------------------------------------------------------------

    def on_volume(self, scale: Gtk.Scale, cid: str, kind: str, target: str, value: Gtk.Label) -> None:
        value.set_label(f"{round(scale.get_value())} %")
        if self.updating:
            return
        self.touched[cid] = time.monotonic()
        first = cid not in self.pending
        self.pending[cid] = (kind, target, scale.get_value())
        if first:
            GLib.timeout_add(APPLY_MS, self.apply_volume, cid)

    def apply_volume(self, cid: str) -> bool:
        """Dragging fires many changes; only the latest one goes to PipeWire."""
        kind, target, value = self.pending.pop(cid)
        self.run(lambda: sound.set_volume(kind, target, value))
        return False

    def on_mute(self, button: Gtk.ToggleButton, cid: str, kind: str, target: str) -> None:
        button.set_icon_name(mute_icon(button.get_active()))
        if self.updating:
            return
        self.touched[cid] = time.monotonic()
        mute = button.get_active()
        self.run(lambda: sound.set_mute(kind, target, mute))

    def on_default(self, button: Gtk.CheckButton, device: dict) -> None:
        if self.updating or not button.get_active():
            return
        self.run(lambda: sound.set_default(device["kind"], device["name"]))
        self.window.toast(t("Default: {device}", device=device["label"]))

    def on_switch_on(self, _button, device: dict) -> None:
        self.run(lambda: sound.switch_on(device["card"], device["profile"]))
        self.window.toast(t("{device} switched on", device=device["label"]))

    def on_app_output(self, dropdown: Gtk.DropDown, _param, app: dict, names: list[str]) -> None:
        if self.updating:
            return
        sink = names[dropdown.get_selected()]
        self.run(lambda: sound.move_app(app["index"], sink))

    def on_force(self, switch: Gtk.Switch, _param, device: dict) -> None:
        if self.updating:
            return
        on = switch.get_active()
        cfg = config.load()
        entry = sound.forced(cfg).get(device["key"], {})
        sound.set_forced(cfg, device, on)
        config.save(cfg)
        self.window.cfg = cfg
        if on:
            self.run(lambda: sound.enforce(cfg))
            self.window.toast(t("Force Mute on: {device}", device=device["label"]))
        else:
            self.run(lambda: sound.release(device, entry))
            self.window.toast(t("Force Mute off: {device}", device=device["label"]))
