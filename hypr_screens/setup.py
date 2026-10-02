"""First-run setup wizard (terminal, keyboard only). Sets keys, not monitors."""
import shutil
import sys

from hypr_screens import config, hypr, install, keybinds, samsung

INTRO = """
  hypr-minimizer + hypr-screens · setup
  ─────────────────────────────────────
  • Minimizer: hide windows, get them back from a menu, peek with "-".
  • Screens: every monitor you plug in is remembered; rotation, scale,
    resolution and position per monitor, optionally only while another
    monitor is connected.
  • One desktop: with an external monitor, one screen keeps a single desktop.

  Only window keys go on the keyboard. Everything else is set in a window
  that opens from the tray icon (it starts with Hyprland).
  Enter takes the suggestion in [brackets].
"""


def ask(question: str, default: str = "") -> str:
    try:
        answer = input(f"  {question} " + (f"[{default}] " if default else ""))
    except EOFError:
        print()
        return default
    return answer.strip() or default


def yes(question: str, default: bool = True) -> bool:
    answer = ask(question + (" (Y/n)" if default else " (y/N)")).lower()
    return default if not answer else answer.startswith(("y", "j"))


def step(number: int, title: str) -> None:
    print(f"\n  {number}/4  {title}\n  " + "─" * (len(title) + 6))


def show_keys(cfg: dict) -> None:
    binds = hypr.query_list("binds")
    for action, label, _command in config.ACTIONS:
        keys = [key for key in cfg["keybinds"][action] if key]
        taken = [note for key in keys for note in keybinds.conflicts(key, binds)]
        extra = f"   (replaces: {', '.join(taken)})" if taken else ""
        print(f"  {label:<26} {' | '.join(keys) or '—'}{extra}")


def edit_keys(cfg: dict) -> None:
    print("  Type a combination like SUPER + SHIFT + PERIOD, - to clear, Enter to keep.")
    for action, label, _command in config.ACTIONS:
        for slot in (0, 1):
            current = cfg["keybinds"][action][slot]
            while True:
                answer = ask(f"{label}, key {slot + 1}:", current or "-")
                combo = "" if answer == "-" else answer
                try:
                    note = keybinds.set_key(cfg, action, slot, combo)
                except ValueError as error:
                    print(f"    ✗ {error}")
                    continue
                if note:
                    print(f"    ! {note}")
                break


def run() -> int:
    if not sys.stdin.isatty():
        print("hypr-screens setup needs a terminal.", file=sys.stderr)
        return 1
    print(INTRO)
    cfg = config.load()

    step(1, "Keys")
    show_keys(cfg)
    if not yes("Keep these keys?"):
        edit_keys(cfg)

    step(2, "One desktop")
    print("  With an external monitor, one screen shows a single fixed desktop and")
    print("  desktops 1-10 live on the other one (SUPER + 1…0 go through hypr-screens).")
    uses = cfg["desktop_keys"] or cfg["default_fixed"] != "off"
    if yes("Use it?", uses):
        cfg["desktop_keys"] = True
        choice = ask("Which screen keeps one desktop on new monitors? external / laptop / off:",
                     {"external": "external", "panel": "laptop", "off": "off"}.get(cfg["default_fixed"], "external"))
        cfg["default_fixed"] = {"laptop": "panel", "l": "panel", "off": "off", "o": "off"}.get(choice.lower(), "external")
    else:
        cfg["desktop_keys"] = False
        cfg["default_fixed"] = "off"

    step(3, "Hyprland config")
    config.save(cfg)
    path = keybinds.write(cfg)
    print(f"  Wrote {path}")
    hyprland = keybinds.hyprland_file()
    if keybinds.is_required():
        print(f"  {hyprland.name} already loads it.")
    elif hyprland.exists():
        if yes(f"Add `{keybinds.REQUIRE_LINE}` to {hyprland}?"):
            keybinds.add_require()
            print("  Added (backup: hyprland.lua.bak-hypr-screens).")
        else:
            print(f"  Add this line at the end of {hyprland} yourself:\n    {keybinds.REQUIRE_LINE}")
    else:
        print("  No hyprland.lua found. hypr-screens needs Hyprland >= 0.56 with a Lua config;")
        print(f"  load {path} from it:  {keybinds.REQUIRE_LINE}")

    step(4, "Menus")
    if not shutil.which("hypr-screens") or not shutil.which("hypr-minimizer"):
        if yes(f"Put hypr-screens and hypr-minimizer into {install.BIN}?"):
            for name, result in install.install_launchers().items():
                print(f"  {name}: {result}")
    if install.has_omarchy_shell():
        for plugin in install.remove_retired_plugins():
            print(f"  removed old {plugin}")
        if yes("Set up the Omarchy window menu (and bar widget)?"):
            plugins = ["hypr-minimizer.picker"]
            if cfg["desktop_keys"]:
                plugins.append(install.WORKSPACES_WIDGET)
            for plugin, result in install.install_plugins(plugins).items():
                print(f"  {plugin}: {result}")
            if cfg["desktop_keys"] and yes("Show the fixed screen in the bar (replaces the workspaces widget)?"):
                print(f"  bar: {install.use_bar_widget()}")
    else:
        print("  No omarchy-shell: no window menu; everything else works.")

    if samsung.present():
        step(5, "Samsung Galaxy Book")
        if samsung.is_set_up():
            print("  Charge limit and performance mode can already be changed.")
        elif yes("Allow changing charge limit, performance mode and the firmware switches? "
                 "(needs your password once)"):
            print("  Done." if samsung.setup() else "  ! Setup failed; try again: hypr-screens samsung setup")
        if install.has_omarchy_shell() and yes("Use the battery panel with the four Samsung modes in the bar?"):
            result = install.install_plugins([install.POWER_WIDGET])[install.POWER_WIDGET]
            print(f"  {install.POWER_WIDGET}: {result}")
            print(f"  bar: {install.use_bar_widget(install.POWER_WIDGET)}")
    missing = install.gui_available()
    if missing:
        print(f"  ! The settings window needs GTK 4 + libadwaita + PyGObject ({missing}).")
        print("    Arch: sudo pacman -S python-gobject libadwaita")

    if keybinds.is_required():
        hypr.hyprctl("reload")
    install.start_watcher()
    if not missing:
        install.start_tray()

    keys = cfg["keybinds"]
    print("\n  Done.")
    print("  Settings:       tray icon (or: hypr-screens settings)")
    print(f"  Window menu:    {' | '.join(k for k in keys['minimizer_menu'] if k) or '(no key)'}")
    print("  Again later:    hypr-screens setup\n")
    return 0
