import QtQuick
import qs.Commons
import "ColorTools.js" as ColorTools

// The arrange tool's color palette for the widget picked in the color mode.
// First the whole widget: its base color (every part on "accent" follows it)
// from the theme's colors, the wallpaper's, the ones used last or an own one,
// and color schemes made from it. "Fine-tuning" opens the single parts. A
// color under the pointer shows on the widget at once (the service's
// preview); a click takes it into the draft, Ctrl+Z or ↶ takes it back, and
// the toolbar's Save keeps it. It sits beside the widget (Service.placePalette)
// and can be dragged by its title.
Rectangle {
  id: picker

  property var service: null
  property string screenKey: ""
  // Dragged by its title to (x, y).
  signal moved(real x, real y)

  readonly property var selection: service ? service.selection : null
  readonly property string kind: selection ? selection.kind : ""
  // "base": the whole widget, else one part.
  readonly property string part: selection ? selection.part : "base"
  readonly property bool whole: part === "base"
  readonly property var titles: service && service.partTitles && service.partTitles[kind] ? service.partTitles[kind] : ({})
  readonly property var texts: service && service.texts ? service.texts : ({})
  readonly property var colors: service && kind ? (service.placement(kind).colors || {}) : ({})
  readonly property string value: colors[part] || ""
  readonly property color shown: !service || !kind ? "white"
                                 : whole ? service.tint(kind) : service.colorOf(kind, part, Color.foreground)
  readonly property real unit: Style.space(1)
  property bool ownOpen: false
  property bool appliedAll: false

  // The own color being picked.
  property real hue: 0
  property real sat: 0
  property real val: 1
  property real alpha: 1
  property bool syncing: false

  width: Math.round(340 * unit)
  height: content.implicitHeight + Math.round(24 * unit)
  radius: Math.round(12 * unit)
  color: Qt.rgba(0.08, 0.08, 0.1, 0.95)
  border.color: Color.accent
  border.width: 1

  // Take the target's color into the own-color fields when the target changes.
  onPartChanged: Qt.callLater(takeShown)
  onKindChanged: { Qt.callLater(takeShown); picker.appliedAll = false }
  Component.onCompleted: takeShown()
  onVisibleChanged: if (visible && service && !service.wallpaperColors.length) sampler.sample()
  function takeShown() {
    picker.syncing = true
    var c = picker.shown
    picker.hue = c.hsvHue < 0 ? picker.hue : c.hsvHue
    picker.sat = c.hsvSaturation
    picker.val = c.hsvValue
    picker.alpha = c.a
    picker.syncing = false
  }
  function hexOf(c) { return ColorTools.hex({ r: c.r, g: c.g, b: c.b, a: c.a }) }

  // The target's colors with `value` in it ("" = its default).
  function withValue(value) {
    var next = Object.assign({}, picker.colors)
    if (value) next[picker.part] = value
    else delete next[picker.part]
    return next
  }
  function hover(value) { if (picker.kind) picker.service.preview = { kind: picker.kind, colors: picker.withValue(value) } }
  function hoverColors(colors) { if (picker.kind) picker.service.preview = { kind: picker.kind, colors: colors } }
  function unhover() { if (picker.service) picker.service.preview = null }
  // step: a new step for undo; keep: among the colors used last.
  function pick(value, step, keep) {
    if (!picker.service || !picker.kind) return
    picker.service.preview = null
    picker.service.setPartColor(picker.kind, picker.part, value, step !== false, !!keep)
  }
  function pickOwn(step, keep) {
    if (picker.syncing) return
    picker.pick(picker.hexOf(Qt.hsva(picker.hue, picker.sat, picker.val, picker.alpha)), step, keep)
  }
  // Three colors that show what a scheme does: main, text and the quieter parts.
  function schemeDots(id) {
    var s = picker.service
    var c = s.schemeColors(picker.kind, id)
    var main = c.base ? s.colorValue(picker.kind, c.base) : id === "theme" ? s.themeColor("accent") : s.tint(picker.kind)
    var defaults = s.parts[picker.kind] || {}
    var text = null, quiet = null
    for (var p in defaults) {
      var r = ColorTools.role(defaults[p])
      var v = c[p] || defaults[p]
      var look = v === "accent" ? main : s.colorValue(picker.kind, v)
      if (r === "text" && text === null) text = look
      if (r === "quiet" && quiet === null) quiet = look
    }
    return [main, text || main, quiet || text || main]
  }
  function setFineTune(on) {
    picker.service.fineTune = on
    var sel = picker.selection
    picker.service.selection = Object.assign({}, sel, { part: on && sel.clicked ? sel.clicked : "base" })
  }

  // Swallow clicks, so they do not reach the widgets underneath.
  MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onWheel: function(w) { w.accepted = true } }

  // The wallpaper, small, to find its main colors.
  Canvas {
    id: sampler
    width: 64
    height: 36
    opacity: 0
    enabled: false
    readonly property string source: picker.service ? "file://" + picker.service.wallpaper : ""
    function sample() {
      if (!source) return
      unloadImage(source)
      loadImage(source)
    }
    onImageLoaded: requestPaint()
    onPaint: {
      if (!isImageLoaded(source)) return
      var ctx = getContext("2d")
      ctx.drawImage(source, 0, 0, width, height)
      var data = ctx.getImageData(0, 0, width, height).data
      var pixels = []
      for (var i = 0; i < data.length; i++) pixels.push(data[i])
      picker.service.wallpaperColors = ColorTools.mainColors(pixels, 7)
    }
  }

  component Label: Text {
    color: "white"
    font.family: picker.service ? picker.service.fontFamily : ""
    font.pixelSize: Style.font.bodySmall
  }
  component Caption: Label {
    color: Qt.rgba(1, 1, 1, 0.6)
    font.pixelSize: Style.font.bodySmall * 0.92
  }
  component Swatch: Rectangle {
    id: swatch
    property string value: ""
    property color fill: "transparent"
    property bool chosen: false
    width: Math.round(24 * picker.unit)
    height: width
    radius: width / 2
    color: fill
    border.width: chosen ? 3 : 1
    border.color: chosen ? "white" : Qt.rgba(1, 1, 1, 0.35)
    scale: swatchArea.containsMouse ? 1.15 : 1
    Behavior on scale { NumberAnimation { duration: 90 } }
    MouseArea {
      id: swatchArea
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: picker.hover(swatch.value)
      onExited: picker.unhover()
      onClicked: { picker.pick(swatch.value, true, swatch.value.charAt(0) === "#"); picker.takeShown() }
    }
  }
  component Chip: Rectangle {
    id: chip
    property string label: ""
    property bool current: false
    property bool marked: false
    signal clicked()
    radius: height / 2
    color: current ? Color.accent : Qt.rgba(1, 1, 1, chipArea.containsMouse ? 0.16 : 0.08)
    implicitWidth: chipText.implicitWidth + Math.round(16 * picker.unit)
    implicitHeight: chipText.implicitHeight + Math.round(8 * picker.unit)
    Label {
      id: chipText
      anchors.centerIn: parent
      text: chip.label + (chip.marked ? " •" : "")
      color: chip.current ? Color.background : "white"
    }
    MouseArea { id: chipArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: chip.clicked() }
  }
  component Button: Rectangle {
    id: button
    property string label: ""
    signal clicked()
    radius: Math.round(6 * picker.unit)
    color: Qt.rgba(1, 1, 1, buttonArea.containsMouse && enabled ? 0.16 : 0.08)
    opacity: enabled ? 1 : 0.4
    implicitWidth: buttonText.implicitWidth + Math.round(20 * picker.unit)
    implicitHeight: buttonText.implicitHeight + Math.round(10 * picker.unit)
    Label { id: buttonText; anchors.centerIn: parent; text: button.label }
    MouseArea { id: buttonArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: button.clicked() }
  }
  component Fold: Item {
    id: fold
    property string label: ""
    property bool open: false
    signal toggled()
    width: parent ? parent.width : 0
    height: foldText.implicitHeight + Math.round(4 * picker.unit)
    Label {
      id: foldText
      anchors.verticalCenter: parent.verticalCenter
      text: (fold.open ? "▾  " : "▸  ") + fold.label
      font.bold: true
      opacity: foldArea.containsMouse ? 1 : 0.85
    }
    MouseArea { id: foldArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: fold.toggled() }
  }

  Column {
    id: content
    x: Math.round(12 * picker.unit)
    y: Math.round(12 * picker.unit)
    width: picker.width - 2 * x
    spacing: Math.round(10 * picker.unit)

    // The title: drag it to move the palette.
    Item {
      width: parent.width
      height: heading.implicitHeight + Math.round(4 * picker.unit)
      HoverHandler { cursorShape: Qt.SizeAllCursor }
      DragHandler {
        target: picker
        onActiveChanged: if (!active) picker.moved(picker.x, picker.y)
      }
      Label {
        id: heading
        anchors.verticalCenter: parent.verticalCenter
        text: "⠿  " + (picker.texts[picker.kind] || picker.kind) + "  ·  "
              + (picker.whole ? (picker.texts.baseColor || "Base color") : (picker.titles[picker.part] || picker.part))
        font.bold: true
        width: parent.width - undo.width - close.width - Math.round(24 * picker.unit)
        elide: Text.ElideRight
      }
      Label {
        id: undo
        anchors.right: close.left
        anchors.rightMargin: Math.round(14 * picker.unit)
        anchors.verticalCenter: parent.verticalCenter
        text: "↶"
        font.pixelSize: Style.font.body
        opacity: picker.service && picker.service.colorHistory.length ? 1 : 0.3
        MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor
                    onClicked: { picker.service.undoColors(); picker.takeShown() } }
      }
      Label {
        id: close
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        text: "✕"
        MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor
                    onClicked: { picker.unhover(); picker.service.selection = null } }
      }
    }

    // The theme's colors (for a part also the base color, "accent").
    Caption { text: picker.texts.themeColors || "Theme" }
    Flow {
      width: parent.width
      spacing: Math.round(6 * picker.unit)
      Repeater {
        model: (picker.whole ? [] : ["accent"]).concat(["theme:accent", "theme:foreground", "theme:muted", "theme:background",
                "theme:red", "theme:orange", "theme:yellow", "theme:green", "theme:cyan", "theme:blue", "theme:magenta"])
        Swatch {
          required property string modelData
          value: modelData
          fill: picker.service && picker.kind ? picker.service.colorValue(picker.kind, modelData) : "transparent"
          chosen: picker.value === modelData
        }
      }
    }

    // The wallpaper's colors, and the own ones used last.
    Caption { visible: wallpaperRow.count > 0; text: picker.texts.wallpaper || "Wallpaper" }
    Flow {
      visible: wallpaperRow.count > 0
      width: parent.width
      spacing: Math.round(6 * picker.unit)
      Repeater {
        id: wallpaperRow
        model: picker.service ? picker.service.wallpaperColors : []
        Swatch {
          required property string modelData
          value: modelData
          fill: picker.service ? picker.service.hexColor(modelData) : "transparent"
          chosen: picker.value === modelData
        }
      }
    }
    Caption { visible: recentRow.count > 0; text: picker.texts.recent || "Recent" }
    Flow {
      visible: recentRow.count > 0
      width: parent.width
      spacing: Math.round(6 * picker.unit)
      Repeater {
        id: recentRow
        model: picker.service ? picker.service.recentColors : []
        Swatch {
          required property string modelData
          value: modelData
          fill: picker.service ? picker.service.hexColor(modelData) : "transparent"
          chosen: picker.value === modelData
        }
      }
    }

    // An own color: saturation (across) and brightness (down) for the hue,
    // the hue, the opacity and #rrggbb[aa].
    Fold {
      label: picker.texts.ownColor || "Own color"
      open: picker.ownOpen
      onToggled: picker.ownOpen = !picker.ownOpen
    }
    Column {
      visible: picker.ownOpen
      width: parent.width
      spacing: Math.round(10 * picker.unit)

      Rectangle {
        id: field
        width: parent.width
        height: Math.round(110 * picker.unit)
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
          function take(mouse, step) {
            picker.sat = Math.max(0, Math.min(1, mouse.x / width))
            picker.val = Math.max(0, Math.min(1, 1 - mouse.y / height))
            picker.pickOwn(step, false)
          }
          onPressed: function(mouse) { take(mouse, true) }
          onPositionChanged: function(mouse) { if (pressed) take(mouse, false) }
          onReleased: picker.pickOwn(false, true)
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
          function take(mouse, step) {
            picker.hue = Math.max(0, Math.min(0.999, (mouse.x - 4) / (width - 8)))
            picker.pickOwn(step, false)
          }
          onPressed: function(mouse) { take(mouse, true) }
          onPositionChanged: function(mouse) { if (pressed) take(mouse, false) }
          onReleased: picker.pickOwn(false, true)
        }
      }

      // The opacity.
      Rectangle {
        width: parent.width
        height: Math.round(14 * picker.unit)
        radius: height / 2
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
          function take(mouse, step) {
            picker.alpha = Math.max(0, Math.min(1, (mouse.x - 4) / (width - 8)))
            picker.pickOwn(step, false)
          }
          onPressed: function(mouse) { take(mouse, true) }
          onPositionChanged: function(mouse) { if (pressed) take(mouse, false) }
          onReleased: picker.pickOwn(false, true)
        }
      }

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
            if (/^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(v)) { picker.pick(v.toLowerCase(), true, true); picker.takeShown() }
          }
        }
      }
    }

    // Schemes for the whole widget, made from its base color.
    Caption { text: picker.texts.scheme || "Color scheme" }
    Flow {
      width: parent.width
      spacing: Math.round(6 * picker.unit)
      Repeater {
        model: ColorTools.SCHEMES
        Rectangle {
          id: schemeChip
          required property string modelData
          readonly property var dots: picker.visible && picker.kind ? picker.schemeDots(modelData) : []
          radius: height / 2
          color: Qt.rgba(1, 1, 1, schemeArea.containsMouse ? 0.16 : 0.08)
          implicitWidth: schemeRow.implicitWidth + Math.round(16 * picker.unit)
          implicitHeight: schemeRow.implicitHeight + Math.round(8 * picker.unit)
          Row {
            id: schemeRow
            anchors.centerIn: parent
            spacing: Math.round(3 * picker.unit)
            Repeater {
              model: schemeChip.dots
              Rectangle {
                required property var modelData
                anchors.verticalCenter: parent.verticalCenter
                width: Math.round(10 * picker.unit)
                height: width
                radius: width / 2
                color: modelData
                border.color: Qt.rgba(1, 1, 1, 0.3)
              }
            }
            Item { width: Math.round(3 * picker.unit); height: 1 }
            Label {
              anchors.verticalCenter: parent.verticalCenter
              text: (picker.texts.schemes || {})[schemeChip.modelData] || schemeChip.modelData
            }
          }
          MouseArea {
            id: schemeArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onEntered: picker.hoverColors(picker.service.schemeColors(picker.kind, schemeChip.modelData))
            onExited: picker.unhover()
            onClicked: {
              picker.service.setColors(picker.kind, picker.service.schemeColors(picker.kind, schemeChip.modelData))
              picker.takeShown()
            }
          }
        }
      }
    }

    Row {
      spacing: Math.round(8 * picker.unit)
      Button {
        label: picker.appliedAll ? "✓ " + (picker.texts.applied || "Applied to all widgets")
                                 : (picker.texts.applyAll || "Apply to all widgets")
        onClicked: { picker.service.applyToAll(picker.kind); picker.appliedAll = true }
      }
      Button {
        // The whole widget back to the theme, or this part to its default.
        label: picker.whole ? (picker.texts.reset || "Reset") : (picker.texts.byDefault || "Default")
        enabled: picker.whole ? Object.keys(picker.colors).length > 0 : picker.value !== ""
        onClicked: {
          if (picker.whole) picker.service.setColors(picker.kind, {})
          else picker.pick("", true, false)
          picker.takeShown()
        }
      }
    }

    // Single parts: the base color and each part (• has an own color).
    Fold {
      label: picker.texts.fineTune || "Fine-tuning"
      open: !!picker.service && picker.service.fineTune
      onToggled: picker.setFineTune(!picker.service.fineTune)
    }
    Flow {
      visible: !!picker.service && picker.service.fineTune
      width: parent.width
      spacing: Math.round(4 * picker.unit)
      Repeater {
        model: ["base"].concat(Object.keys(picker.titles))
        Chip {
          required property string modelData
          label: modelData === "base" ? (picker.texts.baseColor || "Base color") : picker.titles[modelData]
          current: modelData === picker.part
          marked: !!picker.colors[modelData]
          onClicked: picker.service.selection = Object.assign({}, picker.selection, { part: modelData })
        }
      }
    }
  }
}
