import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick
import qs.Commons
import qs.Ui

// Minimized-window picker for hypr-minimizer.
//
// Summoned by `hypr-minimizer menu` with a JSON payload:
//   { "prompt": "...", "selectionFile": "...", "doneFile": "...",
//     "entries": [{ "address", "name", "detail", "icon", "windowClass", "workspace" }],
//     "monitors": { "panel", "external", "description", "fixed" } }   (optional)
// Enter writes "origin<TAB><address>" to selectionFile, Shift+Enter writes
// "here<TAB><address>", "-" writes "peek<TAB><address>"; cancelling writes
// nothing. doneFile is touched last.
//
// With "monitors", Right/Left switch to a second page that picks the screen
// keeping a single desktop; Enter there writes "fixed<TAB>panel|external".
Item {
  id: root

  property var shell: null
  property var manifest: null

  property bool opened: false
  property string prompt: "Minimized windows"
  property string filterText: ""
  property int selectedIndex: 0
  property var entries: []
  property string selectionFile: ""
  property string doneFile: ""
  property var monitors: null
  property int page: 0            // 0 = windows, 1 = monitors
  property int monitorIndex: 0
  readonly property bool hasMonitorPage: root.monitors !== null

  // Shares the [menu] surface tokens so themes style it like the Omarchy menu.
  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color border: Color.menu.border
  property var borderSpec: Border.surfaceSpec("menu", "border", border, Math.max(1, Style.space(2)))
  property color scrim: Color.menu.scrim
  property color selectedBackground: Color.menu.selectedBackground
  property color selectedText: Color.menu.selectedText
  readonly property int cornerRadius: Style.cornerRadius
  property string fontFamily: Style.font.menuFamily
  property int contentMargin: Style.spacing.panelPadding
  property int contentSpacing: Style.spacing.md
  property int headerHeight: Math.max(Style.space(34), Style.font.title + Style.spacing.controlPaddingY * 2)
  property int footerHeight: Style.font.caption + Style.space(6)
  property int rowHeight: Math.max(Style.space(52), Style.font.body + Style.font.caption + Style.spacing.rowPaddingX * 2)
  property int rowSpacing: Style.spacing.xs
  property int iconSize: Math.round(Style.font.iconLarge * 1.5)
  property int cardWidth: Math.min(Style.space(520), panel.width - Style.gapsOut * 2)
  // Sized for the longer page so switching pages does not resize the card.
  property int listHeight: Math.max(1, displayModel.count, monitorModel.count) * (rowHeight + rowSpacing)
  property int cardHeight: Math.min(
    contentMargin * 2 + headerHeight + contentSpacing + listHeight + contentSpacing + footerHeight,
    panel.height - Style.gapsOut * 2)

  function open(payloadJson) {
    var payload = {}
    try { payload = JSON.parse(payloadJson || "{}") } catch (error) { payload = {} }

    // A new summon replaces an unanswered one; release its caller first.
    root.finish(null)

    root.prompt = String(payload.prompt || "Minimized windows")
    root.entries = Array.isArray(payload.entries) ? payload.entries : []
    root.selectionFile = String(payload.selectionFile || "")
    root.doneFile = String(payload.doneFile || "")
    root.monitors = payload.monitors && payload.monitors.external ? payload.monitors : null
    root.filterText = ""
    root.selectedIndex = 0
    root.page = 0
    root.rebuildDisplay()
    root.rebuildMonitors()
    root.opened = true
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  function close() {
    root.finish(null)
    root.opened = false
  }

  function dismiss(selection) {
    root.finish(selection)
    root.opened = false
    if (root.shell && typeof root.shell.hide === "function")
      root.shell.hide((root.manifest && root.manifest.id) || "hypr-minimizer.picker")
  }

  function finish(selection) {
    if (!root.doneFile) return

    var done = Util.shellQuote(root.doneFile)
    var command = ": > " + done
    if (selection && root.selectionFile)
      command = "printf '%s\\n' " + Util.shellQuote(selection) + " > " + Util.shellQuote(root.selectionFile) + "; " + command

    root.selectionFile = ""
    root.doneFile = ""
    Quickshell.execDetached(["bash", "-c", command])
  }

  function iconSource(entry) {
    var icon = String(entry.icon || "")
    if (icon.charAt(0) === "/") return Util.fileUrl(icon)
    var themed = icon ? Quickshell.iconPath(icon, true) : ""
    if (themed) return themed

    var desktopEntry = DesktopEntries.heuristicLookup(String(entry.windowClass || ""))
    var desktopIcon = desktopEntry ? String(desktopEntry.icon || "") : ""
    if (desktopIcon.charAt(0) === "/") return Util.fileUrl(desktopIcon)
    themed = desktopIcon ? Quickshell.iconPath(desktopIcon, true) : ""
    if (themed) return themed

    return Quickshell.iconPath("application-x-executable", true)
  }

  function matches(entry, needle) {
    if (!needle) return true
    var haystack = (String(entry.name || "") + " " + String(entry.detail || "")).toLowerCase()
    return haystack.indexOf(needle) !== -1
  }

  function rebuildDisplay() {
    var needle = root.filterText.toLowerCase()
    displayModel.clear()
    for (var i = 0; i < root.entries.length; i++) {
      var entry = root.entries[i]
      if (!root.matches(entry, needle)) continue
      displayModel.append({
        address: String(entry.address || ""),
        name: String(entry.name || ""),
        detail: String(entry.detail || ""),
        workspace: String(entry.workspace || ""),
        iconUrl: root.iconSource(entry)
      })
    }
    root.selectedIndex = Math.max(0, Math.min(root.selectedIndex, displayModel.count - 1))
  }

  function themedIcon(names) {
    for (var i = 0; i < names.length; i++) {
      var path = Quickshell.iconPath(names[i], true)
      if (path) return path
    }
    return Quickshell.iconPath("application-x-executable", true)
  }

  function rebuildMonitors() {
    monitorModel.clear()
    if (!root.hasMonitorPage) return

    var fixed = String(root.monitors.fixed || "")
    monitorModel.append({
      role: "panel",
      name: "Laptop",
      detail: String(root.monitors.panel || ""),
      iconUrl: root.themedIcon(["computer-laptop", "computer"]),
      current: fixed === "panel"
    })
    monitorModel.append({
      role: "external",
      name: "External monitor",
      detail: String(root.monitors.description || root.monitors.external || ""),
      iconUrl: root.themedIcon(["video-display", "display", "computer"]),
      current: fixed === "external"
    })
    root.monitorIndex = fixed === "external" ? 1 : 0
  }

  function showPage(nextPage) {
    if (nextPage === 1 && !root.hasMonitorPage) return
    root.page = nextPage
  }

  function applyMonitor(index) {
    if (index < 0 || index >= monitorModel.count) return
    root.dismiss("fixed\t" + monitorModel.get(index).role)
  }

  function setFilter(nextFilter) {
    root.filterText = nextFilter
    root.selectedIndex = 0
    root.rebuildDisplay()
  }

  function select(delta) {
    if (root.page === 1) {
      if (monitorModel.count > 0)
        root.monitorIndex = (root.monitorIndex + delta + monitorModel.count) % monitorModel.count
      return
    }
    if (displayModel.count === 0) return
    root.selectedIndex = (root.selectedIndex + delta + displayModel.count) % displayModel.count
    resultList.positionViewAtIndex(root.selectedIndex, ListView.Contain)
  }

  function activateIndex(index, target) {
    if (index < 0 || index >= displayModel.count) return
    root.dismiss(target + "\t" + displayModel.get(index).address)
  }

  ListModel { id: displayModel }
  ListModel { id: monitorModel }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "hypr-minimizer-picker"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.Exclusive
    exclusionMode: ExclusionMode.Ignore

    Rectangle {
      anchors.fill: parent
      color: root.scrim
    }

    MouseArea {
      anchors.fill: parent
      onClicked: root.dismiss(null)
    }

    BorderSurface {
      id: card
      width: root.cardWidth
      height: root.cardHeight
      radius: root.cornerRadius
      anchors.centerIn: parent
      color: root.background
      borderSpec: root.borderSpec
      padding: root.contentMargin

      MouseArea { anchors.fill: parent; onClicked: {} }

      Item {
        id: keyCatcher
        anchors.fill: parent
        focus: true

        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) {
            if (root.filterText) root.setFilter("")
            else root.dismiss(null)
            event.accepted = true
          } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Left) {
            root.showPage(event.key === Qt.Key_Right ? 1 : 0)
            event.accepted = true
          } else if (root.page === 1) {
            // Monitor page: only moving, applying and leaving.
            if (event.key === Qt.Key_Up || event.key === Qt.Key_Backtab)
              root.select(-1)
            else if (event.key === Qt.Key_Down || event.key === Qt.Key_Tab)
              root.select(1)
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)
              root.applyMonitor(root.monitorIndex)
            event.accepted = true
          } else if (Util.editsFilter(event, root.filterText)) {
            root.setFilter(Util.editedFilter(event, root.filterText))
            event.accepted = true
          } else if (event.key === Qt.Key_Up || (event.key === Qt.Key_Tab && (event.modifiers & Qt.ShiftModifier)) || event.key === Qt.Key_Backtab) {
            root.select(-1)
            event.accepted = true
          } else if (event.key === Qt.Key_Down || event.key === Qt.Key_Tab) {
            root.select(1)
            event.accepted = true
          } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
            root.activateIndex(root.selectedIndex, (event.modifiers & Qt.ShiftModifier) ? "here" : "origin")
            event.accepted = true
          } else if (event.text === "-") {
            // Peek: show the window full-size over this workspace until SUPER+M.
            root.activateIndex(root.selectedIndex, "peek")
            event.accepted = true
          } else if (event.text && event.text.length === 1 && event.text.charCodeAt(0) >= 32 && event.text.charCodeAt(0) !== 127) {
            root.setFilter(root.filterText + event.text)
            event.accepted = true
          }
        }
      }

      Column {
        anchors.fill: parent
        anchors.topMargin: card.contentTopInset
        anchors.rightMargin: card.contentRightInset
        anchors.bottomMargin: card.contentBottomInset
        anchors.leftMargin: card.contentLeftInset
        spacing: root.contentSpacing

        Item {
          width: parent.width
          height: root.headerHeight

          Text {
            textFormat: Text.PlainText
            anchors.left: parent.left
            anchors.right: pageTabs.visible ? pageTabs.left : parent.right
            anchors.rightMargin: pageTabs.visible ? Style.space(12) : 0
            anchors.verticalCenter: parent.verticalCenter
            text: root.page === 1 ? "Screen with one desktop" : (root.filterText || (root.prompt + "…"))
            color: root.foreground
            opacity: root.page === 0 && root.filterText ? 1 : 0.58
            font.family: root.fontFamily
            font.pixelSize: Style.font.heading
            elide: Text.ElideRight
          }

          Row {
            id: pageTabs
            visible: root.hasMonitorPage
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(12)

            Repeater {
              model: ["Windows", "Monitors"]

              Text {
                required property int index
                required property string modelData
                textFormat: Text.PlainText
                text: modelData
                color: root.foreground
                opacity: root.page === index ? 1 : 0.45
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
                font.bold: root.page === index

                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: root.showPage(index)
                }
              }
            }
          }
        }

        Item {
          width: parent.width
          height: parent.height - root.headerHeight - root.footerHeight - root.contentSpacing * 2

          ListView {
            id: resultList
            anchors.fill: parent
            visible: root.page === 0
            model: displayModel
            clip: true
            spacing: root.rowSpacing
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
              id: row
              required property int index
              required property string name
              required property string detail
              required property string workspace
              required property string iconUrl

              readonly property bool hasCursor: row.index === root.selectedIndex

              width: ListView.view.width
              height: root.rowHeight
              radius: root.cornerRadius
              color: row.hasCursor ? root.selectedBackground : "transparent"

              Image {
                id: appIcon
                width: root.iconSize
                height: root.iconSize
                fillMode: Image.PreserveAspectFit
                // Decode at physical pixels so PNG icons stay sharp on HiDPI.
                sourceSize.width: width * Screen.devicePixelRatio
                sourceSize.height: height * Screen.devicePixelRatio
                source: row.iconUrl
                asynchronous: true
                anchors.left: parent.left
                anchors.leftMargin: Style.space(10)
                anchors.verticalCenter: parent.verticalCenter
              }

              Column {
                anchors.left: appIcon.right
                anchors.leftMargin: Style.space(12)
                anchors.right: workspaceText.left
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(2)

                Text {
                  textFormat: Text.PlainText
                  width: parent.width
                  text: row.name
                  color: row.hasCursor ? root.selectedText : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  elide: Text.ElideRight
                }

                Text {
                  textFormat: Text.PlainText
                  width: parent.width
                  visible: row.detail.length > 0
                  text: row.detail
                  color: root.foreground
                  opacity: 0.58
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideRight
                }
              }

              Text {
                id: workspaceText
                textFormat: Text.PlainText
                text: "ws " + row.workspace
                color: root.foreground
                opacity: 0.58
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.right: parent.right
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
              }

              MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                cursorShape: Qt.PointingHandCursor
                onContainsMouseChanged: if (containsMouse) root.selectedIndex = row.index
                // Shift+click or middle click brings the window here.
                onClicked: function(mouse) {
                  var here = mouse.button === Qt.MiddleButton || (mouse.modifiers & Qt.ShiftModifier) !== 0
                  root.activateIndex(row.index, here ? "here" : "origin")
                }
              }
            }
          }

          ListView {
            id: monitorList
            anchors.fill: parent
            visible: root.page === 1
            model: monitorModel
            clip: true
            spacing: root.rowSpacing
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
              id: monitorRow
              required property int index
              required property string name
              required property string detail
              required property string iconUrl
              required property bool current

              readonly property bool hasCursor: monitorRow.index === root.monitorIndex

              width: ListView.view.width
              height: root.rowHeight
              radius: root.cornerRadius
              color: monitorRow.hasCursor ? root.selectedBackground : "transparent"

              Image {
                id: monitorIcon
                width: root.iconSize
                height: root.iconSize
                fillMode: Image.PreserveAspectFit
                sourceSize.width: width * Screen.devicePixelRatio
                sourceSize.height: height * Screen.devicePixelRatio
                source: monitorRow.iconUrl
                asynchronous: true
                anchors.left: parent.left
                anchors.leftMargin: Style.space(10)
                anchors.verticalCenter: parent.verticalCenter
              }

              Column {
                anchors.left: monitorIcon.right
                anchors.leftMargin: Style.space(12)
                anchors.right: currentText.left
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
                spacing: Style.space(2)

                Text {
                  textFormat: Text.PlainText
                  width: parent.width
                  text: monitorRow.name
                  color: monitorRow.hasCursor ? root.selectedText : root.foreground
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.body
                  elide: Text.ElideRight
                }

                Text {
                  textFormat: Text.PlainText
                  width: parent.width
                  visible: monitorRow.detail.length > 0
                  text: monitorRow.detail
                  color: root.foreground
                  opacity: 0.58
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  elide: Text.ElideRight
                }
              }

              Text {
                id: currentText
                textFormat: Text.PlainText
                text: monitorRow.current ? "one desktop" : ""
                color: root.foreground
                opacity: 0.58
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
                anchors.right: parent.right
                anchors.rightMargin: Style.space(12)
                anchors.verticalCenter: parent.verticalCenter
              }

              MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onContainsMouseChanged: if (containsMouse) root.monitorIndex = monitorRow.index
                onClicked: root.applyMonitor(monitorRow.index)
              }
            }
          }

          Text {
            anchors.centerIn: parent
            visible: root.page === 0 && displayModel.count === 0
            textFormat: Text.PlainText
            text: root.entries.length === 0 ? "No minimized windows" : "No matches for “" + root.filterText + "”"
            color: root.foreground
            opacity: 0.7
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
          }
        }

        Text {
          width: parent.width
          height: root.footerHeight
          textFormat: Text.PlainText
          text: root.page === 1
            ? "Enter  keep one desktop here     ←  windows"
            : (root.hasMonitorPage
              ? "Enter  restore     Shift+Enter  bring here     -  peek     →  monitors"
              : "Enter  restore to its desktop     Shift+Enter  bring here     -  peek")
          color: root.foreground
          opacity: 0.45
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          horizontalAlignment: Text.AlignHCenter
          verticalAlignment: Text.AlignVCenter
        }
      }
    }
  }
}
