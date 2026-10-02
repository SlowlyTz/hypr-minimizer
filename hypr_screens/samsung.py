"""Samsung Galaxy Book settings through the samsung-galaxybook kernel driver --
what Samsung Settings does on Windows: charge limit, performance mode (fan
noise), power on lid open, USB charging while off, keyboard backlight.

The performance mode is one of four platform profiles. power-profiles-daemon
only knows three and Omarchy switches it on boot and on AC changes, so
`setup()` blocks its platform_profile driver (it keeps tuning the CPU) and
the watcher (`guard_tick`) keeps both on the chosen mode. Pressing the
keyboard's mode key changes the platform profile directly; that is taken over.

Writing needs root: `setup()` installs a udev rule that hands the few files to
the user, once, through pkexec or sudo.
"""
import getpass
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from hypr_screens import config

SYSFS = Path("/sys")
DRIVER = "samsung-galaxybook"
KEYBOARD_LED = "samsung-galaxybook::kbd_backlight"
# (platform profile, label, power-profiles-daemon profile for the CPU)
MODES = [
    ("low-power", "Saver", "power-saver"),
    ("quiet", "Quiet", "balanced"),
    ("balanced", "Balanced", "balanced"),
    ("performance", "Performance", "performance"),
]
ATTRIBUTES = {
    "power_on_lid_open": "Power on when the lid opens",
    "usb_charging": "USB charging while off",
}
PPD = ("org.freedesktop.UPower.PowerProfiles", "/org/freedesktop/UPower/PowerProfiles",
       "org.freedesktop.UPower.PowerProfiles", "ActiveProfile")
UDEV_RULE = Path("/etc/udev/rules.d/90-hypr-screens-samsung.rules")
PPD_DROPIN = Path("/etc/systemd/system/power-profiles-daemon.service.d/hypr-screens.conf")


# --- reading -------------------------------------------------------------------------


def read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def write(path: Path, value: object) -> bool:
    try:
        path.write_text(f"{value}\n")
        return True
    except OSError:
        return False


def present() -> bool:
    """A Samsung laptop with the samsung-galaxybook driver loaded."""
    vendor = read(SYSFS / "class/dmi/id/sys_vendor").upper()
    return "SAMSUNG" in vendor and (SYSFS / "bus/platform/drivers" / DRIVER).exists()


def battery_dir() -> Path | None:
    for path in sorted((SYSFS / "class/power_supply").glob("*")):
        if read(path / "type") == "Battery" and (path / "charge_control_end_threshold").exists():
            return path
    return None


def profile_dir() -> Path | None:
    for path in sorted((SYSFS / "class/platform-profile").glob("*")):
        if read(path / "name") == DRIVER:
            return path
    return None


def attribute_file(name: str) -> Path:
    return SYSFS / "class/firmware-attributes" / DRIVER / "attributes" / name / "current_value"


def ac_online() -> bool:
    supplies = [p for p in (SYSFS / "class/power_supply").glob("*") if read(p / "type") == "Mains"]
    if supplies:
        return any(read(p / "online") == "1" for p in supplies)
    battery = battery_dir()
    return battery is not None and read(battery / "status") != "Discharging"


def number(path: Path) -> int | None:
    try:
        return int(read(path))
    except ValueError:
        return None


def battery_info() -> dict:
    battery = battery_dir()
    if battery is None:
        return {}
    full = number(battery / "charge_full") or number(battery / "energy_full")
    design = number(battery / "charge_full_design") or number(battery / "energy_full_design")
    power = number(battery / "power_now")
    if power is None:
        current, voltage = number(battery / "current_now"), number(battery / "voltage_now")
        power = current * voltage // 1_000_000 if current is not None and voltage is not None else None
    return {
        "percent": number(battery / "capacity"),
        "status": read(battery / "status"),
        "health": round(100 * full / design) if full and design else None,
        "cycles": number(battery / "cycle_count"),
        "watts": round(power / 1_000_000, 1) if power is not None else None,
    }


def fan() -> dict:
    """{"rpm": speed or None, "running": True/False or None}. Galaxy Books do not
    report a speed (reading it fails), only whether the fan is on: the ACPI fan's
    cooling state."""
    rpm = None
    for hwmon in (SYSFS / "class/hwmon").glob("*"):
        if read(hwmon / "name") == "acpi_fan":
            rpm = number(hwmon / "fan1_input")
    running = None
    for device in (SYSFS / "class/thermal").glob("cooling_device*"):
        if read(device / "type") == "Fan":
            state = number(device / "cur_state")
            if state is not None:
                running = bool(running) or state > 0
    if rpm:
        running = True
    return {"rpm": rpm or None, "running": running}


