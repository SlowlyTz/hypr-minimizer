#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


MINIMIZED_WORKSPACE = "special:minimized"
LEGACY_STATE_FILE = Path("/tmp/hypr_minimizer_state.json")
BRAVE_APP_CLASS_RE = re.compile(r"^brave-([a-z]+)-Default$")
# Chromium URL web apps without a desktop file, e.g. chrome-web.whatsapp.com__-Default.
URL_APP_CLASS_RE = re.compile(r"^chrome-(.+?)__.*-Default$")
URL_APP_ICON = "web-browser"
MAX_UNDO_HISTORY = 5
PICKER_PLUGIN_ID = "hypr-minimizer.picker"
PICKER_TIMEOUT_SECONDS = 600
# A few frames for Hyprland to settle a window parked below the screen edge.
SLIDE_SETTLE_SECONDS = 0.05
# Hyprland events after which a peeked window may have gone out of sight.
PEEK_WATCH_EVENTS = {
    "workspace",
    "workspacev2",
    "focusedmon",
    "focusedmonv2",
    "closewindow",
    "movewindow",
    "movewindowv2",
    "monitorremoved",
    "monitorremovedv2",
    "activespecial",
    "activespecialv2",
}
HistoryEntry = dict[str, object]


def default_state_file() -> Path:
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    if runtime_dir:
        return Path(runtime_dir) / "hypr-minimizer" / "state.json"

    state_home = os.environ.get("XDG_STATE_HOME")
    if state_home:
        return Path(state_home) / "hypr-minimizer" / "state.json"

    return Path.home() / ".local" / "state" / "hypr-minimizer" / "state.json"


STATE_FILE = default_state_file()


def run_hyprctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["hyprctl", *args],
        check=True,
        text=True,
        capture_output=True,
    )


def _lua_dispatch_supported() -> bool | None:
    """Hyprland >= 0.56 expects Lua for `hyprctl dispatch`; older versions take strings."""
    global _LUA_DISPATCH
    if _LUA_DISPATCH is None:
        probe = subprocess.run(
            ["hyprctl", "dispatch", "hl.dsp.no_op()"],
            text=True,
            capture_output=True,
        )
        _LUA_DISPATCH = probe.returncode == 0
    return _LUA_DISPATCH


_LUA_DISPATCH: bool | None = None


def move_window(address: str, workspace: str, silent: bool = False) -> None:
    if _lua_dispatch_supported():
        follow = "false" if silent else "true"
        run_hyprctl(
            "dispatch",
            f"hl.dsp.window.move({{ workspace = '{workspace}', follow = {follow}, window = 'address:{address}' }})",
        )
    else:
        dispatcher = "movetoworkspacesilent" if silent else "movetoworkspace"
        run_hyprctl("dispatch", dispatcher, f"{workspace},address:{address}")


def focus_window(address: str) -> None:
    if _lua_dispatch_supported():
        run_hyprctl("dispatch", f"hl.dsp.focus({{ window = 'address:{address}' }})")
    else:
        run_hyprctl("dispatch", "focuswindow", f"address:{address}")


def set_floating(address: str, floating: bool) -> None:
    if _lua_dispatch_supported():
        action = "enable" if floating else "disable"
        run_hyprctl(
            "dispatch",
            f"hl.dsp.window.float({{ action = '{action}', window = 'address:{address}' }})",
        )
    else:
        dispatcher = "setfloating" if floating else "settiled"
        run_hyprctl("dispatch", dispatcher, f"address:{address}")


def place_window(address: str, geometry: list[int]) -> None:
    x, y, width, height = geometry
    if _lua_dispatch_supported():
        run_hyprctl(
            "dispatch",
            f"hl.dsp.window.resize({{ x = {width}, y = {height}, window = 'address:{address}' }})",
        )
        run_hyprctl(
            "dispatch",
            f"hl.dsp.window.move({{ x = {x}, y = {y}, window = 'address:{address}' }})",
        )
    else:
        run_hyprctl("dispatch", "resizewindowpixel", f"exact {width} {height},address:{address}")
        run_hyprctl("dispatch", "movewindowpixel", f"exact {x} {y},address:{address}")


def slide_in(address: str, workspace_id: str, x: int, y: int, below: int) -> None:
    """Bring a window onto a workspace from below the screen edge (Lua dispatch only)."""
    window = f"window = 'address:{address}'"

    def batch(*steps: str) -> None:
        # One eval runs within a single frame, so nothing is drawn in between.
        run_hyprctl("eval", "; ".join(f"hl.dispatch({step})" for step in steps))

    # Moving onto a workspace pulls a window back on screen, so it is parked
    # below the edge right afterwards, unanimated and unseen.
    batch(
        f"hl.dsp.window.set_prop({{ prop = 'no_anim', value = '1', {window} }})",
        f"hl.dsp.window.move({{ workspace = '{workspace_id}', follow = true, {window} }})",
        f"hl.dsp.window.move({{ x = {x}, y = {below}, {window} }})",
    )
    # Hyprland only takes the parked spot as the animation's start once a frame
    # has passed; re-enabling animations sooner fades it in at the target instead.
    time.sleep(SLIDE_SETTLE_SECONDS)
    batch(
        f"hl.dsp.window.set_prop({{ prop = 'no_anim', value = 'unset', {window} }})",
        f"hl.dsp.window.move({{ x = {x}, y = {y}, {window} }})",
    )


