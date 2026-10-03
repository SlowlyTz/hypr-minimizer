import QtQuick
import qs.Commons

// The song's lines, synced to the player and scrolling like a teleprompter.
//
// The widget's box is the text: its height (`size`, in pixels) is split into
// one slot per visible line and the font fills the slot; a line too long for
// the width first gets smaller, then takes two rows in its slot. All lines sit
// in one column that slides up, so the line being sung stays in the middle
// slot: the next one comes up from below, the last one moves on up and fades.
// At the start and end of a song the lines fill the box from the top or to
// the bottom instead of leaving slots empty.
// Shown while there are synced lyrics (or while arranging).
//
// Highlight "line" colors the line being sung, "word" each word as it is sung
// (from the word times of the lyrics, or spread over the line), "off" none.
Item {
  id: view

  property var service: null
  property bool editing: false

  readonly property var settings: service ? service.widget("lyrics") : null
  // Its place and size on this screen (set by Placed).
  property var spot: null
  readonly property int shownLines: settings ? settings.lines : 3
  readonly property string highlight: settings ? settings.highlight : "line"
  readonly property string align: settings ? settings.align : "center"
  readonly property color tint: service ? service.tint("lyrics") : Color.accent
  readonly property var look: service ? service.textLook("lyrics") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  function paint(part, fallback) { return view.service ? view.service.colorOf("lyrics", part, fallback) : fallback }
  readonly property bool hidePaused: !!(settings && settings.hide_paused)
  readonly property var lines: service ? service.lyricLines : []
  readonly property bool hasLyrics: lines.length > 0
  readonly property string sample: service && service.texts ? (service.texts.lyricsSample || "♪") : "♪"
  // What the column holds, and the line in the middle (-1: before the first).
  readonly property var shown: hasLyrics ? lines : (editing ? [{ t: 0, text: sample }] : [])
  readonly property int current: hasLyrics ? (service ? service.lyricIndex : -1) : 0

  readonly property real slot: height / Math.max(1, shownLines)
  // The font fills most of its slot; long lines go down to half of it.
  readonly property real fontSize: Math.max(8, Math.floor(slot * 0.6))
  // The other lines are a little smaller than the one being sung.
  readonly property real restScale: 0.88

  implicitWidth: spot && spot.width > 0 ? spot.width : 720
  implicitHeight: spot ? spot.size : 200
  width: implicitWidth
  height: implicitHeight
  opacity: editing || (hasLyrics && (!hidePaused || (service && service.playing))) ? 1 : 0
  Behavior on opacity { NumberAnimation { duration: 500 } }

  function escaped(text) {
    return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
  }

  // The line being sung with the words sung so far in the accent color.
  function wordLine(index, time) {
    var words = view.service ? view.service.wordsFor(index) : []
    if (!words.length) return view.escaped(view.shown[index] ? view.shown[index].text : "")
    var sung = view.cssColor(view.paint("sung", view.tint))
    var waiting = view.cssColor(view.paint("waiting", Color.foreground))
    var out = []
    for (var i = 0; i < words.length; i++) {
      out.push('<font color="' + (words[i].t <= time + 0.1 ? sung : waiting) + '">' + view.escaped(words[i].text) + "</font>")
    }
    return out.join(" ")
  }

  // Where the column goes: the current line in the middle slot (the upper of
  // the two with an even number of lines), but never past the first line at
  // the top or the last at the bottom; fewer lines than slots sit in the middle.
  readonly property real columnY: {
    var total = view.shown.length * view.slot
    if (total <= view.height) return (view.height - total) / 2
    var middle = (Math.floor((view.shownLines - 1) / 2) - view.current) * view.slot
    return Math.max(view.height - total, Math.min(0, middle))
  }

  // StyledText takes #aarrggbb.
  function cssColor(c) {
    function two(v) { var h = Math.round(v * 255).toString(16); return h.length < 2 ? "0" + h : h }
    return "#" + two(c.a) + two(c.r) + two(c.g) + two(c.b)
  }

  // A new song (or lyrics) jumps into place; only the next line scrolls.
  property bool jumping: false
  onShownChanged: { jumping = true; Qt.callLater(function() { view.jumping = false }) }

  Column {
    id: column
    width: view.width
    y: view.columnY
    Behavior on y {
      enabled: !view.jumping
      NumberAnimation { duration: 550; easing.type: Easing.OutCubic }
    }

    Repeater {
      model: view.shown
      Text {
        required property var modelData
        required property int index
        readonly property int distance: index - view.current
        readonly property bool sung: distance === 0
        readonly property bool byWord: sung && view.highlight === "word" && view.hasLyrics
        width: column.width
        height: view.slot
        horizontalAlignment: view.align === "left" ? Text.AlignLeft : (view.align === "right" ? Text.AlignRight : Text.AlignHCenter)
        verticalAlignment: Text.AlignVCenter
        transformOrigin: view.align === "left" ? Item.Left : (view.align === "right" ? Item.Right : Item.Center)
        wrapMode: Text.WordWrap
        fontSizeMode: Text.Fit
        minimumPixelSize: Math.max(6, Math.floor(view.fontSize / 2))
        lineHeight: 0.95
        textFormat: byWord ? Text.StyledText : Text.PlainText
        text: byWord ? view.wordLine(index, view.service ? view.service.songTime : 0) : (modelData.text || "♪")
        color: sung ? (view.highlight === "line" ? view.paint("current", view.tint) : view.paint("waiting", Color.foreground))
                    : view.paint(distance > 0 ? "upcoming" : "past", Color.foreground)
        // Inside the box once the column has moved: the coming lines a bit
        // brighter than the ones sung; outside it, gone.
        readonly property real slotTop: view.columnY + index * view.slot
        readonly property bool inside: slotTop > -view.slot / 2 && slotTop + view.slot < view.height + view.slot / 2
        opacity: !inside ? 0 : (sung ? 1 : (distance > 0 ? 0.7 : 0.4))
        scale: sung ? 1 : view.restScale
        font.family: view.look.family
        font.pixelSize: view.fontSize
        font.weight: view.look.weight
        font.letterSpacing: view.look.spacing * view.fontSize / 30
        style: view.look.outline ? Text.Outline : Text.Normal
        styleColor: view.look.outline ? view.look.outlineColor : "transparent"
        Behavior on opacity { NumberAnimation { duration: 450; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 450; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 350 } }
      }
    }
  }
}
