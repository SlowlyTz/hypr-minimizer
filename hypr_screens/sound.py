"""Sound: outputs, inputs and app streams through pactl (PipeWire's Pulse
server), plus force mute -- a device that has to stay silent.

Devices are keyed by card and port ("alsa_card...:[Out] Speaker"). That key
survives a profile switch, which recreates the sink under another name; a
device without a card port is keyed by its node name.

Force mute is kept by `guard()`, which runs inside `hypr-screens watch`: it
mutes the device and sets it to 0 % on every PipeWire change and once a second.
WirePlumber stores that state per port, so the device also comes back silent.
"""
import json
import os
import select
import subprocess
import sys
import time

from hypr_screens import config
from hypr_screens.i18n import t

GUARD_SECONDS = 1.0
VOLUME_MAX = 100
KINDS = ("sink", "source")
# What a port is called on the page, by its port.type.
PORT_LABELS = {
    "speaker": "Laptop speakers",
    "headphones": "Headphones (jack)",
}


def pactl(*args: str) -> str:
    try:
        return subprocess.run(["pactl", *args], check=False, text=True, capture_output=True).stdout
    except OSError:
        return ""


def pactl_list(what: str) -> list[dict]:
    try:
        result = json.loads(pactl("-f", "json", "list", what) or "[]")
    except json.JSONDecodeError:
        return []
    return [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []


def percent(volume: object) -> int:
    """Average of the channels, e.g. {"front-left": {"value_percent": "45%"}} -> 45."""
    if not isinstance(volume, dict):
        return 0
    values = []
    for channel in volume.values():
        try:
            values.append(int(str(channel.get("value_percent", "0")).rstrip("%")))
        except (AttributeError, ValueError):
            continue
    return round(sum(values) / len(values)) if values else 0


def port_direction(name: str) -> str:
    lowered = name.lower()
    if "[out]" in lowered or "output" in lowered:
        return "sink"
    if "[in]" in lowered or "input" in lowered:
        return "source"
    return ""


def device_key(card: str, port: str, name: str) -> str:
    return f"{card}:{port}" if card and port else name


def is_monitor(source: dict) -> bool:
    props = source.get("properties") or {}
    return props.get("device.class") == "monitor" or str(source.get("name", "")).endswith(".monitor")


def friendly_label(description: str, card_description: str, port: dict) -> str:
    """"Laptop speakers" rather than "Core Ultra 200V ... HD Audio Speaker"."""
    props = port.get("properties") or {}
    port_type = str(props.get("port.type") or port.get("type") or "").lower()
    if port_type in PORT_LABELS:
        return t(PORT_LABELS[port_type])
    if port_type == "mic":
        # A jack has an availability group (plugged or not); the built-in mic has none.
        return t("Microphone (jack)") if props.get("port.availability-group") else t("Laptop microphone")
    if port_type == "hdmi" and props.get("device.product.name"):
        return t("Screen {name}", name=props["device.product.name"])
    text = description
    if card_description and text.startswith(card_description):
        text = text[len(card_description):].strip()
    return text.removesuffix(" Output").removesuffix(" Input").strip() or description


def device_icon(kind: str, port_type: str, bluetooth: bool) -> str:
    if kind == "source":
        return "audio-input-microphone-symbolic"
    if bluetooth or port_type in ("headphones", "headset"):
        return "audio-headphones-symbolic"
    if port_type == "hdmi":
        return "video-display-symbolic"
    return "audio-speakers-symbolic"


# --- devices -------------------------------------------------------------------------


def card_index(cards: list[dict]) -> dict[str, dict]:
    return {str(card.get("name")): card for card in cards if card.get("name")}


def node_device(kind: str, node: dict, cards: dict[str, dict], default: str) -> dict:
    props = node.get("properties") or {}
    card_name = str(props.get("device.name") or "")
    card = cards.get(card_name, {})
    port_name = str(node.get("active_port") or "")
    port = next((p for p in node.get("ports") or [] if p.get("name") == port_name), {})
    # The card knows more about its ports (type, monitor name) than the sink does.
    port = {**port, **((card.get("ports") or {}).get(port_name) or {})}
    port_type = str(((port.get("properties") or {}).get("port.type") or port.get("type") or "")).lower()
    card_description = str((card.get("properties") or {}).get("device.description") or "")
    bluetooth = props.get("device.api") == "bluez5" or card_name.startswith("bluez")
    name = str(node.get("name") or "")
    description = str(node.get("description") or name)
    return {
        "kind": kind,
        "key": device_key(card_name, port_name, name),
        "name": name,
        "label": description if bluetooth else friendly_label(description, card_description, port),
        "detail": "Bluetooth" if bluetooth else card_description,
        "icon": device_icon(kind, port_type, bluetooth),
        "volume": percent(node.get("volume")),
        "mute": bool(node.get("mute")),
        "active": True,
        "default": name == default,
        "available": str(port.get("availability") or ""),
        "card": card_name,
        "profile": "",
    }


def idle_ports(kind: str, cards: dict[str, dict], taken: set[str]) -> list[dict]:
    """Ports of a sound card that no current profile drives -- e.g. the laptop
    speakers while the card sits on its headphone profile. Each comes with the
    best profile that would switch it on."""
    found = []
    for card_name, card in cards.items():
        if not card_name.startswith("alsa_card"):
            continue
        profiles = card.get("profiles") or {}
        active = card.get("active_profile")
        card_description = str((card.get("properties") or {}).get("device.description") or "")
        for port_name, port in (card.get("ports") or {}).items():
            key = device_key(card_name, port_name, "")
            if port_direction(port_name) != kind or key in taken:
                continue
            if port.get("availability") == "not available" or active in (port.get("profiles") or []):
                continue
            usable = [
                name for name in port.get("profiles") or []
                if (profiles.get(name) or {}).get("available") and (profiles.get(name) or {}).get(f"{kind}s", 0)
            ]
            if not usable:
                continue
            profile = max(usable, key=lambda name: (profiles[name].get("priority") or 0))
            port_type = str(((port.get("properties") or {}).get("port.type") or port.get("type") or "")).lower()
            found.append({
                "kind": kind,
                "key": key,
                "name": "",
                "label": friendly_label(str(port.get("description") or port_name), card_description, port),
                "detail": card_description,
                "icon": device_icon(kind, port_type, False),
                "volume": 0,
                "mute": False,
                "active": False,
                "default": False,
                "available": str(port.get("availability") or ""),
                "card": card_name,
                "profile": profile,
            })
    return found


def devices(kind: str, nodes: list[dict], cards: list[dict], default: str) -> list[dict]:
    """Every output (kind "sink") or input ("source"): the ones that exist, then
    switched-off card ports. Sinks on an unplugged port are left out unless
    they are the default -- they could not make a sound anyway."""
    by_name = card_index(cards)
    existing = [
        node_device(kind, node, by_name, default)
        for node in nodes
        if not (kind == "source" and is_monitor(node))
    ]
    shown = [d for d in existing if d["available"] != "not available" or d["default"]]
    return shown + idle_ports(kind, by_name, {d["key"] for d in existing})


def app_streams(inputs: list[dict], sinks: list[dict]) -> list[dict]:
    sink_names = {sink.get("index"): str(sink.get("name") or "") for sink in sinks}
    streams = []
    for stream in inputs:
        props = stream.get("properties") or {}
        label = str(props.get("application.name") or props.get("node.name") or t("Unknown"))
        media = str(props.get("media.name") or "")
        streams.append({
            "index": stream.get("index"),
            "label": label,
            "detail": "" if media.lower() in (label.lower(), "playback", "audio stream") else media,
            "icons": [name for name in (
                props.get("application.icon_name"),
                props.get("application.process.binary"),
                props.get("pipewire.access.portal.app_id"),
                label.lower(),
            ) if name],
            "search": label,
            "volume": percent(stream.get("volume")),
            "mute": bool(stream.get("mute")),
            "sink": sink_names.get(stream.get("sink"), ""),
            "paused": bool(stream.get("corked")),
        })
    return streams


def snapshot() -> dict:
    cards = pactl_list("cards")
    sinks = pactl_list("sinks")
    sources = pactl_list("sources")
    return {
        "outputs": devices("sink", sinks, cards, pactl("get-default-sink").strip()),
        "inputs": devices("source", sources, cards, pactl("get-default-source").strip()),
        "apps": app_streams(pactl_list("sink-inputs"), sinks),
    }


# --- changes -------------------------------------------------------------------------


def clamp(value: float) -> int:
    return max(0, min(VOLUME_MAX, round(value)))


def set_volume(kind: str, target: str, value: float) -> None:
    pactl(f"set-{kind}-volume", str(target), f"{clamp(value)}%")


def set_mute(kind: str, target: str, mute: bool) -> None:
    pactl(f"set-{kind}-mute", str(target), "1" if mute else "0")


def set_default(kind: str, name: str) -> None:
    pactl(f"set-default-{kind}", name)


def move_app(index: int, sink: str) -> None:
    pactl("move-sink-input", str(index), sink)


def switch_on(card: str, profile: str) -> None:
    """Switch a card to the profile that drives a port, keeping the default
    output and input where they are (a new sink must not take over)."""
    defaults = {kind: pactl(f"get-default-{kind}").strip() for kind in KINDS}
    pactl("set-card-profile", card, profile)
    time.sleep(0.3)
    for kind, name in defaults.items():
        if name and pactl(f"get-default-{kind}").strip() != name:
            set_default(kind, name)


# --- force mute ----------------------------------------------------------------------


def forced(cfg: dict) -> dict[str, dict]:
    return dict((cfg.get("sound") or {}).get("force_mute") or {})


def silence_commands(entries: dict[str, dict], kind: str, nodes: list[dict], cards: list[dict]) -> list[list[str]]:
    """pactl calls that make every force-muted device of this kind silent."""
    by_name = card_index(cards)
    commands = []
    for node in nodes:
        if kind == "source" and is_monitor(node):
            continue
        device = node_device(kind, node, by_name, "")
        if device["key"] not in entries:
            continue
        if not device["mute"]:
            commands.append([f"set-{kind}-mute", device["name"], "1"])
        if device["volume"] > 0:
            commands.append([f"set-{kind}-volume", device["name"], "0%"])
    return commands


def enforce(cfg: dict | None = None) -> int:
    """Silence force-muted devices that are not; returns how many calls it took."""
    entries = forced(cfg if cfg is not None else config.load())
    if not entries:
        return 0
    cards = pactl_list("cards")
    commands = []
    for kind in KINDS:
        commands += silence_commands(entries, kind, pactl_list(f"{kind}s"), cards)
    for command in commands:
        pactl(*command)
    return len(commands)


def set_forced(cfg: dict, device: dict, on: bool) -> None:
    """Remember (on) or forget (off) a force mute; the volume before it is kept
    so switching it off can bring the device back where it was."""
    sound = cfg.setdefault("sound", {})
    entries = sound.setdefault("force_mute", {})
    if on:
        entries[device["key"]] = {
            "kind": device["kind"],
            "label": device["label"],
            "volume": device["volume"] if device.get("active") else 0,
            "mute": bool(device.get("mute")) if device.get("active") else False,
        }
    else:
        entries.pop(device["key"], None)


def release(device: dict, entry: dict) -> None:
    """After force mute: back to the volume and mute from before."""
    if not device.get("active") or not device.get("name"):
        return
    set_volume(device["kind"], device["name"], entry.get("volume") or 0)
    set_mute(device["kind"], device["name"], bool(entry.get("mute")))


def relevant(line: bytes) -> bool:
    """`pactl subscribe` lines that can unmute a device ("on sink-input" cannot)."""
    return any(marker in line for marker in (b" on sink #", b" on source #", b" on card #", b" on server"))


def guard() -> None:
    """Keep force-muted devices silent: on every device change, and every second
    as a safety net. Restarts `pactl subscribe` when PipeWire restarts."""
    while True:
        try:
            with subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL) as events:
                fd = events.stdout.fileno()
                enforce()
                last = time.monotonic()
                while True:
                    ready, _, _ = select.select([fd], [], [], GUARD_SECONDS)
                    due = time.monotonic() - last >= GUARD_SECONDS
                    if ready:
                        chunk = os.read(fd, 65536)
                        if not chunk:
                            break
                        due = due or any(relevant(line) for line in chunk.splitlines())
                    if due:
                        enforce()
                        last = time.monotonic()
        except Exception as error:  # never take the watcher down
            print(f"hypr-screens sound guard: {error}", file=sys.stderr, flush=True)
        time.sleep(GUARD_SECONDS)
