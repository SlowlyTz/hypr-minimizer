"""Samsung Galaxy Book settings against a fake /sys."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from hypr_screens import cli, config, install, samsung


def put(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n")


@pytest.fixture()
def sysfs(tmp_path, monkeypatch):
    root = tmp_path / "sys"
    put(root / "class/dmi/id/sys_vendor", "SAMSUNG ELECTRONICS CO., LTD.")
    put(root / "class/dmi/id/product_family", "Galaxy Book5 360")
    (root / "bus/platform/drivers/samsung-galaxybook").mkdir(parents=True)
    battery = root / "class/power_supply/BAT1"
    for name, value in {"type": "Battery", "charge_control_end_threshold": 80, "capacity": 80,
                        "status": "Not charging", "charge_full": 5300000, "charge_full_design": 5600000,
                        "cycle_count": 24, "current_now": 1500000, "voltage_now": 12000000}.items():
        put(battery / name, value)
    put(root / "class/power_supply/ADP1/type", "Mains")
    put(root / "class/power_supply/ADP1/online", 1)
    profile = root / "class/platform-profile/platform-profile-0"
    put(profile / "name", "samsung-galaxybook")
    put(profile / "choices", "low-power quiet balanced performance")
    put(profile / "profile", "balanced")
    attributes = root / "class/firmware-attributes/samsung-galaxybook/attributes"
    put(attributes / "power_on_lid_open/current_value", 0)
    put(attributes / "usb_charging/current_value", 1)
    put(root / "class/leds/samsung-galaxybook::kbd_backlight/brightness", 2)
    put(root / "class/leds/samsung-galaxybook::kbd_backlight/max_brightness", 3)
    put(root / "class/hwmon/hwmon3/name", "acpi_fan")
    put(root / "class/hwmon/hwmon3/fan1_input", 3100)
    put(root / "class/hwmon/hwmon7/name", "coretemp")
    put(root / "class/hwmon/hwmon7/temp1_label", "Package id 0")
    put(root / "class/hwmon/hwmon7/temp1_input", 71000)
    put(root / "class/hwmon/hwmon7/temp2_label", "Core 0")
    put(root / "class/hwmon/hwmon7/temp2_input", 64000)
    put(root / "class/thermal/cooling_device0/type", "Fan")
    put(root / "class/thermal/cooling_device0/cur_state", 1)
    monkeypatch.setattr(samsung, "SYSFS", root)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return root


@pytest.fixture()
def ppd(monkeypatch):
    """power-profiles-daemon over busctl: remembers the profile, records calls."""
    state = {"profile": "balanced", "calls": []}

    def run(args, **_kwargs):
        state["calls"].append(args)
        if args[:2] == ["busctl", "get-property"]:
            return subprocess.CompletedProcess(args, 0, stdout=f's "{state["profile"]}"\n')
        if args[:2] == ["busctl", "set-property"]:
            state["profile"] = args[-1]
        return subprocess.CompletedProcess(args, 0, stdout="")

    monkeypatch.setattr(samsung.subprocess, "run", run)
    return state


def battery(sysfs: Path, name: str) -> str:
    return (sysfs / "class/power_supply/BAT1" / name).read_text().strip()


def profile(sysfs: Path) -> str:
    return (sysfs / "class/platform-profile/platform-profile-0/profile").read_text().strip()


def test_detects_only_samsung_laptops_with_the_driver(sysfs):
    assert samsung.present()
    put(sysfs / "class/dmi/id/sys_vendor", "LENOVO")
    assert not samsung.present()


def test_status_reads_battery_modes_and_switches(sysfs):
    state = samsung.status(config.default_config())
    assert state["limit"] == 80 and state["ac"] is True
    assert state["battery"] == {"percent": 80, "status": "Not charging", "health": 95, "cycles": 24, "watts": 18.0}
    assert state["modes"] == [("low-power", "Saver"), ("quiet", "Quiet"), ("balanced", "Balanced"),
                              ("performance", "Performance")]
    assert state["mode"] == "balanced" and state["fan"] == {"rpm": 3100, "running": True}
    assert state["cpu_temperature"] == 71
    assert state["attributes"] == {"power_on_lid_open": False, "usb_charging": True}
    assert state["keyboard"] == (2, 3)


def test_fan_without_a_speed_still_says_whether_it_runs(sysfs):
    # Galaxy Books fail reading the speed; only the cooling state is there.
    (sysfs / "class/hwmon/hwmon3/fan1_input").unlink()
    assert samsung.fan() == {"rpm": None, "running": True}
    put(sysfs / "class/thermal/cooling_device0/cur_state", 0)
    assert samsung.fan() == {"rpm": None, "running": False}


def test_changes_need_the_setup_first(sysfs, monkeypatch):
    monkeypatch.setattr(samsung, "writable", lambda: False)
    cfg = config.default_config()
    with pytest.raises(samsung.NotSetUp):
        samsung.set_mode(cfg, "quiet")
    with pytest.raises(samsung.NotSetUp):
        samsung.set_limit(cfg, 60)
    assert profile(sysfs) == "balanced" and battery(sysfs, "charge_control_end_threshold") == "80"


def test_mode_sets_the_platform_profile_the_cpu_and_omarchys_memory(sysfs, ppd):
    cfg = config.default_config()
    samsung.set_mode(cfg, "performance")
    assert profile(sysfs) == "performance" and ppd["profile"] == "performance"
    assert cfg["samsung"]["mode"] == "performance"
    state_dir = Path(os.environ["XDG_STATE_HOME"]) / "omarchy/powerprofiles"
    assert (state_dir / "ac").read_text().strip() == "performance"
    assert (state_dir / "battery").read_text().strip() == "performance"

    # Quiet has no power-profiles-daemon twin: the CPU stays balanced.
    samsung.set_mode(cfg, "quiet")
    assert profile(sysfs) == "quiet" and ppd["profile"] == "balanced"
    with pytest.raises(ValueError):
        samsung.set_mode(cfg, "turbo")


def test_guard_puts_the_cpu_back_after_omarchy_switched_it(sysfs, ppd):
    cfg = config.default_config()
    samsung.set_mode(cfg, "quiet")
    ppd["profile"] = "performance"  # Omarchy on plugging in the charger
    assert samsung.guard_tick(cfg) == "cpu balanced"
    assert ppd["profile"] == "balanced" and profile(sysfs) == "quiet"
    assert samsung.guard_tick(cfg) == ""


def test_guard_takes_over_the_keyboards_mode_key(sysfs, ppd):
    cfg = config.default_config()
    samsung.set_mode(cfg, "balanced")
    put(sysfs / "class/platform-profile/platform-profile-0/profile", "performance")
    assert "mode performance from the keyboard" in samsung.guard_tick(cfg)
    assert cfg["samsung"]["mode"] == "performance" and ppd["profile"] == "performance"


def test_guard_holds_the_charge_limit(sysfs, ppd):
    cfg = config.default_config()
    samsung.set_limit(cfg, 60)
    assert battery(sysfs, "charge_control_end_threshold") == "60"
    put(sysfs / "class/power_supply/BAT1/charge_control_end_threshold", 100)
    assert samsung.guard_tick(cfg) == "limit 60"
    assert battery(sysfs, "charge_control_end_threshold") == "60"


@pytest.mark.parametrize("unplug, full", [(True, False), (False, True)])
def test_full_charge_once_ends_when_unplugged_or_full(sysfs, ppd, unplug, full):
    cfg = config.default_config()
    samsung.full_once(cfg, True)
    assert battery(sysfs, "charge_control_end_threshold") == "100"
    assert cfg["samsung"] == {"limit": 80, "mode": None, "full_once": True}
    assert samsung.guard_tick(cfg) == ""  # still charging

    if unplug:
        put(sysfs / "class/power_supply/ADP1/online", 0)
    if full:
        put(sysfs / "class/power_supply/BAT1/status", "Full")
    assert samsung.guard_tick(cfg) == "full charge done, limit back"
    assert battery(sysfs, "charge_control_end_threshold") == "80"
    assert cfg["samsung"]["full_once"] is False


def test_firmware_switches(sysfs):
    assert samsung.set_attribute("power_on_lid_open", True)
    assert samsung.status(config.default_config())["attributes"]["power_on_lid_open"] is True
    with pytest.raises(ValueError):
        samsung.set_attribute("bios_password", True)


def test_samsung_settings_survive_the_config_file():
    cfg = config.normalize({"samsung": {"limit": 85, "mode": "quiet", "full_once": 1}})
    assert cfg["samsung"] == {"limit": 85, "mode": "quiet", "full_once": True}
    cfg = config.normalize({"samsung": {"limit": 400, "mode": 3}})
    assert cfg["samsung"] == {"limit": None, "mode": None, "full_once": False}


def test_setup_hands_the_files_to_the_user_and_keeps_ppd_off_the_profile():
    rule = samsung.udev_rule("slowly")
    assert 'RUN+="/usr/bin/chown slowly /sys%p/charge_control_end_threshold"' in rule
    assert 'SUBSYSTEM=="platform-profile", RUN+="/usr/bin/chown slowly /sys%p/profile"' in rule
    assert "attributes/*/current_value" in rule
    script = samsung.setup_script("slowly")
    assert "--block-driver platform_profile" in script
    assert "systemctl try-restart power-profiles-daemon" in script


def test_panel_lists_samsung_modes(sysfs, capsys):
    assert cli.run(cli.build_parser().parse_args(["power", "list"])) == 0
    assert capsys.readouterr().out.splitlines() == ["low-power\t0", "quiet\t0", "balanced\t1", "performance\t0"]


def test_panel_falls_back_to_omarchy_elsewhere(sysfs, monkeypatch):
    put(sysfs / "class/dmi/id/sys_vendor", "LENOVO")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda args, **kw: calls.append(args) or
                        subprocess.CompletedProcess(args, 0))
    cli.run(cli.build_parser().parse_args(["power", "set", "performance"]))
    assert calls == [["omarchy-powerprofiles-set", "autodetect", "performance"]]


def test_bar_gets_our_power_widget(tmp_path, monkeypatch):
    shell = tmp_path / "shell.json"
    shell.write_text(json.dumps({"bar": {"layout": {"right": [{"id": "omarchy.clock"}, {"id": "omarchy.power"}]}}}))
    monkeypatch.setattr(install, "shell_json", lambda: shell)
    assert install.use_bar_widget(install.POWER_WIDGET) == "replaced omarchy.power"
    assert json.loads(shell.read_text())["bar"]["layout"]["right"][1]["id"] == "hypr-screens.power"
    assert install.use_bar_widget(install.POWER_WIDGET) == "ok"


def test_turning_off_restores_the_limit_and_forgets_the_settings(sysfs, ppd, monkeypatch):
    cfg = config.default_config()
    samsung.set_mode(cfg, "quiet")
    samsung.full_once(cfg, True)
    config.save(cfg)
    scripts = []
    monkeypatch.setattr(samsung, "run_as_root", lambda text, graphical: scripts.append(text) or True)

    assert samsung.teardown()
    assert battery(sysfs, "charge_control_end_threshold") == "80"
    assert config.load()["samsung"] == {"limit": None, "mode": None, "full_once": False}
    assert f"rm -f {samsung.UDEV_RULE} {samsung.PPD_DROPIN}" in scripts[0]
    assert "systemctl try-restart power-profiles-daemon" in scripts[0]


def test_a_cancelled_turn_off_changes_nothing(sysfs, ppd, monkeypatch):
    cfg = config.default_config()
    samsung.set_mode(cfg, "quiet")
    config.save(cfg)
    monkeypatch.setattr(samsung, "run_as_root", lambda text, graphical: False)
    assert not samsung.teardown()
    assert config.load()["samsung"]["mode"] == "quiet"


@pytest.fixture()
def bar(tmp_path, monkeypatch):
    shell = tmp_path / "shell.json"
    shell.write_text(json.dumps({"bar": {"layout": {"right": [{"id": "omarchy.clock"}, {"id": "omarchy.power"}]}}}))
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    monkeypatch.setattr(install, "shell_json", lambda: shell)
    monkeypatch.setattr(install, "plugins_dir", lambda: plugins)
    monkeypatch.setattr(install, "has_omarchy_shell", lambda: True)
    monkeypatch.setattr(install.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0))
    return shell


def power_widget(shell: Path) -> str:
    return json.loads(shell.read_text())["bar"]["layout"]["right"][1]["id"]


def test_battery_panel_follows_samsung_control(bar):
    assert install.sync_power_panel(True) == "replaced omarchy.power"
    assert power_widget(bar) == "hypr-screens.power"
    assert (bar.parent / "plugins/hypr-screens.power").resolve() == install.PLUGINS["hypr-screens.power"]
    assert install.sync_power_panel(True) == "ok"

    assert install.sync_power_panel(False) == "restored omarchy.power"
    assert power_widget(bar) == "omarchy.power"
    assert install.sync_power_panel(False) == "ok"
