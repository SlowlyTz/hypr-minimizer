import QtQuick
import qs.Commons

// The arrange tool's color palette for one part of a widget: the widget's
// parts to switch between, the widget accent and the theme's colors (they
// follow a theme change), the colors used last, and an own color (hue,
// saturation/brightness, opacity, or typed as #rrggbb[aa]). Every change goes
// into the draft; the toolbar's Save keeps it, Cancel drops it.
Rectangle {
  id: picker

  property var service: null
  readonly property var selection: service ? service.selection : null
  readonly property string kind: selection ? selection.kind : ""
  readonly property string part: selection ? selection.part : ""
  readonly property var titles: service && service.partTitles && service.partTitles[kind] ? service.partTitles[kind] : ({})
  readonly property var texts: service && service.texts ? service.texts : ({})
  readonly property string value: service && kind ? ((service.placement(kind).colors || {})[part] || "") : ""
  readonly property color shown: service && kind ? service.colorOf(kind, part, Color.foreground) : "white"
  readonly property real unit: Style.space(1)

  // The own color being picked.
  property real hue: 0
  property real sat: 0
  property real val: 1
  property real alpha: 1
  property bool syncing: false

  width: Math.round(340 * unit)
  height: content.implicitHeight + Math.round(24 * unit)
  radius: Math.round(12 * unit)
  color: Qt.rgba(0.08, 0.08, 0.1, 0.94)
  border.color: Color.accent
  border.width: 1

  // Take the part's color into the picker when another part is picked.
  // (Later: `shown` follows the new part only after this.)
  onPartChanged: Qt.callLater(takeShown)
  onKindChanged: Qt.callLater(takeShown)
  Component.onCompleted: takeShown()
  function takeShown() {
    picker.syncing = true
    var c = picker.shown
    picker.hue = c.hsvHue < 0 ? picker.hue : c.hsvHue
    picker.sat = c.hsvSaturation
    picker.val = c.hsvValue
    picker.alpha = c.a
    picker.syncing = false
  }
  function two(v) { var h = Math.round(Math.max(0, Math.min(1, v)) * 255).toString(16); return h.length < 2 ? "0" + h : h }
  function hexOf(c) { return "#" + two(c.r) + two(c.g) + two(c.b) + (c.a < 0.999 ? two(c.a) : "") }
  // remember: keep it among the colors used last (not while dragging).
  function pick(value, remember) {
    if (picker.service && picker.kind) picker.service.setPartColor(picker.kind, picker.part, value, remember !== false)
  }
  function pickOwn(remember) {
    if (picker.syncing) return
    picker.pick(picker.hexOf(Qt.hsva(picker.hue, picker.sat, picker.val, picker.alpha)), !!remember)
  }

  // Swallow clicks, so they do not reach the widgets underneath.
  MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: function(w) { w.accepted = true } }

  component Label: Text {
    color: "white"
    font.family: picker.service ? picker.service.fontFamily : ""
    font.pixelSize: Style.font.bodySmall
  }
  component Swatch: Rectangle {
    id: swatch
    property string value: ""
    property color fill: "transparent"
    property bool chosen: false
    signal picked()
    width: Math.round(24 * picker.unit)
    height: width
    radius: width / 2
    color: fill
    border.width: chosen ? 3 : 1
    border.color: chosen ? "white" : Qt.rgba(1, 1, 1, 0.35)
    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: swatch.picked() }
  }

  Column {
    id: content
    x: Math.round(12 * picker.unit)
    y: Math.round(12 * picker.unit)
    width: picker.width - 2 * x
    spacing: Math.round(10 * picker.unit)

    Item {
      width: parent.width
      height: heading.implicitHeight
      Label {
        id: heading
        text: (picker.service && picker.service.texts[picker.kind] ? picker.service.texts[picker.kind] : picker.kind)
              + "  ·  " + (picker.titles[picker.part] || picker.part)
        font.bold: true
        width: parent.width - close.width - 8
        elide: Text.ElideRight
      }
      Label {
        id: close
        anchors.right: parent.right
        text: "✕"
        MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor
                    onClicked: picker.service.selection = null }
      }
    }

    // The widget's parts.
    Flow {
      width: parent.width
      spacing: Math.round(4 * picker.unit)
      Repeater {
        model: Object.keys(picker.titles)
        Rectangle {
          required property string modelData
          readonly property bool current: modelData === picker.part
          radius: height / 2
          color: current ? Color.accent : Qt.rgba(1, 1, 1, area.containsMouse ? 0.16 : 0.08)
          implicitWidth: partName.implicitWidth + Math.round(16 * picker.unit)
          implicitHeight: partName.implicitHeight + Math.round(8 * picker.unit)
          Label {
            id: partName
            anchors.centerIn: parent
            text: picker.titles[parent.modelData]
            color: parent.current ? Color.background : "white"
          }
          MouseArea {
            id: area
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: picker.service.selection = Object.assign({}, picker.selection, { part: parent.modelData })
          }
        }
      }
    }

    // The widget accent and the theme's colors.
    Flow {
      width: parent.width
      spacing: Math.round(6 * picker.unit)
      Repeater {
        model: ["accent", "theme:accent", "theme:foreground", "theme:muted", "theme:background", "theme:red",
                "theme:orange", "theme:yellow", "theme:green", "theme:cyan", "theme:blue", "theme:magenta"]
        Swatch {
          required property string modelData
          value: modelData
          fill: picker.service && picker.kind ? picker.service.colorValue(picker.kind, modelData) : "transparent"
          chosen: picker.value === modelData
          onPicked: picker.pick(modelData)
        }
      }
    }

    // The own colors used last.
    Row {
      visible: picker.service && picker.service.recentColors.length > 0
      spacing: Math.round(6 * picker.unit)
      Label { anchors.verticalCenter: parent.verticalCenter; text: picker.texts.recent || "Recent" }
      Repeater {
        model: picker.service ? picker.service.recentColors : []
        Swatch {
          required property string modelData
          fill: picker.service ? picker.service.hexColor(modelData) : "transparent"
          chosen: picker.value === modelData
          onPicked: { picker.pick(modelData); picker.takeShown() }
        }
      }
    }

    // An own color: saturation (across) and brightness (down) for the hue.
    Rectangle {
      id: field
      width: parent.width
      height: Math.round(120 * picker.unit)
      radius: Math.round(6 * picker.unit)
      color: Qt.hsva(picker.hue, 1, 1, 1)
      Rectangle {
        anchors.fill: parent
        radius: parent.radius
        gradient: Gradient {
          orientation: Gradient.Horizontal
          GradientStop { position: 0; color: "white" }
          GradientStop { position: 1; color: "transparent" }
        }
      }
      Rectangle {
        anchors.fill: parent
        radius: parent.radius
        gradient: Gradient {
          GradientStop { position: 0; color: "transparent" }
          GradientStop { position: 1; color: "black" }
        }
      }
      Rectangle {
        x: picker.sat * field.width - width / 2
        y: (1 - picker.val) * field.height - height / 2
        width: Math.round(14 * picker.unit)
        height: width
        radius: width / 2
        color: "transparent"
        border.color: "white"
        border.width: 2
      }
      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.CrossCursor
        preventStealing: true
        function take(mouse) {
          picker.sat = Math.max(0, Math.min(1, mouse.x / width))
          picker.val = Math.max(0, Math.min(1, 1 - mouse.y / height))
          picker.pickOwn()
        }
        onPressed: function(mouse) { take(mouse) }
        onPositionChanged: function(mouse) { if (pressed) take(mouse) }
        onReleased: picker.pickOwn(true)
      }
    }

    // The hue.
    Rectangle {
      width: parent.width
      height: Math.round(14 * picker.unit)
      radius: height / 2
      gradient: Gradient {
        orientation: Gradient.Horizontal
        GradientStop { position: 0.0; color: Qt.hsva(0.0, 1, 1, 1) }
        GradientStop { position: 0.17; color: Qt.hsva(0.17, 1, 1, 1) }
        GradientStop { position: 0.33; color: Qt.hsva(0.33, 1, 1, 1) }
        GradientStop { position: 0.5; color: Qt.hsva(0.5, 1, 1, 1) }
        GradientStop { position: 0.67; color: Qt.hsva(0.67, 1, 1, 1) }
        GradientStop { position: 0.83; color: Qt.hsva(0.83, 1, 1, 1) }
        GradientStop { position: 1.0; color: Qt.hsva(0.999, 1, 1, 1) }
      }
      Rectangle {
        x: picker.hue * parent.width - width / 2
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(6 * picker.unit)
        height: parent.height + 4
        radius: 3
        color: "white"
      }
      MouseArea {
        anchors.fill: parent
        anchors.margins: -4
        preventStealing: true
        function take(mouse) { picker.hue = Math.max(0, Math.min(0.999, (mouse.x - 4) / (width - 8))); picker.pickOwn() }
        onPressed: function(mouse) { take(mouse) }
        onPositionChanged: function(mouse) { if (pressed) take(mouse) }
        onReleased: picker.pickOwn(true)
      }
    }

    // The opacity.
    Rectangle {
      width: parent.width
      height: Math.round(14 * picker.unit)
      radius: height / 2
      color: Qt.rgba(1, 1, 1, 0.15)
      gradient: Gradient {
        orientation: Gradient.Horizontal
        GradientStop { position: 0; color: Qt.hsva(picker.hue, picker.sat, picker.val, 0) }
        GradientStop { position: 1; color: Qt.hsva(picker.hue, picker.sat, picker.val, 1) }
      }
      border.color: Qt.rgba(1, 1, 1, 0.3)
      Rectangle {
        x: picker.alpha * parent.width - width / 2
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(6 * picker.unit)
        height: parent.height + 4
        radius: 3
        color: "white"
      }
      MouseArea {
        anchors.fill: parent
        anchors.margins: -4
        preventStealing: true
        function take(mouse) { picker.alpha = Math.max(0, Math.min(1, (mouse.x - 4) / (width - 8))); picker.pickOwn() }
        onPressed: function(mouse) { take(mouse) }
        onPositionChanged: function(mouse) { if (pressed) take(mouse) }
        onReleased: picker.pickOwn(true)
      }
    }

    Row {
      spacing: Math.round(8 * picker.unit)
      Rectangle {
        width: Math.round(120 * picker.unit)
        height: hex.implicitHeight + Math.round(10 * picker.unit)
        radius: Math.round(6 * picker.unit)
        color: Qt.rgba(1, 1, 1, 0.08)
        border.color: hex.activeFocus ? Color.accent : Qt.rgba(1, 1, 1, 0.25)
        TextInput {
          id: hex
          anchors.fill: parent
          anchors.margins: Math.round(5 * picker.unit)
          verticalAlignment: TextInput.AlignVCenter
          color: "white"
          font.family: picker.service ? picker.service.fontFamily : ""
          font.pixelSize: Style.font.bodySmall
          selectByMouse: true
          text: picker.hexOf(picker.shown)
          validator: RegularExpressionValidator { regularExpression: /#?[0-9a-fA-F]{0,8}/ }
          onAccepted: {
            var v = text.charAt(0) === "#" ? text : "#" + text
            if (/^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(v)) { picker.pick(v.toLowerCase()); picker.takeShown() }
          }
        }
      }
      Rectangle {
        radius: Math.round(6 * picker.unit)
        color: Qt.rgba(1, 1, 1, reset.containsMouse ? 0.16 : 0.08)
        implicitWidth: resetText.implicitWidth + Math.round(20 * picker.unit)
        implicitHeight: resetText.implicitHeight + Math.round(10 * picker.unit)
        opacity: picker.value !== "" ? 1 : 0.4
        Label { id: resetText; anchors.centerIn: parent; text: picker.texts.byDefault || "Default" }
        MouseArea {
          id: reset
          anchors.fill: parent
          hoverEnabled: true
          enabled: picker.value !== ""
          cursorShape: Qt.PointingHandCursor
          onClicked: { picker.pick(""); picker.takeShown() }
        }
      }
    }
  }
}
