import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import qs.Commons
import qs.Ui

// Workspace indicator for the fixed screen of hypr-screens.
//
// With an external monitor attached, one screen -- laptop or external, see
// see `hypr-screens menu` -- is pinned to one workspace and shows a single "1";
// desktops 1-10 live on the other one. Without one, it behaves like the stock
// widget. Each bar highlights the workspace active on *its own* screen, not the
// globally focused one.
BarWidget {
  id: root
  moduleName: "hypr-screens.workspaces"

  readonly property string panelName: "eDP-1"
  readonly property int fixedWorkspace: 99

  // The output this particular bar instance lives on.
  readonly property string screenName: {
    var window = root.QsWindow ? root.QsWindow.window : null
    return window && window.screen ? String(window.screen.name || "") : ""
  }

  readonly property bool docked: {
    var monitors = Hyprland.monitors.values
    for (var i = 0; i < monitors.length; i++) {
      if (monitors[i] && String(monitors[i].name || "") !== root.panelName) return true
    }
    return false
  }

  // The fixed screen is whichever one shows the fixed workspace; one tile only.
  readonly property bool pinned: root.docked && root.activeWorkspace === root.fixedWorkspace

  readonly property int activeWorkspace: {
    var monitors = Hyprland.monitors.values
    var fallback = 0

    for (var i = 0; i < monitors.length; i++) {
      var monitor = monitors[i]
      if (!monitor || !monitor.activeWorkspace) continue
      if (String(monitor.name || "") === root.screenName) return monitor.activeWorkspace.id
      if (monitor.focused) fallback = monitor.activeWorkspace.id
    }

    return fallback
  }

  function workspaceById(id) {
    var values = Hyprland.workspaces.values
    for (var i = 0; i < values.length; i++) {
      if (values[i].id === id) return values[i]
    }
    return null
  }

  function hasWindows(id) {
    var workspace = root.workspaceById(id)
    return workspace !== null && workspace.toplevels.values.length > 0
  }

  function workspaceIds() {
    if (root.pinned) return [root.fixedWorkspace]

    var ids = [1, 2, 3, 4, 5]
    var values = Hyprland.workspaces.values

    for (var i = 0; i < values.length; i++) {
      var id = values[i].id
      if (id > 0 && id <= 10 && ids.indexOf(id) === -1) ids.push(id)
    }

    ids.sort(function(left, right) { return left - right })
    return ids
  }

  function label(id) {
    if (id === root.fixedWorkspace) return "1"
    return id === 10 ? "0" : String(id)
  }

  // Go through hypr-screens so desktops stay on the right screen.
  function focusWorkspace(id) {
    if (!root.bar || root.pinned) return
    root.bar.run("hypr-screens switch " + Util.shellQuote(String(id)))
  }

  readonly property real trailingGap: root.vertical ? 0 : Style.spaceReal(1.5)

  implicitWidth: grid.implicitWidth + trailingGap
  implicitHeight: grid.implicitHeight

  GridLayout {
    id: grid
    anchors.fill: parent
    anchors.rightMargin: root.trailingGap
    columns: root.vertical ? 1 : root.workspaceIds().length
    columnSpacing: root.vertical ? 0 : Style.space(1)
    rowSpacing: root.vertical ? Style.space(2) : 0

    Repeater {
      model: root.workspaceIds()

      WidgetButton {
        required property int modelData

        readonly property bool occupied: root.hasWindows(modelData)
        readonly property bool focused: root.activeWorkspace === modelData

        bar: root.bar
        text: focused ? "󱓻" : root.label(modelData)
        opacity: occupied || focused ? 1 : 0.5
        horizontalMargin: 6
        verticalPadding: 6
        fixedWidth: root.vertical ? root.barSize : Style.space(20)
        fixedHeight: root.barSize
        onPressed: function() { root.focusWorkspace(modelData) }
      }
    }
  }
}
