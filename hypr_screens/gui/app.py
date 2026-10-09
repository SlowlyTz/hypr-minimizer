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

from hypr_screens import config, desktops, hypr, i18n  # noqa: E402
from hypr_screens.i18n import t  # noqa: E402
from hypr_screens.gui import theme  # noqa: E402

APP_ID = "io.github.slowlytz.HyprScreens"


def focused_workspace() -> int | None:
    """The desktop on the screen you are on."""
    monitor = next((m for m in hypr.monitors() if m.get("focused")), None)
    workspace = (monitor or {}).get("activeWorkspace") or {}
    return workspace.get("id")


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

        i18n.use_configured()
        self.tray = Tray(
            t("Screens & keys"),
            "video-display-symbolic",
            self.show_settings,
            [(t("Open settings"), self.show_settings),
             (t("Swap the fixed screen"), self.swap),
             None,
             (t("Quit"), self.quit)],
        )
        self.tray.start()
        self.hold()  # keep running without a window

    def show_settings(self) -> bool:
        from hypr_screens.gui.window import SettingsWindow

        self.load_theme()
        if self.window is None:
            self.window = SettingsWindow(self)
            self.window.connect("close-request", self.on_close)
            self.window.present()
            GLib.timeout_add(150, self.window.float_centered)
            return False
        # Open on another desktop: bring it to this one (asked before present(),
        # which may switch to the window's desktop).
        here = None if not self.window.get_visible() else focused_workspace()
        self.window.refresh(force=True)
        self.window.present()
        GLib.timeout_add(150, self.window.bring_here, here)
        return False

    def reopen_settings(self, page: str) -> bool:
        """Build the window anew (e.g. in another language), on the same page."""
        from hypr_screens.gui.window import SettingsWindow

        old = self.window
        self.window = SettingsWindow(self, page)
        self.window.connect("close-request", self.on_close)
        self.window.present()
        if old is not None:
            old.destroy()
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
