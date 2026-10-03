"""Background watcher: re-sync on monitor hotplug and config reloads, keep
force-muted sound devices silent (sound.guard), hold the Samsung charge
limit and performance mode (samsung.guard) and feed the virtual camera
(camera.guard), each in its own thread.

A hotplug arrives as a burst of events and settles over a moment, so events are
collected until SETTLE_SECONDS pass quietly, then one sync runs.
"""
import fcntl
import os
import socket
import sys
import threading
from pathlib import Path

from hypr_screens import camera, config, engine, install, samsung, sound

SETTLE_SECONDS = 1.0
EVENTS = {
    "monitoradded": "added",
    "monitoraddedv2": "added",
    "monitorremoved": "removed",
    "monitorremovedv2": "removed",
    "configreloaded": "reload",
}


def event_socket() -> Path | None:
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not signature:
        return None
    for base in (os.environ.get("XDG_RUNTIME_DIR"), "/tmp"):
        if base:
            path = Path(base) / "hypr" / signature / ".socket2.sock"
            if path.exists():
                return path
    return None


def kinds(lines: list[bytes]) -> set[str]:
    return {EVENTS[name] for name in (line.partition(b">>")[0].decode(errors="replace") for line in lines) if name in EVENTS}


def strongest(found: set[str]) -> str:
    """One sync per burst: plugging in wins over unplugging over a reload."""
    for kind in ("added", "removed", "reload"):
        if kind in found:
            return kind
    return ""


def log(message: str) -> None:
    print(f"hypr-screens watch: {message}", file=sys.stderr, flush=True)


def watch() -> int:
    lock = open(config.runtime_dir() / "watch.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("already running")
        return 0

    threading.Thread(target=sound.guard, daemon=True).start()
    threading.Thread(target=samsung.guard, daemon=True).start()
    threading.Thread(target=camera.guard, daemon=True).start()
    try:
        log(f"battery panel: {install.sync_power_panel(samsung.active())}")
    except Exception as error:  # the bar is a nicety; the watcher must run
        log(f"battery panel: {error}")

    path = event_socket()
    if path is None:
        log("no Hyprland event socket")
        return 1

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as events:
        events.connect(str(path))
        log(f"started, {engine.sync('added') or 'nothing to change'}")
        buffer = b""
        pending: set[str] = set()
        while True:
            events.settimeout(SETTLE_SECONDS if pending else None)
            try:
                chunk = events.recv(4096)
            except TimeoutError:
                kind = strongest(pending)
                pending.clear()
                log(f"{kind}: {engine.sync(kind) or 'nothing to change'}")
                continue
            if not chunk:
                return 0
            buffer += chunk
            *lines, buffer = buffer.split(b"\n")
            pending |= kinds(lines)
