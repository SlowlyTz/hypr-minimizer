import QtQuick
import qs.Commons

// Every disk (no small boot partitions): its mount point, how much is used
// (or free) of its size, and a bar.
Item {
  id: view

  property var service: null
  property bool editing: false
  // Its place and size on this screen (set by Placed).
  property var spot: null

  readonly property var settings: service ? service.widget("disk") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property var look: service ? service.textLook("disk") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  readonly property color tint: service ? service.tint("disk") : Color.accent
  readonly property var texts: service && service.texts ? service.texts : ({})
  readonly property bool free: !!(settings && settings.show_free)
  function paint(part, fallback) { return view.service ? view.service.colorOf("disk", part, fallback) : fallback }

  implicitWidth: spot && spot.width > 0 ? spot.width : Math.round(300 * scale)
  implicitHeight: column.implicitHeight
  width: implicitWidth
  height: implicitHeight

  Column {
    id: column
    width: parent.width
    spacing: Math.round(10 * view.scale)
    Repeater {
      model: view.service ? view.service.disks : []
      Column {
        required property var modelData
        width: column.width
        spacing: Math.round(4 * view.scale)
        Item {
          width: parent.width
          height: label.implicitHeight
          WidgetText {
            part: "label"
            id: label
            anchors.left: parent.left
            width: parent.width - value.implicitWidth - Math.round(10 * view.scale)
            elide: Text.ElideMiddle
            look: view.look; factor: view.scale; points: 14
            text: modelData.mount === "/" ? (view.texts.systemDisk || "System") : modelData.mount
            color: view.paint("label", Color.foreground)
          }
          WidgetText {
            part: "value"
            id: value
            anchors.right: parent.right
            look: view.look; factor: view.scale; points: 14; strong: true
            text: view.service ? (view.free ? view.service.bytes(modelData.size - modelData.used) + " " + (view.texts.free || "free")
                                            : view.service.bytes(modelData.used) + " / " + view.service.bytes(modelData.size)) : ""
            color: view.paint("value", view.tint)
          }
        }
        Rectangle {
          width: parent.width
          height: Math.max(3, Math.round(6 * view.scale))
          radius: height / 2
          color: view.paint("bar_track", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.15))
          PartHit { part: "bar_track"; anchors.margins: -3 }
          Rectangle {
            width: parent.width * Math.min(1, modelData.used / Math.max(1, modelData.size))
            height: parent.height
            radius: parent.radius
            color: view.paint("bar", view.tint)
            PartHit { part: "bar"; anchors.margins: -3 }
          }
        }
      }
    }
  }
}
