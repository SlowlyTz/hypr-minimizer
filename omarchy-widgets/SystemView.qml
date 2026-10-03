import QtQuick
import qs.Commons

// CPU, memory and CPU temperature (each can be left out): the value now and,
// unless switched off, the last two minutes as a small curve.
Item {
  id: view

  property var service: null

  readonly property var spot: service ? service.placement("system") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property var settings: service ? service.widget("system") : null
  readonly property var texts: service && service.texts ? service.texts : ({})
  readonly property color tint: service ? service.tint("system") : Color.accent
  readonly property bool curves: !(settings && settings.curves === false)
  function shows(key) { return !(settings && settings[key] === false) }

  // A width of its own once it was pulled wider; until then it grows with the size.
  implicitWidth: spot && spot.width > 0 ? spot.width : Math.round(300 * scale)
  implicitHeight: column.implicitHeight
  width: implicitWidth
  height: implicitHeight

  component Gauge: Item {
    id: gauge
    property string name: ""
    property string value: ""
    property var history: []
    width: view.width
    height: Math.round((view.curves ? 44 : 20) * view.scale)

    Text {
      id: nameText
      anchors.left: parent.left
      anchors.top: parent.top
      text: gauge.name
      color: Color.foreground
      opacity: 0.75
      font.family: view.service ? view.service.fontFamily : ""
      font.pixelSize: Math.round(14 * view.scale)
    }
    Text {
      anchors.right: parent.right
      anchors.top: parent.top
      text: gauge.value
      color: view.tint
      font.family: view.service ? view.service.fontFamily : ""
      font.pixelSize: Math.round(14 * view.scale)
      font.bold: true
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
        ctx.strokeStyle = view.tint
        ctx.lineWidth = Math.max(1.5, 2 * view.scale)
        ctx.stroke()
        ctx.lineTo(width, height)
        ctx.lineTo(width - (points.length - 1) * step, height)
        ctx.closePath()
        ctx.fillStyle = Qt.rgba(view.tint.r, view.tint.g, view.tint.b, 0.15)
        ctx.fill()
      }
      Connections {
        target: gauge
        function onHistoryChanged() { curve.requestPaint() }
      }
      Connections {
        target: view
        function onTintChanged() { curve.requestPaint() }
      }
    }
  }

  Column {
    id: column
    width: parent.width
    spacing: Math.round(10 * view.scale)
    Gauge {
      visible: view.shows("cpu")
      name: view.texts.cpu || "CPU"
      value: view.service ? Math.round(view.service.cpu * 100) + " %" : ""
      history: view.service ? view.service.cpuHistory : []
    }
    Gauge {
      visible: view.shows("memory")
      name: view.texts.memory || "Memory"
      value: view.service ? Math.round(view.service.memory * 100) + " %" : ""
      history: view.service ? view.service.memoryHistory : []
    }
    Gauge {
      visible: view.shows("temperature") && view.service && view.service.cpuTemperatureFile !== ""
      name: view.texts.temperature || "Temperature"
      value: view.service ? Math.round(view.service.temperature) + " °C" : ""
      history: view.service ? view.service.temperatureHistory : []
    }
  }
}
