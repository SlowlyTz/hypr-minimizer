// The arrange tool's color helpers: color schemes made from a widget's base
// color, carrying one widget's colors over to another, and the main colors of
// the wallpaper. Colors come in as {r, g, b, a} (0..1) and go out as values
// widgets.py keeps: "accent", "theme:<name>" or "#rrggbb[aa]".
.pragma library

// What a part does, from its default color: the widget's main color, text,
// something quieter, the card behind it, or worked out by the widget itself.
function role(fallback) {
  if (fallback === "accent") return "main"
  if (fallback === "theme:foreground") return "text"
  if (fallback === "theme:background") return "background"
  if (fallback === "auto") return ""
  return "quiet"
}

function clamp(v) { return Math.max(0, Math.min(1, v)) }

function toHsv(c) {
  var max = Math.max(c.r, c.g, c.b), min = Math.min(c.r, c.g, c.b), d = max - min
  var h = 0
  if (d > 0) {
    if (max === c.r) h = ((c.g - c.b) / d) % 6
    else if (max === c.g) h = (c.b - c.r) / d + 2
    else h = (c.r - c.g) / d + 4
    h = ((h / 6) % 1 + 1) % 1
  }
  return { h: h, s: max > 0 ? d / max : 0, v: max, a: c.a === undefined ? 1 : c.a }
}

function fromHsv(h, s, v, a) {
  h = ((h % 1) + 1) % 1
  s = clamp(s); v = clamp(v)
  var i = Math.floor(h * 6), f = h * 6 - i
  var p = v * (1 - s), q = v * (1 - f * s), t = v * (1 - (1 - f) * s)
  var rgb = [[v, t, p], [q, v, p], [p, v, t], [p, q, v], [t, p, v], [v, p, q]][i % 6]
  return { r: rgb[0], g: rgb[1], b: rgb[2], a: a === undefined ? 1 : clamp(a) }
}

function two(v) { var h = Math.round(clamp(v) * 255).toString(16); return h.length < 2 ? "0" + h : h }
function hex(c) { return "#" + two(c.r) + two(c.g) + two(c.b) + (c.a !== undefined && c.a < 0.999 ? two(c.a) : "") }
function hsvHex(h, s, v, a) { return hex(fromHsv(h, s, v, a)) }

// The schemes in the order they are offered; "theme" gives every part its
// default back.
var SCHEMES = ["theme", "mono", "contrast", "pastel", "colorful", "muted"]

// A whole widget's colors for scheme `id`. baseValue: the base color as kept
// ("" = none, else "theme:<name>" or "#…"); base: how it looks ({r, g, b, a});
// defaults: part -> default color.
function scheme(id, baseValue, base, defaults) {
  if (id === "theme") return {}
  var hsv = toHsv(base)
  var own = baseValue || hex(base)
  var colors = {}
  var main = 0
  for (var part in defaults) {
    var r = role(defaults[part])
    if (!r || r === "background") continue
    var value = null
    if (id === "mono") {
      value = r === "main" ? "accent" : r === "text" ? own : hsvHex(hsv.h, hsv.s, hsv.v, 0.6)
    } else if (id === "contrast") {
      value = r === "main" ? "accent" : r === "text" ? "#ffffff" : "#ffffffb3"
    } else if (id === "pastel") {
      value = r === "main" ? "accent" : r === "text" ? hsvHex(hsv.h, 0.12, 1) : hsvHex(hsv.h, 0.3, 0.92, 0.8)
    } else if (id === "colorful") {
      // Main parts walk round the color wheel from the base, the rest takes its opposite.
      value = r === "main" ? (main++ === 0 ? "accent" : hsvHex(hsv.h + 0.09 * (main - 1), Math.max(0.5, hsv.s), Math.max(0.75, hsv.v)))
            : r === "text" ? hsvHex(hsv.h, 0.12, 1) : hsvHex(hsv.h + 0.5, Math.max(0.45, hsv.s * 0.8), 0.9)
    } else if (id === "muted") {
      value = r === "main" ? "accent" : r === "text" ? hsvHex(hsv.h, 0.08, 0.85) : hsvHex(hsv.h, 0.12, 0.6, 0.85)
    }
    if (value) colors[part] = value
  }
  if (id === "contrast") {
    for (var p in defaults) if (role(defaults[p]) === "background") colors[p] = "#000000"
  }
  // The base itself: pastel and muted soften it.
  if (id === "pastel") colors.base = hsvHex(hsv.h, Math.min(hsv.s, 0.45), Math.max(hsv.v, 0.92), hsv.a)
  else if (id === "muted") colors.base = hsvHex(hsv.h, hsv.s * 0.55, hsv.v * 0.85, hsv.a)
  else if (baseValue) colors.base = baseValue
  return colors
}

// One widget's colors over on another: the base, parts of the same name, and
// for the rest the color its kind of part has on the first widget.
function carry(from, fromDefaults, toDefaults) {
  var byRole = {}
  for (var part in fromDefaults) {
    var r = role(fromDefaults[part])
    if (r && from[part] !== undefined && byRole[r] === undefined) byRole[r] = from[part]
  }
  var colors = {}
  if (from.base) colors.base = from.base
  for (var p in toDefaults) {
    if (from[p] !== undefined && fromDefaults[p] !== undefined) colors[p] = from[p]
    else if (byRole[role(toDefaults[p])] !== undefined) colors[p] = byRole[role(toDefaults[p])]
  }
  return colors
}

// Up to `count` main colors of an image (RGBA bytes): colorful pixels by hue
// and brightness, the most of them first, each one well apart from the others;
// a light and a dark one fill up when the image has few colors.
function mainColors(pixels, count) {
  var buckets = {}
  var light = { r: 0, g: 0, b: 0, n: 0 }, dark = { r: 0, g: 0, b: 0, n: 0 }
  for (var i = 0; i + 3 < pixels.length; i += 4) {
    var c = { r: pixels[i] / 255, g: pixels[i + 1] / 255, b: pixels[i + 2] / 255 }
    var hsv = toHsv(c)
    var into = hsv.v > 0.6 ? light : hsv.v < 0.35 ? dark : null
    if (into) { into.r += c.r; into.g += c.g; into.b += c.b; into.n++ }
    if (hsv.s < 0.22 || hsv.v < 0.22) continue
    var key = Math.floor(hsv.h * 18) + "-" + (hsv.v > 0.65 ? 1 : 0)
    var bucket = buckets[key] || (buckets[key] = { r: 0, g: 0, b: 0, n: 0, weight: 0 })
    bucket.r += c.r; bucket.g += c.g; bucket.b += c.b; bucket.n++
    bucket.weight += hsv.s * hsv.v
  }
  var list = Object.keys(buckets).map(function(k) { return buckets[k] })
  list.sort(function(a, b) { return b.weight - a.weight })
  var out = [], picked = []
  for (var j = 0; j < list.length && out.length < count; j++) {
    var b = list[j]
    var mean = { r: b.r / b.n, g: b.g / b.n, b: b.b / b.n, a: 1 }
    var near = picked.some(function(o) { return Math.abs(o.r - mean.r) + Math.abs(o.g - mean.g) + Math.abs(o.b - mean.b) < 0.25 })
    if (near) continue
    picked.push(mean)
    out.push(hex(mean))
  }
  var fill = [light, dark]
  for (var k = 0; k < fill.length; k++) {
    var t = fill[k]
    if (out.length < count && t.n > 0) out.push(hex({ r: t.r / t.n, g: t.g / t.n, b: t.b / t.n, a: 1 }))
  }
  return out
}
