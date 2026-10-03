import QtQuick
import QtQuick.Effects
import qs.Commons

// Puts one widget at its spot: the centre at (x, y) as fractions of the
// screen, turned by `rotation`, at its size. While editing it can be dragged,
// turned with the wheel (5° a notch, 1° with Shift) and resized with the
// handles on its frame: a corner scales it, an edge makes it only wider or
// taller (the clock always scales), and the opposite side stays where it is.
// Every change goes into the service's draft, so all screens follow along.
//
// Its look: an optional card behind it (with room around the view, `pad`),
// a shadow or glow around all of it, and its opacity.
Item {
  id: placed

  property var service: null
  property string kind: ""
  property bool editable: false
  // This screen's id: with same_place off the widget has a place per screen.
  property string screenKey: ""
  default property alias content: holder.data

  readonly property var spot: service ? service.placement(kind, screenKey) : { x: 0.5, y: 0.5, rotation: 0, size: 100, width: 0 }
  readonly property var settings: service ? service.widget(kind) : null
  readonly property string title: service && service.texts && service.texts[kind] ? service.texts[kind] : kind
  readonly property real frameMargin: Style.space(10)
  readonly property bool card: !!(settings && settings.card)
  readonly property real pad: card ? settings.card_padding : 0
  readonly property string effect: settings ? settings.effect : "outline"
  readonly property real strength: settings ? settings.effect_strength / 100 : 0.35
  // The resize in progress: the side pulled, the sizes and the pointer at the
  // press, and the point (opposite side) that stays put.
  property var resize: null

  width: holder.childrenRect.width + 2 * pad
  height: holder.childrenRect.height + 2 * pad
  x: spot.x * (parent ? parent.width : 0) - width / 2
  y: spot.y * (parent ? parent.height : 0) - height / 2
  rotation: spot.rotation

  onWidthChanged: keepAnchor()
  onHeightChanged: keepAnchor()

  function commit() {
    var w = parent ? parent.width : 1
    var h = parent ? parent.height : 1
    service.setPlacement(kind, (x + width / 2) / w, (y + height / 2) / h, spot.rotation, screenKey)
    // Dragging set x and y directly; follow the spot again.
    x = Qt.binding(function() { return spot.x * (parent ? parent.width : 0) - width / 2 })
    y = Qt.binding(function() { return spot.y * (parent ? parent.height : 0) - height / 2 })
  }

  function turn(degrees) {
    var next = Math.round(spot.rotation + degrees)
    while (next > 180) next -= 360
    while (next <= -180) next += 360
    service.setPlacement(kind, spot.x, spot.y, next, screenKey)
  }

  // --- resizing ----------------------------------------------------------------------

  // Between the widget's own (unturned) axes and the screen's.
  function toScreen(lx, ly) {
    var a = spot.rotation * Math.PI / 180
    return { x: lx * Math.cos(a) - ly * Math.sin(a), y: lx * Math.sin(a) + ly * Math.cos(a) }
  }
  function toLocal(dx, dy) {
    var a = spot.rotation * Math.PI / 180
    return { x: dx * Math.cos(a) + dy * Math.sin(a), y: -dx * Math.sin(a) + dy * Math.cos(a) }
  }

  function beginResize(sx, sy, point) {
    var cx = spot.x * parent.width
    var cy = spot.y * parent.height
    var offset = toScreen(-sx * width / 2, -sy * height / 2)
    resize = {
      // The view's own size, without the card's room around it.
      sx: sx, sy: sy, pointer: point, width: width - 2 * pad, height: height - 2 * pad, size: spot.size,
      // No width of its own yet: the one it has now.
      wide: spot.width > 0 ? spot.width : width - 2 * pad,
      anchor: { x: cx + offset.x, y: cy + offset.y }
    }
  }

  function moveResize(point) {
    if (!resize) return
    var d = toLocal(point.x - resize.pointer.x, point.y - resize.pointer.y)
    var wider = (resize.width + resize.sx * d.x) / resize.width
    var taller = (resize.height + resize.sy * d.y) / resize.height
    var scalesOnly = !service.hasWidth(kind)
    var size = resize.size
    var wide = resize.wide
    if (resize.sx && resize.sy) {
      var factor = (wider + taller) / 2
      size = resize.size * factor
      wide = resize.wide * factor
    } else if (resize.sx) {
      if (scalesOnly) size = resize.size * wider
      else wide = resize.wide * wider
    } else {
      size = resize.size * taller
    }
    service.setSize(kind, size, scalesOnly ? 0 : wide, screenKey)
    keepAnchor()
  }

  function endResize() {
    resize = null
  }

  // Move the centre so the side opposite the pulled one stays where it was.
  function keepAnchor() {
    if (!resize || !parent || parent.width <= 0 || parent.height <= 0) return
    var offset = toScreen(-resize.sx * width / 2, -resize.sy * height / 2)
    service.setPlacement(kind, (resize.anchor.x - offset.x) / parent.width,
                         (resize.anchor.y - offset.y) / parent.height, spot.rotation, screenKey)
  }

  // The resize arrow that points the way this handle pulls on the turned widget.
  function cursorFor(sx, sy) {
    var direction = toScreen(sx, sy)
    var angle = Math.atan2(direction.y, direction.x) * 180 / Math.PI
    angle = ((angle % 180) + 180) % 180
    if (angle < 22.5 || angle >= 157.5) return Qt.SizeHorCursor
    if (angle < 67.5) return Qt.SizeFDiagCursor
    if (angle < 112.5) return Qt.SizeVerCursor
    return Qt.SizeBDiagCursor
  }

  // --- drawing ------------------------------------------------------------------------

  Rectangle {
    visible: placed.editable
    anchors.fill: parent
    anchors.margins: -placed.frameMargin
    radius: Style.space(10)
    color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, drag.active || placed.resize ? 0.18 : 0.08)
    border.color: Color.accent
    border.width: 2
  }

  // The card and the view, drawn as one so the shadow or glow takes both.
  Item {
    id: body
    anchors.fill: parent
    opacity: placed.settings ? placed.settings.opacity / 100 : 1
    layer.enabled: placed.effect === "shadow" || placed.effect === "glow"
    layer.effect: MultiEffect {
      shadowEnabled: true
      shadowColor: placed.service ? placed.service.colorOf(placed.kind, "effect",
                                     placed.effect === "glow" ? placed.service.tint(placed.kind) : "black") : "black"
      shadowBlur: placed.effect === "glow" ? Math.min(1, 0.3 + placed.strength) : Math.min(1, 0.2 + placed.strength * 0.8)
      shadowOpacity: placed.effect === "glow" ? Math.min(1, 0.4 + placed.strength * 0.6) : Math.min(1, 0.3 + placed.strength * 0.7)
      shadowHorizontalOffset: placed.effect === "glow" ? 0 : 2 + placed.strength * 6
      shadowVerticalOffset: placed.effect === "glow" ? 0 : 2 + placed.strength * 6
      shadowScale: placed.effect === "glow" ? 1.02 : 1
      blurMax: 48
    }

    Rectangle {
      visible: placed.card
      anchors.fill: parent
      radius: placed.settings ? placed.settings.card_radius : 0
      readonly property color base: placed.service ? placed.service.colorOf(placed.kind, "card", Color.background) : Color.background
      color: Qt.rgba(base.r, base.g, base.b, base.a * (placed.settings ? placed.settings.card_opacity / 100 : 0.45))
    }

    Item {
      id: holder
      x: placed.pad
      y: placed.pad
      width: childrenRect.width
      height: childrenRect.height
    }
  }

  Rectangle {
    visible: placed.editable
    anchors.bottom: parent.top
    anchors.bottomMargin: Style.space(24)
    anchors.horizontalCenter: parent.horizontalCenter
    radius: Style.space(6)
    color: Color.accent
    implicitWidth: badge.implicitWidth + Style.space(16)
    implicitHeight: badge.implicitHeight + Style.space(8)
    Text {
      id: badge
      anchors.centerIn: parent
      text: placed.title + "  ·  " + (placed.resize ? Math.round(placed.width) + " × " + Math.round(placed.height)
                                                   : Math.round(placed.spot.rotation) + "°")
      color: Color.background
      font.family: placed.service ? placed.service.fontFamily : ""
      font.pixelSize: Style.font.bodySmall
      font.bold: true
    }
  }

  DragHandler {
    id: drag
    enabled: placed.editable && !placed.resize
    target: placed
    onActiveChanged: if (!active) placed.commit()
  }

  WheelHandler {
    enabled: placed.editable && !placed.resize
    acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    onWheel: function(event) {
      var step = (event.modifiers & Qt.ShiftModifier) ? 1 : 5
      var delta = event.angleDelta.y !== 0 ? event.angleDelta.y : event.angleDelta.x
      if (delta !== 0) placed.turn(delta > 0 ? step : -step)
    }
  }

  // Four corners and four edges, on the frame.
  Repeater {
    model: placed.editable ? [[-1, -1], [0, -1], [1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0]] : []
    Item {
      id: handle
      required property var modelData
      readonly property int sx: modelData[0]
      readonly property int sy: modelData[1]
      readonly property bool corner: sx !== 0 && sy !== 0
      z: 5
      width: Style.space(28)
      height: width
      x: placed.width / 2 + sx * (placed.width / 2 + placed.frameMargin) - width / 2
      y: placed.height / 2 + sy * (placed.height / 2 + placed.frameMargin) - height / 2

      Rectangle {
        anchors.centerIn: parent
        width: handle.corner ? Style.space(14) : (handle.sy !== 0 ? Style.space(28) : Style.space(8))
        height: handle.corner ? Style.space(14) : (handle.sx !== 0 ? Style.space(28) : Style.space(8))
        radius: Math.min(width, height) / 2
        color: area.pressed || area.containsMouse ? Color.accent : Color.background
        border.color: Color.accent
        border.width: 2
      }

      MouseArea {
        id: area
        anchors.fill: parent
        hoverEnabled: true
        // The widget's own drag must not take the pointer over.
        preventStealing: true
        cursorShape: placed.cursorFor(handle.sx, handle.sy)
        onPressed: function(mouse) { placed.beginResize(handle.sx, handle.sy, mapToItem(placed.parent, mouse.x, mouse.y)) }
        onPositionChanged: function(mouse) {
          if (pressed) placed.moveResize(mapToItem(placed.parent, mouse.x, mouse.y))
        }
        onReleased: placed.endResize()
        onCanceled: placed.endResize()
      }
    }
  }
}
