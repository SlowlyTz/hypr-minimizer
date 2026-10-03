import QtQuick
import qs.Commons

// Bars growing from the bottom; turned with the widget (90° makes them grow
// from the left edge). `size` is the longest bar in pixels, `width` the whole
// row (0: from the height). Style "mirrored" grows them both ways from the
// middle. Fades out while it is quiet; while arranging it shows a still
// pattern so it can be placed.
Item {
  id: view

  property var service: null
  property bool editing: false

  readonly property var settings: service ? service.widget("visualizer") : null
  readonly property var spot: service ? service.placement("visualizer") : null
  readonly property int count: settings ? settings.bars : 32
  readonly property real length: spot ? spot.size : 160
  readonly property real wide: spot ? spot.width : 0
  // A bar and half a bar of gap each; with a width of its own they share it.
  readonly property real thickness: wide > 0 ? Math.max(1, wide / (count * 1.5 - 0.5))
                                             : Math.max(3, Math.round(length / 22))
  readonly property real gap: wide > 0 ? thickness / 2 : Math.max(2, Math.round(thickness / 2))
  readonly property bool gradient: settings && settings.color === "gradient"
  readonly property bool mirrored: !!(settings && settings.style === "mirrored")
  readonly property color tint: service ? service.tint("visualizer") : Color.accent

  implicitWidth: count * thickness + (count - 1) * gap
  implicitHeight: length
  width: implicitWidth
  height: implicitHeight
  opacity: editing || (service && !service.quiet) ? 1 : 0
  Behavior on opacity { NumberAnimation { duration: 600; easing.type: Easing.InOutQuad } }

  function level(index) {
    if (editing && service && service.quiet) return 0.25 + 0.6 * Math.abs(Math.sin(index * 0.55))
    var levels = service ? service.levels : []
    return index < levels.length ? levels[index] : 0
  }

  Row {
    height: view.length
    spacing: view.gap
    Repeater {
      model: view.count
      Rectangle {
        required property int index
        width: view.thickness
        height: Math.max(view.thickness, view.level(index) * view.length)
        y: view.mirrored ? (view.length - height) / 2 : view.length - height
        radius: view.thickness / 2
        color: view.tint
        gradient: view.gradient ? barGradient : null
        Gradient {
          id: barGradient
          GradientStop { position: 0.0; color: Qt.lighter(view.tint, 1.5) }
          GradientStop { position: view.mirrored ? 0.5 : 1.0; color: view.tint }
          GradientStop { position: 1.0; color: view.mirrored ? Qt.lighter(view.tint, 1.5) : view.tint }
        }
        Behavior on height { NumberAnimation { duration: 60 } }
      }
    }
  }
}
