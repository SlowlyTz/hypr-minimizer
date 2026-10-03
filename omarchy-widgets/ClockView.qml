import QtQuick
import qs.Commons
import "WordClock.js" as WordClock

// A big clock in one of four styles – digital, analog (hands on a dial), flip
// cards, or words ("quarter past six") – optionally with the weekday and date
// below and a second time zone. Every part has its own color.
Item {
  id: view

  property var service: null
  property bool editing: false
  // Its place and size on this screen (set by Placed).
  property var spot: null

  readonly property var settings: service ? service.widget("clock") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property string clockStyle: settings ? settings.clock_style : "digital"
  readonly property bool seconds: !!(settings && settings.seconds)
  readonly property bool twelve: !!(settings && settings.hours === "12")
  readonly property date now: service ? service.now : new Date()
  readonly property var look: service ? service.textLook("clock") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  readonly property var locale: Qt.locale(service && service.locale ? service.locale : "")
  readonly property color accent: service ? service.tint("clock") : Color.accent

  // The hour as shown: 0-23 with two digits, or 1-12 (Qt only counts to 12
  // when "AP" is in the same pattern).
  function hourText(padded) {
    var h = view.now.getHours()
    if (view.twelve) h = h % 12 === 0 ? 12 : h % 12
    var text = String(h)
    return (padded || !view.twelve) && text.length < 2 ? "0" + text : text
  }

  function paint(part, fallback) { return view.service ? view.service.colorOf("clock", part, fallback) : fallback }

  // The date line: weekday (long or short) and the date in the chosen format.
  function dateText() {
    var s = view.settings || {}
    var format = s.date_format || "long"
    var pattern = { long: "d MMMM", medium: "d MMM yyyy", iso: "yyyy-MM-dd" }[format]
    if (format === "short") pattern = view.locale.dateFormat(Locale.ShortFormat)
    if (format === "custom") pattern = s.date_pattern || "d MMMM"
    return view.now.toLocaleDateString(view.locale, pattern)
  }
  function weekdayText() {
    var s = view.settings || {}
    if (s.weekday === false) return ""
    return view.now.toLocaleDateString(view.locale, (s.date_format || "long") === "long" ? "dddd" : "ddd") + ", "
  }
  readonly property string zoneName: settings && settings.zone2 ? settings.zone2.split("/").pop().replace(/_/g, " ") : ""

  implicitWidth: column.implicitWidth
  implicitHeight: column.implicitHeight
  width: implicitWidth
  height: implicitHeight

  component Part: Text {
    property string part: ""
    property real points: 96
    property bool strong: true
    color: view.paint(part, Color.foreground)
    font.family: view.look.family
    font.pixelSize: Math.max(6, Math.round(points * view.scale))
    font.weight: strong ? view.look.weight : view.look.lighter
    font.letterSpacing: view.look.spacing * view.scale
    style: view.look.outline ? Text.Outline : Text.Normal
    styleColor: view.look.outline ? view.look.outlineColor : "transparent"
    PartHit { part: parent.part }
  }

  // --- the four faces ------------------------------------------------------------------

  component Digital: Row {
    Part { part: "hours"; text: view.hourText(false) }
    Part { part: "colon"; text: ":" }
    Part { part: "minutes"; text: Qt.formatTime(view.now, "mm") }
    Part { part: "colon"; text: ":"; visible: view.seconds }
    Part { part: "seconds"; text: Qt.formatTime(view.now, "ss"); visible: view.seconds }
    Part { part: "ampm"; visible: view.twelve; points: 48; anchors.baseline: parent.children[0].baseline
           text: " " + Qt.formatTime(view.now, "AP") }
  }

  component Analog: Item {
    id: dial
    readonly property real size: Math.round(220 * view.scale)
    width: size
    height: size
    Canvas {
      id: canvas
      anchors.fill: parent
      readonly property var stamp: view.now
      readonly property color face: view.paint("face", Qt.rgba(Color.background.r, Color.background.g, Color.background.b, 0.45))
      readonly property color ticks: view.paint("ticks", Color.foreground)
      readonly property color hourHand: view.paint("hour_hand", Color.foreground)
      readonly property color minuteHand: view.paint("minute_hand", Color.foreground)
      readonly property color secondHand: view.paint("second_hand", view.accent)
      onStampChanged: requestPaint()
      onFaceChanged: requestPaint()
      onTicksChanged: requestPaint()
      onHourHandChanged: requestPaint()
      onMinuteHandChanged: requestPaint()
      onSecondHandChanged: requestPaint()
      PartHit { part: "face" }
      onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        var r = width / 2
        ctx.translate(r, r)
        ctx.beginPath()
        ctx.arc(0, 0, r - 2, 0, Math.PI * 2)
        ctx.fillStyle = face
        ctx.fill()
        for (var i = 0; i < 60; i++) {
          var big = i % 5 === 0
          var a = i * Math.PI / 30
          ctx.beginPath()
          ctx.moveTo(Math.sin(a) * (r - 8), -Math.cos(a) * (r - 8))
          ctx.lineTo(Math.sin(a) * (r - (big ? 22 : 13)), -Math.cos(a) * (r - (big ? 22 : 13)))
          ctx.strokeStyle = ticks
          ctx.globalAlpha = big ? 1 : 0.5
          ctx.lineWidth = big ? Math.max(2, r / 30) : Math.max(1, r / 70)
          ctx.stroke()
        }
        ctx.globalAlpha = 1
        var d = view.now
        var hand = function(angle, length, w, color) {
          ctx.beginPath()
          ctx.moveTo(-Math.sin(angle) * r * 0.1, Math.cos(angle) * r * 0.1)
          ctx.lineTo(Math.sin(angle) * length, -Math.cos(angle) * length)
          ctx.strokeStyle = color
          ctx.lineWidth = w
          ctx.lineCap = "round"
          ctx.stroke()
        }
        hand(((d.getHours() % 12) + d.getMinutes() / 60) * Math.PI / 6, r * 0.5, Math.max(3, r / 16), hourHand)
        hand((d.getMinutes() + d.getSeconds() / 60) * Math.PI / 30, r * 0.75, Math.max(2, r / 24), minuteHand)
        if (view.seconds) hand(d.getSeconds() * Math.PI / 30, r * 0.82, Math.max(1, r / 60), secondHand)
        ctx.beginPath()
        ctx.arc(0, 0, Math.max(3, r / 22), 0, Math.PI * 2)
        ctx.fillStyle = view.seconds ? secondHand : minuteHand
        ctx.fill()
      }
    }
  }

  // One flip card: the digit falls over (turns on its middle) when it changes.
  component Card: Rectangle {
    id: card
    property string digit: "0"
    property string part: "hours"
    property string shown: digit
    readonly property real w: Math.round(68 * view.scale)
    width: w
    height: Math.round(w * 1.45)
    radius: Math.round(10 * view.scale)
    color: view.paint("flip_card", Qt.rgba(Color.background.r, Color.background.g, Color.background.b, 0.8))
    PartHit { part: "flip_card" }
    Part {
      anchors.centerIn: parent
      part: card.part
      points: 80
      text: card.shown
    }
    Rectangle {
      anchors.verticalCenter: parent.verticalCenter
      width: parent.width
      height: Math.max(1, Math.round(2 * view.scale))
      color: Qt.rgba(0, 0, 0, 0.35)
    }
    transform: Scale { id: fold; origin.y: card.height / 2; yScale: 1 }
    onDigitChanged: flip.restart()
    SequentialAnimation {
      id: flip
      NumberAnimation { target: fold; property: "yScale"; to: 0; duration: 140; easing.type: Easing.InQuad }
      ScriptAction { script: card.shown = card.digit }
      NumberAnimation { target: fold; property: "yScale"; to: 1; duration: 160; easing.type: Easing.OutQuad }
    }
  }

  component Flip: Row {
    spacing: Math.round(6 * view.scale)
    readonly property string hh: view.hourText(true)
    readonly property string mm: Qt.formatTime(view.now, "mm")
    readonly property string ss: Qt.formatTime(view.now, "ss")
    Card { digit: parent.hh[0]; part: "hours" }
    Card { digit: parent.hh[1]; part: "hours" }
    Part { part: "colon"; text: ":"; points: 80; anchors.verticalCenter: parent.verticalCenter }
    Card { digit: parent.mm[0]; part: "minutes" }
    Card { digit: parent.mm[1]; part: "minutes" }
    Part { part: "colon"; text: ":"; points: 80; anchors.verticalCenter: parent.verticalCenter; visible: view.seconds }
    Card { digit: parent.ss[0]; part: "seconds"; visible: view.seconds }
    Card { digit: parent.ss[1]; part: "seconds"; visible: view.seconds }
    Part { part: "ampm"; visible: view.twelve; points: 36; anchors.verticalCenter: parent.verticalCenter
           text: Qt.formatTime(view.now, "AP") }
  }

  component Words: Text {
    width: Math.round(560 * view.scale)
    horizontalAlignment: Text.AlignHCenter
    wrapMode: Text.WordWrap
    textFormat: Text.StyledText
    font.family: view.look.family
    font.pixelSize: Math.round(54 * view.scale)
    font.weight: view.look.weight
    font.letterSpacing: view.look.spacing * view.scale
    style: view.look.outline ? Text.Outline : Text.Normal
    styleColor: view.look.outline ? view.look.outlineColor : "transparent"
    color: Color.foreground
    text: {
      var parts = WordClock.sentence(view.service ? view.service.locale : "en", view.now)
      var out = ""
      for (var i = 0; i < parts.length; i++) {
        var c = parts[i].part === "words"
                ? view.paint("words", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.55))
                : view.paint(parts[i].part, Color.foreground)
        out += '<font color="' + view.css(c) + '">' + parts[i].text.replace(/&/g, "&amp;").replace(/</g, "&lt;") + "</font>"
      }
      return out
    }
    PartHit { part: "words" }
  }
  // StyledText takes #aarrggbb.
  function css(c) {
    function two(v) { var h = Math.round(v * 255).toString(16); return h.length < 2 ? "0" + h : h }
    return "#" + two(c.a) + two(c.r) + two(c.g) + two(c.b)
  }

  Column {
    id: column
    spacing: Math.round(4 * view.scale)
    Loader {
      anchors.horizontalCenter: parent.horizontalCenter
      sourceComponent: view.clockStyle === "analog" ? analog : view.clockStyle === "flip" ? flip
                       : view.clockStyle === "words" ? words : digital
    }
    Row {
      visible: !(view.settings && view.settings.date === false)
      anchors.horizontalCenter: parent.horizontalCenter
      Part { part: "weekday"; points: 24; strong: false; color: view.paint("weekday", view.accent); text: view.weekdayText() }
      Part { part: "date"; points: 24; strong: false; color: view.paint("date", view.accent); text: view.dateText() }
    }
    Part {
      visible: view.zoneName !== "" && !!(view.service && view.service.zoneKnown)
      anchors.horizontalCenter: parent.horizontalCenter
      part: "zone"
      points: 20
      strong: false
      text: view.zoneName + "  " + (view.service ? Qt.formatTime(view.service.zoneTime(view.now), view.twelve ? "h:mm AP" : "HH:mm") : "")
    }
  }

  Component { id: digital; Digital {} }
  Component { id: analog; Analog {} }
  Component { id: flip; Flip {} }
  Component { id: words; Words {} }
}
