#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path


STATE_FILE = Path("/tmp/hypr_minimizer_state.json")
MINIMIZED_WORKSPACE = "special:minimized"


def run_hyprctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["hyprctl", *args],
        check=True,
        text=True,
        capture_output=True,
    )


def load_state(path: Path | None = None) -> dict[str, list[str]]:
    path = path or STATE_FILE
    if not path.exists():
        return {}

    try:
        raw_state = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    if not isinstance(raw_state, dict):
        return {}

    state: dict[str, list[str]] = {}
    for workspace_id, addresses in raw_state.items():
        if isinstance(addresses, list):
            state[str(workspace_id)] = [
                address for address in addresses if isinstance(address, str)
            ]
    return state


def save_state(state: dict[str, list[str]], path: Path | None = None) -> None:
    path = path or STATE_FILE
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def get_active_window() -> tuple[str, str]:
    active_window = json.loads(run_hyprctl("-j", "activewindow").stdout)
    address = active_window["address"]
    workspace_id = str(active_window["workspace"]["id"])
    return address, workspace_id


def get_active_workspace_id() -> str:
    active_workspace = json.loads(run_hyprctl("-j", "activeworkspace").stdout)
    return str(active_workspace["id"])


def stash() -> None:
    address, workspace_id = get_active_window()
    if not address:
        return

    state = load_state()
    state.setdefault(workspace_id, []).append(address)
    save_state(state)

    run_hyprctl(
        "dispatch",
        "movetoworkspacesilent",
        f"{MINIMIZED_WORKSPACE},address:{address}",
    )


def pop() -> None:
    workspace_id = get_active_workspace_id()
    state = load_state()
    workspace_stack = state.get(workspace_id, [])
    if not workspace_stack:
        return

    address = workspace_stack.pop()
    if workspace_stack:
        state[workspace_id] = workspace_stack
    else:
        state.pop(workspace_id, None)
    save_state(state)

    run_hyprctl("dispatch", "movetoworkspace", f"{workspace_id},address:{address}")
    run_hyprctl("dispatch", "focuswindow", f"address:{address}")


def pop_all() -> None:
    workspace_id = get_active_workspace_id()
    state = load_state()
    workspace_stack = state.pop(workspace_id, [])
    if not workspace_stack:
        return
    save_state(state)

    while workspace_stack:
        address = workspace_stack.pop()
        run_hyprctl("dispatch", "movetoworkspace", f"{workspace_id},address:{address}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Workspace-aware LIFO minimizer for Hyprland."
    )
    parser.add_argument("command", choices=("stash", "pop", "pop_all"))
    args = parser.parse_args()

    if args.command == "stash":
        stash()
    elif args.command == "pop":
        pop()
    elif args.command == "pop_all":
        pop_all()


if __name__ == "__main__":
    main()
