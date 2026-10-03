"""Command line entry point of hypr-screens."""
import argparse
import json
import sys


def print_state(cfg: dict | None = None, message: str = "") -> None:
    from hypr_screens import engine

    print(json.dumps(engine.state(cfg, message)))


def change(mutate) -> int:
    """Load the config, mutate it, save, re-sync, print the new state."""
    from hypr_screens import config, engine

    cfg = config.load()
    try:
        message = mutate(cfg) or ""
    except (ValueError, RuntimeError) as error:
        print_state(cfg, f"error: {error}")
        return 1
    config.save(cfg)
    engine.sync()
    print_state(None, message)
    return 0


def gui(tray: bool) -> int:
    try:
        from hypr_screens.gui import app
    except (ImportError, ValueError) as error:
        print(f"hypr-screens: the settings window needs GTK 4, libadwaita and PyGObject ({error})", file=sys.stderr)
        return 1
    return app.run(tray)


def parse_value(key: str, raw: str) -> object:
    from hypr_screens import config

    if raw in ("", "unset", "default", "none"):
        return None
    if key == "rotation":
        value = int(raw)
        if value not in config.ROTATIONS:
            raise ValueError(f"rotation must be one of {config.ROTATIONS}")
        return value
    if key == "scale":
        return "auto" if raw == "auto" else float(raw)
    if key == "position":
        if raw not in config.POSITIONS:
            raise ValueError(f"position must be one of {config.POSITIONS}")
        return raw
    if key == "one_desktop":
        return raw in ("1", "true", "yes", "on")
    return raw


def resolve_screen(cfg: dict, name: str) -> str:
    """Accept a screen id, a connector (DP-3) or a name (HP 32f, Laptop)."""
    if name in cfg["screens"]:
        return name
    for sid, screen in cfg["screens"].items():
        if name.lower() in (str(screen.get("connector", "")).lower(), str(screen.get("name", "")).lower()):
            return sid
    raise ValueError(f"unknown screen: {name}")


def power(args: argparse.Namespace) -> int:
    """The battery panel's profile buttons: Samsung's four modes when this is a
    Galaxy Book, otherwise Omarchy's power profiles unchanged."""
    from hypr_screens import config, samsung

    if not samsung.present():
        import subprocess

        command = (["omarchy-powerprofiles-list", "--active-state"] if args.action == "list"
                   else ["omarchy-powerprofiles-set", "autodetect", args.mode or ""])
        return subprocess.run(command, check=False).returncode
    if args.action == "list":
        current = samsung.current_mode()
        for mode, _label in samsung.modes():
            print(f"{mode}\t{1 if mode == current else 0}")
        return 0
    cfg = config.load()
    try:
        samsung.set_mode(cfg, args.mode or "")
    except (ValueError, RuntimeError) as error:
        print(f"hypr-screens: {error}", file=sys.stderr)
        return 1
    config.save(cfg)
    return 0


def camera_command(args: argparse.Namespace) -> int:
    from hypr_screens import camera, config

    if args.action == "status":
        print(json.dumps({"set_up": camera.is_set_up(), "virtual": str(camera.virtual_device() or ""),
                          "real": str(camera.real_device() or ""), "rotation": camera.rotation()}, indent=2))
        return 0
    if args.action in ("setup", "teardown"):
        work = camera.setup if args.action == "setup" else camera.teardown
        return 0 if work(graphical=not sys.stdin.isatty()) else 1
    if args.degrees not in camera.ROTATIONS:
        print(f"hypr-screens: rotation must be one of {camera.ROTATIONS}", file=sys.stderr)
        return 1
    cfg = config.load()
    cfg["camera"]["rotation"] = args.degrees
    config.save(cfg)
    return 0


