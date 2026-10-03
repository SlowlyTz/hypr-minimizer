"""The settings window: a sidebar of pages in sections (System, Devices,
Appearance, General) with a search on top, and the page on the right.

Every place is a "destination": a page with its title bar, its content and,
if it needs one, a bar at the bottom that does not scroll away. Pages can
have pages under them (a widget's page, its colors); the title bar then has
a back button. navigate(key) opens any of them, also from the search, which
finds pages, groups and rows by their titles (gui/search.py).
"""
import copy
import os
import subprocess
import threading
import time
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk, Pango  # noqa: E402

from hypr_screens import camera, config, desktops, engine, hypr, i18n, keybinds, samsung  # noqa: E402
from hypr_screens.gui import search, texts  # noqa: E402
from hypr_screens.gui.camera_page import CameraPage  # noqa: E402
from hypr_screens.gui.look_page import LookPage  # noqa: E402
from hypr_screens.gui.samsung_page import SamsungPage  # noqa: E402
from hypr_screens.gui.sound_page import SoundPage  # noqa: E402
from hypr_screens.gui.widgets_tab import WidgetsTab  # noqa: E402
from hypr_screens.i18n import t  # noqa: E402

WIDTH, HEIGHT = 1000, 720
KEEP_SECONDS = 20
MONITOR_KEYS = {"rotation", "scale", "mode", "position"}
# After (re)building a page, widgets may report "changed" on their own; such
# signals within this time are not user input and must never touch settings.
SETTLE_SECONDS = 0.6
DOCS_URL = "https://github.com/SlowlyTz/hypr-minimizer/tree/master/docs"
# How long a place found by the search stays marked.
HIT_MS = 1800


def label(text: str, *classes: str, wrap: bool = True, xalign: float = 0.0) -> Gtk.Label:
    widget = Gtk.Label(label=text, xalign=xalign, wrap=wrap, css_classes=list(classes))
    widget.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    return widget


def item_factory(row: Adw.ComboRow | None) -> Gtk.SignalListItemFactory:
    """Dropdown items that never get cut off: full text, wrapped in the list.
    With `row`, it is the popup list and marks the selected entry."""
    factory = Gtk.SignalListItemFactory()

    def setup(_factory, item):
        box = Gtk.Box(spacing=10)
        text = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.NONE, wrap=row is not None)
        if row is not None:
            text.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            text.set_max_width_chars(46)
        box.append(text)
        if row is not None:
            box.append(Gtk.Image.new_from_icon_name("object-select-symbolic"))
        item.set_child(box)

    def bind(_factory, item):
        box = item.get_child()
        box.get_first_child().set_label(item.get_item().get_string())
        if row is not None:
            box.get_last_child().set_opacity(1 if item.get_position() == row.get_selected() else 0)

    factory.connect("setup", setup)
    factory.connect("bind", bind)
    return factory


def combo_row(title: str, labels: list[str]) -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels))
    row.set_factory(item_factory(None))
    row.set_list_factory(item_factory(row))
    return row


def clear(box: Gtk.Widget) -> None:
    child = box.get_first_child()
    while child is not None:
        following = child.get_next_sibling()
        box.remove(child)
        child = following


def children(widget: Gtk.Widget):
    child = widget.get_first_child()
    while child is not None:
        yield child
        child = child.get_next_sibling()


@dataclass
class Destination:
    key: str
    title: str
    section: str
    parent: str | None
    icon: str
    page: Adw.NavigationPage
    box: Gtk.Box               # what the page builds into
    footer: Gtk.Box            # the bar at the bottom (hidden unless filled)
    viewport: Gtk.Viewport
    words: str = ""            # more words the search finds it by
    intro: str = ""            # the sentence under its title


