import QtQuick

// Makes an element of a widget pickable in the arrange tool's color mode:
// a click selects `part` (its color can then be set). It finds its widget
// (Placed) by itself and does nothing outside the color mode.
MouseArea {
  id: hit
  property string part: ""
  property Item placed: null

  anchors.fill: parent
  enabled: part !== "" && !!placed && placed.colorMode
  hoverEnabled: enabled
  cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
  Component.onCompleted: {
    var p = hit.parent
    while (p && !p.isPlaced) p = p.parent
    hit.placed = p
  }
  onClicked: function(mouse) { hit.placed.pickPart(hit.part, hit.mapToItem(null, mouse.x, mouse.y)) }

  // A light frame shows what a click would color.
  Rectangle {
    anchors.fill: parent
    anchors.margins: -2
    visible: hit.enabled && (hit.containsMouse || (hit.placed && hit.placed.selectedPart === hit.part))
    color: "transparent"
    radius: 4
    border.width: 2
    border.color: hit.placed && hit.placed.selectedPart === hit.part ? "white" : Qt.rgba(1, 1, 1, 0.5)
  }
}
