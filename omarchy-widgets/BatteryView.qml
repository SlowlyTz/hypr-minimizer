import QtQuick
import Quickshell.Services.UPower
import qs.Commons

// The battery as a ring: its charge, in the charging color while it charges
// and the low color at `low` percent or less; the percent in the middle and
// the time left (or until full) below.
Item {
  id: view

  property var service: null
  property bool editing: false
  // Its place and size on this screen (set by Placed).
  property var spot: null

  readonly property var settings: service ? service.widget("battery") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property var look: service ? service.textLook("battery") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  readonly property color tint: service ? service.tint("battery") : Color.accent
  readonly property var texts: service && service.texts ? service.texts : ({})
  function shows(key) { return !(settings && settings[key] === false) }
  function paint(part, fallback) { return view.service ? view.service.colorOf("battery", part, fallback) : fallback }

  readonly property var device: UPower.displayDevice
  readonly property bool present: !!(device && device.ready && device.isLaptopBattery)
  // Quickshell gives 0-1; older versions 0-100.
  readonly property real charge: present ? (device.percentage > 1 ? device.percentage / 100 : device.percentage) : 0.7
  readonly property bool charging: present && (device.state === UPowerDeviceState.Charging
                                               || device.state === UPowerDeviceState.PendingCharge)
  readonly property bool low: !charging && charge * 100 <= (settings ? settings.low : 20)
  readonly property color ring: charging ? paint("charging", "#a6e3a1") : low ? paint("low_ring", Color.urgent) : paint("ring", tint)
  readonly property color track: paint("ring_track", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.15))
  readonly property real size: Math.round(130 * scale)

  function duration(seconds) {
    var minutes = Math.round(seconds / 60)
    var h = Math.floor(minutes / 60)
    var m = minutes % 60
    return h > 0 ? h + " h " + m + " min" : m + " min"
  }
  readonly property string timeText: {
    if (!present) return view.texts.noBattery || "No battery"
    if (charging && device.timeToFull > 0) return (view.texts.fullIn || "Full in {time}").replace("{time}", duration(device.timeToFull))
    if (!charging && device.timeToEmpty > 0) return (view.texts.timeLeft || "{time} left").replace("{time}", duration(device.timeToEmpty))
    return charging ? (view.texts.charging || "Charging") : ""
  }

  implicitWidth: Math.max(size, below.implicitWidth)
  implicitHeight: size + (below.visible ? below.implicitHeight + Math.round(6 * scale) : 0)
  width: implicitWidth
  height: implicitHeight

  Canvas {
    id: canvas
    width: view.size
    height: view.size
    anchors.horizontalCenter: parent.horizontalCenter
    readonly property var stamp: [view.charge, view.ring, view.track, view.size]
    onStampChanged: requestPaint()
    onPaint: {
      var ctx = getContext("2d")
      ctx.reset()
      var line = Math.max(4, width / 11)
      var r = width / 2 - line / 2 - 1
      ctx.lineWidth = line
      ctx.lineCap = "round"
      ctx.beginPath()
      ctx.arc(width / 2, height / 2, r, 0, Math.PI * 2)
      ctx.strokeStyle = view.track
      ctx.stroke()
      ctx.beginPath()
      ctx.arc(width / 2, height / 2, r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.max(0.005, view.charge))
      ctx.strokeStyle = view.ring
      ctx.stroke()
    }
  }
  Column {
    anchors.centerIn: canvas
    WidgetText {
      visible: view.shows("show_percent")
      anchors.horizontalCenter: parent.horizontalCenter
      look: view.look; factor: view.scale; points: 30; strong: true
      text: Math.round(view.charge * 100) + "%"
      color: view.paint("percent", Color.foreground)
    }
    WidgetText {
      visible: view.charging
      anchors.horizontalCenter: parent.horizontalCenter
      look: view.look; factor: view.scale; points: 16
      text: String.fromCodePoint(0xf140b)
      color: view.ring
    }
  }
  WidgetText {
    id: below
    visible: view.shows("show_remaining") && view.timeText !== ""
    anchors.top: canvas.bottom
    anchors.topMargin: Math.round(6 * view.scale)
    anchors.horizontalCenter: parent.horizontalCenter
    look: view.look; factor: view.scale; points: 13
    text: view.timeText
    color: view.paint("time_left", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.7))
  }
}