def move_animation_seconds() -> float:
    """How long Hyprland animates a window move, following its animation tree."""
    try:
        animations = json.loads(run_hyprctl("-j", "animations").stdout)[0]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError):
        return 0.0
    by_name = {
        animation.get("name"): animation
        for animation in animations
        if isinstance(animation, dict)
    }
    for name in ("windowsMove", "windows", "global"):
        animation = by_name.get(name)
        if animation is None or (name != "global" and not animation.get("overridden")):
            continue
        if not animation.get("enabled", True):
            return 0.0
        # Hyprland speeds are in deciseconds.
        return float(animation.get("speed") or 0) / 10
    return 0.0


def notify(summary: str, body: str) -> None:
    notify_send = shutil.which("notify-send")
    if not notify_send:
        return

    subprocess.run([notify_send, summary, body], check=False)


def read_json(path: Path) -> object:
    return json.loads(path.read_text())


def normalize_state(raw_state: object) -> dict[str, list[str]]:
    if not isinstance(raw_state, dict):
        return {}

    state: dict[str, list[str]] = {}
    for workspace_id, addresses in raw_state.items():
        if not isinstance(addresses, list):
            continue

        stack: list[str] = []
        seen: set[str] = set()
        for address in addresses:
            if not isinstance(address, str) or address in seen:
                continue
            stack.append(address)
            seen.add(address)

        if stack:
            state[str(workspace_id)] = stack

    return state


def normalize_history_entry(raw_entry: object) -> HistoryEntry | None:
    if not isinstance(raw_entry, dict):
        return None

    if "stacks" in raw_entry:
        workspace_id = raw_entry.get("workspace_id")
        if workspace_id is not None:
            workspace_id = str(workspace_id)
        return {
            "workspace_id": workspace_id,
            "stacks": normalize_state(raw_entry.get("stacks")),
        }

    return {
        "workspace_id": None,
        "stacks": normalize_state(raw_entry),
    }


def normalize_history(raw_history: object) -> list[HistoryEntry]:
    if not isinstance(raw_history, list):
        return []

    history: list[HistoryEntry] = []
    for snapshot in raw_history:
        entry = normalize_history_entry(snapshot)
        if entry is not None:
            history.append(entry)
    return history[-MAX_UNDO_HISTORY:]


def normalize_peek(raw_peek: object) -> dict[str, object] | None:
    if not isinstance(raw_peek, dict):
        return None

    address = raw_peek.get("address")
    origin = raw_peek.get("origin")
    workspace_id = raw_peek.get("workspace")
    if not isinstance(address, str) or origin is None or workspace_id is None:
        return None

    index = raw_peek.get("index")
    geometry = raw_peek.get("geometry")
    if not (
        isinstance(geometry, list)
        and len(geometry) == 4
        and all(isinstance(value, int) for value in geometry)
    ):
        geometry = None
    return {
        "address": address,
        "origin": str(origin),
        "workspace": str(workspace_id),
        "index": index if isinstance(index, int) else None,
        "floating": bool(raw_peek.get("floating")),
        "geometry": geometry,
    }


def normalize_storage(raw_storage: object) -> dict[str, object]:
    if isinstance(raw_storage, dict) and (
        "stacks" in raw_storage or "history" in raw_storage
    ):
        return {
            "stacks": normalize_state(raw_storage.get("stacks")),
            "history": normalize_history(raw_storage.get("history")),
            "peek": normalize_peek(raw_storage.get("peek")),
        }

    return {
        "stacks": normalize_state(raw_storage),
        "history": [],
        "peek": None,
    }


def load_storage(path: Path | None = None) -> dict[str, object]:
    path = path or STATE_FILE
    if not path.exists() and path == STATE_FILE and LEGACY_STATE_FILE.exists():
        path = LEGACY_STATE_FILE

    if not path.exists():
        return normalize_storage(None)

    try:
        return normalize_storage(read_json(path))
    except (json.JSONDecodeError, OSError):
        return normalize_storage(None)


def load_state(path: Path | None = None) -> dict[str, list[str]]:
    storage = load_storage(path)
    return storage["stacks"]  # type: ignore[return-value]


def load_history(path: Path | None = None) -> list[HistoryEntry]:
    storage = load_storage(path)
    return storage["history"]  # type: ignore[return-value]


def save_storage(storage: dict[str, object], path: Path | None = None) -> None:
    path = path or STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_storage(storage)
    path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")


