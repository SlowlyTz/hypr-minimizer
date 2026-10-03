import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

// The visualizer in the bar, right of the desktops. Its levels come from the
// plugin's service (Service.qml), which runs cava once for bar and desktop.
BarWidget {
  id: root
  moduleName: "hypr-screens.widgets"

  readonly property var service: {
    var shell = bar ? bar.shell : null
    if (!shell) return null
    if (typeof shell.serviceFor === "function") return shell.serviceFor("hypr-screens.widgets")
    if (typeof shell.firstPartyServiceFor === "function") return shell.firstPartyServiceFor("hypr-screens.widgets")
    return null
  }
  readonly property var screen: root.QsWindow && root.QsWindow.window ? root.QsWindow.window.screen : null
  readonly property bool shown: !!service && !vertical && service.inBar() && service.screenMatches("visualizer", screen)
  readonly property var visualizer: service ? service.widget("visualizer") : null
  readonly property int count: visualizer ? visualizer.bars : 0
  readonly property real thickness: 3
  readonly property real gap: 2
  readonly property real length: Math.round(barSize * 0.6)
  readonly property bool gradient: !!(visualizer && visualizer.color === "gradient")

  visible: shown
  implicitWidth: shown ? count * thickness + (count - 1) * gap + Style.space(12) : 0
  implicitHeight: barSize

  function level(index) {
    var levels = service ? service.levels : []
    return index < levels.length ? levels[index] : 0
  }

  Row {
    anchors.centerIn: parent
    height: root.length
    spacing: root.gap
    opacity: root.service && !root.service.quiet ? 1 : 0.35
    Behavior on opacity { NumberAnimation { duration: 600 } }
    Repeater {
      model: root.shown ? root.count : 0
      Rectangle {
        required property int index
        width: root.thickness
        height: Math.max(2, root.level(index) * root.length)
        anchors.bottom: parent.bottom
        radius: 1.5
        color: root.gradient ? Color.accent : root.bar.barForeground
        gradient: root.gradient ? barGradient : null
        Gradient {
          id: barGradient
          GradientStop { position: 0.0; color: Qt.lighter(Color.accent, 1.5) }
          GradientStop { position: 1.0; color: Color.accent }
        }
        Behavior on height { NumberAnimation { duration: 60 } }
      }
    }
  }
}