def cpu_temperature() -> int | None:
    """The CPU package in °C: coretemp's "Package id 0", else the x86_pkg_temp zone."""
    for hwmon in (SYSFS / "class/hwmon").glob("*"):
        if read(hwmon / "name") != "coretemp":
            continue
        for label in sorted(hwmon.glob("temp*_label")):
            if read(label).startswith("Package"):
                value = number(hwmon / label.name.replace("_label", "_input"))
                if value is not None:
                    return round(value / 1000)
    for zone in (SYSFS / "class/thermal").glob("thermal_zone*"):
        if read(zone / "type") == "x86_pkg_temp":
            value = number(zone / "temp")
            if value is not None:
                return round(value / 1000)
    return None


def keyboard() -> tuple[int, int] | None:
    led = SYSFS / "class/leds" / KEYBOARD_LED
    value, top = number(led / "brightness"), number(led / "max_brightness")
    return (value, top) if value is not None and top else None


def modes() -> list[tuple[str, str]]:
    """The modes this laptop offers, as (platform profile, label)."""
    directory = profile_dir()
    choices = read(directory / "choices").split() if directory else []
    return [(mode, label) for mode, label, _cpu in MODES if mode in choices]


def current_mode() -> str:
    directory = profile_dir()
    return read(directory / "profile") if directory else ""


def writable() -> bool:
    """Whether the udev rule from setup() is in place for this user."""
    battery, directory = battery_dir(), profile_dir()
    files = [battery / "charge_control_end_threshold" if battery else None,
             directory / "profile" if directory else None]
    return all(path is not None and os.access(path, os.W_OK) for path in files)


def settings(cfg: dict) -> dict:
    return dict(cfg.get("samsung") or {})


