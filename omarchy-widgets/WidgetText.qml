import QtQuick

// Text in a widget's look (service.textLook): its font, weight, letter
// spacing and outline. `points` is the size at 100 %, `strong` the widget's
// weight (else a lighter one).
Text {
  property var look: ({ family: "", weight: 700, lighter: 400, spacing: 0, outline: false, outlineColor: "black" })
  property real factor: 1
  property real points: 14
  property bool strong: false

  font.family: look.family
  font.pixelSize: Math.max(6, Math.round(points * factor))
  font.weight: strong ? look.weight : look.lighter
  font.letterSpacing: look.spacing * factor
  style: look.outline ? Text.Outline : Text.Normal
  styleColor: look.outline ? look.outlineColor : "transparent"
}
