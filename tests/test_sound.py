"""Sound devices, app streams and force mute, against canned pactl output."""
import json

import pytest

from hypr_screens import config, sound

CARD = "alsa_card.pci-0000_00_1f.3-platform-skl_hda_dsp_generic"
BT_CARD = "bluez_card.5C_DC_49_73_41_5C"
SPEAKER_PROFILE = "HiFi (HDMI1, Mic1, Speaker)"
HEADPHONE_PROFILE = "HiFi (HDMI1, Headphones, Mic1)"
SPEAKER_KEY = f"{CARD}:[Out] Speaker"


def volume(value: int) -> dict:
    return {"front-left": {"value_percent": f"{value}%"}, "front-right": {"value_percent": f"{value}%"}}


def port(description, port_type, availability="available", profiles=(), **props):
    return {"description": description, "type": port_type.title(), "availability": availability,
            "profiles": list(profiles), "properties": {"port.type": port_type, **props}}


def card(active=HEADPHONE_PROFILE):
    return {
        "name": CARD,
        "active_profile": active,
        "properties": {"device.description": "HD Audio"},
        "profiles": {
            SPEAKER_PROFILE: {"available": True, "sinks": 2, "sources": 1, "priority": 10200},
            HEADPHONE_PROFILE: {"available": True, "sinks": 2, "sources": 1, "priority": 10100},
            "off": {"available": True, "sinks": 0, "sources": 0, "priority": 0},
        },
        "ports": {
            "[Out] HDMI1": port("HDMI / DisplayPort 1 Output", "hdmi", profiles=[SPEAKER_PROFILE, HEADPHONE_PROFILE],
                                **{"device.product.name": "B27-9"}),
            "[Out] Speaker": port("Speaker", "speaker", "availability unknown", [SPEAKER_PROFILE]),
            "[Out] Headphones": port("Headphones", "headphones", "not available", [HEADPHONE_PROFILE],
                                     **{"port.availability-group": "Headphone"}),
            "[In] Mic1": port("Digital Microphone", "mic", "availability unknown",
                              [SPEAKER_PROFILE, HEADPHONE_PROFILE]),
        },
    }


def sink(name, description, port_name, card_name=CARD, vol=100, mute=False, availability="available", index=1,
         api="alsa"):
    return {
        "index": index, "name": name, "description": description, "mute": mute, "volume": volume(vol),
        "active_port": port_name,
        "ports": [{"name": port_name, "availability": availability}],
        "properties": {"device.name": card_name, "device.api": api},
    }


BT = sink("bluez_output.5C.1", "Buds3 Pro", "headset-output", BT_CARD, vol=45, index=10, api="bluez5")
HDMI = sink(f"{CARD}.HiFi__HDMI1__sink", "HD Audio HDMI / DisplayPort 1 Output", "[Out] HDMI1", index=11)
HEADPHONES = sink(f"{CARD}.HiFi__Headphones__sink", "HD Audio Headphones", "[Out] Headphones",
                  availability="not available", index=12)
SPEAKER = sink(f"{CARD}.HiFi__Speaker__sink", "HD Audio Speaker", "[Out] Speaker", vol=50, index=13)


def by_key(devices):
    return {device["key"]: device for device in devices}


def test_outputs_name_devices_and_list_switched_off_speakers_with_their_profile():
    outputs = by_key(sound.devices("sink", [BT, HDMI, HEADPHONES], [card()], "bluez_output.5C.1"))

    assert outputs[f"{BT_CARD}:headset-output"]["label"] == "Buds3 Pro"
    assert outputs[f"{BT_CARD}:headset-output"]["default"] is True
    assert outputs[f"{CARD}:[Out] HDMI1"]["label"] == "Screen B27-9"
    # An unplugged jack makes no sound, so it is not offered.
    assert f"{CARD}:[Out] Headphones" not in outputs
    speaker = outputs[SPEAKER_KEY]
    assert speaker["label"] == "Laptop speakers"
    assert speaker["active"] is False and speaker["profile"] == SPEAKER_PROFILE


def test_active_speakers_are_not_listed_twice():
    outputs = sound.devices("sink", [BT, HDMI, SPEAKER], [card(active=SPEAKER_PROFILE)], "")
    assert [d["key"] for d in outputs].count(SPEAKER_KEY) == 1
    assert by_key(outputs)[SPEAKER_KEY]["active"] is True
    assert by_key(outputs)[SPEAKER_KEY]["volume"] == 50


def test_inputs_skip_monitors_and_name_the_built_in_mic():
    mic = sink(f"{CARD}.HiFi__Mic1__source", "HD Audio Digital Microphone", "[In] Mic1", index=20)
    monitor = dict(BT, name="bluez_output.5C.1.monitor", properties={"device.class": "monitor"})
    inputs = sound.devices("source", [mic, monitor], [card()], "")
    assert [d["label"] for d in inputs] == ["Laptop microphone"]