def status(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else config.load()
    battery = battery_dir()
    return {
        "present": present(),
        "writable": writable(),
        "limit": number(battery / "charge_control_end_threshold") if battery else None,
        "wanted_limit": settings(cfg).get("limit"),
        "full_once": bool(settings(cfg).get("full_once")),
        "mode": current_mode(),
        "modes": modes(),
        "ac": ac_online(),
        "battery": battery_info(),
        "fan": fan(),
        "cpu_temperature": cpu_temperature(),
        "attributes": {name: read(attribute_file(name)) == "1" if attribute_file(name).exists() else None
                       for name in ATTRIBUTES},
        "attributes_writable": all(os.access(attribute_file(name), os.W_OK)
                                   for name in ATTRIBUTES if attribute_file(name).exists()),
        "keyboard": keyboard(),
    }


# --- changing ------------------------------------------------------------------------


def cpu_profile(mode: str) -> str:
    return next((cpu for name, _label, cpu in MODES if name == mode), "balanced")


def ppd_profile() -> str:
    try:
        out = subprocess.run(["busctl", "get-property", *PPD], check=False, text=True, capture_output=True).stdout
    except OSError:
        return ""
    return out.strip().removeprefix("s ").strip('"')


def set_ppd(profile: str) -> None:
    try:
        subprocess.run(["busctl", "set-property", *PPD, "s", profile], check=False, capture_output=True)
    except OSError:
        pass


def omarchy_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "omarchy" / "powerprofiles"


def tell_omarchy(profile: str) -> None:
    """Omarchy sets its remembered profile on boot and on AC changes; remember
    ours there, for both, so it sets the same one and nothing flips back."""
    directory = omarchy_state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    for source in ("ac", "battery"):
        if read(directory / source) != profile:
            write(directory / source, profile)


def apply_mode(mode: str) -> None:
    directory = profile_dir()
    if directory is not None and read(directory / "profile") != mode:
        write(directory / "profile", mode)
    cpu = cpu_profile(mode)
    if ppd_profile() not in ("", cpu):
        set_ppd(cpu)


class NotSetUp(RuntimeError):
    def __init__(self):
        super().__init__("needs a one-time setup first: hypr-screens samsung setup")


def set_mode(cfg: dict, mode: str) -> None:
    if mode not in [name for name, _label in modes()]:
        raise ValueError(f"mode must be one of {[name for name, _label in modes()]}")
    if not writable():
        raise NotSetUp()
    cfg.setdefault("samsung", {})["mode"] = mode
    tell_omarchy(cpu_profile(mode))
    apply_mode(mode)


def set_limit(cfg: dict, limit: int) -> None:
    if not writable():
        raise NotSetUp()
    limit = max(50, min(100, int(limit)))
    cfg.setdefault("samsung", {})["limit"] = limit
    battery = battery_dir()
    if battery is not None and not settings(cfg).get("full_once"):
        write(battery / "charge_control_end_threshold", limit)


def full_once(cfg: dict, on: bool) -> None:
    """Charge to 100 % once; the limit comes back when the battery is full or
    the charger is unplugged (guard_tick)."""
    if not writable():
        raise NotSetUp()
    samsung = cfg.setdefault("samsung", {})
    battery = battery_dir()
    if samsung.get("limit") is None and battery is not None:
        samsung["limit"] = number(battery / "charge_control_end_threshold")
    samsung["full_once"] = on
    if battery is not None:
        write(battery / "charge_control_end_threshold", 100 if on else samsung.get("limit") or 100)


def set_attribute(name: str, on: bool) -> bool:
    if name not in ATTRIBUTES:
        raise ValueError(f"unknown setting: {name}")
    return write(attribute_file(name), 1 if on else 0)


def set_keyboard(level: int) -> None:
    subprocess.run(["brightnessctl", "-q", "-d", KEYBOARD_LED, "set", str(int(level))],
                   check=False, capture_output=True)


# --- watcher ---------------------------------------------------------------------------


def guard_tick(cfg: dict) -> str:
    """One check of the watcher; returns what it did ("" for nothing)."""
    samsung = settings(cfg)
    done = []
    battery = battery_dir()

    if samsung.get("full_once") and battery is not None:
        info = battery_info()
        if not ac_online() or info.get("status") == "Full" or (info.get("percent") or 0) >= 100:
            cfg["samsung"]["full_once"] = False
            write(battery / "charge_control_end_threshold", samsung.get("limit") or 100)
            done.append("full charge done, limit back")
    elif samsung.get("limit") is not None and battery is not None:
        if number(battery / "charge_control_end_threshold") != samsung["limit"]:
            if write(battery / "charge_control_end_threshold", samsung["limit"]):
                done.append(f"limit {samsung['limit']}")

    mode = samsung.get("mode")
    if mode:
        current = current_mode()
        if current and current != mode and current in [name for name, _label in modes()]:
            # Nothing else writes the profile once power-profiles-daemon is kept
            # off it: this is the keyboard's mode key. Take it over.
            cfg["samsung"]["mode"] = mode = current
            tell_omarchy(cpu_profile(current))
            done.append(f"mode {current} from the keyboard")
        cpu = cpu_profile(mode)
        active = ppd_profile()
        if active and active != cpu:
            set_ppd(cpu)
            done.append(f"cpu {cpu}")
    return ", ".join(done)


def guard() -> None:
    """Watcher thread: every second, keep the limit and the mode."""
    if not present():
        return
    while True:
        try:
            cfg = config.load()
            if settings(cfg):
                before = json.dumps(cfg, sort_keys=True)
                guard_tick(cfg)
                if json.dumps(cfg, sort_keys=True) != before:
                    config.save(cfg)
        except Exception as error:  # never take the watcher down
            print(f"hypr-screens samsung guard: {error}", flush=True)
        time.sleep(1.0)


# --- one-time root setup -----------------------------------------------------------------


def udev_rule(user: str) -> str:
    return "\n".join([
        "# hypr-screens: let this user change Samsung Galaxy Book settings without root.",
        'ACTION=="add", SUBSYSTEM=="power_supply", ATTR{type}=="Battery", '
        f'RUN+="/usr/bin/chown {user} /sys%p/charge_control_end_threshold"',
        f'ACTION=="add", SUBSYSTEM=="platform-profile", RUN+="/usr/bin/chown {user} /sys%p/profile"',
        f'ACTION=="add", SUBSYSTEM=="firmware-attributes", KERNEL=="{DRIVER}", '
        f'RUN+="/bin/sh -c \'/usr/bin/chown {user} /sys%p/attributes/*/current_value\'"',
        "",
    ])


def ppd_dropin() -> str:
    return "\n".join([
        "# hypr-screens owns the platform profile (4 Samsung modes); power-profiles-daemon",
        "# keeps tuning the CPU only.",
        "[Service]",
        "ExecStart=",
        "ExecStart=/usr/lib/power-profiles-daemon --block-driver platform_profile",
        "",
    ])


def setup_script(user: str) -> str:
    return "\n".join([
        "set -e",
        f"mkdir -p {PPD_DROPIN.parent}",
        f"cat > {UDEV_RULE} <<'EOF'\n{udev_rule(user)}EOF",
        f"cat > {PPD_DROPIN} <<'EOF'\n{ppd_dropin()}EOF",
        "udevadm control --reload",
        "udevadm trigger --action=add --subsystem-match=power_supply "
        "--subsystem-match=platform-profile --subsystem-match=firmware-attributes",
        "udevadm settle || true",
        "systemctl daemon-reload",
        "systemctl try-restart power-profiles-daemon",
        "",
    ])


def is_set_up() -> bool:
    return UDEV_RULE.exists() and PPD_DROPIN.exists() and writable()


def setup(graphical: bool = False) -> bool:
    """Install the udev rule and the power-profiles-daemon drop-in as root:
    pkexec (password dialog) from the window, sudo from a terminal."""
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as script:
        script.write(setup_script(getpass.getuser()))
    try:
        elevate = ["pkexec"] if graphical or not shutil.which("sudo") else ["sudo"]
        done = subprocess.run([*elevate, "/bin/sh", script.name], check=False)
        return done.returncode == 0
    finally:
        os.unlink(script.name)
