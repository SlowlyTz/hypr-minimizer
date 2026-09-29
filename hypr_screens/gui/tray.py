"""Tray icon over D-Bus: StatusNotifierItem plus a com.canonical.dbusmenu menu.

Pure Gio, no toolkit-specific tray library, so it works next to GTK 4.
"""
import os

from gi.repository import Gio, GLib

ITEM_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"

ITEM_XML = """
<node>
  <interface name="org.kde.StatusNotifierItem">
    <property name="Category" type="s" access="read"/>
    <property name="Id" type="s" access="read"/>
    <property name="Title" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconName" type="s" access="read"/>
    <property name="IconThemePath" type="s" access="read"/>
    <property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
    <property name="ItemIsMenu" type="b" access="read"/>
    <property name="Menu" type="o" access="read"/>
    <method name="Activate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="SecondaryActivate"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="ContextMenu"><arg name="x" type="i" direction="in"/><arg name="y" type="i" direction="in"/></method>
    <method name="Scroll"><arg name="delta" type="i" direction="in"/><arg name="orientation" type="s" direction="in"/></method>
    <signal name="NewIcon"/>
    <signal name="NewTitle"/>
    <signal name="NewToolTip"/>
    <signal name="NewStatus"><arg name="status" type="s"/></signal>
  </interface>
</node>
"""

MENU_XML = """
<node>
  <interface name="com.canonical.dbusmenu">
    <property name="Version" type="u" access="read"/>
    <property name="TextDirection" type="s" access="read"/>
    <property name="Status" type="s" access="read"/>
    <property name="IconThemePath" type="as" access="read"/>
    <method name="GetLayout">
      <arg name="parentId" type="i" direction="in"/>
      <arg name="recursionDepth" type="i" direction="in"/>
      <arg name="propertyNames" type="as" direction="in"/>
      <arg name="revision" type="u" direction="out"/>
      <arg name="layout" type="(ia{sv}av)" direction="out"/>
    </method>
    <method name="GetGroupProperties">
      <arg name="ids" type="ai" direction="in"/>
      <arg name="propertyNames" type="as" direction="in"/>
      <arg name="properties" type="a(ia{sv})" direction="out"/>
    </method>
    <method name="GetProperty">
      <arg name="id" type="i" direction="in"/>
      <arg name="name" type="s" direction="in"/>
      <arg name="value" type="v" direction="out"/>
    </method>
    <method name="Event">
      <arg name="id" type="i" direction="in"/>
      <arg name="eventId" type="s" direction="in"/>
      <arg name="data" type="v" direction="in"/>
      <arg name="timestamp" type="u" direction="in"/>
    </method>
    <method name="EventGroup">
      <arg name="events" type="a(isvu)" direction="in"/>
      <arg name="idErrors" type="ai" direction="out"/>
    </method>
    <method name="AboutToShow">
      <arg name="id" type="i" direction="in"/>
      <arg name="needUpdate" type="b" direction="out"/>
    </method>
    <method name="AboutToShowGroup">
      <arg name="ids" type="ai" direction="in"/>
      <arg name="updatesNeeded" type="ai" direction="out"/>
      <arg name="idErrors" type="ai" direction="out"/>
    </method>
    <signal name="ItemsPropertiesUpdated">
      <arg name="updatedProps" type="a(ia{sv})"/>
      <arg name="removedProps" type="a(ias)"/>
    </signal>
    <signal name="LayoutUpdated">
      <arg name="revision" type="u"/>
      <arg name="parent" type="i"/>
    </signal>
  </interface>
</node>
"""


