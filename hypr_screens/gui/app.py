"""One running instance: the tray icon, and the settings window on demand.

`hypr-screens tray` starts it in the background (autostart). `hypr-screens
settings`, or a click on the tray icon, shows the window; a second start just
forwards the request to the running instance (GApplication uniqueness).
"""
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from hypr_screens import config, desktops  # noqa: E402
from hypr_screens.gui import theme  # noqa: E402

APP_ID = "io.github.slowlytz.HyprScreens"


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None
        self.tray = None
        self.css = None

    def do_startup(self):
        Adw.Application.do_startup(self)
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
        self.load_theme()

    def load_theme(self) -> None:
        colors = theme.palette()
        manager = Adw.StyleManager.get_default()
        manager.set_color_scheme(Adw.ColorScheme.FORCE_LIGHT if colors.get("mode") == "light"
                                 else Adw.ColorScheme.FORCE_DARK)
        self.css.load_from_string(theme.css(colors, theme.rounding(), theme.font()))

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        if "--tray" in args:
            self.start_tray()
        else:
            self.show_settings()
        return 0

    def start_tray(self) -> None:
        if self.tray is not None:
            return
        from hypr_screens.gui.tray import Tray

        self.tray = Tray(
            "Bildschirme & Tasten",
            "video-display-symbolic",
            self.show_settings,
            [("Einstellungen öffnen", self.show_settings),
             ("Festen Bildschirm tauschen", self.swap),
             None,
             ("Beenden", self.quit)],
        )
        self.tray.start()
        self.hold()  # keep running without a window

    def show_settings(self) -> bool:
        from hypr_screens.gui.window import SettingsWindow

        self.load_theme()
        if self.window is None:
            self.window = SettingsWindow(self)
            self.window.connect("close-request", self.on_close)
        else:
            self.window.refresh(force=True)
        self.window.present()
        GLib.timeout_add(150, self.window.float_centered)
        return False

    def on_close(self, window) -> bool:
        if self.tray is None:
            return False  # started without tray: closing ends the app
        window.set_visible(False)
        return True

    def swap(self) -> bool:
        try:
            desktops.swap(config.load())
        except RuntimeError:
            pass
        if self.window is not None and self.window.get_visible():
            self.window.refresh(force=True)
        return False


def run(tray: bool) -> int:
    return App().run([sys.argv[0], "--tray"] if tray else [sys.argv[0]])
