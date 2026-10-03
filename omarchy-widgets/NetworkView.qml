import QtQuick
import qs.Commons

// Download and upload right now (all network devices but loopback) and,
// unless switched off, the last two minutes as curves.
Item {
  id: view

  property var service: null
  property bool editing: false
  // Its place and size on this screen (set by Placed).
  property var spot: null

  readonly property var settings: service ? service.widget("network") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property var look: service ? service.textLook("network") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  readonly property color tint: service ? service.tint("network") : Color.accent
  readonly property var texts: service && service.texts ? service.texts : ({})
  readonly property bool curves: !(settings && settings.curves === false)
  function paint(part, fallback) { return view.service ? view.service.colorOf("network", part, fallback) : fallback }

  implicitWidth: spot && spot.width > 0 ? spot.width : Math.round(300 * scale)
  implicitHeight: column.implicitHeight
  width: implicitWidth
  height: implicitHeight

  component Rate: Item {
    id: gauge
    property string key: ""
    property string name: ""
    property real value: 0
    property var history: []
    readonly property color line: view.paint(key + "_line", view.tint)
    width: view.width
    height: Math.round((view.curves ? 46 : 20) * view.scale)

    WidgetText {
      anchors.left: parent.left
      look: view.look; factor: view.scale; points: 14
      text: gauge.name
      color: view.paint("labels", Color.foreground)
    }
    WidgetText {
      anchors.right: parent.right
      look: view.look; factor: view.scale; points: 14; strong: true
      text: view.service ? view.service.rate(gauge.value) : ""
      color: view.paint(gauge.key + "_value", view.tint)
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
        var top = 1
        for (var j = 0; j < points.length; j++) top = Math.max(top, points[j])
        var step = width / 59
        ctx.beginPath()
        ctx.moveTo(width - (points.length - 1) * step, height - points[0] / top * height)
        for (var i = 1; i < points.length; i++) ctx.lineTo(width - (points.length - 1 - i) * step, height - points[i] / top * height)
        ctx.strokeStyle = gauge.line
        ctx.lineWidth = Math.max(1.5, 2 * view.scale)
        ctx.stroke()
        ctx.lineTo(width, height)
        ctx.lineTo(width - (points.length - 1) * step, height)
        ctx.closePath()
        ctx.fillStyle = Qt.rgba(gauge.line.r, gauge.line.g, gauge.line.b, 0.15)
        ctx.fill()
      }
      Connections {
        target: gauge
        function onHistoryChanged() { curve.requestPaint() }
        function onLineChanged() { curve.requestPaint() }
      }
    }
  }

  Column {
    id: column
    width: parent.width
    spacing: Math.round(10 * view.scale)
    Rate {
      key: "down"
      name: view.texts.download || "Download"
      value: view.service ? view.service.netDown : 0
      history: view.service ? view.service.netDownHistory : []
    }
    Rate {
      key: "up"
      name: view.texts.upload || "Upload"
      value: view.service ? view.service.netUp : 0
      history: view.service ? view.service.netUpHistory : []
    }
  }
}
