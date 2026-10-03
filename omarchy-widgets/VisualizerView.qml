import QtQuick
import qs.Commons

// The sound as bars; turned with the widget (90° makes them grow from the
// left edge). Styles: bars from the bottom, mirrored from the middle, a wave,
// dots, or bars around a circle. `size` is the longest bar in pixels (the
// circle's radius and its bars), `width` the whole row (0: from the height).
// `gap`: room between bars in percent of a bar; `sensitivity` raises or
// lowers the levels; peak marks fall slowly from the highest level.
// Fades out while it is quiet; while arranging it shows a still pattern so it
// can be placed.
Item {
  id: view

  property var service: null
  property bool editing: false
  // Its place and size on this screen (set by Placed).
  property var spot: null

  readonly property var settings: service ? service.widget("visualizer") : null
  readonly property string barStyle: settings ? settings.style : "bottom"
  readonly property bool round: barStyle === "circle"
  readonly property int count: settings ? settings.bars : 32
  readonly property real length: spot ? spot.size : 160
  readonly property real wide: spot ? spot.width : 0
  readonly property real gapShare: settings ? settings.gap / 100 : 0.5
  readonly property real gain: settings ? settings.sensitivity / 100 : 1
  readonly property bool peaks: !!(settings && settings.peaks)
  // A bar and its gap share the width; with a width of its own they fill it.
  readonly property real thickness: wide > 0 ? Math.max(1, wide / (count + (count - 1) * gapShare))
                                             : Math.max(3, Math.round(length / 22))
  readonly property real gap: thickness * gapShare
  readonly property bool mirrored: barStyle === "mirrored"
  readonly property color tint: service ? service.tint("visualizer") : Color.accent
  // The bars' color, and their tips' (a gradient when set or chosen).
  readonly property color bars: service ? service.colorOf("visualizer", "bars", tint) : tint
  readonly property color tips: service ? service.colorOf("visualizer", "bars_end", Qt.lighter(bars, 1.5)) : bars
  readonly property color peakColor: service ? service.colorOf("visualizer", "peaks", Color.foreground) : Color.foreground
  readonly property bool gradient: !!(settings && settings.color === "gradient")
                                   || !!(service && service.hasColor("visualizer", "bars_end"))

  implicitWidth: round ? length * 2 : count * thickness + (count - 1) * gap
  implicitHeight: round ? length * 2 : length
  width: implicitWidth
  height: implicitHeight
  opacity: editing || (service && !service.quiet) ? 1 : 0
  Behavior on opacity { NumberAnimation { duration: 600; easing.type: Easing.InOutQuad } }

  function level(index) {
    if (editing && service && service.quiet) return 0.25 + 0.6 * Math.abs(Math.sin(index * 0.55))
    var levels = service ? service.levels : []
    return index < levels.length ? Math.min(1, levels[index] * view.gain) : 0
  }

  // The peaks: each bar's highest level, falling a little every frame.
  property var peakLevels: []
  Connections {
    target: view.service
    enabled: view.peaks || view.barStyle !== "bottom"
    function onLevelsChanged() {
      if (view.peaks) {
        var next = []
        for (var i = 0; i < view.count; i++) next.push(Math.max(view.level(i), (view.peakLevels[i] || 0) - 0.012))
        view.peakLevels = next
      }
      if (canvas.visible) canvas.requestPaint()
    }
  }

  // In the color mode a click anywhere picks the bars (the palette lists the rest).
  PartHit { z: 5; part: "bars" }

  // --- bars (bottom, mirrored) ------------------------------------------------------------

  Row {
    visible: view.barStyle === "bottom" || view.barStyle === "mirrored"
    height: view.length
    spacing: view.gap
    Repeater {
      model: parent.visible ? view.count : 0
      Item {
        required property int index
        width: view.thickness
        height: view.length
        Rectangle {
          width: view.thickness
          height: Math.max(view.thickness, view.level(index) * view.length)
          y: view.mirrored ? (view.length - height) / 2 : view.length - height
          radius: view.thickness / 2
          color: view.bars
          gradient: view.gradient ? barGradient : null
          Gradient {
            id: barGradient
            GradientStop { position: 0.0; color: view.tips }
            GradientStop { position: view.mirrored ? 0.5 : 1.0; color: view.bars }
            GradientStop { position: 1.0; color: view.mirrored ? view.tips : view.bars }
          }
          Behavior on height { NumberAnimation { duration: 60 } }
        }
        Rectangle {
          visible: view.peaks
          width: view.thickness
          height: Math.max(2, view.thickness / 3)
          radius: height / 2
          color: view.peakColor
          readonly property real peakTop: (view.peakLevels[index] || 0) * view.length
          y: view.mirrored ? (view.length - peakTop) / 2 - height : view.length - peakTop - height
        }
      }
    }
  }

  // --- wave, dots, circle -----------------------------------------------------------------

  Canvas {
    id: canvas
    anchors.fill: parent
    visible: view.barStyle === "wave" || view.barStyle === "dots" || view.barStyle === "circle"
    onVisibleChanged: if (visible) requestPaint()
    // Without sound nothing else asks it to paint again.
    Connections {
      target: view
      function onBarStyleChanged() { canvas.requestPaint() }
      function onBarsChanged() { canvas.requestPaint() }
      function onTipsChanged() { canvas.requestPaint() }
      function onGapShareChanged() { canvas.requestPaint() }
      function onCountChanged() { canvas.requestPaint() }
      function onEditingChanged() { canvas.requestPaint() }
    }
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
      var ctx = getContext("2d")
      ctx.reset()
      var n = view.count
      if (view.barStyle === "wave") {
        var step = width / Math.max(1, n - 1)
        var y = function(i) { return height - Math.max(0.02, view.level(i)) * height * 0.95 }
        ctx.beginPath()
        ctx.moveTo(0, y(0))
        for (var i = 1; i < n; i++) {
          var x0 = (i - 1) * step, x1 = i * step
          ctx.bezierCurveTo(x0 + step / 2, y(i - 1), x1 - step / 2, y(i), x1, y(i))
        }
        ctx.lineWidth = Math.max(2, view.thickness / 1.5)
        ctx.strokeStyle = view.bars
        ctx.lineJoin = "round"
        ctx.stroke()
        ctx.lineTo(width, height)
        ctx.lineTo(0, height)
        ctx.closePath()
        var fill = ctx.createLinearGradient(0, 0, 0, height)
        fill.addColorStop(0, Qt.rgba(view.tips.r, view.tips.g, view.tips.b, 0.45))
        fill.addColorStop(1, Qt.rgba(view.bars.r, view.bars.g, view.bars.b, 0.05))
        ctx.fillStyle = fill
        ctx.fill()
      } else if (view.barStyle === "dots") {
        var dot = view.thickness
        var rows = Math.max(1, Math.floor(height / (dot + view.gap)))
        for (var b = 0; b < n; b++) {
          var lit = Math.round(view.level(b) * rows)
          var x = b * (dot + view.gap) + dot / 2
          for (var r = 0; r < Math.max(1, lit); r++) {
            var share = rows > 1 ? r / (rows - 1) : 0
            ctx.fillStyle = view.gradient ? Qt.rgba(view.bars.r + (view.tips.r - view.bars.r) * share,
                                                    view.bars.g + (view.tips.g - view.bars.g) * share,
                                                    view.bars.b + (view.tips.b - view.bars.b) * share, 1) : view.bars
            ctx.beginPath()
            ctx.arc(x, height - r * (dot + view.gap) - dot / 2, dot / 2, 0, Math.PI * 2)
            ctx.fill()
          }
          if (view.peaks) {
            var top = Math.round((view.peakLevels[b] || 0) * rows)
            ctx.fillStyle = view.peakColor
            ctx.beginPath()
            ctx.arc(x, height - top * (dot + view.gap) - dot / 2, dot / 2.5, 0, Math.PI * 2)
            ctx.fill()
          }
        }
      } else {
        var cx = width / 2, cy = height / 2
        var inner = view.length * 0.45
        var bar = Math.max(2, (2 * Math.PI * inner / n) / (1 + view.gapShare))
        ctx.lineCap = "round"
        ctx.lineWidth = bar
        for (var k = 0; k < n; k++) {
          var a = k / n * Math.PI * 2 - Math.PI / 2
          var len = Math.max(bar, view.level(k) * view.length * 0.55)
          var grad = ctx.createLinearGradient(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner,
                                              cx + Math.cos(a) * (inner + len), cy + Math.sin(a) * (inner + len))
          grad.addColorStop(0, view.bars)
          grad.addColorStop(1, view.gradient ? view.tips : view.bars)
          ctx.strokeStyle = grad
          ctx.beginPath()
          ctx.moveTo(cx + Math.cos(a) * inner, cy + Math.sin(a) * inner)
          ctx.lineTo(cx + Math.cos(a) * (inner + len), cy + Math.sin(a) * (inner + len))
          ctx.stroke()
          if (view.peaks) {
            var p = inner + Math.max(bar, (view.peakLevels[k] || 0) * view.length * 0.55) + bar
            ctx.fillStyle = view.peakColor
            ctx.beginPath()
            ctx.arc(cx + Math.cos(a) * p, cy + Math.sin(a) * p, bar / 3, 0, Math.PI * 2)
            ctx.fill()
          }
        }
      }
    }
  }
}
