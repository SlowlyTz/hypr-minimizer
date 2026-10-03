import QtQuick
import qs.Commons

// The weather at Omarchy's weather place (set in Omarchy's weather panel):
// an icon, the temperature, the place, details (feels like, humidity, wind)
// and the next three days. Celsius or Fahrenheit.
Item {
  id: view

  property var service: null
  property bool editing: false
  // Its place and size on this screen (set by Placed).
  property var spot: null

  readonly property var settings: service ? service.widget("weather") : null
  readonly property real scale: spot ? spot.size / 100 : 1
  readonly property var look: service ? service.textLook("weather") : ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false })
  readonly property color tint: service ? service.tint("weather") : Color.accent
  readonly property var texts: service && service.texts ? service.texts : ({})
  readonly property var report: service ? service.weather : null
  readonly property bool fahrenheit: !!(settings && settings.units === "f")
  readonly property var locale: Qt.locale(service && service.locale ? service.locale : "")
  function shows(key) { return !(settings && settings[key] === false) }
  function paint(part, fallback) { return view.service ? view.service.colorOf("weather", part, fallback) : fallback }
  function degrees(c) { return Math.round(view.fahrenheit ? c * 9 / 5 + 32 : c) + "°" }
  function speed(kmh) { return view.fahrenheit ? Math.round(kmh / 1.609) + " mph" : Math.round(kmh) + " km/h" }

  implicitWidth: column.implicitWidth
  implicitHeight: column.implicitHeight
  width: implicitWidth
  height: implicitHeight

  Column {
    id: column
    spacing: Math.round(10 * view.scale)

    Row {
      spacing: Math.round(14 * view.scale)
      WidgetText {
        anchors.verticalCenter: parent.verticalCenter
        look: view.look; factor: view.scale; points: 64; strong: true
        text: view.report && view.service ? view.service.weatherIcon(view.report.code, view.report.day) : String.fromCodePoint(0xf0595)
        color: view.paint("icon", view.tint)
      }
      Column {
        anchors.verticalCenter: parent.verticalCenter
        spacing: Math.round(2 * view.scale)
        WidgetText {
          look: view.look; factor: view.scale; points: 44; strong: true
          text: view.report ? view.degrees(view.report.temp) : "–"
          color: view.paint("temp", Color.foreground)
        }
        WidgetText {
          visible: view.shows("show_place")
          look: view.look; factor: view.scale; points: 15
          text: view.service && view.service.weatherPlace.name ? view.service.weatherPlace.name
                : (view.texts.noWeatherPlace || "Pick a place in Omarchy's weather panel")
          color: view.paint("place", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.7))
        }
        WidgetText {
          visible: view.shows("show_details") && !!view.report
          look: view.look; factor: view.scale; points: 13
          text: view.report ? (view.texts.feelsLike || "Feels like") + " " + view.degrees(view.report.feels) + "  ·  "
                            + Math.round(view.report.humidity) + " %  ·  " + view.speed(view.report.wind) : ""
          color: view.paint("details", Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.7))
        }
      }
    }

    Row {
      visible: view.shows("show_forecast") && !!view.report && view.report.days.length > 0
      spacing: Math.round(22 * view.scale)
      Repeater {
        model: view.report ? view.report.days : []
        Column {
          required property var modelData
          spacing: Math.round(2 * view.scale)
          WidgetText {
            anchors.horizontalCenter: parent.horizontalCenter
            look: view.look; factor: view.scale; points: 13
            text: new Date(modelData.date + "T12:00:00").toLocaleDateString(view.locale, "ddd")
            color: view.paint("forecast", Color.foreground)
          }
          WidgetText {
            anchors.horizontalCenter: parent.horizontalCenter
            look: view.look; factor: view.scale; points: 24; strong: true
            text: view.service ? view.service.weatherIcon(modelData.code, true) : ""
            color: view.paint("icon", view.tint)
          }
          WidgetText {
            anchors.horizontalCenter: parent.horizontalCenter
            look: view.look; factor: view.scale; points: 13
            text: view.degrees(modelData.max) + " / " + view.degrees(modelData.min)
            color: view.paint("forecast", Color.foreground)
          }
        }
      }
    }
  }
}
