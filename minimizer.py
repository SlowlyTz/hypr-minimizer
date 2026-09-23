#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


MINIMIZED_WORKSPACE = "special:minimized"
LEGACY_STATE_FILE = Path("/tmp/hypr_minimizer_state.json")
BRAVE_APP_CLASS_RE = re.compile(r"^brave-([a-z]+)-Default$")
MAX_UNDO_HISTORY = 5
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


def normalize_storage(raw_storage: object) -> dict[str, object]:
    if isinstance(raw_storage, dict) and (
        "stacks" in raw_storage or "history" in raw_storage
    ):
        return {
            "stacks": normalize_state(raw_storage.get("stacks")),
            "history": normalize_history(raw_storage.get("history")),
        }

    return {
        "stacks": normalize_state(raw_storage),
        "history": [],
    }


def load_storage(path: Path | None = None) -> dict[str, object]:
    path = path or STATE_FILE
    if not path.exists() and path == STATE_FILE and LEGACY_STATE_FILE.exists():
        path = LEGACY_STATE_FILE

    if not path.exists():
        return {"stacks": {}, "history": []}

    try:
        return normalize_storage(read_json(path))
    except (json.JSONDecodeError, OSError):
        return {"stacks": {}, "history": []}


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
    if history is None:
        history = load_history(path)

    save_storage({"stacks": state, "history": history}, path)


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


def desktop_file_for_class(window_class: str) -> Path | None:
    candidates = [
        Path.home() / ".local" / "share" / "applications" / f"{window_class}.desktop",
        Path("/usr/share/applications") / f"{window_class}.desktop",
    ]
    for path in candidates:
        if path.exists():
            return path

    brave_match = BRAVE_APP_CLASS_RE.match(window_class)
    if not brave_match:
        return None

    app_id = brave_match.group(1)
    brave_candidates = [
        Path.home()
        / ".local"
        / "share"
        / "applications"
        / f"brave-{app_id}-Default.desktop",
        Path("/usr/share/applications") / f"brave-{app_id}-Default.desktop",
    ]
    for path in brave_candidates:
        if path.exists():
            return path

    return None


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


def get_active_window() -> tuple[str, str]:
    active_window = json.loads(run_hyprctl("-j", "activewindow").stdout)
    address = active_window.get("address", "")
    workspace = active_window.get("workspace", {})
    workspace_id = str(workspace.get("id", "")) if isinstance(workspace, dict) else ""
    return address, workspace_id


def get_active_workspace_id() -> str:
    active_workspace = json.loads(run_hyprctl("-j", "activeworkspace").stdout)
    return str(active_workspace["id"])


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

    return window_class


def minimized_entries(prune: bool = False) -> list[dict[str, object]]:
    state = load_state()
    clients = clients_by_address()

    if prune:
        pruned_state = prune_missing(state, clients)
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
    if not address or not workspace_id:
        return

    state = load_state()
    history = push_undo_snapshot(load_history(), state, workspace_id)

    move_window(address, MINIMIZED_WORKSPACE, silent=True)

    append_to_stack(state, workspace_id, address)
    save_state(state, history=history)


def stash_others() -> None:
    active_address, workspace_id = get_active_window()
    if not active_address or not workspace_id:
        return

    addresses: list[str] = []
    for client in get_clients():
        address = client.get("address")
        client_workspace = client.get("workspace", {})
        if not isinstance(address, str) or not isinstance(client_workspace, dict):
            continue
        client_workspace_id = str(client_workspace.get("id"))
        if address != active_address and client_workspace_id == workspace_id:
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
    storage = load_storage()
    state = storage["stacks"]  # type: ignore[assignment]
    history = storage["history"]  # type: ignore[assignment]
    clients = clients_by_address()
    pruned_state = prune_missing(state, clients)

    if address not in clients:
        if pruned_state != state:
            save_state(pruned_state, history=history)
        return False

    target_workspace = workspace_id or workspace_for_address(pruned_state, address)
    if not target_workspace:
        return False
    history = push_undo_snapshot(history, pruned_state, target_workspace)
    remove_address(pruned_state, address)

    move_window(address, str(target_workspace))
    focus_window(address)
    save_state(pruned_state, history=history)
    return True


def pop() -> None:
    workspace_id = get_active_workspace_id()
    storage = load_storage()
    state = storage["stacks"]  # type: ignore[assignment]
    history = storage["history"]  # type: ignore[assignment]
    clients = clients_by_address()
    state = prune_missing(state, clients)
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
    workspace_id = get_active_workspace_id()
    storage = load_storage()
    state = storage["stacks"]  # type: ignore[assignment]
    history = storage["history"]  # type: ignore[assignment]
    clients = clients_by_address()
    state = prune_missing(state, clients)
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
    workspace_id = get_active_workspace_id()
    storage = load_storage()
    state = storage["stacks"]  # type: ignore[assignment]
    history = storage["history"]  # type: ignore[assignment]
    if not history:
        return

    clients = clients_by_address()
    current_state = prune_missing(state, clients)
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
    pruned_state = prune_missing(state, clients_by_address())
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


def menu_label(entry: dict[str, object], duplicate_app_names: set[str]) -> str:
    app_name = str(entry["app_name"])
    workspace_label = f"{app_name}  [ws {entry['workspace_id']}]"
    if app_name not in duplicate_app_names:
        return workspace_label

    detail = window_title_detail(app_name, str(entry.get("title") or ""))
    if detail:
        return f"{workspace_label}  {detail}"

    return f"{workspace_label} ({entry['address']})"


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


def menu_command() -> int:
    entries = minimized_entries(prune=True)
    if not entries:
        notify("Minimized windows", "No minimized windows to restore")
        return 0

    current_workspace_id = get_active_workspace_id()
    entries = sort_menu_entries(entries, current_workspace_id)

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

    args = parser.parse_args()

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
        raise SystemExit(0 if restore_address(args.address) else 1)
    elif args.command == "menu":
        raise SystemExit(menu_command())


if __name__ == "__main__":
    main()
