import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import Quickshell.Services.Mpris
import Quickshell.Services.UPower
import qs.Commons
import qs.Ui

// Desktop widgets of hypr-screens: visualizer, lyrics, clock and system,
// drawn behind the windows on every chosen screen; the bar visualizer
// (BarWidget.qml) reads its levels from here.
//
// Settings come from ~/.config/hypr-screens/widgets.json, written by the
// settings window (hypr_screens/widgets.py). While arranging, every screen
// with a widget gets an extra layer above the windows that shows the
// wallpaper -- an empty desktop -- where the widgets can be dragged, resized
// by their edges and corners and turned with the wheel. Its own Save/Cancel
// (and Esc) end it, so nothing behind it is needed; Save hands places and
// sizes to `hypr-screens widgets save`.
Item {
  id: root

  property var shell: null
  property var manifest: null

  readonly property string configDir: (Quickshell.env("XDG_CONFIG_HOME") || (Quickshell.env("HOME") + "/.config")) + "/hypr-screens"
  readonly property string wallpaper: Quickshell.env("HOME") + "/.local/state/omarchy/current/background"
  property var widgets: ({})
  property string cavaConfig: ""
  property string cpuTemperatureFile: ""
  property string fontFamily: ""
  // Texts in the settings window's language, and its locale for the date.
  property var texts: ({})
  property string locale: ""
  // kind -> {size: [min, max], width: [min, max] or null}, from widgets.py.
  property var ranges: ({})
  property bool editing: false
  // kind -> {x, y, rotation, size, width, colors}: the centre as fractions of
  // the screen, degrees, the size (width 0: it follows the size) and the
  // colors of its parts (only the ones set).
  property var draft: ({})
  // The widgets there are, and each one's parts with a color: part -> default.
  property var kinds: ["visualizer", "lyrics", "clock", "system"]
  property var parts: ({})
  // The theme's colors by name, from its colors.toml (follows a theme change).
  property var palette: ({})

  // --- settings ------------------------------------------------------------------

  FileView {
    id: settingsFile
    path: root.configDir + "/widgets.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.parseSettings(text())
  }

  function parseSettings(text) {
    var data
    try { data = JSON.parse(String(text)) } catch (e) { return }
    var bars = root.widget("visualizer") ? root.widget("visualizer").bars : 0
    root.widgets = data.widgets || {}
    root.cavaConfig = String(data.cava || "")
    root.cpuTemperatureFile = String(data.cpuTemperature || "")
    root.fontFamily = String(data.font || "")
    root.texts = data.texts || {}
    root.locale = String(data.locale || "")
    root.ranges = data.ranges || {}
    if (data.kinds) root.kinds = data.kinds
    root.parts = data.parts || {}
    if (!root.editing) root.draft = root.placementsFromSettings()
    if (root.widget("visualizer") && root.widget("visualizer").bars !== bars) root.restartCava()
  }

  FileView {
    id: themeFile
    path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/colors.toml"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      var found = {}
      var rows = String(text()).split("\n")
      for (var i = 0; i < rows.length; i++) {
        var match = rows[i].match(/^\s*([a-z_]+)\s*=\s*"(#[0-9a-fA-F]{6})"/)
        if (match) found[match[1]] = match[2]
      }
      root.palette = found
    }
  }
  // A theme switch replaces the file; the shell's colors change with it.
  Connections {
    target: Color
    function onAccentChanged() { themeFile.reload() }
  }

  function themeColor(name) {
    if (root.palette[name]) return root.hexColor(root.palette[name])
    if (name === "foreground") return Color.foreground
    if (name === "background") return Color.background
    if (name === "muted") return Color.muted
    if (name === "red") return Color.urgent
    return Color.accent
  }
  // "#rrggbb" or "#rrggbbaa" (CSS order; Qt reads #aarrggbb).
  function hexColor(value) {
    var hex = String(value).slice(1)
    var alpha = hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1
    return Qt.rgba(parseInt(hex.slice(0, 2), 16) / 255, parseInt(hex.slice(2, 4), 16) / 255,
                   parseInt(hex.slice(4, 6), 16) / 255, alpha)
  }
  function colorValue(kind, value) {
    if (value === "accent") return root.tint(kind)
    if (String(value).indexOf("theme:") === 0) return root.themeColor(String(value).slice(6))
    if (/^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(String(value))) return root.hexColor(value)
    return null
  }
  // A part's color: set by the user (in the draft while arranging), else its
  // default; `fallback` where the default is "auto".
  function colorOf(kind, part, fallback) {
    var spot = root.draft[kind]
    var set = spot && spot.colors ? spot.colors[part] : undefined
    var value = set || (root.parts[kind] ? root.parts[kind][part] : undefined) || "accent"
    var color = value === "auto" ? null : root.colorValue(kind, value)
    return color === null ? (fallback !== undefined ? fallback : root.tint(kind)) : color
  }
  function hasColor(kind, part) {
    var spot = root.draft[kind]
    return !!(spot && spot.colors && spot.colors[part])
  }

  readonly property var weights: ({ light: 300, regular: 400, medium: 500, bold: 700, black: 900 })
  // A widget's text: font, weight, spacing and the outline (its effect).
  function textLook(kind) {
    var w = root.widget(kind)
    var weight = w ? (root.weights[w.font_weight] || 700) : 700
    var strength = w ? w.effect_strength / 100 : 0.35
    return {
      family: w && w.font_family ? w.font_family : root.fontFamily,
      weight: weight,
      lighter: Math.max(300, weight - 300),
      spacing: w ? w.letter_spacing : 0,
      outline: !!(w && w.effect === "outline" && strength > 0),
      outlineColor: root.colorOf(kind, "effect", Qt.rgba(0, 0, 0, strength))
    }
  }
  // Which layer a widget sits on: below or above the windows, with blur
  // behind its card or without.
  function groupOf(kind) {
    var w = root.widget(kind)
    if (!w) return "bottom"
    return (w.above ? "top" : "bottom") + (w.card && w.card_blur ? "-blur" : "")
  }

  function widget(kind) { return root.widgets ? (root.widgets[kind] || null) : null }
  function enabled(kind) { var w = root.widget(kind); return !!(w && w.enabled) }
  function onDesktop(kind) {
    var w = root.widget(kind)
    return !!(w && w.enabled && (kind !== "visualizer" || w.where !== "bar"))
  }
  // A widget's accent color (settings "color"; the gradient starts from the accent).
  function tint(kind) {
    var w = root.widget(kind)
    var name = w ? w.color : "accent"
    if (name === "foreground") return Color.foreground
    if (name === "white") return Qt.rgba(1, 1, 1, 1)
    return Color.accent
  }
  function inBar() {
    var w = root.widget("visualizer")
    return !!(w && w.enabled && w.where !== "desktop")
  }
  function placementsFromSettings() {
    var out = {}
    for (var kind in root.widgets) {
      var w = root.widgets[kind]
      out[kind] = { x: Number(w.x), y: Number(w.y), rotation: Number(w.rotation),
                    size: Number(w.size), width: Number(w.width || 0), colors: Object.assign({}, w.colors || {}),
                    same_place: w.same_place !== false, spots: JSON.parse(JSON.stringify(w.spots || {})) }
    }
    return out
  }
  // The place on a screen (sid: its id): the widget's own, or with
  // same_place off the screen's own spot once it has one.
  function placement(kind, sid) {
    var base = root.draft[kind] || { x: 0.5, y: 0.5, rotation: 0, size: { visualizer: 160, lyrics: 200 }[kind] || 100,
                                     width: 0, colors: {}, same_place: true, spots: {} }
    if (sid && base.same_place === false && base.spots && base.spots[sid]) return Object.assign({}, base, base.spots[sid])
    return base
  }
  function changePlacement(kind, changes, sid) {
    var next = Object.assign({}, root.draft)
    var base = Object.assign({}, root.placement(kind))
    if (sid && base.same_place === false) {
      var here = root.placement(kind, sid)
      var spots = Object.assign({}, base.spots || {})
      spots[sid] = Object.assign({ x: here.x, y: here.y, rotation: here.rotation, size: here.size, width: here.width }, changes)
      base.spots = spots
    } else {
      Object.assign(base, changes)
    }
    next[kind] = base
    root.draft = next
  }
  function setPlacement(kind, x, y, rotation, sid) {
    root.changePlacement(kind, { x: Math.max(0, Math.min(1, x)), y: Math.max(0, Math.min(1, y)), rotation: rotation }, sid)
  }
  function hasWidth(kind) { return !!(root.ranges[kind] && root.ranges[kind].width) }
  function clamp(value, range) { return range ? Math.max(range[0], Math.min(range[1], value)) : value }
  function setSize(kind, size, width, sid) {
    var range = root.ranges[kind] || {}
    root.changePlacement(kind, { size: Math.round(root.clamp(size, range.size)),
                                 width: width > 0 ? Math.round(root.clamp(width, range.width)) : 0 }, sid)
  }

  // hypr-screens' screen id: "make|model|serial", like config.screen_id().
  function screenId(screen) {
    var monitor = screen ? Hyprland.monitorFor(screen) : null
    var o = monitor ? monitor.lastIpcObject : null
    if (!o) return ""
    var parts = [String(o.make || "").trim(), String(o.model || "").trim(), String(o.serial || "").trim()]
    if (!parts[0] && !parts[1] && !parts[2]) parts = [String(o.description || o.name || "").trim()]
    return parts.join("|")
  }
  function screenMatches(kind, screen) {
    var w = root.widget(kind)
    if (!w || !screen) return false
    var mode = (w.monitors && w.monitors.mode) || "all"
    var internal = /^(eDP|LVDS|DSI)/.test(String(screen.name || ""))
    if (mode === "all") return true
    if (mode === "laptop") return internal
    if (mode === "external") return !internal
    return root.screenId(screen) === String(w.monitors.screen || "")
  }

  Component.onCompleted: {
    Hyprland.refreshMonitors()
    if (root.cavaWanted) cava.running = true
  }

  // --- visualizer: cava ------------------------------------------------------------

  // 0..1 per bar; all zero while it is quiet.
  property var levels: []
  property double lastFrame: 0
  property bool quiet: true
  readonly property bool cavaWanted: root.enabled("visualizer") && root.cavaConfig !== ""

  Process {
    id: cava
    command: ["setpriv", "--pdeathsig", "TERM", "cava", "-p", root.cavaConfig]
    running: false
    stdout: SplitParser { onRead: function(line) { root.takeFrame(line) } }
    onExited: if (root.cavaWanted) cavaRestart.restart()
  }
  onCavaWantedChanged: {
    if (cavaWanted) cava.running = true
    else { cava.running = false; root.levels = [] }
  }
  // Without cava (not installed yet) this retries quietly every ten seconds.
  Timer { id: cavaRestart; interval: 10000; onTriggered: if (root.cavaWanted) cava.running = true }

  function restartCava() {
    if (!root.cavaWanted) return
    cava.running = false
    cavaRestart.interval = 300
    cavaRestart.restart()
    cavaRestart.interval = 10000
  }

  function takeFrame(line) {
    var parts = String(line).split(";")
    var next = []
    var loud = false
    for (var i = 0; i < parts.length; i++) {
      if (parts[i] === "") continue
      var value = Math.max(0, Math.min(1, Number(parts[i]) / 1000))
      if (value > 0.02) loud = true
      next.push(value)
    }
    root.levels = next
    root.lastFrame = Date.now()
    if (loud) root.quiet = false
  }

  // cava stops printing while it sleeps: let the bars fall and fade out.
  Timer {
    interval: 500
    repeat: true
    running: root.cavaWanted
    onTriggered: {
      var stale = Date.now() - root.lastFrame > 1000
      var max = 0
      for (var i = 0; i < root.levels.length; i++) max = Math.max(max, root.levels[i])
      if (stale || max < 0.02) {
        if (stale && max > 0) root.levels = root.levels.map(function() { return 0 })
        root.quietSince = root.quietSince || Date.now()
        if (Date.now() - root.quietSince > 2000) root.quiet = true
      } else {
        root.quietSince = 0
      }
    }
  }
  property double quietSince: 0

  // --- lyrics: Mpris + lrclib ----------------------------------------------------------

  property var player: null
  property string trackKey: ""
  property var lyricLines: []        // [{t: seconds, text, words: [{t, text}] or null}]
  property int lyricIndex: -1
  property bool playing: false
  // The player's position and when it was read; songTime runs on from it
  // smoothly while words are highlighted.
  property real positionAt: 0
  property double positionStamp: 0
  property real songTime: 0
  property string lyricsState: "none"  // none | loading | synced | missing
  property var lyricsCache: ({})
  readonly property bool lyricsWanted: root.enabled("lyrics")

  // The player that plays; while none does, the one from before, else one
  // that looks like music (a track with an album) rather than a video.
  function pickPlayer() {
    var players = Mpris.players ? Mpris.players.values : []
    for (var i = 0; i < players.length; i++) {
      if (players[i].isPlaying) return players[i]
    }
    var music = null
    var any = null
    for (var j = 0; j < players.length; j++) {
      var p = players[j]
      if (p === root.player && p.trackTitle) return p
      if (!music && p.trackTitle && p.trackAlbum) music = p
      if (!any && p.trackTitle) any = p
    }
    return music || any
  }

  Timer {
    interval: 250
    repeat: true
    running: root.lyricsWanted
    onTriggered: {
      var next = root.pickPlayer()
      if (next !== root.player) root.player = next
      var p = root.player
      if (!p) { root.trackKey = ""; root.lyricLines = []; root.lyricsState = "none"; root.playing = false; return }
      var key = String(p.trackArtist || "") + "\u0001" + String(p.trackTitle || "")
      if (key !== root.trackKey) {
        root.trackKey = key
        root.lyricIndex = -1
        root.loadLyrics(p)
      }
      if (p.isPlaying) p.positionChanged()
      root.playing = !!p.isPlaying
      root.positionAt = Number(p.position || 0)
      root.positionStamp = Date.now()
      root.songTime = root.positionAt
      root.lyricIndex = root.lineAt(root.positionAt)
    }
  }

  readonly property bool wordsWanted: root.lyricsWanted && root.widget("lyrics") && root.widget("lyrics").highlight === "word"
  Timer {
    interval: 40
    repeat: true
    running: root.wordsWanted && root.playing && root.lyricLines.length > 0
    onTriggered: root.songTime = root.positionAt + (Date.now() - root.positionStamp) / 1000
  }

  function lineAt(seconds) {
    var lines = root.lyricLines
    var found = -1
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].t <= seconds + 0.25) found = i
      else break
    }
    return found
  }

  function parseSynced(text) {
    var out = []
    var rows = String(text || "").split("\n")
    for (var i = 0; i < rows.length; i++) {
      var match = rows[i].match(/^\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)$/)
      if (!match) continue
      var words = root.parseWords(match[3])
      var clean = match[3].replace(/<\d+:\d+(?:\.\d+)?>/g, " ").replace(/\s+/g, " ").trim()
      out.push({ t: Number(match[1]) * 60 + Number(match[2]), text: clean, words: words })
    }
    return out
  }

  // Enhanced LRC ("<00:12.34>word <00:12.80>word"): a time for each word.
  function parseWords(line) {
    if (!/<\d+:\d+(?:\.\d+)?>/.test(line)) return null
    var words = []
    var time = null
    var parts = String(line).split(/(<\d+:\d+(?:\.\d+)?>)/)
    for (var i = 0; i < parts.length; i++) {
      var tag = parts[i].match(/^<(\d+):(\d+(?:\.\d+)?)>$/)
      if (tag) { time = Number(tag[1]) * 60 + Number(tag[2]); continue }
      var pieces = parts[i].split(/\s+/)
      for (var j = 0; j < pieces.length; j++) {
        if (pieces[j] !== "" && time !== null) words.push({ t: time, text: pieces[j] })
      }
    }
    return words.length ? words : null
  }

  // The words of a line with the time each is sung: from the lyrics when they
  // have them, otherwise spread over the line by their length (the singing
  // takes about a tenth of a second a letter, at most most of the line).
  function wordsFor(index) {
    var line = root.lyricLines[index]
    if (!line) return []
    if (line.words) return line.words
    var words = String(line.text).split(/\s+/).filter(function(w) { return w !== "" })
    var next = index + 1 < root.lyricLines.length ? root.lyricLines[index + 1].t : line.t + 6
    var letters = 0
    for (var i = 0; i < words.length; i++) letters += words[i].length + 1
    var duration = Math.min((next - line.t) * 0.9, Math.max(1.2, letters * 0.1))
    var out = []
    var time = line.t
    for (var k = 0; k < words.length; k++) {
      out.push({ t: time, text: words[k] })
      time += duration * (words[k].length + 1) / letters
    }
    return out
  }

  function loadLyrics(p) {
    var title = String(p.trackTitle || "")
    var artist = String(p.trackArtist || "")
    if (!title) { root.lyricLines = []; root.lyricsState = "none"; return }
    var key = root.trackKey
    if (root.lyricsCache[key] !== undefined) {
      root.lyricLines = root.lyricsCache[key]
      root.lyricsState = root.lyricLines.length ? "synced" : "missing"
      return
    }
    root.lyricLines = []
    root.lyricsState = "loading"
    var query = "track_name=" + encodeURIComponent(title) + "&artist_name=" + encodeURIComponent(artist)
    if (p.trackAlbum) query += "&album_name=" + encodeURIComponent(String(p.trackAlbum))
    if (p.lengthSupported && p.length > 0) query += "&duration=" + Math.round(p.length)
    root.request("https://lrclib.net/api/get?" + query, key, function(data) {
      if (data && data.syncedLyrics) return root.parseSynced(data.syncedLyrics)
      return null
    }, function() {
      // No exact match (album or length differ): search by title and artist.
      root.request("https://lrclib.net/api/search?" + "track_name=" + encodeURIComponent(title)
                   + "&artist_name=" + encodeURIComponent(artist), key, function(list) {
        for (var i = 0; list && i < list.length; i++) {
          if (list[i].syncedLyrics) return root.parseSynced(list[i].syncedLyrics)
        }
        return []
      }, function() { root.storeLyrics(key, []) })
    })
  }

  function request(url, key, parse, otherwise) {
    var xhr = new XMLHttpRequest()
    xhr.onreadystatechange = function() {
      if (xhr.readyState !== XMLHttpRequest.DONE) return
      if (key !== root.trackKey) return
      var lines = null
      if (xhr.status === 200) {
        try { lines = parse(JSON.parse(xhr.responseText)) } catch (e) { lines = null }
      }
      if (lines === null) otherwise()
      else root.storeLyrics(key, lines)
    }
    xhr.open("GET", url)
    xhr.setRequestHeader("User-Agent", "hypr-screens (https://github.com/SlowlyTz/hypr-minimizer)")
    xhr.send()
  }

  function storeLyrics(key, lines) {
    var cache = Object.assign({}, root.lyricsCache)
    cache[key] = lines
    root.lyricsCache = cache
    if (key !== root.trackKey) return
    root.lyricLines = lines
    root.lyricsState = lines.length ? "synced" : "missing"
  }

  // --- clock -------------------------------------------------------------------------

  property date now: new Date()
  Timer {
    interval: 1000
    repeat: true
    running: root.enabled("clock")
    triggeredOnStart: true
    onTriggered: root.now = new Date()
  }

  // The second time zone's offset from UTC in minutes (from `date`, so
  // summer time is right); asked again every ten minutes.
  readonly property string zone: root.widget("clock") ? String(root.widget("clock").zone2 || "") : ""
  property int zoneOffset: 0
  property bool zoneKnown: false
  onZoneChanged: { root.zoneKnown = false; root.askZone() }
  // The command is set here: a binding on `zone` could still hold the old one.
  function askZone() {
    if (!root.zone || zoneProcess.running) return
    zoneProcess.command = ["sh", "-c", "TZ=\"$1\" date +%z", "sh", root.zone]
    zoneProcess.running = true
  }
  Process {
    id: zoneProcess
    stdout: StdioCollector {
      onStreamFinished: {
        var match = String(text).trim().match(/^([+-])(\d\d)(\d\d)$/)
        if (!match) return
        root.zoneOffset = (match[1] === "-" ? -1 : 1) * (Number(match[2]) * 60 + Number(match[3]))
        root.zoneKnown = true
      }
    }
  }
  Timer {
    interval: 600000
    repeat: true
    running: root.zone !== "" && root.enabled("clock")
    onTriggered: root.askZone()
  }
  function zoneTime(date) {
    return new Date(date.getTime() + (root.zoneOffset + date.getTimezoneOffset()) * 60000)
  }

  // --- system ----------------------------------------------------------------------------

  property real cpu: 0
  property real memory: 0
  property real temperature: 0
  property var cpuHistory: []
  property var memoryHistory: []
  property var temperatureHistory: []
  property var lastCpu: null

  Process {
    id: stats
    command: ["sh", "-c", "head -1 /proc/stat; grep -E '^(MemTotal|MemAvailable):' /proc/meminfo; cat \"$1\" 2>/dev/null || echo 0",
              "sh", root.cpuTemperatureFile || "/nonexistent"]
    stdout: StdioCollector { onStreamFinished: root.takeStats(text) }
  }
  Timer {
    interval: 2000
    repeat: true
    running: root.enabled("system")
    triggeredOnStart: true
    onTriggered: if (!stats.running) stats.running = true
  }

  function pushHistory(list, value) {
    var next = list.slice(Math.max(0, list.length - 59))
    next.push(value)
    return next
  }

  function takeStats(text) {
    var lines = String(text).split("\n")
    var fields = (lines[0] || "").trim().split(/\s+/).slice(1).map(Number)
    if (fields.length >= 4) {
      var idle = fields[3] + (fields[4] || 0)
      var total = 0
      for (var i = 0; i < fields.length; i++) total += fields[i]
      if (root.lastCpu) {
        var dt = total - root.lastCpu.total
        root.cpu = dt > 0 ? Math.max(0, Math.min(1, 1 - (idle - root.lastCpu.idle) / dt)) : 0
      }
      root.lastCpu = { total: total, idle: idle }
    }
    var memTotal = 0, memAvailable = 0
    for (var j = 1; j < lines.length; j++) {
      var m = lines[j].match(/^(MemTotal|MemAvailable):\s+(\d+)/)
      if (m && m[1] === "MemTotal") memTotal = Number(m[2])
      if (m && m[1] === "MemAvailable") memAvailable = Number(m[2])
    }
    if (memTotal > 0) root.memory = 1 - memAvailable / memTotal
    var last = Number((lines[lines.length - 1] || lines[lines.length - 2] || "0").trim())
    root.temperature = last > 1000 ? last / 1000 : last
    root.cpuHistory = root.pushHistory(root.cpuHistory, root.cpu)
    root.memoryHistory = root.pushHistory(root.memoryHistory, root.memory)
    root.temperatureHistory = root.pushHistory(root.temperatureHistory, Math.min(1, root.temperature / 100))
  }

  // --- the layers -----------------------------------------------------------------------

  // Is the widget on this screen, and (without a group: on any layer, as while
  // arranging) in this group and allowed by its rules right now?
  function shows(kind, screen, group) {
    return root.onDesktop(kind) && root.screenMatches(kind, screen)
           && (!group || (root.groupOf(kind) === group && root.allowedNow(kind, screen)))
  }
  // Its rules: only on some desktops (workspace ids, 99 the fixed screen),
  // only while the desktop has no window, not on battery.
  function allowedNow(kind, screen) {
    var w = root.widget(kind)
    if (!w) return false
    if (w.hide_on_battery && UPower.onBattery) return false
    var monitor = screen ? Hyprland.monitorFor(screen) : null
    var workspace = monitor ? monitor.activeWorkspace : null
    if (w.desktops && w.desktops.length && (!workspace || w.desktops.indexOf(workspace.id) < 0)) return false
    if (w.only_empty && workspace && workspace.toplevels && workspace.toplevels.values.length > 0) return false
    return true
  }
  function anyOn(screen, group) {
    for (var i = 0; i < root.kinds.length; i++) {
      if (root.shows(root.kinds[i], screen, group)) return true
    }
    return false
  }

  // Each widget's view; a view has `service` and `editing`.
  Component { id: visualizerView; VisualizerView { service: root } }
  Component { id: lyricsView; LyricsView { service: root } }
  Component { id: clockView; ClockView { service: root } }
  Component { id: systemView; SystemView { service: root } }
  readonly property var views: ({ visualizer: visualizerView, lyrics: lyricsView, clock: clockView, system: systemView })

  // --- arranging ------------------------------------------------------------------------

  function startEditing() {
    Hyprland.refreshMonitors()
    root.draft = root.placementsFromSettings()
    root.editing = true
  }
  function cancelEditing() {
    root.draft = root.placementsFromSettings()
    root.editing = false
  }
  function saveEditing() {
    if (saver.running) return
    saver.command = ["hypr-screens", "widgets", "save", JSON.stringify(root.draft)]
    saver.running = true
  }
  Process {
    id: saver
    // The settings file changes with it and brings the saved places back in.
    onExited: root.editing = false
  }

  // One screen's layer. `group`: "bottom" (behind the windows) or "top"
  // (above them), each with "-blur" for widgets with a blurred card (Hyprland
  // blurs that layer, see the layer rule in hypr_screens.lua). The edit layer
  // holds every widget.
  component Layer: PanelWindow {
    id: panel
    required property var modelData
    property bool editLayer: false
    property string group: "bottom"
    readonly property var hyprMonitor: Hyprland.monitorFor(modelData)
    readonly property bool fullscreen: !!(hyprMonitor && hyprMonitor.activeWorkspace && hyprMonitor.activeWorkspace.hasFullscreen)
    screen: modelData
    visible: root.anyOn(modelData, editLayer ? "" : group) && (editLayer ? root.editing : (!root.editing && !fullscreen))
             && !remap.remapping
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.namespace: editLayer ? "hypr-screens-widgets-edit"
                             : "hypr-screens-widgets" + (group === "bottom" ? "" : "-" + group)
    WlrLayershell.layer: editLayer ? WlrLayer.Overlay : (group.indexOf("top") === 0 ? WlrLayer.Top : WlrLayer.Bottom)
    // While arranging, Esc must reach it; otherwise it never takes the keyboard.
    WlrLayershell.keyboardFocus: editLayer ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None
    // Clicks go through, except while arranging.
    mask: editLayer ? allInput : noInput
    onVisibleChanged: if (visible && editLayer) canvas.forceActiveFocus()
    Region { id: noInput }
    Region { id: allInput; item: canvas }
    ScreenMoveRemap { id: remap; window: panel }

    Item {
      id: canvas
      anchors.fill: parent
      focus: panel.editLayer
      Keys.onEscapePressed: root.cancelEditing()
      Keys.onReturnPressed: root.saveEditing()

      // An empty desktop to arrange on: the wallpaper, over all windows.
      Image {
        anchors.fill: parent
        visible: panel.editLayer
        source: panel.editLayer ? "file://" + root.wallpaper : ""
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        cache: false
      }
      Rectangle {
        anchors.fill: parent
        visible: panel.editLayer
        color: Qt.rgba(0, 0, 0, 0.15)
      }

      Rectangle {
        id: toolbar
        visible: panel.editLayer
        z: 10
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: Style.space(60)
        radius: Style.space(12)
        color: Qt.rgba(0, 0, 0, 0.7)
        border.color: Color.accent
        border.width: 1
        implicitWidth: bar.implicitWidth + Style.space(24)
        implicitHeight: bar.implicitHeight + Style.space(16)

        Row {
          id: bar
          anchors.centerIn: parent
          spacing: Style.space(16)

          Text {
            anchors.verticalCenter: parent.verticalCenter
            text: root.texts.hint || "Drag the widgets  ·  scroll to turn (Shift: fine)"
            color: "white"
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }
          ToolButton { label: root.texts.cancel || "Cancel"; onClicked: root.cancelEditing() }
          ToolButton { label: root.texts.save || "Save"; primary: true; onClicked: root.saveEditing() }
        }
      }

      Repeater {
        model: root.kinds
        Placed {
          id: placed
          required property string modelData
          service: root
          kind: modelData
          screenKey: root.screenId(panel.modelData)
          editable: panel.editLayer
          visible: root.shows(kind, panel.modelData, panel.editLayer ? "" : panel.group)
          Loader {
            id: view
            active: placed.visible
            sourceComponent: root.views[placed.kind] || null
          }
          Binding { target: view.item; property: "editing"; value: panel.editLayer; when: view.item !== null }
          Binding { target: view.item; property: "spot"; value: placed.spot; when: view.item !== null }
        }
      }
    }
  }

  component ToolButton: Rectangle {
    id: button
    property string label: ""
    property bool primary: false
    signal clicked()
    anchors.verticalCenter: parent ? parent.verticalCenter : undefined
    radius: Style.space(8)
    color: primary ? Color.accent : (area.containsMouse ? Qt.rgba(1, 1, 1, 0.15) : Qt.rgba(1, 1, 1, 0.08))
    implicitWidth: text.implicitWidth + Style.space(28)
    implicitHeight: text.implicitHeight + Style.space(14)
    Text {
      id: text
      anchors.centerIn: parent
      text: button.label
      color: button.primary ? Color.background : "white"
      font.family: root.fontFamily
      font.pixelSize: Style.font.body
      font.bold: true
    }
    MouseArea {
      id: area
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: button.clicked()
    }
  }

  Variants {
    model: Quickshell.screens
    Layer { group: "bottom" }
  }
  Variants {
    model: Quickshell.screens
    Layer { group: "bottom-blur" }
  }
  Variants {
    model: Quickshell.screens
    Layer { group: "top" }
  }
  Variants {
    model: Quickshell.screens
    Layer { group: "top-blur" }
  }
  Variants {
    model: Quickshell.screens
    Layer { editLayer: true }
  }

  // --- IPC: omarchy-shell hypr-screens.widgets <function> ------------------------------

  IpcHandler {
    target: "hypr-screens.widgets"

    function edit(): string {
      root.startEditing()
      return "ok"
    }
    function editing(): string { return root.editing ? "yes" : "no" }
    function placements(): string { return JSON.stringify(root.draft) }
    function done(): void { root.editing = false }
    function cancel(): void { root.cancelEditing() }
    function reload(): void { settingsFile.reload() }
  }
}