def save_state(
    state: dict[str, list[str]],
    path: Path | None = None,
    history: list[HistoryEntry] | None = None,
) -> None:
    storage = load_storage(path)
    if history is None:
        history = storage["history"]  # type: ignore[assignment]

    save_storage({"stacks": state, "history": history, "peek": storage["peek"]}, path)


def push_undo_snapshot(
    history: list[HistoryEntry], state: dict[str, list[str]], workspace_id: str
) -> list[HistoryEntry]:
    snapshot: HistoryEntry = {
        "workspace_id": workspace_id,
        "stacks": normalize_state(state),
    }
    if history and history[-1] == snapshot:
        return history

    updated_history = [*history, snapshot]
    return updated_history[-MAX_UNDO_HISTORY:]


def workspace_state(
    state: dict[str, list[str]], workspace_id: str
) -> list[str]:
    return list(state.get(workspace_id, []))


def set_workspace_state(
    state: dict[str, list[str]], workspace_id: str, stack: list[str]
) -> None:
    if stack:
        state[workspace_id] = stack
        return

    state.pop(workspace_id, None)


def append_to_stack(
    state: dict[str, list[str]], workspace_id: str, address: str
) -> None:
    stack = state.setdefault(workspace_id, [])
    if address in stack:
        stack.remove(address)
    stack.append(address)


def extend_stack(
    state: dict[str, list[str]], workspace_id: str, addresses: list[str]
) -> None:
    for address in addresses:
        append_to_stack(state, workspace_id, address)


def insert_into_stack(
    state: dict[str, list[str]], workspace_id: str, address: str, index: int | None
) -> None:
    remove_address(state, address)
    stack = state.setdefault(workspace_id, [])
    position = len(stack) if index is None else max(0, min(index, len(stack)))
    stack.insert(position, address)


def remove_address(state: dict[str, list[str]], address: str) -> str | None:
    for workspace_id, stack in list(state.items()):
        if address not in stack:
            continue
        state[workspace_id] = [
            stack_address for stack_address in stack if stack_address != address
        ]
        if not state[workspace_id]:
            state.pop(workspace_id, None)
        return workspace_id
    return None


def workspace_for_address(
    state: dict[str, list[str]], address: str
) -> str | None:
    for workspace_id, stack in state.items():
        if address in stack:
            return workspace_id
    return None


def application_dirs() -> list[Path]:
    return [
        Path.home() / ".local" / "share" / "applications",
        Path("/usr/share/applications"),
    ]


_WM_CLASS_INDEX: dict[tuple[Path, ...], dict[str, Path]] = {}


def desktop_files_by_wm_class() -> dict[str, Path]:
    dirs = tuple(application_dirs())
    if dirs not in _WM_CLASS_INDEX:
        index: dict[str, Path] = {}
        for directory in dirs:
            for path in sorted(directory.glob("*.desktop")):
                wm_class = read_desktop_entry(path).get("StartupWMClass")
                if wm_class:
                    index.setdefault(wm_class, path)
        _WM_CLASS_INDEX[dirs] = index
    return _WM_CLASS_INDEX[dirs]


def desktop_file_for_class(window_class: str) -> Path | None:
    names = [f"{window_class}.desktop"]
    brave_match = BRAVE_APP_CLASS_RE.match(window_class)
    if brave_match:
        names.append(f"brave-{brave_match.group(1)}-Default.desktop")

    for name in names:
        for directory in application_dirs():
            path = directory / name
            if path.exists():
                return path

    return desktop_files_by_wm_class().get(window_class)


def read_desktop_entry(path: Path) -> dict[str, str]:
    entry: dict[str, str] = {}
    in_desktop_entry = False
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return entry

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#!") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_desktop_entry = line == "[Desktop Entry]"
            continue
        if not in_desktop_entry or "=" not in line:
            continue
        key, value = line.split("=", 1)
        entry[key] = value

    return entry


def workspace_key(workspace: object) -> str:
    """Stacks are keyed by workspace id, special workspaces (the scratchpad) by
    name: special ids are not stable, and moving a window takes the name."""
    if not isinstance(workspace, dict):
        return ""
    name = str(workspace.get("name") or "")
    if name.startswith("special:"):
        return name
    return str(workspace.get("id", ""))


def monitor_workspace_keys(monitor: dict) -> list[str]:
    """What a monitor shows, topmost first: an open special workspace (the
    scratchpad) covers the desktop underneath."""
    keys = []
    special = monitor.get("specialWorkspace")
    if (
        isinstance(special, dict)
        and str(special.get("name") or "").startswith("special:")
        and special.get("name") != MINIMIZED_WORKSPACE
    ):
        keys.append(workspace_key(special))
    if isinstance(monitor.get("activeWorkspace"), dict):
        keys.append(workspace_key(monitor["activeWorkspace"]))
    return keys


