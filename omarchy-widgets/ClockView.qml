import QtQuick
import qs.Commons

// A big clock (24 or 12 hours), optionally with seconds and the weekday and
// date below. Every part has its own color (hours, colon, minutes, seconds,
// AM/PM, weekday, date).
Item {
  id: view

  property var service: null
  property bool editing: false

  readonly property var settings: service ? service.widget("clock") : null
  // Its place and size on this screen (set by Placed).
  property var spot: null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property bool seconds: !!(settings && settings.seconds)
  readonly property bool date: !(settings && settings.date === false)
  readonly property bool twelve: !!(settings && settings.hours === "12")
  readonly property date now: service ? service.now : new Date()
  readonly property var look: service ? service.textLook("clock") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  readonly property var locale: Qt.locale(service && service.locale ? service.locale : "")

  function paint(part, fallback) { return view.service ? view.service.colorOf("clock", part, fallback) : Color.foreground }

  implicitWidth: column.implicitWidth
  implicitHeight: column.implicitHeight
  width: implicitWidth
  height: implicitHeight

  component Part: Text {
    property string part: ""
    property bool big: true
    color: view.paint(part, Color.foreground)
    font.family: view.look.family
    font.pixelSize: Math.round((big ? 96 : 24) * view.scale)
    font.weight: big ? view.look.weight : view.look.lighter
    font.letterSpacing: view.look.spacing * view.scale
    style: view.look.outline ? Text.Outline : Text.Normal
    styleColor: view.look.outline ? view.look.outlineColor : "transparent"
  }

  Column {
    id: column
    spacing: Math.round(2 * view.scale)
    Row {
      anchors.horizontalCenter: parent.horizontalCenter
      Part { part: "hours"; text: Qt.formatTime(view.now, view.twelve ? "h" : "HH") }
      Part { part: "colon"; text: ":" }
      Part { part: "minutes"; text: Qt.formatTime(view.now, "mm") }
      Part { part: "colon"; text: ":"; visible: view.seconds }
      Part { part: "seconds"; text: Qt.formatTime(view.now, "ss"); visible: view.seconds }
      Part {
        part: "ampm"
        visible: view.twelve
        text: " " + Qt.formatTime(view.now, "AP")
      }
    }
    Row {
      visible: view.date
      anchors.horizontalCenter: parent.horizontalCenter
      Part { part: "weekday"; big: false; color: view.paint("weekday", view.service ? view.service.tint("clock") : Color.accent)
             text: view.now.toLocaleDateString(view.locale, "dddd") + ", " }
      Part { part: "date"; big: false; color: view.paint("date", view.service ? view.service.tint("clock") : Color.accent)
             text: view.now.toLocaleDateString(view.locale, "d MMMM") }
    }
  }
}
