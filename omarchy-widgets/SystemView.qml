import QtQuick
import qs.Commons

// CPU, memory and CPU temperature (each can be left out): the value now and,
// unless switched off, the last two minutes as a small curve. Each gauge's
// label, value, curve and the area under it have their own color.
Item {
  id: view

  property var service: null
  property bool editing: false

  readonly property var spot: service ? service.placement("system") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property var settings: service ? service.widget("system") : null
  readonly property var texts: service && service.texts ? service.texts : ({})
  readonly property color tint: service ? service.tint("system") : Color.accent
  readonly property bool curves: !(settings && settings.curves === false)
  function shows(key) { return !(settings && settings[key] === false) }
  readonly property var look: service ? service.textLook("system") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  function paint(part, fallback) { return view.service ? view.service.colorOf("system", part, fallback) : fallback }

  // A width of its own once it was pulled wider; until then it grows with the size.
  implicitWidth: spot && spot.width > 0 ? spot.width : Math.round(300 * scale)
  implicitHeight: column.implicitHeight
  width: implicitWidth
  height: implicitHeight

  component Gauge: Item {
    id: gauge
    property string key: ""
    property string name: ""
    readonly property color line: view.paint(key + "_line", view.tint)
    readonly property color fill: view.paint(key + "_fill", Qt.rgba(line.r, line.g, line.b, 0.15))
    property string value: ""
    property var history: []
    width: view.width
    height: Math.round((view.curves ? 44 : 20) * view.scale)

    Text {
      id: nameText
      anchors.left: parent.left
      anchors.top: parent.top
      text: gauge.name
      color: view.paint(gauge.key + "_label", Color.foreground)
      opacity: view.service && view.service.hasColor("system", gauge.key + "_label") ? 1 : 0.75
      font.family: view.look.family
      font.pixelSize: Math.round(14 * view.scale)
      font.weight: view.look.lighter
      font.letterSpacing: view.look.spacing * view.scale
      style: view.look.outline ? Text.Outline : Text.Normal
      styleColor: view.look.outline ? view.look.outlineColor : "transparent"
    }
    Text {
      anchors.right: parent.right
      anchors.top: parent.top
      text: gauge.value
      color: view.paint(gauge.key + "_value", view.tint)
      font.family: view.look.family
      font.pixelSize: Math.round(14 * view.scale)
      font.weight: view.look.weight
      font.letterSpacing: view.look.spacing * view.scale
      style: view.look.outline ? Text.Outline : Text.Normal
      styleColor: view.look.outline ? view.look.outlineColor : "transparent"
    }
    Canvas {
      id: curve
      visible: view.curves
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.bottom: parent.bottom
      height: Math.round(22 * view.scale)
      onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        var points = gauge.history
        if (points.length < 2) return
        var step = width / 59
        ctx.beginPath()
        ctx.moveTo(width - (points.length - 1) * step, height - points[0] * height)
        for (var i = 1; i < points.length; i++) {
          ctx.lineTo(width - (points.length - 1 - i) * step, height - points[i] * height)
        }
        ctx.strokeStyle = gauge.line
        ctx.lineWidth = Math.max(1.5, 2 * view.scale)
        ctx.stroke()
        ctx.lineTo(width, height)
        ctx.lineTo(width - (points.length - 1) * step, height)
        ctx.closePath()
        ctx.fillStyle = gauge.fill
        ctx.fill()
      }
      Connections {
        target: gauge
        function onHistoryChanged() { curve.requestPaint() }
      }
      Connections {
        target: gauge
        function onLineChanged() { curve.requestPaint() }
        function onFillChanged() { curve.requestPaint() }
      }
    }
  }

  Column {
    id: column
    width: parent.width
    spacing: Math.round(10 * view.scale)
    Gauge {
      visible: view.shows("cpu")
      key: "cpu"
      name: view.texts.cpu || "CPU"
      value: view.service ? Math.round(view.service.cpu * 100) + " %" : ""
      history: view.service ? view.service.cpuHistory : []
    }
    Gauge {
      visible: view.shows("memory")
      key: "memory"
      name: view.texts.memory || "Memory"
      value: view.service ? Math.round(view.service.memory * 100) + " %" : ""
      history: view.service ? view.service.memoryHistory : []
    }
    Gauge {
      visible: view.shows("temperature") && view.service && view.service.cpuTemperatureFile !== ""
      key: "temperature"
      name: view.texts.temperature || "Temperature"
      value: view.service ? Math.round(view.service.temperature) + " °C" : ""
      history: view.service ? view.service.temperatureHistory : []
    }
  }
}