def get_active_window() -> tuple[str, str]:
    active_window = json.loads(run_hyprctl("-j", "activewindow").stdout)
    address = active_window.get("address", "")
    return address, workspace_key(active_window.get("workspace"))


def get_active_workspace_id() -> str:
    """The focused monitor's workspace, or the scratchpad while it is open there."""
    monitor = next(
        (monitor for monitor in get_monitors() if monitor.get("focused")), None
    )
    keys = monitor_workspace_keys(monitor) if monitor else []
    if not keys:
        raise RuntimeError("no focused monitor")
    return keys[0]


def get_monitors() -> list[dict]:
    monitors = json.loads(run_hyprctl("-j", "monitors").stdout)
    if not isinstance(monitors, list):
        return []
    return [monitor for monitor in monitors if isinstance(monitor, dict)]


def visible_workspace_ids() -> set[str]:
    return {key for monitor in get_monitors() for key in monitor_workspace_keys(monitor)}


def option_values(name: str) -> list[int]:
    """Read a numeric or CSS-style ("top right bottom left") Hyprland option."""
    option = json.loads(run_hyprctl("-j", "getoption", name).stdout)
    if not isinstance(option, dict):
        return [0]
    if isinstance(option.get("int"), int):
        return [option["int"]]
    raw = str(option.get("css") or option.get("custom") or "0")
    try:
        return [int(float(value)) for value in raw.split()] or [0]
    except ValueError:
        return [0]


def css_sides(values: list[int]) -> tuple[int, int, int, int]:
    """Expand 1-4 CSS values to (top, right, bottom, left)."""
    top = values[0]
    right = values[1] if len(values) > 1 else top
    bottom = values[2] if len(values) > 2 else top
    left = values[3] if len(values) > 3 else right
    return top, right, bottom, left


def monitor_size(monitor: dict) -> tuple[int, int]:
    """Logical size, as window coordinates see it."""
    scale = float(monitor.get("scale") or 1)
    width = round(monitor["width"] / scale)
    height = round(monitor["height"] / scale)
    if int(monitor.get("transform") or 0) % 2:
        width, height = height, width
    return width, height


def monitor_bottom(monitor: dict) -> int:
    return int(monitor.get("y") or 0) + monitor_size(monitor)[1]


def peek_target() -> tuple[str, list[int], int]:
    """The focused monitor's workspace, the area a lone tiled window takes on it
    and the y just below its bottom edge."""
    monitor = next(
        (monitor for monitor in get_monitors() if monitor.get("focused")), None
    )
    if monitor is None:
        raise RuntimeError("no focused monitor")

    width, height = monitor_size(monitor)

    reserved_left, reserved_top, reserved_right, reserved_bottom = (
        list(monitor.get("reserved") or []) + [0, 0, 0, 0]
    )[:4]
    gap_top, gap_right, gap_bottom, gap_left = css_sides(option_values("general:gaps_out"))
    border = option_values("general:border_size")[0]

    left = reserved_left + gap_left + border
    top = reserved_top + gap_top + border
    right = reserved_right + gap_right + border
    bottom = reserved_bottom + gap_bottom + border
    geometry = [
        int(monitor.get("x") or 0) + left,
        int(monitor.get("y") or 0) + top,
        width - left - right,
        height - top - bottom,
    ]
    return monitor_workspace_keys(monitor)[0], geometry, monitor_bottom(monitor)


def get_clients() -> list[dict]:
    clients = json.loads(run_hyprctl("-j", "clients").stdout)
    if not isinstance(clients, list):
        return []
    return [client for client in clients if isinstance(client, dict)]


def clients_by_address() -> dict[str, dict]:
    clients: dict[str, dict] = {}
    for client in get_clients():
        address = client.get("address")
        if isinstance(address, str):
            clients[address] = client
    return clients


def prune_missing(
    state: dict[str, list[str]], clients: dict[str, dict]
) -> dict[str, list[str]]:
    live_addresses = set(clients)
    pruned: dict[str, list[str]] = {}
    for workspace_id, stack in state.items():
        live_stack = [address for address in stack if address in live_addresses]
        if live_stack:
            pruned[workspace_id] = live_stack
    return pruned


def is_minimized(client: dict) -> bool:
    workspace = client.get("workspace")
    return isinstance(workspace, dict) and workspace.get("name") == MINIMIZED_WORKSPACE


def client_workspace_id(client: dict) -> str:
    return workspace_key(client.get("workspace"))


def prune_stale(
    state: dict[str, list[str]], clients: dict[str, dict]
) -> dict[str, list[str]]:
    """Drop windows that were closed or left the scratchpad without us."""
    minimized_clients = {
        address: client for address, client in clients.items() if is_minimized(client)
    }
    return prune_missing(state, minimized_clients)


def client_label(client: dict) -> str:
    app_name = client_app_name(client)
    title = str(client.get("title") or "")
    pid = client.get("pid")
    pid_label = f" pid:{pid}" if pid else ""
    detail = window_title_detail(app_name, title)
    if detail:
        return f"{app_name} - {detail}{pid_label}"
    return f"{app_name}{pid_label}"


