import QtQuick
import qs.Commons

// The song playing: cover, title, artist, album, a progress bar with the time
// and buttons (back, play/pause, next) – each can be left out. Side by side
// ("row") or the cover on top ("column"). The buttons take clicks even
// behind the windows: the layer lets clicks through everywhere else
// (`controls` is the clickable part).
Item {
  id: view

  property var service: null
  property bool editing: false
  // Its place and size on this screen (set by Placed).
  property var spot: null
  readonly property Item controls: buttons.visible ? buttons : null

  readonly property var settings: service ? service.widget("nowplaying") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property var look: service ? service.textLook("nowplaying") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  readonly property color tint: service ? service.tint("nowplaying") : Color.accent
  readonly property var texts: service && service.texts ? service.texts : ({})
  readonly property bool column: !!(settings && settings.np_layout === "column")
  function shows(key) { return !(settings && settings[key] === false) }
  function paint(part, fallback) { return view.service ? view.service.colorOf("nowplaying", part, fallback) : fallback }

  readonly property var player: service ? service.npPlayer : null
  readonly property bool hasTrack: !!(player && player.trackTitle)
  readonly property string title: hasTrack ? player.trackTitle : (texts.sampleTitle || "Song title")
  readonly property string artist: hasTrack ? String(player.trackArtist || "") : (texts.sampleArtist || "Artist")
  readonly property string album: hasTrack ? String(player.trackAlbum || "") : (texts.sampleAlbum || "Album")
  readonly property string art: hasTrack ? String(player.trackArtUrl || "") : ""
  readonly property real length: hasTrack && player.lengthSupported ? Number(player.length || 0) : 0
  readonly property real position: service ? service.npPosition : 0
  readonly property bool playing: !!(player && player.isPlaying)

  readonly property real cover: Math.round((column ? 180 : 96) * scale)
  readonly property real textWidth: spot && spot.width > 0 ? Math.max(60, spot.width - (column ? 0 : cover + gap))
                                                            : Math.round((column ? 180 : 280) * scale)
  readonly property real gap: Math.round(16 * scale)

  implicitWidth: layout.implicitWidth
  implicitHeight: layout.implicitHeight
  width: implicitWidth
  height: implicitHeight
  opacity: editing || hasTrack || !(settings && settings.hide_idle) ? 1 : 0
  Behavior on opacity { NumberAnimation { duration: 500 } }

  function time(seconds) {
    seconds = Math.max(0, Math.floor(seconds))
    var m = Math.floor(seconds / 60)
    var s = seconds % 60
    return m + ":" + (s < 10 ? "0" : "") + s
  }

  Grid {
    id: layout
    columns: view.column ? 1 : 2
    spacing: view.gap
    horizontalItemAlignment: view.column ? Grid.AlignHCenter : Grid.AlignLeft
    verticalItemAlignment: Grid.AlignVCenter

    Rectangle {
      visible: view.shows("show_cover")
      width: view.cover
      height: view.cover
      radius: Math.round(10 * view.scale)
      color: Qt.rgba(Color.background.r, Color.background.g, Color.background.b, 0.6)
      clip: true
      Image {
        id: coverImage
        anchors.fill: parent
        source: view.art
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        visible: status === Image.Ready
      }
      WidgetText {
        anchors.centerIn: parent
        visible: coverImage.status !== Image.Ready
        look: view.look
        factor: view.scale
        points: 42
        text: String.fromCodePoint(0xf075a)
        color: view.tint
      }
    }

    Column {
      width: view.textWidth
      spacing: Math.round(4 * view.scale)
      WidgetText {
        part: "title"
        visible: view.shows("show_title")
        width: parent.width
        horizontalAlignment: view.column ? Text.AlignHCenter : Text.AlignLeft
        elide: Text.ElideRight
        look: view.look; factor: view.scale; points: 20; strong: true
        text: view.title
        color: view.paint("title", Color.foreground)
      }
      WidgetText {
        part: "artist"
        visible: view.shows("show_artist") && view.artist !== ""
        width: parent.width
        horizontalAlignment: view.column ? Text.AlignHCenter : Text.AlignLeft
        elide: Text.ElideRight
        look: view.look; factor: view.scale; points: 15
        text: view.artist
        color: view.paint("artist", view.tint)
      }
      WidgetText {
        part: "album"
        visible: view.shows("show_album") && view.album !== ""
        width: parent.width
        horizontalAlignment: view.column ? Text.AlignHCenter : Text.AlignLeft
        elide: Text.ElideRight
        look: view.look; factor: view.scale; points: 13
        text: view.album
        color: view.paint("album", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.7))
      }
      Item {
        visible: view.shows("show_progress")
        width: parent.width
        height: Math.round(10 * view.scale)
        Rectangle {
          anchors.verticalCenter: parent.verticalCenter
          width: parent.width
          height: Math.max(2, Math.round(4 * view.scale))
          radius: height / 2
          color: view.paint("progress_track", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.2))
          PartHit { part: "progress_track"; anchors.margins: -4 }
          Rectangle {
            width: view.length > 0 ? parent.width * Math.min(1, view.position / view.length) : (view.editing ? parent.width * 0.4 : 0)
            height: parent.height
            radius: parent.radius
            color: view.paint("progress", view.tint)
            Behavior on width { NumberAnimation { duration: 500 } }
            PartHit { part: "progress"; anchors.margins: -4 }
          }
        }
      }
      WidgetText {
        part: "time"
        visible: view.shows("show_time") && (view.length > 0 || view.editing)
        width: parent.width
        horizontalAlignment: view.column ? Text.AlignHCenter : Text.AlignLeft
        look: view.look; factor: view.scale; points: 12
        text: view.time(view.position) + " / " + view.time(view.length || 210)
        color: view.paint("time", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.7))
      }
      Row {
        id: buttons
        visible: view.shows("show_controls")
        anchors.horizontalCenter: view.column ? parent.horizontalCenter : undefined
        spacing: Math.round(14 * view.scale)
        Repeater {
          model: [
            { glyph: 0xf04ae, act: "previous" },
            { glyph: view.playing ? 0xf03e4 : 0xf040a, act: "toggle" },
            { glyph: 0xf04ad, act: "next" }
          ]
          WidgetText {
            part: "buttons"
            required property var modelData
            look: view.look; factor: view.scale; points: 26; strong: true
            text: String.fromCodePoint(modelData.glyph)
            color: view.paint("buttons", Color.foreground)
            opacity: area.containsMouse ? 1 : 0.8
            MouseArea {
              id: area
              anchors.fill: parent
              anchors.margins: -Math.round(4 * view.scale)
              hoverEnabled: true
              cursorShape: Qt.PointingHandCursor
              enabled: !view.editing && !!view.player
              onClicked: {
                if (modelData.act === "previous") view.player.previous()
                else if (modelData.act === "next") view.player.next()
                else view.player.togglePlaying()
              }
            }
          }
        }
      }
    }
  }
}
