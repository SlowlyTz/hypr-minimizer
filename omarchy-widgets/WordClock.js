// The time in words, to five minutes ("quarter past six"), in the settings
// window's language. sentence() gives segments [{text, part}]: "hours" for the
// hour, "minutes" for the minutes, "words" for the words in between, so each
// can have its own color.
.pragma library

function rounded(date) {
  var minutes = date.getHours() * 60 + date.getMinutes() + (date.getSeconds() >= 30 ? 1 : 0)
  minutes = Math.round(minutes / 5) * 5
  return { hour: Math.floor(minutes / 60) % 24, minute: minutes % 60 }
}

function twelve(hour) {
  var h = hour % 12
  return h === 0 ? 12 : h
}

var EN = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve"]
var DE = ["", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun", "zehn", "elf", "zwölf"]
var ES = ["", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce"]
var FR = ["", "une", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze"]
var IT = ["", "una", "due", "tre", "quattro", "cinque", "sei", "sette", "otto", "nove", "dieci", "undici", "dodici"]

function seg(text, part) { return { text: text, part: part } }

function english(t) {
  var past = { 5: "five", 10: "ten", 15: "quarter", 20: "twenty", 25: "twenty-five", 30: "half" }
  var to = { 35: "twenty-five", 40: "twenty", 45: "quarter", 50: "ten", 55: "five" }
  var out = [seg("It's ", "words")]
  if (t.minute === 0) return out.concat([seg(EN[twelve(t.hour)], "hours"), seg(" o'clock", "words")])
  if (past[t.minute]) return out.concat([seg(past[t.minute], "minutes"), seg(" past ", "words"), seg(EN[twelve(t.hour)], "hours")])
  return out.concat([seg(to[t.minute], "minutes"), seg(" to ", "words"), seg(EN[twelve(t.hour + 1)], "hours")])
}

function german(t) {
  var out = [seg("Es ist ", "words")]
  var next = DE[twelve(t.hour + 1)]
  var now = DE[twelve(t.hour)]
  switch (t.minute) {
  case 0: return out.concat([seg(now === "eins" ? "ein" : now, "hours"), seg(" Uhr", "words")])
  case 5: return out.concat([seg("fünf", "minutes"), seg(" nach ", "words"), seg(now, "hours")])
  case 10: return out.concat([seg("zehn", "minutes"), seg(" nach ", "words"), seg(now, "hours")])
  case 15: return out.concat([seg("Viertel", "minutes"), seg(" nach ", "words"), seg(now, "hours")])
  case 20: return out.concat([seg("zwanzig", "minutes"), seg(" nach ", "words"), seg(now, "hours")])
  case 25: return out.concat([seg("fünf vor halb", "minutes"), seg(" ", "words"), seg(next, "hours")])
  case 30: return out.concat([seg("halb", "minutes"), seg(" ", "words"), seg(next, "hours")])
  case 35: return out.concat([seg("fünf nach halb", "minutes"), seg(" ", "words"), seg(next, "hours")])
  case 40: return out.concat([seg("zwanzig", "minutes"), seg(" vor ", "words"), seg(next, "hours")])
  case 45: return out.concat([seg("Viertel", "minutes"), seg(" vor ", "words"), seg(next, "hours")])
  case 50: return out.concat([seg("zehn", "minutes"), seg(" vor ", "words"), seg(next, "hours")])
  default: return out.concat([seg("fünf", "minutes"), seg(" vor ", "words"), seg(next, "hours")])
  }
}

function spanish(t) {
  var after = { 0: "en punto", 5: "cinco", 10: "diez", 15: "cuarto", 20: "veinte", 25: "veinticinco", 30: "media" }
  var before = { 35: "veinticinco", 40: "veinte", 45: "cuarto", 50: "diez", 55: "cinco" }
  var hour = t.minute > 30 ? twelve(t.hour + 1) : twelve(t.hour)
  var out = [seg(hour === 1 ? "Es la " : "Son las ", "words"), seg(ES[hour], "hours")]
  if (t.minute === 0) return out.concat([seg(" " + after[0], "minutes")])
  if (t.minute <= 30) return out.concat([seg(" y ", "words"), seg(after[t.minute], "minutes")])
  return out.concat([seg(" menos ", "words"), seg(before[t.minute], "minutes")])
}

function french(t) {
  var hour24 = t.minute > 30 ? (t.hour + 1) % 24 : t.hour
  var name = hour24 === 0 ? "minuit" : (hour24 === 12 ? "midi" : FR[twelve(hour24)])
  var unit = hour24 === 0 || hour24 === 12 ? "" : (twelve(hour24) === 1 ? " heure" : " heures")
  var out = [seg("Il est ", "words"), seg(name, "hours"), seg(unit, "words")]
  var after = { 5: "cinq", 10: "dix", 15: "et quart", 20: "vingt", 25: "vingt-cinq", 30: "et demie" }
  var before = { 35: "moins vingt-cinq", 40: "moins vingt", 45: "moins le quart", 50: "moins dix", 55: "moins cinq" }
  if (t.minute === 0) return out
  return out.concat([seg(" ", "words"), seg(t.minute <= 30 ? after[t.minute] : before[t.minute], "minutes")])
}

function italian(t) {
  var hour24 = t.minute > 30 ? (t.hour + 1) % 24 : t.hour
  var out
  if (hour24 === 0) out = [seg("È ", "words"), seg("mezzanotte", "hours")]
  else if (hour24 === 12) out = [seg("È ", "words"), seg("mezzogiorno", "hours")]
  else if (twelve(hour24) === 1) out = [seg("È l'", "words"), seg("una", "hours")]
  else out = [seg("Sono le ", "words"), seg(IT[twelve(hour24)], "hours")]
  var after = { 5: "cinque", 10: "dieci", 15: "un quarto", 20: "venti", 25: "venticinque", 30: "mezza" }
  var before = { 35: "venticinque", 40: "venti", 45: "un quarto", 50: "dieci", 55: "cinque" }
  if (t.minute === 0) return out
  if (t.minute <= 30) return out.concat([seg(" e ", "words"), seg(after[t.minute], "minutes")])
  return out.concat([seg(" meno ", "words"), seg(before[t.minute], "minutes")])
}

function sentence(locale, date) {
  var t = rounded(date)
  var lang = String(locale || "en").slice(0, 2)
  if (lang === "de") return german(t)
  if (lang === "es") return spanish(t)
  if (lang === "fr") return french(t)
  if (lang === "it") return italian(t)
  return english(t)
}