def window_title_detail(app_name: str, title: str) -> str:
    if not title or title == app_name:
        return ""

    for separator in (" - ", " | "):
        prefix = f"{app_name}{separator}"
        if title.startswith(prefix):
            return title.removeprefix(prefix)

    if title.endswith(" - Brave"):
        return title.removesuffix(" - Brave")

    return title


def client_app_name(client: dict) -> str:
    window_class = str(client.get("class") or "unknown")
    desktop_file = desktop_file_for_class(window_class)
    if desktop_file:
        desktop_entry = read_desktop_entry(desktop_file)
        name = desktop_entry.get("Name")
        if name:
            return name

    url_app_match = URL_APP_CLASS_RE.match(window_class)
    if url_app_match:
        return url_app_match.group(1)

    initial_title = client.get("initialTitle")
    if isinstance(initial_title, str) and initial_title:
        return initial_title

    return window_class


def client_icon(client: dict) -> str:
    window_class = str(client.get("class") or "")
    desktop_file = desktop_file_for_class(window_class)
    if desktop_file:
        desktop_entry = read_desktop_entry(desktop_file)
        icon = desktop_entry.get("Icon")
        if icon:
            return icon

    if URL_APP_CLASS_RE.match(window_class):
        return URL_APP_ICON

    return window_class


def minimized_entries(prune: bool = False) -> list[dict[str, object]]:
    state = load_state()
    clients = clients_by_address()

    if prune:
        pruned_state = prune_stale(state, clients)
        if pruned_state != state:
            save_state(pruned_state)
        state = pruned_state

    entries: list[dict[str, object]] = []
    for workspace_id, stack in state.items():
        for stack_index, address in enumerate(stack):
            client = clients.get(address)
            if not client:
                continue
            entries.append(
                {
                    "workspace_id": workspace_id,
                    "address": address,
                    "stack_index": stack_index,
                    "app_name": client_app_name(client),
                    "class": client.get("class", ""),
                    "icon": client_icon(client),
                    "title": client.get("title", ""),
                    "pid": client.get("pid", ""),
                    "label": client_label(client),
                }
            )
    return entries


def stash() -> None:
    address, workspace_id = get_active_window()
    if end_peek() == address:
        # Minimizing a peeked window just hides it again.
        return
    if not address or not workspace_id:
        return

    state = load_state()
    history = push_undo_snapshot(load_history(), state, workspace_id)

    move_window(address, MINIMIZED_WORKSPACE, silent=True)

    append_to_stack(state, workspace_id, address)
    save_state(state, history=history)


def stash_others() -> None:
    end_peek()
    active_address, workspace_id = get_active_window()
    if not active_address or not workspace_id:
        return

    addresses: list[str] = []
    for client in get_clients():
        address = client.get("address")
        if not isinstance(address, str):
            continue
        if address != active_address and client_workspace_id(client) == workspace_id:
            addresses.append(address)

    if not addresses:
        return

    state = load_state()
    history = push_undo_snapshot(load_history(), state, workspace_id)

    moved_addresses: list[str] = []
    for address in addresses:
        move_window(address, MINIMIZED_WORKSPACE, silent=True)
        moved_addresses.append(address)

    extend_stack(state, workspace_id, moved_addresses)
    save_state(state, history=history)

    focus_window(active_address)


def restore_address(address: str, workspace_id: str | None = None) -> bool:
    end_peek()
    storage = load_storage()
    state = storage["stacks"]  # type: ignore[assignment]
    history = storage["history"]  # type: ignore[assignment]
    clients = clients_by_address()
    pruned_state = prune_stale(state, clients)

    origin_workspace = workspace_for_address(pruned_state, address)
    if not origin_workspace:
        if pruned_state != state:
            save_state(pruned_state, history=history)
        return False

    target_workspace = workspace_id or origin_workspace
    snapshot = pruned_state
    if target_workspace != origin_workspace:
        # The window now belongs here: undo re-minimizes it from this workspace.
        snapshot = normalize_state(pruned_state)
        remove_address(snapshot, address)
        append_to_stack(snapshot, target_workspace, address)
    history = push_undo_snapshot(history, snapshot, target_workspace)
    remove_address(pruned_state, address)

    move_window(address, str(target_workspace))
    focus_window(address)
    save_state(pruned_state, history=history)
    return True


