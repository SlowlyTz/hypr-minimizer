import QtQuick
import qs.Commons

// A big clock (24 or 12 hours), optionally with seconds and the date below in
// the accent color.
Item {
  id: view

  property var service: null

  readonly property var settings: service ? service.widget("clock") : null
  readonly property var spot: service ? service.placement("clock") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property bool seconds: !!(settings && settings.seconds)
  readonly property bool date: !(settings && settings.date === false)
  readonly property bool twelve: !!(settings && settings.hours === "12")
  readonly property string format: (twelve ? "h:mm" : "HH:mm") + (seconds ? ":ss" : "") + (twelve ? " AP" : "")
  readonly property date now: service ? service.now : new Date()

  implicitWidth: column.implicitWidth
  implicitHeight: column.implicitHeight
  width: implicitWidth
  height: implicitHeight

  Column {
    id: column
    spacing: Math.round(2 * view.scale)
    Text {
      anchors.horizontalCenter: parent.horizontalCenter
      text: Qt.formatTime(view.now, view.format)
      color: Color.foreground
      font.family: view.service ? view.service.fontFamily : ""
      font.pixelSize: Math.round(96 * view.scale)
      font.bold: true
      style: Text.Outline
      styleColor: Qt.rgba(0, 0, 0, 0.3)
    }
    Text {
      visible: view.date
      anchors.horizontalCenter: parent.horizontalCenter
      text: view.now.toLocaleDateString(Qt.locale(view.service && view.service.locale ? view.service.locale : ""), "dddd, d MMMM")
      color: view.service ? view.service.tint("clock") : Color.accent
      font.family: view.service ? view.service.fontFamily : ""
      font.pixelSize: Math.round(24 * view.scale)
      style: Text.Outline
      styleColor: Qt.rgba(0, 0, 0, 0.3)
    }
  }
}