class Tray:
    """entries: [(label, callback)]; None entries are separators."""

    def __init__(self, title: str, icon: str, on_activate, entries):
        self.title = title
        self.icon = icon
        self.on_activate = on_activate
        self.entries = entries
        self.bus = None
        self.name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"

    # --- setup -------------------------------------------------------------------

    def start(self) -> None:
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        item = Gio.DBusNodeInfo.new_for_xml(ITEM_XML).interfaces[0]
        menu = Gio.DBusNodeInfo.new_for_xml(MENU_XML).interfaces[0]
        self.bus.register_object(ITEM_PATH, item, self._item_call, self._item_property, None)
        self.bus.register_object(MENU_PATH, menu, self._menu_call, self._menu_property, None)
        Gio.bus_own_name_on_connection(self.bus, self.name, Gio.BusNameOwnerFlags.NONE, None, None)
        self._register()
        # The watcher lives in the bar; register again whenever it (re)appears.
        Gio.bus_watch_name_on_connection(
            self.bus, "org.kde.StatusNotifierWatcher", Gio.BusNameWatcherFlags.NONE,
            lambda *_args: self._register(), None,
        )

    def _register(self) -> None:
        self.bus.call(
            "org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher", "org.kde.StatusNotifierWatcher",
            "RegisterStatusNotifierItem", GLib.Variant("(s)", (self.name,)),
            None, Gio.DBusCallFlags.NONE, -1, None, None,
        )

    # --- StatusNotifierItem ------------------------------------------------------------

    def _item_property(self, _connection, _sender, _path, _interface, name):
        values = {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", "hypr-screens"),
            "Title": GLib.Variant("s", self.title),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", self.icon),
            "IconThemePath": GLib.Variant("s", ""),
            "ToolTip": GLib.Variant("(sa(iiay)ss)", (self.icon, [], self.title, "")),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", MENU_PATH),
        }
        return values.get(name)

    def _item_call(self, _connection, _sender, _path, _interface, method, _params, invocation):
        if method in ("Activate", "SecondaryActivate"):
            GLib.idle_add(self.on_activate)
        invocation.return_value(None)

    # --- dbusmenu ------------------------------------------------------------------------

    def _props(self, index: int) -> dict:
        entry = self.entries[index - 1]
        if entry is None:
            return {"type": GLib.Variant("s", "separator"), "visible": GLib.Variant("b", True)}
        return {
            "label": GLib.Variant("s", entry[0]),
            "enabled": GLib.Variant("b", True),
            "visible": GLib.Variant("b", True),
        }

    def _layout(self):
        children = [
            GLib.Variant("(ia{sv}av)", (index, self._props(index), []))
            for index in range(1, len(self.entries) + 1)
        ]
        return (0, {"children-display": GLib.Variant("s", "submenu")}, children)

    def _menu_property(self, _connection, _sender, _path, _interface, name):
        values = {
            "Version": GLib.Variant("u", 3),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", []),
        }
        return values.get(name)

    def _menu_call(self, _connection, _sender, _path, _interface, method, params, invocation):
        if method == "GetLayout":
            invocation.return_value(GLib.Variant("(u(ia{sv}av))", (1, self._layout())))
        elif method == "GetGroupProperties":
            ids = params.unpack()[0] or range(1, len(self.entries) + 1)
            found = [(i, self._props(i)) for i in ids if 1 <= i <= len(self.entries)]
            invocation.return_value(GLib.Variant("(a(ia{sv}))", (found,)))
        elif method == "GetProperty":
            index, name = params.unpack()
            value = self._props(index).get(name) if 1 <= index <= len(self.entries) else None
            invocation.return_value(GLib.Variant("(v)", (value or GLib.Variant("s", ""),)))
        elif method == "Event":
            index, event, _data, _time = params.unpack()
            self._clicked(index, event)
            invocation.return_value(None)
        elif method == "EventGroup":
            for index, event, _data, _time in params.unpack()[0]:
                self._clicked(index, event)
            invocation.return_value(GLib.Variant("(ai)", ([],)))
        elif method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
        elif method == "AboutToShowGroup":
            invocation.return_value(GLib.Variant("(aiai)", ([], [])))
        else:
            invocation.return_value(None)

    def _clicked(self, index: int, event: str) -> None:
        if event != "clicked" or not 1 <= index <= len(self.entries):
            return
        entry = self.entries[index - 1]
        if entry is not None:
            GLib.idle_add(entry[1])
