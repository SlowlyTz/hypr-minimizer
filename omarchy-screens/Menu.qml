import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import qs.Commons
import qs.Ui

// Screens menu for hypr-screens. Keyboard only.
//
// Summoned by `hypr-screens menu` with { "command": [argv prefix] }. The menu
// asks `<command> state` for everything it shows; every change runs another
// `<command> ...` that prints the new state, so the menu never keeps its own
// copy of the settings.
//
// Pages: screens (list) -> screen (its settings); Tab switches to keys & options.
Item {
  id: root

  property var shell: null
  property var manifest: null

  property bool opened: false
  property var command: []
  property var data: ({ screens: [], keybinds: [], options: [], status: {}, message: "" })
  property string page: "screens"       // screens | screen | app
  property int screenIndex: 0
  property int settingIndex: 0
  property int appIndex: 0
  property int slotIndex: 0
  property string forgetArmed: ""
  property bool recording: false
  property var queue: []

  readonly property var screens: root.data.screens || []
  readonly property var current: root.screens.length > 0 ? root.screens[Math.min(root.screenIndex, root.screens.length - 1)] : null
  readonly property var settings: root.current ? root.current.settings : []
  readonly property var appRows: {
    var rows = []
    var binds = root.data.keybinds || []
    for (var i = 0; i < binds.length; i++) rows.push({ kind: "key", action: binds[i].action, label: binds[i].label, keys: binds[i].keys })
    var options = root.data.options || []
    for (var j = 0; j < options.length; j++) rows.push({ kind: "option", key: options[j].key, label: options[j].label, value: options[j].value })
    return rows
  }

  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property var borderSpec: Border.surfaceSpec("menu", "border", Color.menu.border, Math.max(1, Style.space(2)))
  property color scrim: Color.menu.scrim
  property color selectedBackground: Color.menu.selectedBackground
  property color selectedText: Color.menu.selectedText
  readonly property int cornerRadius: Style.cornerRadius
  property string fontFamily: Style.font.menuFamily
  property int rowHeight: Math.max(Style.space(48), Style.font.body + Style.font.caption + Style.spacing.rowPaddingX * 2)
  property int cardWidth: Math.min(Style.space(640), panel.width - Style.gapsOut * 2)
  property int cardHeight: Math.min(Style.space(620), panel.height - Style.gapsOut * 2)

  // --- talking to hypr-screens -------------------------------------------------------

  function run(args) {
    if (!root.command || root.command.length === 0) return
    root.queue = root.queue.concat([root.command.concat(args)])
    root.pump()
  }

  function pump() {
    if (runner.running || root.queue.length === 0) return
    runner.command = root.queue[0]
    root.queue = root.queue.slice(1)
    runner.running = true
  }

  function applyState(text) {
    try {
      var parsed = JSON.parse(String(text || ""))
      if (parsed && parsed.screens) root.data = parsed
    } catch (error) {
      root.data = Object.assign({}, root.data, { message: "error: " + String(text || error).slice(0, 200) })
    }
    root.screenIndex = Math.max(0, Math.min(root.screenIndex, root.screens.length - 1))
    root.settingIndex = Math.max(0, Math.min(root.settingIndex, root.settings.length - 1))
    root.appIndex = Math.max(0, Math.min(root.appIndex, root.appRows.length - 1))
  }

  Process {
    id: runner
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.applyState(text)
    }
    onExited: root.pump()
  }

  // --- recording a shortcut ------------------------------------------------------------
  //
  // While recording, Hyprland switches to an empty keymap (defined in the
  // generated Lua file), so combos that are already bound reach us instead of
  // firing. Escape in that keymap drops back to the normal one; we notice by
  // polling, and every other way out resets it too.

  function startRecording() {
    root.recording = true
    Quickshell.execDetached(["hyprctl", "dispatch", 'hl.dsp.submap("' + (root.data.recordSubmap || "hypr-screens-record") + '")'])
    recordTimeout.restart()
    submapPoll.start()
  }

  function stopRecording() {
    if (!root.recording) return
    root.recording = false
    recordTimeout.stop()
    submapPoll.stop()
    Quickshell.execDetached(["hyprctl", "dispatch", 'hl.dsp.submap("reset")'])
  }

  Timer { id: recordTimeout; interval: 10000; onTriggered: root.stopRecording() }

  Timer {
    id: submapPoll
    interval: 300
    repeat: true
    onTriggered: submapProc.running = true
  }

  Process {
    id: submapProc
    command: ["hyprctl", "submap"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: if (root.recording && String(text).trim() === "default") root.stopRecording()
    }
  }

  function keyName(event) {
    var key = event.key
    if (key >= Qt.Key_A && key <= Qt.Key_Z) return String.fromCharCode(key)
    if (key >= Qt.Key_F1 && key <= Qt.Key_F35) return "F" + (key - Qt.Key_F1 + 1)
    if (key >= Qt.Key_0 && key <= Qt.Key_9 && !(event.modifiers & Qt.ShiftModifier)) return String.fromCharCode(key)
    var names = {}
    names[Qt.Key_Period] = "PERIOD"; names[Qt.Key_Comma] = "COMMA"; names[Qt.Key_Minus] = "MINUS"
    names[Qt.Key_Space] = "SPACE"; names[Qt.Key_Return] = "RETURN"; names[Qt.Key_Enter] = "RETURN"
    names[Qt.Key_Tab] = "TAB"; names[Qt.Key_Backtab] = "TAB"; names[Qt.Key_Backspace] = "BACKSPACE"
    names[Qt.Key_Delete] = "DELETE"; names[Qt.Key_Insert] = "INSERT"; names[Qt.Key_Home] = "HOME"
    names[Qt.Key_End] = "END"; names[Qt.Key_PageUp] = "PRIOR"; names[Qt.Key_PageDown] = "NEXT"
    names[Qt.Key_Left] = "LEFT"; names[Qt.Key_Right] = "RIGHT"; names[Qt.Key_Up] = "UP"; names[Qt.Key_Down] = "DOWN"
    names[Qt.Key_Print] = "PRINT"
    if (names[key] !== undefined) return names[key]
    // Shifted symbols and layout-specific keys: bind the physical key.
    return event.nativeScanCode > 0 ? "code:" + event.nativeScanCode : ""
  }

  function recordKey(event) {
    var modifierKeys = [Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_Super_L, Qt.Key_Super_R, Qt.Key_AltGr, Qt.Key_Hyper_L, Qt.Key_Hyper_R]
    if (modifierKeys.indexOf(event.key) !== -1) return
    var name = root.keyName(event)
    if (!name) return
    var mods = []
    if (event.modifiers & Qt.MetaModifier) mods.push("SUPER")
    if (event.modifiers & Qt.ControlModifier) mods.push("CTRL")
    if (event.modifiers & Qt.AltModifier) mods.push("ALT")
    if (event.modifiers & Qt.ShiftModifier) mods.push("SHIFT")
    var row = root.appRows[root.appIndex]
    root.stopRecording()
    if (row && row.kind === "key") root.run(["bind", row.action, String(root.slotIndex + 1), mods.concat([name]).join(" + ")])
  }

  // --- open / close ------------------------------------------------------------------------

  function open(payloadJson) {
    var payload = {}
    try { payload = JSON.parse(payloadJson || "{}") } catch (error) { payload = {} }
    root.command = Array.isArray(payload.command) ? payload.command : ["hypr-screens"]
    root.page = "screens"
    root.forgetArmed = ""
    root.opened = true
    root.run(["state"])
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.stopRecording()
    root.opened = false
  }

  function dismiss() {
    root.close()
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide((root.manifest && root.manifest.id) || "hypr-screens.menu")
  }

  // --- keys ------------------------------------------------------------------------------------

  function clampIndex(index, count) { return count <= 0 ? 0 : (index + count) % count }

  function handleKey(event) {
    if (root.recording) { root.recordKey(event); return }
    var key = event.key
    var text = String(event.text || "").toLowerCase()

    if (key === Qt.Key_Tab || key === Qt.Key_Backtab) {
      root.page = root.page === "app" ? "screens" : "app"
      return
    }

    if (root.page === "screens") {
      if (key === Qt.Key_Escape) root.dismiss()
      else if (key === Qt.Key_Up) root.screenIndex = root.clampIndex(root.screenIndex - 1, root.screens.length)
      else if (key === Qt.Key_Down) root.screenIndex = root.clampIndex(root.screenIndex + 1, root.screens.length)
      else if ((key === Qt.Key_Return || key === Qt.Key_Enter) && root.current) { root.settingIndex = 0; root.page = "screen" }
      else if (text === "f" && root.current) root.run(["favorite", root.current.id])
      else if (text === "s") root.run(["swap"])
      else if (text === "x" && root.current) {
        if (root.forgetArmed === root.current.id) { root.forgetArmed = ""; root.run(["forget", root.current.id]) }
        else root.forgetArmed = root.current.id
        return
      }
      root.forgetArmed = ""
      screenList.positionViewAtIndex(root.screenIndex, ListView.Contain)
      return
    }

    if (root.page === "screen") {
      var setting = root.settings[root.settingIndex]
      if (key === Qt.Key_Escape || key === Qt.Key_Backspace) root.page = "screens"
      else if (key === Qt.Key_Up) root.settingIndex = root.clampIndex(root.settingIndex - 1, root.settings.length)
      else if (key === Qt.Key_Down) root.settingIndex = root.clampIndex(root.settingIndex + 1, root.settings.length)
      else if ((key === Qt.Key_Left || key === Qt.Key_Right) && setting)
        root.run(["step", root.current.id, setting.key, key === Qt.Key_Right ? "1" : "-1"])
      else if (text === "c" && setting)
        root.run(["step", root.current.id, setting.key, (event.modifiers & Qt.ShiftModifier) ? "-1" : "1", "--condition"])
      return
    }

    // app page
    var row = root.appRows[root.appIndex]
    if (key === Qt.Key_Escape) root.page = "screens"
    else if (key === Qt.Key_Up) root.appIndex = root.clampIndex(root.appIndex - 1, root.appRows.length)
    else if (key === Qt.Key_Down) root.appIndex = root.clampIndex(root.appIndex + 1, root.appRows.length)
    else if (row && row.kind === "key") {
      if (key === Qt.Key_Left || key === Qt.Key_Right) root.slotIndex = key === Qt.Key_Right ? 1 : 0
      else if (key === Qt.Key_Return || key === Qt.Key_Enter) root.startRecording()
      else if (key === Qt.Key_Delete || key === Qt.Key_Backspace) root.run(["bind", row.action, String(root.slotIndex + 1), ""])
    } else if (row && row.kind === "option") {
      if (key === Qt.Key_Left || key === Qt.Key_Right || key === Qt.Key_Return || key === Qt.Key_Enter)
        root.run(["option", row.key, key === Qt.Key_Left ? "prev" : "next"])
    }
    appList.positionViewAtIndex(root.appIndex, ListView.Contain)
  }

  readonly property string footer: {
    if (root.recording) return "Press the new shortcut…     Esc  cancel"
    if (root.page === "screens")
      return root.forgetArmed ? "x  again to forget     any other key  keep" :
        "Enter  settings   f  favorite   x  forget   s  swap fixed   Tab  keys   Esc  close"
    if (root.page === "screen") return "←→  change   c  condition   ↑↓  select   Esc  back"
    return "←→  slot / value   Enter  record   Del  clear   Tab  screens   Esc  back"
  }

  function iconFor(screen) {
    var names = screen && screen.internal ? ["computer-laptop", "computer"] : ["video-display", "display", "computer"]
    for (var i = 0; i < names.length; i++) {
      var path = Quickshell.iconPath(names[i], true)
      if (path) return path
    }
    return ""
  }

  readonly property string statusLine: {
    var status = root.data.status || {}
    if (!status.external) return "No external screen connected"
    if (!status.fixed) return "No fixed screen: desktops on both screens"
    return "One desktop on " + (status.fixed === "panel" ? "the laptop" : "the external screen") +
      (status.swapped ? " (swapped until unplugged)" : "")
  }

  // --- view ------------------------------------------------------------------------------------

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "hypr-screens-menu"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle { anchors.fill: parent; color: root.scrim }
    MouseArea { anchors.fill: parent; onClicked: root.dismiss() }

    BorderSurface {
      id: card
      width: root.cardWidth
      height: root.cardHeight
      radius: root.cornerRadius
      anchors.centerIn: parent
      color: root.background
      borderSpec: root.borderSpec
      padding: Style.spacing.panelPadding

      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          root.handleKey(event)
          event.accepted = true
        }
      }

      Column {
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset
        spacing: Style.spacing.md

        // Header: title left, pages right.
        Item {
          width: parent.width
          height: Style.font.heading + Style.space(12)

          Text {
            anchors.left: parent.left
            anchors.right: tabs.left
            anchors.rightMargin: Style.space(12)
            anchors.verticalCenter: parent.verticalCenter
            textFormat: Text.PlainText
            text: root.page === "screen" && root.current ? root.current.name : (root.page === "app" ? "Keys & options" : "Screens")
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            elide: Text.ElideRight
          }

          Row {
            id: tabs
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(12)
            Repeater {
              model: [["Screens", "screens"], ["Keys & options", "app"]]
              Text {
                required property var modelData
                readonly property bool active: modelData[1] === "app" ? root.page === "app" : root.page !== "app"
                textFormat: Text.PlainText
                text: modelData[0]
                color: root.foreground
                opacity: active ? 1 : 0.45
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: active
              }
            }
          }
        }

        Text {
          width: parent.width
          textFormat: Text.PlainText
          text: root.page === "screen" && root.current
            ? (root.current.connected ? root.current.connector + " · connected" : "not connected") + (root.current.description ? " · " + root.current.description : "")
            : root.statusLine
          color: root.foreground
          opacity: 0.58
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }

        Item {
          id: body
          width: parent.width
          height: parent.height - y - footerText.height - messageText.height - Style.spacing.md * 2

          // Screens -----------------------------------------------------------------
          ListView {
            id: screenList
            anchors.fill: parent
            visible: root.page === "screens"
            model: root.screens
            clip: true
            spacing: Style.spacing.xs
            boundsBehavior: Flickable.StopAtBounds
            section.property: "section"
            section.delegate: Text {
              required property string section
              width: ListView.view.width
              height: Style.font.caption + Style.space(14)
              verticalAlignment: Text.AlignBottom
              textFormat: Text.PlainText
              text: section
              color: root.foreground
              opacity: 0.45
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
            }

            delegate: Rectangle {
              id: screenRow
              required property int index
              required property var modelData
              readonly property bool hasCursor: index === root.screenIndex
              width: ListView.view.width
              height: root.rowHeight
              radius: root.cornerRadius
              color: hasCursor ? root.selectedBackground : "transparent"

              Image {
                id: screenIcon
                width: Style.font.iconLarge
                height: Style.font.iconLarge
                sourceSize.width: width * Screen.devicePixelRatio
                sourceSize.height: height * Screen.devicePixelRatio
                source: root.iconFor(screenRow.modelData)
                anchors.left: parent.left
                anchors.leftMargin: Style.space(10)
                anchors.verticalCenter: parent.verticalCenter
                opacity: screenRow.modelData.connected ? 1 : 0.45
              }

              Column {
                anchors.left: screenIcon.right
                anchors.leftMargin: Style.space(12)
                anchors.right: marks.left
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(2)
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: screenRow.modelData.name
                  color: screenRow.hasCursor ? root.selectedText : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  elide: Text.ElideRight
                }
                Text {
                  width: parent.width
                  textFormat: Text.PlainText
                  text: (screenRow.modelData.connected ? screenRow.modelData.connector : "not connected") +
                    (screenRow.modelData.summary ? " · " + screenRow.modelData.summary : "")
                  color: root.foreground
                  opacity: 0.58
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideRight
                }
              }

              Text {
                id: marks
                anchors.right: parent.right
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                textFormat: Text.PlainText
                text: (root.forgetArmed === screenRow.modelData.id ? "forget?  " : "") +
                  (screenRow.modelData.favorite ? "★  " : "") + (screenRow.modelData.connected ? "●" : "○")
                color: root.foreground
                opacity: 0.7
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
              }
            }
          }

          // One screen's settings ------------------------------------------------------
          ListView {
            id: settingList
            anchors.fill: parent
            visible: root.page === "screen"
            model: root.settings
            clip: true
            spacing: Style.spacing.xs
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
              id: settingRow
              required property int index
              required property var modelData
              readonly property bool hasCursor: index === root.settingIndex
              width: ListView.view.width
              height: root.rowHeight
              radius: root.cornerRadius
              color: hasCursor ? root.selectedBackground : "transparent"

              Text {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(14)
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * 0.3
                textFormat: Text.PlainText
                text: settingRow.modelData.label
                color: settingRow.hasCursor ? root.selectedText : root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
              }

              Column {
                anchors.right: parent.right
                anchors.rightMargin: Style.space(14)
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * 0.6
                spacing: Style.space(2)
                Text {
                  width: parent.width
                  horizontalAlignment: Text.AlignRight
                  textFormat: Text.PlainText
                  text: (settingRow.hasCursor ? "‹  " : "") + settingRow.modelData.value + (settingRow.hasCursor ? "  ›" : "")
                  color: settingRow.hasCursor ? root.selectedText : root.foreground
                  opacity: settingRow.modelData.set ? 1 : 0.58
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  elide: Text.ElideLeft
                }
                Text {
                  width: parent.width
                  horizontalAlignment: Text.AlignRight
                  visible: settingRow.modelData.set
                  textFormat: Text.PlainText
                  text: settingRow.modelData.when + (settingRow.modelData.active ? "" : "  (not now)")
                  color: root.foreground
                  opacity: 0.58
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideLeft
                }
              }
            }
          }

          // Keys & options ----------------------------------------------------------------
          ListView {
            id: appList
            anchors.fill: parent
            visible: root.page === "app"
            model: root.appRows
            clip: true
            spacing: Style.spacing.xs
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
              id: appRow
              required property int index
              required property var modelData
              readonly property bool hasCursor: index === root.appIndex
              width: ListView.view.width
              height: Math.round(root.rowHeight * 0.8)
              radius: root.cornerRadius
              color: hasCursor ? root.selectedBackground : "transparent"

              Text {
                anchors.left: parent.left
                anchors.leftMargin: Style.space(14)
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * 0.36
                textFormat: Text.PlainText
                text: appRow.modelData.label
                color: appRow.hasCursor ? root.selectedText : root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                elide: Text.ElideRight
              }

              Row {
                anchors.right: parent.right
                anchors.rightMargin: Style.space(14)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(10)
                visible: appRow.modelData.kind === "key"
                Repeater {
                  model: 2
                  Rectangle {
                    required property int index
                    readonly property bool picked: appRow.hasCursor && root.slotIndex === index
                    width: Style.space(170)
                    height: slotText.implicitHeight + Style.space(8)
                    radius: root.cornerRadius
                    color: "transparent"
                    border.width: picked ? 1 : 0
                    border.color: root.foreground
                    Text {
                      id: slotText
                      anchors.centerIn: parent
                      width: parent.width - Style.space(8)
                      horizontalAlignment: Text.AlignHCenter
                      textFormat: Text.PlainText
                      text: picked && root.recording ? "press keys…" :
                        ((appRow.modelData.keys && appRow.modelData.keys[index]) || "—")
                      color: appRow.hasCursor ? root.selectedText : root.foreground
                      opacity: (appRow.modelData.keys && appRow.modelData.keys[index]) || picked ? 1 : 0.45
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.caption
                      elide: Text.ElideMiddle
                    }
                  }
                }
              }

              Text {
                anchors.right: parent.right
                anchors.rightMargin: Style.space(14)
                anchors.verticalCenter: parent.verticalCenter
                visible: appRow.modelData.kind === "option"
                textFormat: Text.PlainText
                text: (appRow.hasCursor ? "‹  " : "") + (appRow.modelData.value || "") + (appRow.hasCursor ? "  ›" : "")
                color: appRow.hasCursor ? root.selectedText : root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
              }
            }
          }
        }

        Text {
          id: messageText
          width: parent.width
          visible: text.length > 0
          height: visible ? implicitHeight : 0
          textFormat: Text.PlainText
          text: String(root.data.message || "")
          color: root.foreground
          opacity: 0.8
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.Wrap
        }

        Text {
          id: footerText
          width: parent.width
          textFormat: Text.PlainText
          text: root.footer
          color: root.foreground
          opacity: 0.45
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          horizontalAlignment: Text.AlignHCenter
          elide: Text.ElideRight
        }
      }
    }
  }
}
