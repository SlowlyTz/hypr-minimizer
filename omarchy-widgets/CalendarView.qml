import QtQuick
import qs.Commons

// This month as a grid: the month's name, the weekdays, the days (today in a
// circle, the neighbouring months' days dimmed) and, optionally, the week
// numbers. Weeks start on Monday or Sunday.
Item {
  id: view

  property var service: null
  property bool editing: false
  // Its place and size on this screen (set by Placed).
  property var spot: null

  readonly property var settings: service ? service.widget("calendar") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property var look: service ? service.textLook("calendar") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  readonly property color tint: service ? service.tint("calendar") : Color.accent
  readonly property var locale: Qt.locale(service && service.locale ? service.locale : "")
  readonly property bool sunday: !!(settings && settings.week_start === "sunday")
  readonly property bool weeks: !!(settings && settings.show_weeks)
  readonly property date now: service ? service.now : new Date()
  // Changes once a day, so the grid is only worked out again then.
  readonly property string day: now.getFullYear() + "-" + now.getMonth() + "-" + now.getDate()
  readonly property real cell: Math.round(34 * scale)
  function paint(part, fallback) { return view.service ? view.service.colorOf("calendar", part, fallback) : fallback }

  // 6 weeks × 7 days from the start of the week the month begins in.
  readonly property var cells: {
    var stamp = view.day
    var first = new Date(view.now.getFullYear(), view.now.getMonth(), 1)
    var shift = (first.getDay() - (view.sunday ? 0 : 1) + 7) % 7
    var out = []
    for (var i = 0; i < 42; i++) {
      var d = new Date(first.getFullYear(), first.getMonth(), 1 - shift + i)
      out.push({ day: d.getDate(), here: d.getMonth() === first.getMonth(),
                 today: d.getDate() === view.now.getDate() && d.getMonth() === view.now.getMonth(), date: d })
    }
    return out
  }
  function isoWeek(d) {
    var t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
    var weekday = t.getUTCDay() || 7
    t.setUTCDate(t.getUTCDate() + 4 - weekday)
    var start = new Date(Date.UTC(t.getUTCFullYear(), 0, 1))
    return Math.ceil(((t - start) / 86400000 + 1) / 7)
  }

  implicitWidth: column.implicitWidth
  implicitHeight: column.implicitHeight
  width: implicitWidth
  height: implicitHeight

  Column {
    id: column
    spacing: Math.round(6 * view.scale)

    WidgetText {
      visible: !(view.settings && view.settings.show_month === false)
      anchors.horizontalCenter: parent.horizontalCenter
      look: view.look; factor: view.scale; points: 20; strong: true
      text: view.now.toLocaleDateString(view.locale, "MMMM yyyy")
      color: view.paint("month", view.tint)
    }

    Grid {
      columns: view.weeks ? 8 : 7
      // The weekdays' names, then the days.
      Repeater {
        model: view.weeks ? 8 : 7
        WidgetText {
          required property int index
          width: view.cell
          horizontalAlignment: Text.AlignHCenter
          look: view.look; factor: view.scale; points: 12
          readonly property int weekday: (index - (view.weeks ? 1 : 0) + (view.sunday ? 0 : 1)) % 7
          text: view.weeks && index === 0 ? "" : view.locale.dayName(weekday, Locale.ShortFormat).slice(0, 2)
          color: view.paint("weekdays", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.7))
        }
      }
      Repeater {
        model: view.weeks ? 48 : 42
        Item {
          required property int index
          readonly property bool weekCell: view.weeks && index % 8 === 0
          readonly property var info: view.cells[view.weeks ? index - Math.floor(index / 8) - 1 : index] || ({})
          width: view.cell
          height: view.cell
          Rectangle {
            visible: !parent.weekCell && !!parent.info.today
            anchors.centerIn: parent
            width: view.cell * 0.86
            height: width
            radius: width / 2
            color: view.paint("today", view.tint)
          }
          WidgetText {
            anchors.centerIn: parent
            look: view.look; factor: view.scale; points: 14
            strong: !parent.weekCell && !!parent.info.today
            text: parent.weekCell ? view.isoWeek(view.cells[(index / 8) * 7 + 3].date) : parent.info.day
            color: parent.weekCell ? view.paint("weeks", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.7))
                   : parent.info.today ? view.paint("today_text", Color.background)
                   : parent.info.here ? view.paint("days", Color.foreground)
                   : view.paint("other_days", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.3))
          }
        }
      }
    }
  }
}