def peek_address(address: str) -> bool:
    """Show a minimized window over the current workspace, sized like a lone tiled window."""
    end_peek()
    storage = load_storage()
    state = storage["stacks"]  # type: ignore[assignment]
    history = storage["history"]  # type: ignore[assignment]
    clients = clients_by_address()
    pruned_state = prune_stale(state, clients)

    origin_workspace = workspace_for_address(pruned_state, address)
    if not origin_workspace:
        if pruned_state != state:
            save_state(pruned_state, history=history)
        return False

    index = pruned_state[origin_workspace].index(address)
    remove_address(pruned_state, address)
    workspace_id, geometry, below = peek_target()
    client = clients[address]
    floating = bool(client.get("floating"))
    original_geometry = None
    if floating:
        original_geometry = [*client.get("at", [0, 0]), *client.get("size", [0, 0])]

    # Floating keeps the tiled windows underneath from reflowing. The size is
    # set while still hidden; the position only once it is on the workspace,
    # because moving it there (to another monitor) shifts it.
    if not floating:
        set_floating(address, True)
    place_window(address, geometry)
    if _lua_dispatch_supported():
        slide_in(address, workspace_id, geometry[0], geometry[1], below)
    else:
        move_window(address, workspace_id)
        place_window(address, geometry)
    focus_window(address)

    peek = {
        "address": address,
        "origin": origin_workspace,
        "workspace": workspace_id,
        "index": index,
        "floating": floating,
        "geometry": original_geometry,
    }
    save_storage({"stacks": pruned_state, "history": history, "peek": peek})
    spawn_peek_watcher(address)
    return True


def end_peek() -> str | None:
    """Minimize the peeked window again; returns its address if it was hidden."""
    storage = load_storage()
    peek = storage["peek"]
    if not isinstance(peek, dict):
        return None

    state = storage["stacks"]  # type: ignore[assignment]
    address = str(peek["address"])
    storage["peek"] = None
    client = clients_by_address().get(address)
    if client is None:
        save_storage(storage)
        return None

    showing = client_workspace_id(client) == peek["workspace"]
    if showing:
        slide_out(address, client)
        move_window(address, MINIMIZED_WORKSPACE, silent=True)
    if not peek["floating"]:
        set_floating(address, False)
    elif peek["geometry"]:
        place_window(address, peek["geometry"])  # type: ignore[arg-type]

    # A peeked window moved to another workspace by hand stays there.
    if showing or is_minimized(client):
        insert_into_stack(state, str(peek["origin"]), address, peek["index"])  # type: ignore[arg-type]
    save_storage(storage)
    return address if showing else None


def slide_out(address: str, client: dict) -> None:
    """Let a peek that is on screen leave through the bottom edge before hiding it."""
    if not _lua_dispatch_supported():
        return
    workspace_id = client_workspace_id(client)
    monitor = next(
        (
            monitor
            for monitor in get_monitors()
            if workspace_id in monitor_workspace_keys(monitor)
        ),
        None,
    )
    seconds = move_animation_seconds() if monitor else 0.0
    if seconds <= 0:
        return

    x = (client.get("at") or [0])[0]
    run_hyprctl(
        "dispatch",
        f"hl.dsp.window.move({{ x = {x}, y = {monitor_bottom(monitor)}, window = 'address:{address}' }})",  # type: ignore[arg-type]
    )
    time.sleep(seconds)


def spawn_peek_watcher(address: str) -> None:
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "watch-peek", address],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def check_peek(address: str) -> bool:
    """End the peek once its window is out of sight; False when there is nothing left to watch."""
    peek = load_storage()["peek"]
    if not isinstance(peek, dict) or peek["address"] != address:
        return False

    client = clients_by_address().get(address)
    if (
        client is not None
        and client_workspace_id(client) == peek["workspace"]
        and peek["workspace"] in visible_workspace_ids()
    ):
        return True

    end_peek()
    return False


def hyprland_event_socket() -> Path | None:
    signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not signature:
        return None

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR")
    candidates = [Path("/tmp") / "hypr" / signature / ".socket2.sock"]
    if runtime_dir:
        candidates.insert(0, Path(runtime_dir) / "hypr" / signature / ".socket2.sock")
    return next((path for path in candidates if path.exists()), None)


def watch_peek(address: str) -> None:
    """Re-minimize a peeked window as soon as its workspace is no longer shown."""
    path = hyprland_event_socket()
    if path is None:
        return

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as events:
        try:
            events.connect(str(path))
        except OSError:
            return

        if not check_peek(address):
            return

        buffer = b""
        while chunk := events.recv(4096):
            buffer += chunk
            *lines, buffer = buffer.split(b"\n")
            names = {line.partition(b">>")[0].decode(errors="replace") for line in lines}
            if names & PEEK_WATCH_EVENTS and not check_peek(address):
                return


def pop() -> None:
    end_peek()
    workspace_id = get_active_workspace_id()
    storage = load_storage()
    state = storage["stacks"]  # type: ignore[assignment]
    history = storage["history"]  # type: ignore[assignment]
    clients = clients_by_address()
    state = prune_stale(state, clients)
    history = push_undo_snapshot(history, state, workspace_id)
    workspace_stack = state.get(workspace_id, [])

    while workspace_stack:
        address = workspace_stack.pop()

        if workspace_stack:
            state[workspace_id] = workspace_stack
        else:
            state.pop(workspace_id, None)

        move_window(address, str(workspace_id))
        focus_window(address)
        save_state(state, history=history)
        return

    if workspace_id in state:
        state.pop(workspace_id, None)
        save_state(state, history=history)