class SettingsWindow(Adw.ApplicationWindow):
    def __init__(self, app: Adw.Application, page: str = "screens"):
        i18n.use_configured()
        super().__init__(application=app, title=t("Screens & keys"), default_width=WIDTH, default_height=HEIGHT)
        self.cfg = config.load()
        self.connected: set[str] = set()
        self.selected: str | None = None
        self.building = False
        self.quiet_until = 0.0
        self.capture = None
        self.dest: dict[str, Destination] = {}
        self.pages: dict[str, Gtk.Box] = {}
        self.footers: dict[str, Gtk.Box] = {}
        self.navigating = False

        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        self.split = Adw.NavigationSplitView(min_sidebar_width=230, max_sidebar_width=270,
                                             sidebar_width_fraction=0.26)
        self.toasts.set_child(self.split)
        self.split.set_sidebar(self.build_sidebar())
        self.content = Adw.NavigationView()
        self.content.connect("notify::visible-page", self.on_visible_page)
        self.split.set_content(Adw.NavigationPage(title=t("Settings"), child=self.content))

        for section, items in texts.sections():
            for key, title, icon in items:
                if key == "samsung" and not samsung.present():
                    continue
                self.add_destination(key, title, icon=icon, section=section, words=t(texts.SEARCH_WORDS[key]),
                                     intro=t(texts.INTROS[key], name=camera.CARD_LABEL))
                self.add_sidebar_row(key, title, icon, section)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self.on_window_key)
        self.add_controller(keys)
        self.refresh(force=True)
        self.sound = SoundPage(self, self.pages["sound"])
        self.samsung = SamsungPage(self, self.pages["samsung"]) if "samsung" in self.pages else None
        self.look = LookPage(self, self.pages["window"], self.footers["window"])
        self.widgets = WidgetsTab(self, self.pages["widgets"])
        self.camera = CameraPage(self, self.pages["camera"])
        start = texts.LEGACY_PAGES.get(page, page)
        self.navigate(start if start in self.dest else "screens")
        GLib.timeout_add_seconds(3, self.poll)

    # --- places ------------------------------------------------------------------------

    def add_destination(self, key: str, title: str, parent: str | None = None, icon: str = "",
                        section: str = "", words: str = "", intro: str = "") -> Gtk.Box:
        """A page (under `parent`, if given); returns the box its content goes into."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22,
                        margin_top=18, margin_bottom=28, margin_start=28, margin_end=28)
        if intro:
            outer.append(label(intro, "hint", "page-intro"))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=22)
        outer.append(box)
        viewport = Gtk.Viewport(scroll_to_focus=True, child=Adw.Clamp(maximum_size=720, child=outer))
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True, child=viewport)
        toolbar = Adw.ToolbarView(content=scroller)
        toolbar.add_top_bar(Adw.HeaderBar())
        footer = Gtk.Box(spacing=12, visible=False, css_classes=["page-footer"],
                         margin_top=10, margin_bottom=10, margin_start=28, margin_end=28)
        toolbar.add_bottom_bar(footer)
        page = Adw.NavigationPage(title=title, tag=key, child=toolbar)
        parent_dest = self.dest.get(parent) if parent else None
        self.dest[key] = Destination(key, title, parent_dest.section if parent_dest else section, parent,
                                     icon or (parent_dest.icon if parent_dest else ""), page, box, footer,
                                     viewport, words, intro)
        self.pages[key] = box
        self.footers[key] = footer
        return box

    def path(self, key: str) -> list[str]:
        """The titles above a place, outermost first: its section, then its parents."""
        titles, dest = [], self.dest[key]
        while dest.parent:
            dest = self.dest[dest.parent]
            titles.insert(0, dest.title)
        return ([dest.section] if dest.section else []) + titles

    def chain(self, key: str) -> list[Destination]:
        out, dest = [], self.dest[key]
        while dest:
            out.insert(0, dest)
            dest = self.dest.get(dest.parent) if dest.parent else None
        return out

    def navigate(self, key: str, target: Gtk.Widget | None = None) -> None:
        """Open a page (with the pages above it to go back to) and show `target` on it."""
        if key not in self.dest:
            return
        chain = self.chain(key)
        self.navigating = True
        row = next((r for r in self.sidebar_rows() if r.page == chain[0].key), None)
        if row is not None and self.sidebar.get_selected_row() is not row:
            self.sidebar.select_row(row)
        self.navigating = False
        now = [page.get_tag() for page in self.stack_pages()]
        wanted = [dest.key for dest in chain]
        if now == wanted[:-1]:
            self.content.push(chain[-1].page)
        elif now != wanted:
            self.content.replace([dest.page for dest in chain])
        if target is not None:
            GLib.timeout_add(260, self.reveal, target)

    def stack_pages(self) -> list[Adw.NavigationPage]:
        model = self.content.get_navigation_stack()
        return [model.get_item(i) for i in range(model.get_n_items())]

    def reveal(self, target: Gtk.Widget) -> bool:
        """Show what the search found in the middle of the page and mark it for a moment."""
        expander = target.get_ancestor(Adw.ExpanderRow)
        if expander is not None and expander is not target and not expander.get_expanded():
            expander.set_expanded(True)
            GLib.timeout_add(320, self.reveal, target)  # once it has unfolded
            return False
        viewport = target.get_ancestor(Gtk.Viewport)
        if viewport is not None:
            ok, bounds = target.compute_bounds(viewport.get_child())
            adjustment = viewport.get_vadjustment()
            if ok and adjustment is not None:
                middle = bounds.get_y() - (adjustment.get_page_size() - bounds.get_height()) / 2
                top = adjustment.get_upper() - adjustment.get_page_size()
                adjustment.set_value(max(adjustment.get_lower(), min(top, middle)))
        target.add_css_class("search-hit")
        GLib.timeout_add(HIT_MS, lambda: (target.remove_css_class("search-hit"), False)[1])
        return False

    def current_page(self) -> str:
        """The page shown now (its key)."""
        page = self.content.get_visible_page()
        return page.get_tag() if page is not None else "screens"

    current_destination = current_page

    def on_visible_page(self, *_args) -> None:
        # The camera, sound and Samsung pages follow what is shown.
        page = self.content.get_visible_page()
        if page is not None:
            self.set_title(f"{page.get_title()} – {t('Screens & keys')}")

    # --- sidebar and search -------------------------------------------------------------

    def build_sidebar(self) -> Adw.NavigationPage:
        view = Adw.ToolbarView()
        header = Adw.HeaderBar(show_end_title_buttons=False)
        header.set_title_widget(Adw.WindowTitle(title="hypr-screens"))
        view.add_top_bar(header)
        self.search = Gtk.SearchEntry(placeholder_text=t("Search"), margin_start=12, margin_end=12,
                                      margin_bottom=8, hexpand=True)
        self.search.connect("search-changed", self.on_search)
        self.search.connect("activate", self.on_search_enter)
        self.search.connect("stop-search", lambda _e: self.search.set_text(""))
        self.search.set_key_capture_widget(self)
        down = Gtk.EventControllerKey()
        down.connect("key-pressed", self.on_search_key)
        self.search.add_controller(down)
        view.add_top_bar(self.search)

        self.sidebar = Gtk.ListBox(css_classes=["navigation-sidebar"])
        self.sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sidebar.set_header_func(self.section_header)
        self.sidebar.connect("row-selected", self.on_sidebar_row)
        self.results = Gtk.ListBox(css_classes=["navigation-sidebar", "search-results"])
        self.results.set_selection_mode(Gtk.SelectionMode.BROWSE)
        self.results.connect("row-activated", lambda _list, row: self.open_result(row.result))
        nothing = label(t("Nothing found. Try another word."), "hint", xalign=0.5)
        nothing.set_margin_top(24)
        nothing.set_margin_start(16)
        nothing.set_margin_end(16)
        self.results.set_placeholder(nothing)

        self.side_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, vexpand=True)
        self.side_stack.add_named(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.sidebar),
                                  "pages")
        self.side_stack.add_named(Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=self.results),
                                  "results")
        view.set_content(self.side_stack)
        return Adw.NavigationPage(title="hypr-screens", child=view)

    def add_sidebar_row(self, key: str, title: str, icon: str, section: str) -> None:
        row = Gtk.ListBoxRow()
        row.page = key
        row.section = section
        box = Gtk.Box(spacing=12)
        box.append(Gtk.Image.new_from_icon_name(icon))
        box.append(Gtk.Label(label=title, xalign=0))
        row.set_child(box)
        self.sidebar.append(row)

    @staticmethod
    def section_header(row: Gtk.ListBoxRow, before: Gtk.ListBoxRow | None) -> None:
        if before is not None and before.section == row.section:
            row.set_header(None)
        elif row.section:
            row.set_header(Gtk.Label(label=row.section, xalign=0, css_classes=["sidebar-section"]))
        else:
            row.set_header(Gtk.Separator(css_classes=["sidebar-separator"]))

    def on_sidebar_row(self, _box, row) -> None:
        if row is not None and not self.navigating:
            self.navigate(row.page)

    def sidebar_rows(self) -> list[Gtk.ListBoxRow]:
        # The section headers are children of the list too.
        return [row for row in children(self.sidebar) if isinstance(row, Gtk.ListBoxRow)]

    def entries(self) -> list[search.Entry]:
        """Everything the search can find: each page, and each group and row on it."""
        out = []
        for key, dest in self.dest.items():
            path = self.path(key)
            parent = dest.parent or ""
            parent_path = self.path(parent) + [self.dest[parent].title] if parent else []
            chain = [d.key for d in self.chain(key)]
            out.append(search.Entry(dest.title, path, key, "page", words=dest.words, subtitle=dest.intro,
                                    parent_dest=parent, parent_path=parent_path, target=None, chain=chain))
            here = path + [dest.title]
            stack = list(children(dest.box))
            while stack:
                widget = stack.pop()
                if not widget.get_visible() or isinstance(widget, Gtk.Popover) or getattr(widget, "search_skip", False):
                    continue
                if isinstance(widget, Adw.PreferencesGroup) and widget.get_title():
                    out.append(search.Entry(widget.get_title(), here, key, "group", target=widget,
                                            subtitle=widget.get_description() or "",
                                            parent_dest=parent, parent_path=parent_path, chain=chain))
                elif isinstance(widget, Adw.PreferencesRow) and widget.get_title():
                    subtitle = widget.get_subtitle() if hasattr(widget, "get_subtitle") else ""
                    out.append(search.Entry(widget.get_title(), here, key, "row", subtitle=subtitle or "",
                                            target=widget, parent_dest=parent, parent_path=parent_path,
                                            chain=chain))
                elif isinstance(widget, Gtk.ListBoxRow) and getattr(widget, "search_title", ""):
                    # Rows of their own make (sound devices, apps) give a title for the search.
                    out.append(search.Entry(widget.search_title, here, key, "row", target=widget,
                                            parent_dest=parent, parent_path=parent_path, chain=chain))
                stack.extend(children(widget))
        return out

    def on_search(self, entry: Gtk.SearchEntry) -> None:
        query = entry.get_text()
        clear(self.results)
        if not query.strip():
            self.side_stack.set_visible_child_name("pages")
            return
        for result in search.rank(self.entries(), query):
            self.results.append(self.result_row(result))
        self.side_stack.set_visible_child_name("results")
        first = self.results.get_row_at_index(0)
        if first is not None:
            self.results.select_row(first)

    def result_row(self, result: search.Result) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.result = result
        box = Gtk.Box(spacing=12)
        box.append(Gtk.Image.new_from_icon_name(self.dest[result.dest].icon or "preferences-system-symbolic"))
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label=result.title, xalign=0, ellipsize=Pango.EllipsizeMode.END)
        text.append(title)
        if result.path:
            text.append(Gtk.Label(label=" → ".join(result.path), xalign=0, ellipsize=Pango.EllipsizeMode.END,
                                  css_classes=["hint", "result-path"]))
        box.append(text)
        row.set_child(box)
        row.set_tooltip_text(" → ".join([*result.path, result.title]))
        return row

    def on_search_enter(self, _entry) -> None:
        row = self.results.get_selected_row() or self.results.get_row_at_index(0)
        if row is not None:
            self.open_result(row.result)

    def on_search_key(self, _controller, keyval: int, _keycode: int, _state) -> bool:
        if keyval in (Gdk.KEY_Down, Gdk.KEY_Up) and self.search.get_text():
            row = self.results.get_selected_row() or self.results.get_row_at_index(0)
            if row is None:
                return True
            step = 1 if keyval == Gdk.KEY_Down else -1
            other = self.results.get_row_at_index(row.get_index() + step)
            self.results.select_row(other or row)
            return True
        return False

    def open_result(self, result: search.Result) -> None:
        self.search.set_text("")
        self.navigate(result.dest, result.target)
        page = self.dest[result.dest].page
        GLib.idle_add(lambda: (page.grab_focus(), False)[1])

    # --- data ------------------------------------------------------------------------

    def refresh(self, force: bool = False) -> None:
        """Reload settings and monitors; rebuild when something outside changed."""
        cfg = config.load()
        monitors = hypr.monitors(include_disabled=True)
        if config.record(cfg, monitors):
            config.save(cfg)
        connected = set(config.connected([m for m in monitors if not m.get("disabled")]))
        if not force and cfg == self.cfg and connected == self.connected:
            return
        self.cfg, self.connected = cfg, connected
        if self.selected not in self.cfg["screens"]:
            self.selected = next((sid for sid, s in self.cfg["screens"].items() if s.get("internal")), None) \
                or next(iter(self.cfg["screens"]), None)
        self.build_screens()
        self.build_desktop()
        self.build_keys()
        self.build_general()

    def poll(self) -> bool:
        if self.get_visible() and self.capture is None:
            self.refresh()
        return True

    def user_input(self) -> bool:
        return not self.building and time.monotonic() >= self.quiet_until

    def settle(self) -> None:
        self.quiet_until = time.monotonic() + SETTLE_SECONDS

    def change(self, mutate, message: str | None = None, apply: bool = True,
               confirm_screen: str | None = None) -> None:
        """Apply one change to a freshly loaded config, so a stale copy in this
        window can never overwrite what the CLI or another window saved.

        confirm_screen: if the change makes that screen take new values, ask
        to keep them and undo it after KEEP_SECONDS without an answer."""
        message = message or t("Saved and applied")
        cfg = config.load()
        before = None
        if confirm_screen in cfg["screens"]:
            before = copy.deepcopy(cfg["screens"][confirm_screen].get("settings", {}))
        if mutate(cfg) is False:
            return
        config.save(cfg)
        self.cfg = cfg
        if not apply:
            self.toast(message)
            return
        undo = (confirm_screen, before) if before is not None else None
        self.run_in_background(engine.sync, message, undo)

    def run_in_background(self, work, message: str, undo=None) -> None:
        def job():
            done = None
            try:
                done = work()
                result = message
            except Exception as error:  # shown to the user, never crash the tray
                result = t("Error: {error}", error=error)
            GLib.idle_add(self.after_background, result, done, undo)
        threading.Thread(target=job, daemon=True).start()

    def after_background(self, message: str, done=None, undo=None) -> bool:
        self.refresh(force=True)
        if undo is not None and done:
            self.ask_to_keep(*undo)
        else:
            self.toast(message)
        return False

    def ask_to_keep(self, sid: str, before: dict) -> None:
        """Like a display dialog: keep the new values, or they go back by themselves."""
        dialog = Adw.AlertDialog(heading=t("Keep this setting?"))
        dialog.add_response("revert", t("Revert"))
        dialog.add_response("keep", t("Keep"))
        dialog.set_response_appearance("keep", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("revert")
        dialog.set_close_response("revert")
        state = {"left": KEEP_SECONDS, "answered": False}

        def body():
            dialog.set_body(t("The screen took the new setting.\n"
                              "Without “Keep” it goes back in {seconds} s.", seconds=state["left"]))

        def tick():
            if state["answered"]:
                return False
            state["left"] -= 1
            if state["left"] <= 0:
                dialog.close()  # emits the close response: revert
                return False
            body()
            return True

        def answered(_dialog, response):
            if state["answered"]:
                return
            state["answered"] = True
            if response == "keep":
                self.toast(t("Kept"))
            else:
                self.revert(sid, before)

        body()
        dialog.connect("response", answered)
        GLib.timeout_add_seconds(1, tick)
        dialog.present(self)

    def revert(self, sid: str, before: dict) -> None:
        def mutate(cfg):
            if sid not in cfg["screens"]:
                return False
            cfg["screens"][sid]["settings"] = copy.deepcopy(before)
        self.change(mutate, t("Reverted"))

    def toast(self, message: str) -> None:
        toast = Adw.Toast.new(message)
        toast.set_timeout(2)
        self.toasts.add_toast(toast)

    # --- page: screens -------------------------------------------------------------------

    def build_screens(self) -> None:
        page = self.pages["screens"]
        clear(page)
        self.building = True
        self.settle()

        rows = engine.screen_rows(self.cfg, self.connected)
        ids = [row["id"] for row in rows]
        names = [f"{'★ ' if row['favorite'] else ''}{row['name']}" for row in rows]
        picker = Adw.PreferencesGroup()
        combo = combo_row(t("Screen"), names)
        combo.add_prefix(Gtk.Image.new_from_icon_name("video-display-symbolic"))
        if self.selected in ids:
            combo.set_selected(ids.index(self.selected))
            screen = self.cfg["screens"][self.selected]
            combo.set_subtitle(t("connected to {connector}", connector=screen.get("connector", "?"))
                               if self.selected in self.connected
                               else t("not connected · last seen {when}", when=screen.get("last_seen", "?")))
        combo.connect("notify::selected", self.on_screen_picked, ids)
        picker.add(combo)
        page.append(picker)

        if self.selected:
            self.build_screen_detail(page, self.selected)
        self.building = False

    def on_screen_picked(self, combo: Adw.ComboRow, _param, ids: list[str]) -> None:
        if self.building:
            return
        index = combo.get_selected()
        if index >= len(ids) or ids[index] == self.selected:
            return
        self.selected = ids[index]
        GLib.idle_add(lambda: self.build_screens() and False)

    def build_screen_detail(self, page: Gtk.Box, sid: str) -> None:
        screen = self.cfg["screens"][sid]
        connected = sid in self.connected

        picture = Adw.PreferencesGroup(title=t("Picture"))
        for key in ("rotation", "scale", "mode", "position"):
            if key == "position" and screen.get("internal"):
                continue
            picture.add(self.setting_row(sid, key))
        page.append(picture)
        desktop = Adw.PreferencesGroup(title=t("Desktops"))
        desktop.add(self.setting_row(sid, "one_desktop"))
        page.append(desktop)

        manage = Adw.PreferencesGroup(title=t("This screen"), description=screen.get("description") or "")
        favorite = Adw.SwitchRow(title=t("Favorite"), subtitle=t("Favorites are higher up in the list."))
        favorite.set_active(bool(screen.get("favorite")))
        favorite.connect("notify::active", self.on_favorite, sid)
        manage.add(favorite)
        if not screen.get("internal"):
            forget = Gtk.Button(label=t("Forget"), css_classes=["destructive-action"], valign=Gtk.Align.CENTER)
            forget.set_sensitive(not connected)
            forget.set_tooltip_text(t("Unplug it first, then forget it.") if connected
                                    else t("Removes the screen and all its settings."))
            forget.connect("clicked", self.on_forget, sid)
            row = Adw.ActionRow(title=t("Forget screen"),
                                subtitle=t("Only possible while it is not connected."))
            row.add_suffix(forget)
            manage.add(row)
        page.append(manage)

    def setting_row(self, sid: str, key: str) -> Adw.ExpanderRow:
        """One setting as one row: what it is set to (and when) in the subtitle,
        unfolded the setting itself and when it applies."""
        title, explanation = texts.setting_text(key)
        setting = config.get_setting(self.cfg, sid, key) or {}
        screen = self.cfg["screens"][sid]
        values = texts.choices(key, screen, self.cfg.get("default_fixed", "off"))
        current = setting.get("value")
        conditions = texts.condition_choices(self.cfg, sid, self.connected, setting.get("when"))
        summary = values[texts.index_of(values, current)][1]
        if current is not None and setting.get("when"):
            summary += " · " + conditions[texts.index_of(conditions, setting.get("when"))][1]
        row = Adw.ExpanderRow(title=title, subtitle=summary)

        value_row = combo_row(t("Setting"), [text for _v, text in values])
        value_row.set_subtitle(explanation)
        value_row.set_selected(texts.index_of(values, current))
        value_row.connect("notify::selected", self.on_value, sid, key, values)
        row.add_row(value_row)

        when_row = combo_row(t("Applies"), [text for _v, text in conditions])
        when_row.set_selected(texts.index_of(conditions, setting.get("when")))
        when_row.set_sensitive(current is not None)
        if current is None:
            when_row.set_subtitle(t("Pick a setting above first."))
        elif setting.get("when"):
            other = self.cfg["screens"].get(setting["when"], {}).get("name", "?")
            active = setting["when"] in self.connected
            when_row.set_subtitle(t("Only while “{name}” is connected – active right now.", name=other) if active
                                  else t("Only while “{name}” is connected – not active right now.", name=other))
        else:
            when_row.set_subtitle(t("Always, whatever is connected."))
        when_row.connect("notify::selected", self.on_condition, sid, key, conditions)
        row.add_row(when_row)
        return row

    def on_value(self, row: Adw.ComboRow, _param, sid: str, key: str, values) -> None:
        if not self.user_input():
            return
        value = values[row.get_selected()][0]

        def mutate(cfg):
            if sid not in cfg["screens"]:
                return False
            stored = (config.get_setting(cfg, sid, key) or {}).get("value")
            if texts.same(stored, value):
                return False
            config.set_setting(cfg, sid, key, value)
        self.change(mutate, confirm_screen=sid if key in MONITOR_KEYS else None)

    def on_condition(self, row: Adw.ComboRow, _param, sid: str, key: str, conditions) -> None:
        if not self.user_input():
            return
        when = conditions[row.get_selected()][0]

        def mutate(cfg):
            setting = config.get_setting(cfg, sid, key)
            if setting is None or setting.get("when") == when:
                return False
            config.set_condition(cfg, sid, key, when)
        self.change(mutate, confirm_screen=sid if key in MONITOR_KEYS else None)

    def on_favorite(self, row: Adw.SwitchRow, _param, sid: str) -> None:
        if not self.user_input():
            return
        active = row.get_active()

        def mutate(cfg):
            if sid not in cfg["screens"] or bool(cfg["screens"][sid].get("favorite")) == active:
                return False
            cfg["screens"][sid]["favorite"] = active
        self.change(mutate, t("Saved"), apply=False)
        GLib.idle_add(lambda: self.refresh(force=True) and False)

    def on_forget(self, _button, sid: str) -> None:
        name = self.cfg["screens"][sid].get("name", sid)
        dialog = Adw.AlertDialog(heading=t("Forget “{name}”?", name=name),
                                 body=t("The screen leaves the list, with all its settings. "
                                        "Plug it in again and it shows up anew (without settings)."))
        dialog.add_response("cancel", t("Cancel"))
        dialog.add_response("forget", t("Forget"))
        dialog.set_response_appearance("forget", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect("response", self.on_forget_answer, sid)
        dialog.present(self)

    def on_forget_answer(self, _dialog, response: str, sid: str) -> None:
        if response != "forget":
            return

        def mutate(cfg):
            if sid not in cfg["screens"]:
                return False
            del cfg["screens"][sid]
            for screen in cfg["screens"].values():
                for setting in screen.get("settings", {}).values():
                    if setting.get("when") == sid:
                        setting["when"] = None
        self.selected = None
        self.change(mutate, t("Forgotten"))

    # --- page: one desktop -------------------------------------------------------------------

    def build_desktop(self) -> None:
        page = self.pages["desktop"]
        clear(page)
        self.building = True
        self.settle()

        status = desktops.status(self.cfg)
        now = Adw.PreferencesGroup(title=t("Right now"))
        row = Adw.ActionRow(title=texts.status_text(status, self.cfg))
        swap = Gtk.Button(label=t("Swap now"), valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        swap.set_sensitive(bool(status.get("external")))
        swap.set_tooltip_text(t("Swaps which screen is fixed – until you unplug the monitor. "
                                "Windows and layout stay."))
        swap.connect("clicked", lambda _b: self.run_in_background(lambda: desktops.swap(config.load()),
                                                                  t("Swapped")))
        row.add_suffix(swap)
        now.add(row)
        page.append(now)

        default = Adw.PreferencesGroup(
            title=t("For new monitors"),
            description=t("Which screen is fixed when the monitor itself has nothing set "
                          "(Screens → “Only one desktop on this screen”)."))
        choices = texts.default_fixed_choices()
        combo = combo_row(t("Fixed is"), [text for _v, text in choices])
        combo.set_selected(texts.index_of(choices, self.cfg["default_fixed"]))
        combo.connect("notify::selected", self.on_default_fixed, choices)
        default.add(combo)
        page.append(default)

        keys = Adw.PreferencesGroup(title=t("Desktop keys"))
        switch = Adw.SwitchRow(
            title=t("Super + 1…0 and Super + Tab through hypr-screens"),
            subtitle=t("Needed so the desktops land on the right screen. Off = plain Hyprland."))
        switch.set_active(bool(self.cfg["desktop_keys"]))
        switch.connect("notify::active", self.on_desktop_keys)
        keys.add(switch)
        page.append(keys)
        self.building = False

    def on_default_fixed(self, row: Adw.ComboRow, _param, choices) -> None:
        if not self.user_input():
            return
        value = choices[row.get_selected()][0]

        def mutate(cfg):
            if cfg["default_fixed"] == value:
                return False
            cfg["default_fixed"] = value
        self.change(mutate)

    def on_desktop_keys(self, row: Adw.SwitchRow, _param) -> None:
        if not self.user_input():
            return
        old = config.load()
        if old["desktop_keys"] == row.get_active():
            return
        cfg = config.load()
        cfg["desktop_keys"] = row.get_active()
        config.save(cfg)
        self.cfg = cfg
        keybinds.write(cfg)
        self.run_in_background(lambda: (keybinds.go_live(old, cfg), engine.sync()), t("Saved and applied"))

    # --- page: keys ----------------------------------------------------------------------------

    def build_keys(self) -> None:
        page = self.pages["keys"]
        clear(page)
        group = Adw.PreferencesGroup(title=t("Hide and bring back windows"),
                                     description=t("While recording, Backspace removes a key and Esc cancels."))
        for action in texts.actions():
            row = Adw.ActionRow(title=texts.action_label(action), subtitle=texts.action_help(action))
            for slot, combo in enumerate(self.cfg["keybinds"][action]):
                button = Gtk.Button(label=texts.combo_label(combo), valign=Gtk.Align.CENTER, css_classes=["keycap"])
                button.set_tooltip_text(t("Click, then press the new keys"))
                button.connect("clicked", self.on_key_clicked, action, slot)
                row.add_suffix(button)
            group.add(row)
        page.append(group)

    def on_key_clicked(self, _button, action: str, slot: int) -> None:
        dialog = Adw.Dialog(title=t("New key"), content_width=460)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        box.append(label(t("{action} – key {number}", action=texts.action_label(action), number=slot + 1),
                         "page-title", xalign=0.5))
        box.append(label(t("Press the new key combination now."), "capture", xalign=0.5))
        box.append(label(t("Backspace = remove key · Esc = cancel"), "hint", xalign=0.5))
        dialog.set_child(box)

        controller = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self.on_capture_key, action, slot)
        dialog.add_controller(controller)
        dialog.connect("closed", self.on_capture_closed)
        self.capture = dialog
        # Hyprland's own shortcuts would fire instead of reaching us: switch to
        # an empty keymap while recording (Esc there drops back, see poll).
        hypr.dispatch(f'hl.dsp.submap("{keybinds.RECORD_SUBMAP}")')
        GLib.timeout_add(300, self.capture_poll, dialog)
        dialog.present(self)

    def capture_poll(self, dialog) -> bool:
        if self.capture is not dialog:
            return False
        if hypr.hyprctl("submap").strip() == "default":
            dialog.close()
            return False
        return True

    def on_capture_closed(self, _dialog) -> None:
        self.capture = None
        hypr.dispatch('hl.dsp.submap("reset")')

    def on_capture_key(self, _controller, keyval: int, keycode: int, state, action: str, slot: int) -> bool:
        name = Gdk.keyval_name(keyval) or ""
        if name in texts.MODIFIER_KEYS:
            return True
        dialog = self.capture
        if name == "Escape":
            dialog.close()
            return True
        if name == "BackSpace":
            dialog.close()
            self.set_key(action, slot, "")
            return True
        combo = texts.combo_from_event(self.base_key_name(keycode, keyval), keycode, int(state))
        dialog.close()
        if combo:
            self.set_key(action, slot, combo)
        return True

    def base_key_name(self, keycode: int, keyval: int) -> str:
        """Name of the key without Shift, e.g. "period" rather than "colon"."""
        display = self.get_display()
        found, keys, keyvals = display.map_keycode(keycode)
        if found:
            for key, value in zip(keys, keyvals):
                if key.group == 0 and key.level == 0:
                    return Gdk.keyval_name(value) or ""
        return Gdk.keyval_name(keyval) or ""

    def set_key(self, action: str, slot: int, combo: str) -> None:
        taken = keybinds.taken_by_us(self.cfg, combo, except_slot=(action, slot)) if combo else None
        if taken:
            self.toast(t("{key} is already used for “{action}”.", key=texts.combo_label(combo),
                         action=texts.label_for(taken)))
            return
        others = keybinds.conflicts(combo) if combo else []
        if not others:
            self.store_key(action, slot, combo)
            return
        dialog = Adw.AlertDialog(
            heading=t("This key is already taken"),
            body=t("{key} does this right now: {current}.\nShould it do “{action}” instead?",
                   key=texts.combo_label(combo), current=", ".join(others), action=texts.action_label(action)))
        dialog.add_response("cancel", t("Cancel"))
        dialog.add_response("replace", t("Replace"))
        dialog.set_response_appearance("replace", Adw.ResponseAppearance.SUGGESTED)
        dialog.connect("response", lambda _d, answer: answer == "replace" and self.store_key(action, slot, combo))
        dialog.present(self)

    def store_key(self, action: str, slot: int, combo: str) -> None:
        old = config.load()
        cfg = config.load()
        keybinds.set_key(cfg, action, slot, combo)
        config.save(cfg)
        self.cfg = cfg
        keybinds.write(cfg)
        self.run_in_background(lambda: keybinds.go_live(old, cfg),
                               t("Key saved") if combo else t("Key removed"))

    # --- page: general -----------------------------------------------------------------------------

    def build_general(self) -> None:
        page = self.pages["general"]
        clear(page)
        self.building = True
        self.settle()
        group = Adw.PreferencesGroup(title=t("Language"))
        codes = list(i18n.LANGUAGES)
        combo = combo_row(t("Language"), [i18n.LANGUAGES[code] for code in codes])
        combo.add_prefix(Gtk.Image.new_from_icon_name("preferences-desktop-locale-symbolic"))
        combo.set_subtitle(t("Texts missing in a language are shown in English."))
        combo.set_selected(codes.index(i18n.language()) if i18n.language() in codes else 0)
        combo.connect("notify::selected", self.on_language, codes)
        group.add(combo)
        page.append(group)

        help_group = Adw.PreferencesGroup(title=t("Help"))
        page_titles = {dest.title for dest in self.dest.values()}
        for title, text in texts.help_items():
            row = Adw.ExpanderRow(title=title)
            row.add_row(self.text_row(text))
            # The page of that name is the better search result.
            row.search_skip = title in page_titles
            help_group.add(row)
        page.append(help_group)

        more = Adw.PreferencesGroup(title=t("More"))
        for title, subtitle, uri in ((t("Open the full guide"), t("All functions explained, on GitHub."), DOCS_URL),
                                     (t("Open the settings folder"), str(config.config_file().parent),
                                      config.config_file().parent.as_uri())):
            row = Adw.ActionRow(title=title, subtitle=subtitle, activatable=True)
            row.add_suffix(Gtk.Image.new_from_icon_name("adw-external-link-symbolic"))
            row.connect("activated", lambda _r, link=uri: self.open_uri(link))
            more.add(row)
        page.append(more)
        self.building = False

    def on_language(self, combo: Adw.ComboRow, _param, codes: list[str]) -> None:
        if not self.user_input():
            return
        code = codes[combo.get_selected()]
        if code == i18n.language():
            return
        cfg = config.load()
        cfg["language"] = code
        config.save(cfg)
        # Every page, the sidebar and the title are built from texts: build the window anew.
        GLib.idle_add(lambda: self.get_application().reopen_settings("general") and False)

    def text_row(self, text: str) -> Gtk.Widget:
        row = Gtk.ListBoxRow(activatable=False)
        row.set_child(label(text, xalign=0.0))
        row.get_child().set_margin_top(10)
        row.get_child().set_margin_bottom(10)
        row.get_child().set_margin_start(12)
        row.get_child().set_margin_end(12)
        return row

    def open_uri(self, uri: str) -> None:
        subprocess.Popen(["xdg-open", uri], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)

    # --- window ------------------------------------------------------------------------------------

    def on_window_key(self, _controller, keyval: int, _keycode: int, state) -> bool:
        """Ctrl+F searches; Esc clears the search, then goes back a page, then closes."""
        if self.capture is not None:
            return False
        if keyval in (Gdk.KEY_f, Gdk.KEY_F) and state & Gdk.ModifierType.CONTROL_MASK:
            self.search.grab_focus()
            return True
        if keyval != Gdk.KEY_Escape or self.get_visible_dialog() is not None:
            return False
        if self.search.get_text():
            self.search.set_text("")
        elif len(self.stack_pages()) > 1:
            self.content.pop()
        else:
            self.close()
        return True

    def float_centered(self) -> bool:
        """Fallback for a Lua file without the window rule (keybinds.render): float
        it, sized, centred on the focused screen. With the rule it already floats."""
        client = next((c for c in hypr.query_list("clients") if c.get("pid") == os.getpid()), None)
        monitor = next((m for m in hypr.monitors() if m.get("focused")), None)
        if client is None or monitor is None or client.get("floating"):
            return False
        address = client["address"]
        scale = float(monitor.get("scale") or 1)
        width, height = int(monitor["width"] / scale), int(monitor["height"] / scale)
        if int(monitor.get("transform") or 0) % 2:
            width, height = height, width
        w, h = min(WIDTH, width - 80), min(HEIGHT, height - 80)
        x, y = monitor["x"] + (width - w) // 2, monitor["y"] + (height - h) // 2
        window = f"window = 'address:{address}'"
        hypr.eval_lua("; ".join([
            f"hl.dispatch(hl.dsp.window.float({{ action = 'enable', {window} }}))",
            f"hl.dispatch(hl.dsp.window.resize({{ x = {w}, y = {h}, {window} }}))",
            f"hl.dispatch(hl.dsp.window.move({{ x = {x}, y = {y}, {window} }}))",
        ]))
        return False