def samsung_command(args: argparse.Namespace) -> int:
    from hypr_screens import config, samsung

    if not samsung.present():
        print("hypr-screens: not a Samsung Galaxy Book (or the samsung-galaxybook driver is not loaded)",
              file=sys.stderr)
        return 1
    if args.action == "status":
        print(json.dumps(samsung.status(), indent=2))
        return 0
    if args.action in ("setup", "teardown"):
        from hypr_screens import install

        work = samsung.setup if args.action == "setup" else samsung.teardown
        if not work(graphical=not sys.stdin.isatty()):
            return 1
        print(f"battery panel: {install.sync_power_panel(samsung.active())}")
        return 0
    cfg = config.load()
    try:
        if args.action == "limit":
            samsung.set_limit(cfg, int(args.value or 100))
        else:
            samsung.full_once(cfg, (args.value or "on") in ("on", "1", "true", "yes"))
    except (ValueError, RuntimeError) as error:
        print(f"hypr-screens: {error}", file=sys.stderr)
        return 1
    config.save(cfg)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hypr-screens",
        description="Per-monitor settings and one fixed screen for Hyprland.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("settings", help="open the settings window")
    sub.add_parser("tray", help="tray icon (started by the generated Lua file)")
    sub.add_parser("setup", help="run the setup wizard")
    sub.add_parser("watch", help="background watcher (started by the generated Lua file)")
    sub.add_parser("apply", help="apply all settings now")
    sub.add_parser("state", help="print everything as JSON")
    sub.add_parser("list", help="list known screens")

    setting = sub.add_parser("set", help="set a screen setting, e.g. `set Laptop rotation 180`")
    setting.add_argument("screen")
    setting.add_argument("key", choices=["rotation", "scale", "mode", "position", "one_desktop"])
    setting.add_argument("value", help="value, or `unset`")

    when = sub.add_parser("when", help="tie a setting to another screen: `when Laptop rotation \"HP 32f\"`")
    when.add_argument("screen")
    when.add_argument("key")
    when.add_argument("other", help="screen that must be connected, or `always`")

    stepper = sub.add_parser("step", help="used by the menu: cycle a value or its condition")
    stepper.add_argument("screen")
    stepper.add_argument("key")
    stepper.add_argument("direction", type=int)
    stepper.add_argument("--condition", action="store_true")

    favorite = sub.add_parser("favorite", help="toggle a favorite")
    favorite.add_argument("screen")
    forget = sub.add_parser("forget", help="forget a screen that is not connected")
    forget.add_argument("screen")

    swap = sub.add_parser("swap", help="swap the fixed screen until unplugged")
    swap.add_argument("role", nargs="?", choices=["panel", "external"])

    bind = sub.add_parser("bind", help="set a key: `bind stash 1 \"SUPER + M\"`")
    bind.add_argument("action")
    bind.add_argument("slot", type=int, choices=[1, 2])
    bind.add_argument("combo", nargs="?", default="", help="empty to clear")

    option = sub.add_parser("option", help="desktop_keys on|off, default_fixed off|external|panel")
    option.add_argument("name", choices=["desktop_keys", "default_fixed"])
    option.add_argument("value", nargs="?", default="next")

    for name, text in (
        ("switch", "show desktop N (1-10)"),
        ("move", "move the active window to desktop N and follow"),
        ("move-silent", "move the active window to desktop N, stay"),
    ):
        desk = sub.add_parser(name, help=text)
        desk.add_argument("index", type=int)
    sub.add_parser("next", help="next used desktop")
    sub.add_parser("prev", help="previous used desktop")
    cycle = sub.add_parser("cycle", help="focus the next visible window")
    cycle.add_argument("direction", nargs="?", choices=["prev"])
    sub.add_parser("status", help="fixed screen status as JSON")
    cam = sub.add_parser("camera", help="the turned virtual camera: status | setup | teardown | rotate 0|90|180|270")
    cam.add_argument("action", choices=["status", "setup", "teardown", "rotate"])
    cam.add_argument("degrees", nargs="?", type=int)
    power = sub.add_parser("power", help="performance mode, used by the battery panel: list | set MODE")
    power.add_argument("action", choices=["list", "set"])
    power.add_argument("mode", nargs="?")
    samsung = sub.add_parser("samsung",
                             help="Samsung Galaxy Book: status | setup | teardown | limit N | full-once on|off")
    samsung.add_argument("action", choices=["status", "setup", "teardown", "limit", "full-once"])
    samsung.add_argument("value", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    raise SystemExit(run(args))


def run(args: argparse.Namespace) -> int:
    from hypr_screens import config

    command = args.command

    # Hot path first: desktop keys fire on every keypress.
    if command in ("switch", "move", "move-silent", "next", "prev", "cycle"):
        from hypr_screens import desktops

        if command == "cycle":
            desktops.cycle(-1 if args.direction == "prev" else 1)
        elif command in ("next", "prev"):
            desktops.step(config.load(), 1 if command == "next" else -1)
        else:
            desktops.switch(config.load(), command, args.index)
        return 0

    if command == "setup":
        from hypr_screens import setup

        return setup.run()
    if not config.exists() and sys.stdin.isatty() and command in ("settings", "apply", "list", "state"):
        from hypr_screens import setup

        setup.run()
        if command != "settings":
            return 0

    if command in ("settings", "tray"):
        return gui(tray=command == "tray")
    if command == "watch":
        from hypr_screens import watch

        return watch.watch()
    if command == "apply":
        from hypr_screens import engine

        done = engine.sync()
        print(", ".join(done) or "nothing to change")
        return 0
    if command == "state":
        print_state()
        return 0
    if command == "status":
        from hypr_screens import desktops

        print(json.dumps(desktops.status(config.load())))
        return 0
    if command == "camera":
        return camera_command(args)
    if command == "power":
        return power(args)
    if command == "samsung":
        return samsung_command(args)
    if command == "list":
        from hypr_screens import engine, hypr

        cfg = config.load()
        for row in engine.screen_rows(cfg, set(config.connected(hypr.monitors()))):
            mark = "●" if row["connected"] else "○"
            star = "★" if row["favorite"] else " "
            print(f"{mark} {star} {row['name']:<24} {row['connector']:<10} {row['summary']}")
        return 0

    if command == "set":
        def mutate(cfg):
            sid = resolve_screen(cfg, args.screen)
            config.set_setting(cfg, sid, args.key, parse_value(args.key, args.value))
        return change(mutate)
    if command == "when":
        def mutate(cfg):
            sid = resolve_screen(cfg, args.screen)
            other = None if args.other == "always" else resolve_screen(cfg, args.other)
            config.set_condition(cfg, sid, args.key, other)
        return change(mutate)
    if command == "step":
        from hypr_screens import engine

        def mutate(cfg):
            sid = resolve_screen(cfg, args.screen)
            if args.condition:
                if not engine.step_condition(cfg, sid, args.key, args.direction):
                    return "set a value first"
            else:
                engine.step_value(cfg, sid, args.key, args.direction)
        return change(mutate)
    if command == "favorite":
        def mutate(cfg):
            screen = cfg["screens"][resolve_screen(cfg, args.screen)]
            screen["favorite"] = not screen.get("favorite")
        return change(mutate)
    if command == "forget":
        from hypr_screens import hypr

        def mutate(cfg):
            sid = resolve_screen(cfg, args.screen)
            if cfg["screens"][sid].get("internal"):
                raise ValueError("the laptop screen cannot be forgotten")
            if sid in config.connected(hypr.monitors()):
                raise ValueError("unplug it first")
            del cfg["screens"][sid]
            for screen in cfg["screens"].values():
                for setting in screen.get("settings", {}).values():
                    if setting.get("when") == sid:
                        setting["when"] = None
        return change(mutate)
    if command == "swap":
        from hypr_screens import desktops

        cfg = config.load()
        try:
            desktops.swap(cfg, args.role)
        except RuntimeError as error:
            print_state(cfg, f"error: {error}")
            return 1
        print_state(cfg)
        return 0
    if command == "bind":
        from hypr_screens import keybinds

        cfg = config.load()
        old = config.normalize(json.loads(json.dumps(cfg)))
        try:
            note = keybinds.set_key(cfg, args.action, args.slot - 1, args.combo)
        except ValueError as error:
            print_state(cfg, f"error: {error}")
            return 1
        config.save(cfg)
        keybinds.write(cfg)
        keybinds.go_live(old, cfg)
        print_state(cfg, note)
        return 0
    if command == "option":
        from hypr_screens import keybinds

        cfg = config.load()
        old = config.normalize(json.loads(json.dumps(cfg)))
        if args.name == "desktop_keys":
            toggle = args.value in ("next", "prev")
            value = not cfg["desktop_keys"] if toggle else args.value in ("on", "1", "true", "yes")
            cfg["desktop_keys"] = value
        else:
            choices = config.FIXED_DEFAULTS
            value = args.value
            if value in ("next", "prev"):
                index = choices.index(cfg["default_fixed"]) + (1 if value == "next" else -1)
                value = choices[index % len(choices)]
            if value not in choices:
                print_state(cfg, f"error: default_fixed must be one of {choices}")
                return 1
            cfg["default_fixed"] = value
        config.save(cfg)
        if args.name == "desktop_keys":
            keybinds.write(cfg)
            keybinds.go_live(old, cfg)
        from hypr_screens import engine

        engine.sync()
        print_state()
        return 0
    return 1