def pop_all() -> None:
    end_peek()
    workspace_id = get_active_workspace_id()
    storage = load_storage()
    state = storage["stacks"]  # type: ignore[assignment]
    history = storage["history"]  # type: ignore[assignment]
    clients = clients_by_address()
    state = prune_stale(state, clients)
    history = push_undo_snapshot(history, state, workspace_id)
    workspace_stack = state.get(workspace_id, [])
    if not workspace_stack:
        if workspace_id in state:
            state.pop(workspace_id, None)
            save_state(state, history=history)
        return

    for address in reversed(workspace_stack):
        move_window(address, str(workspace_id))

    state.pop(workspace_id, None)
    save_state(state, history=history)


def undo() -> None:
    end_peek()
    workspace_id = get_active_workspace_id()
    storage = load_storage()
    state = storage["stacks"]  # type: ignore[assignment]
    history = storage["history"]  # type: ignore[assignment]
    if not history:
        return

    clients = clients_by_address()
    current_state = prune_stale(state, clients)
    history_index = next(
        (
            index
            for index in range(len(history) - 1, -1, -1)
            if history[index].get("workspace_id") == workspace_id
        ),
        None,
    )
    if history_index is None:
        save_state(current_state, history=history)
        return

    entry = history.pop(history_index)
    target_workspace_stack = workspace_state(
        prune_missing(entry.get("stacks", {}), clients), workspace_id
    )
    current_workspace_stack = workspace_state(current_state, workspace_id)

    restored_addresses = [
        address
        for address in current_workspace_stack
        if address not in target_workspace_stack
    ]
    minimized_addresses = [
        address
        for address in target_workspace_stack
        if address not in current_workspace_stack
    ]

    for address in minimized_addresses:
        move_window(address, MINIMIZED_WORKSPACE, silent=True)

    for address in restored_addresses:
        move_window(address, str(workspace_id))

    if restored_addresses:
        focus_window(restored_addresses[-1])

    set_workspace_state(current_state, workspace_id, target_workspace_stack)
    target_state = current_state
    save_state(target_state, history=history)


def clear_missing() -> None:
    state = load_state()
    pruned_state = prune_stale(state, clients_by_address())
    if pruned_state != state:
        save_state(pruned_state)


def print_list(as_json: bool) -> None:
    entries = minimized_entries(prune=True)
    if as_json:
        print(json.dumps(entries, indent=2, sort_keys=True))
        return

    for entry in entries:
        print(
            f"{entry['address']}\tworkspace:{entry['workspace_id']}\t"
            f"{entry['label']}"
        )


def workspace_label(workspace_id: object) -> str:
    """"scratchpad" for special:scratchpad, the number for a desktop."""
    return str(workspace_id).removeprefix("special:")


def menu_label(entry: dict[str, object], duplicate_app_names: set[str]) -> str:
    app_name = str(entry["app_name"])
    label = f"{app_name}  [ws {workspace_label(entry['workspace_id'])}]"
    if app_name not in duplicate_app_names:
        return label

    detail = window_title_detail(app_name, str(entry.get("title") or ""))
    if detail:
        return f"{label}  {detail}"

    return f"{label} ({entry['address']})"


def sort_menu_entries(
    entries: list[dict[str, object]], current_workspace_id: str
) -> list[dict[str, object]]:
    return sorted(
        entries,
        key=lambda entry: (
            str(entry["workspace_id"]) != current_workspace_id,
            str(entry["workspace_id"]),
            int(entry["stack_index"]),
        ),
    )


def picker_entry(entry: dict[str, object]) -> dict[str, object]:
    app_name = str(entry["app_name"])
    return {
        "address": entry["address"],
        "name": app_name,
        "detail": window_title_detail(app_name, str(entry.get("title") or "")),
        "icon": entry["icon"],
        "windowClass": entry["class"],
        "workspace": workspace_label(entry["workspace_id"]),
    }