def test_app_streams_carry_name_icon_candidates_and_output():
    stream = {
        "index": 137, "sink": 10, "mute": False, "corked": True, "volume": volume(80),
        "properties": {"application.name": "Spotify", "media.name": "Song A", "application.process.binary": "spotify"},
    }
    (app,) = sound.app_streams([stream], [BT])
    assert app["label"] == "Spotify" and app["detail"] == "Song A"
    assert app["icons"] == ["spotify", "spotify"] and app["sink"] == "bluez_output.5C.1"
    assert app["volume"] == 80 and app["paused"] is True


def test_force_mute_silences_only_forced_devices_that_are_not_silent():
    entries = {SPEAKER_KEY: {"kind": "sink"}}
    assert sound.silence_commands(entries, "sink", [BT, SPEAKER], [card(active=SPEAKER_PROFILE)]) == [
        ["set-sink-mute", SPEAKER["name"], "1"],
        ["set-sink-volume", SPEAKER["name"], "0%"],
    ]
    silent = dict(SPEAKER, mute=True, volume=volume(0))
    assert sound.silence_commands(entries, "sink", [silent], [card(active=SPEAKER_PROFILE)]) == []


def test_enforce_does_nothing_without_force_mute(monkeypatch):
    calls = []
    monkeypatch.setattr(sound, "pactl", lambda *args: calls.append(args) or "")
    assert sound.enforce(config.default_config()) == 0
    assert calls == []


def test_force_mute_is_saved_with_the_volume_to_come_back_to(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    speaker = by_key(sound.devices("sink", [SPEAKER], [card(active=SPEAKER_PROFILE)], ""))[SPEAKER_KEY]
    cfg = config.load()
    sound.set_forced(cfg, speaker, True)
    config.save(cfg)

    entry = sound.forced(config.load())[SPEAKER_KEY]
    assert entry == {"kind": "sink", "label": "Laptop speakers", "volume": 50, "mute": False}

    calls = []
    monkeypatch.setattr(sound, "pactl", lambda *args: calls.append(args) or "")
    sound.release(speaker, entry)
    assert calls == [("set-sink-volume", SPEAKER["name"], "50%"), ("set-sink-mute", SPEAKER["name"], "0")]

    cfg = config.load()
    sound.set_forced(cfg, speaker, False)
    config.save(cfg)
    assert sound.forced(config.load()) == {}


def test_broken_force_mute_entries_are_dropped():
    cfg = config.normalize({"sound": {"force_mute": {"a": {"kind": "sink", "volume": "x"}, "b": "nope",
                                                     "c": {"kind": "speaker"}}}})
    assert cfg["sound"]["force_mute"] == {"a": {"kind": "sink", "label": "a", "volume": 0, "mute": False}}


@pytest.mark.parametrize("line, wanted", [
    (b"Event 'change' on sink #1698", True),
    (b"Event 'new' on source #12", True),
    (b"Event 'change' on card #3", True),
    (b"Event 'change' on sink-input #137", False),
    (b"Event 'remove' on source-output #5", False),
])
def test_guard_wakes_only_for_device_changes(line, wanted):
    assert sound.relevant(line) is wanted


def test_switching_speakers_on_keeps_the_default_output(monkeypatch):
    calls = []
    defaults = {"sink": ["bluez_output.5C.1", f"{CARD}.HiFi__Speaker__sink"], "source": ["mic", "mic"]}

    def fake(*args):
        calls.append(args)
        if args[0].startswith("get-default-"):
            return defaults[args[0].removeprefix("get-default-")].pop(0) + "\n"
        return ""

    monkeypatch.setattr(sound, "pactl", fake)
    monkeypatch.setattr(sound.time, "sleep", lambda seconds: None)
    sound.switch_on(CARD, SPEAKER_PROFILE)
    assert ("set-card-profile", CARD, SPEAKER_PROFILE) in calls
    assert ("set-default-sink", "bluez_output.5C.1") in calls
    assert ("set-default-source", "mic") not in calls


def test_percent_averages_channels():
    assert sound.percent(volume(45)) == 45
    assert sound.percent({"l": {"value_percent": "40%"}, "r": {"value_percent": "61%"}}) == 50
    assert sound.percent(None) == 0


def test_pactl_list_survives_garbage(monkeypatch):
    monkeypatch.setattr(sound, "pactl", lambda *args: "not json")
    assert sound.pactl_list("sinks") == []
    monkeypatch.setattr(sound, "pactl", lambda *args: json.dumps([{"name": "a"}, 3]))
    assert sound.pactl_list("sinks") == [{"name": "a"}]
