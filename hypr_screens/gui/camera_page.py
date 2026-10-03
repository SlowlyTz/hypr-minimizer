"""The "Camera" page: the virtual camera "Rotated Camera" (camera.py) on or
off, a live preview and its rotation, plus the one-time setup.

The page never opens a camera itself: the watcher's feeder writes a small
preview JPEG next to the picture it gives the apps, and the page shows that
file -- so apps and the preview never fight over the camera. While the page is
shown it asks the feeder for the preview (camera.request_preview()), which
switches the real camera on like an app would. Before the setup there is no
feeder; then the page runs its own small ffmpeg from the real camera.
"""
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango  # noqa: E402

from hypr_screens import camera, config  # noqa: E402
from hypr_screens.i18n import t  # noqa: E402

FRAME_MS = 100
REQUEST_MS = 500


def label(text: str, *classes: str) -> Gtk.Label:
    widget = Gtk.Label(label=text, xalign=0, wrap=True, css_classes=list(classes))
    widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return widget


class CameraPage:
    def __init__(self, window, page: Gtk.Box):
        self.window = window
        self.page = page
        self.direct: subprocess.Popen | None = None
        self.shown_mtime = 0.0
        self.updating = False
        self.set_up = camera.is_set_up()
        self.build()
        GLib.timeout_add(FRAME_MS, self.tick)
        GLib.timeout_add(REQUEST_MS, self.keep_requesting)

    def shown(self) -> bool:
        return self.window.get_visible() and self.window.stack.get_visible_child_name() == "camera"

    # --- building ----------------------------------------------------------------------

    def build(self) -> None:
        child = self.page.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.page.remove(child)
            child = following
        self.updating = True
        cfg = config.load()
        self.page.append(label(t("Camera"), "page-title"))
        self.page.append(label(t("Turns the camera for every app: pick “{name}” as the camera there. "
                                 "The camera only runs while an app uses it.", name=camera.CARD_LABEL), "hint"))
        if not self.set_up:
            self.page.append(self.setup_group())
        else:
            group = Adw.PreferencesGroup()
            self.switch = Adw.SwitchRow(
                title=t("Virtual camera"),
                subtitle=t("On: apps can pick “{name}”. Off: it is gone from their camera lists.",
                           name=camera.CARD_LABEL))
            self.switch.add_prefix(Gtk.Image.new_from_icon_name("camera-web-symbolic"))
            self.switch.set_active(camera.enabled(cfg))
            self.switch.connect("notify::active", self.on_enabled)
            group.add(self.switch)
            self.page.append(group)

        frame = Gtk.Frame(halign=Gtk.Align.CENTER)
        self.picture = Gtk.Picture(content_fit=Gtk.ContentFit.CONTAIN, can_shrink=True)
        self.picture.set_size_request(camera.PREVIEW_WIDTH, camera.PREVIEW_WIDTH * 9 // 16)
        frame.set_child(self.picture)
        self.page.append(frame)
        self.status = label("", "hint")
        self.status.set_xalign(0.5)
        self.page.append(self.status)

        group = Adw.PreferencesGroup(title=t("Rotation"))
        box = Gtk.Box(spacing=8, homogeneous=True, margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        current = camera.rotation(cfg)
        first = None
        for degrees in camera.ROTATIONS:
            button = Gtk.ToggleButton(label=f"{degrees}°")
            if first is None:
                first = button
            else:
                button.set_group(first)
            button.set_active(degrees == current)
            button.connect("toggled", self.on_rotation, degrees)
            box.append(button)
        holder = Gtk.ListBoxRow(activatable=False, selectable=False)
        holder.set_child(box)
        group.add(holder)
        self.page.append(group)
        self.shown_mtime = 0.0
        GLib.idle_add(self.end_update)

    def end_update(self) -> bool:
        self.updating = False
        return False

    def setup_group(self) -> Adw.PreferencesGroup:
        group = Adw.PreferencesGroup(
            title=t("One-time setup"),
            description=t("Installs the virtual camera (v4l2loopback) once and creates “{name}”. "
                          "Needs your password; this can take a minute.", name=camera.CARD_LABEL))
        row = Adw.ActionRow(title=t("Virtual camera"),
                            subtitle=t("Until then, the turn only shows in this preview."))
        self.setup_button = Gtk.Button(label=t("Set up…"), valign=Gtk.Align.CENTER,
                                       css_classes=["suggested-action"])
        self.setup_button.connect("clicked", self.on_setup)
        row.add_suffix(self.setup_button)
        group.add(row)
        return group

    # --- preview -------------------------------------------------------------------------

    def keep_requesting(self) -> bool:
        """Ask the feeder for the preview while it is shown (or run the direct one)."""
        if not self.shown():
            self.stop_direct()
            return True
        if self.set_up:
            if camera.enabled():
                camera.request_preview()
        elif self.direct is None or self.direct.poll() is not None:
            self.start_direct()
        return True

    def start_direct(self) -> None:
        real = camera.real_device()
        if real is None:
            self.direct = None
            return
        command = camera.direct_preview_command(real, camera.rotation(), camera.preview_file())
        self.direct = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)

    def stop_direct(self) -> None:
        if self.direct is not None:
            self.direct.terminate()
            try:
                self.direct.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.direct.kill()
            self.direct = None
            camera.preview_file().unlink(missing_ok=True)

    def tick(self) -> bool:
        if not self.shown():
            return True
        path = camera.preview_file()
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if mtime and mtime != self.shown_mtime:
            try:
                self.picture.set_paintable(Gdk.Texture.new_from_filename(str(path)))
                self.shown_mtime = mtime
            except GLib.Error:
                pass  # replaced while reading: the next frame comes in 100 ms
        elif not mtime and self.shown_mtime:
            self.picture.set_paintable(None)
            self.shown_mtime = 0.0
        self.status.set_label(self.status_text(bool(mtime)))
        return True

    def status_text(self, picture: bool) -> str:
        if not self.set_up:
            if camera.real_device() is None:
                return t("No camera found.")
            return (t("Preview – apps get the camera unturned until the setup is done") if picture
                    else t("Starting the camera …"))
        state = camera.status()
        if not camera.enabled() or state.get("state") == "off":
            return t("The virtual camera is off.")
        if state.get("state") == "busy":
            return t("Another app uses the camera directly – pick “{name}” there to share it.",
                     name=camera.CARD_LABEL)
        if not state:
            return t("The background service is not running (hypr-screens watch).")
        if not picture:
            return t("Starting the camera …")
        users = int(state.get("users") or 0)
        if users:
            return t("Preview – what apps get · in use by {count} app(s)", count=users)
        return t("Preview – what apps get")

    # --- input ---------------------------------------------------------------------------

    def on_enabled(self, switch: Adw.SwitchRow, _param) -> None:
        if self.updating:
            return
        on = switch.get_active()
        cfg = config.load()
        cfg["camera"]["enabled"] = on
        config.save(cfg)
        self.window.cfg = cfg
        if not on:
            self.picture.set_paintable(None)
        self.window.toast(t("Virtual camera on") if on else t("Virtual camera off"))

    def on_rotation(self, button: Gtk.ToggleButton, degrees: int) -> None:
        if self.updating or not button.get_active():
            return
        cfg = config.load()
        cfg["camera"]["rotation"] = degrees
        config.save(cfg)
        self.window.cfg = cfg
        if not self.set_up:
            self.stop_direct()  # the direct preview turns the picture itself: start it anew
        self.window.toast(t("Camera turned to {degrees}°", degrees=degrees))

    def on_setup(self, _button) -> None:
        import threading

        self.setup_button.set_sensitive(False)
        self.stop_direct()  # the setup needs the camera free
        self.window.toast(t("Setting up the virtual camera …"))

        def job():
            done = camera.setup(graphical=True)
            GLib.idle_add(self.after_setup, done)
        threading.Thread(target=job, daemon=True).start()

    def after_setup(self, done: bool) -> bool:
        self.set_up = camera.is_set_up()
        self.build()
        self.window.toast(t("Virtual camera ready: “{name}”", name=camera.CARD_LABEL) if done and self.set_up
                          else t("setup was cancelled or failed"))
        return False