def shell_picker_selection(entries: list[dict[str, object]]) -> str | None:
    """Ask the omarchy-shell picker plugin; None when it is not available."""
    omarchy_shell = shutil.which("omarchy-shell")
    if not omarchy_shell:
        return None

    with tempfile.TemporaryDirectory(prefix="hypr-minimizer-") as tmp:
        selection_file = Path(tmp) / "selection"
        done_file = Path(tmp) / "done"
        payload = {
            "prompt": "Minimized windows",
            "entries": [picker_entry(entry) for entry in entries],
            "selectionFile": str(selection_file),
            "doneFile": str(done_file),
        }
        result = subprocess.run(
            [omarchy_shell, "shell", "summon", PICKER_PLUGIN_ID, json.dumps(payload)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0 or result.stdout.strip() != "ok":
            return None

        deadline = time.monotonic() + PICKER_TIMEOUT_SECONDS
        while not done_file.exists():
            if time.monotonic() > deadline:
                return ""
            time.sleep(0.05)

        if not selection_file.exists():
            return ""
        return selection_file.read_text().strip()


def restore_selection(selection: str, current_workspace_id: str) -> int:
    """Apply a picker result: "origin|here|peek<TAB>address"."""
    if not selection:
        return 0

    target, _, address = selection.partition("\t")
    if not address:
        return 1

    if target == "peek":
        return 0 if peek_address(address) else 1

    workspace_id = current_workspace_id if target == "here" else None
    return 0 if restore_address(address, workspace_id) else 1


def menu_command() -> int:
    end_peek()
    entries = minimized_entries(prune=True)
    if not entries:
        notify("Minimized windows", "No minimized windows to restore")
        return 0

    current_workspace_id = get_active_workspace_id()
    entries = sort_menu_entries(entries, current_workspace_id)

    selection = shell_picker_selection(entries)
    if selection is not None:
        return restore_selection(selection, current_workspace_id)

    menu = (
        shutil.which("omarchy-menu-select")
        or shutil.which("omarchy-launch-walker")
        or shutil.which("walker")
        or shutil.which("wofi")
        or shutil.which("rofi")
    )
    if not menu:
        print(
            "hypr-minimizer: install omarchy, walker, wofi, or rofi to use the menu",
            file=sys.stderr,
        )
        return 1

    app_name_counts: dict[str, int] = {}
    for entry in entries:
        app_name = str(entry["app_name"])
        app_name_counts[app_name] = app_name_counts.get(app_name, 0) + 1
    duplicate_app_names = {
        app_name for app_name, count in app_name_counts.items() if count > 1
    }

    lines = [menu_label(entry, duplicate_app_names) for entry in entries]
    selections = [
        (line, str(entry["address"]))
        for line, entry in zip(lines, entries, strict=True)
    ]
    menu_input = "\n".join(lines) + "\n"

    menu_name = Path(menu).name
    if menu_name == "omarchy-menu-select":
        command = [menu, "Minimized windows", "--", "--width", "520"]
    elif menu_name in {"omarchy-launch-walker", "walker"}:
        command = [
            menu,
            "--dmenu",
            "--theme",
            "omarchy-default",
            "--placeholder",
            "Minimized windows",
            "--width",
            "520",
            "--maxheight",
            "220",
            "--minheight",
            "120",
            "--nohints",
        ]
    elif menu_name == "wofi":
        command = [menu, "--dmenu", "--prompt", "Minimized windows"]
    elif menu_name == "rofi":
        command = [menu, "-dmenu", "-p", "Minimized windows"]

    result = subprocess.run(command, input=menu_input, text=True, capture_output=True)
    if result.returncode != 0:
        return result.returncode

    selected = result.stdout.strip()
    if not selected:
        return 0

    for line, address in selections:
        if selected == line:
            return 0 if restore_address(address) else 1

    return 1


def first_run() -> None:
    """Start the shared setup wizard the first time a command runs in a terminal."""
    if not sys.stdin.isatty():
        return
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from hypr_screens import config as screens_config, setup
    except ImportError:
        return
    if not screens_config.exists():
        setup.run()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Workspace-aware LIFO minimizer for Hyprland."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("stash")
    subparsers.add_parser("stash_others")
    subparsers.add_parser("pop")
    subparsers.add_parser("pop_all")
    subparsers.add_parser("undo")
    subparsers.add_parser("clear-missing")
    subparsers.add_parser("menu")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--json", action="store_true")

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("address")
    restore_parser.add_argument(
        "--here",
        action="store_true",
        help="restore onto the current workspace instead of the original one",
    )

    peek_parser = subparsers.add_parser("peek")
    peek_parser.add_argument("address")

    watch_parser = subparsers.add_parser("watch-peek")
    watch_parser.add_argument("address")

    args = parser.parse_args()
    if args.command not in ("watch-peek", "list", "clear-missing"):
        first_run()

    if args.command == "stash":
        stash()
    elif args.command == "stash_others":
        stash_others()
    elif args.command == "pop":
        pop()
    elif args.command == "pop_all":
        pop_all()
    elif args.command == "undo":
        undo()
    elif args.command == "clear-missing":
        clear_missing()
    elif args.command == "list":
        print_list(args.json)
    elif args.command == "restore":
        workspace_id = get_active_workspace_id() if args.here else None
        raise SystemExit(0 if restore_address(args.address, workspace_id) else 1)
    elif args.command == "peek":
        raise SystemExit(0 if peek_address(args.address) else 1)
    elif args.command == "watch-peek":
        watch_peek(args.address)
    elif args.command == "menu":
        raise SystemExit(menu_command())


if __name__ == "__main__":
    main()
