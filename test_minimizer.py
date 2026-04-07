import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import minimizer


class HyprctlMock:
    def __init__(self, active_windows=None, active_workspaces=None):
        self.active_windows = list(active_windows or [])
        self.active_workspaces = list(active_workspaces or [])
        self.commands = []

    def __call__(self, args, check, text, capture_output):
        self.commands.append(args)

        if args == ["hyprctl", "-j", "activewindow"]:
            return Mock(stdout=json.dumps(self.active_windows.pop(0)))

        if args == ["hyprctl", "-j", "activeworkspace"]:
            return Mock(stdout=json.dumps(self.active_workspaces.pop(0)))

        return Mock(stdout="")


@pytest.fixture()
def state_file(tmp_path, monkeypatch):
    path = tmp_path / "hypr_minimizer_state.json"
    monkeypatch.setattr(minimizer, "STATE_FILE", path)
    return path


def read_state(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def test_stash_records_windows_in_lifo_order_per_workspace(state_file, monkeypatch):
    hyprctl = HyprctlMock(
        active_windows=[
            {"address": "0xaaa", "workspace": {"id": 1}},
            {"address": "0xbbb", "workspace": {"id": 1}},
            {"address": "0xccc", "workspace": {"id": 2}},
        ]
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.stash()
    minimizer.stash()
    minimizer.stash()

    assert read_state(state_file) == {"1": ["0xaaa", "0xbbb"], "2": ["0xccc"]}
    assert hyprctl.commands[-1] == [
        "hyprctl",
        "dispatch",
        "movetoworkspacesilent",
        "special:minimized,address:0xccc",
    ]


def test_pop_uses_lifo_order_for_current_workspace_only(state_file, monkeypatch):
    state_file.write_text(json.dumps({"1": ["0xaaa", "0xbbb"], "2": ["0xccc"]}))
    hyprctl = HyprctlMock(active_workspaces=[{"id": 1}])
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.pop()

    assert read_state(state_file) == {"1": ["0xaaa"], "2": ["0xccc"]}
    assert hyprctl.commands == [
        ["hyprctl", "-j", "activeworkspace"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xbbb"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xbbb"],
    ]


def test_pop_does_not_cross_workspace_boundaries(state_file, monkeypatch):
    state_file.write_text(json.dumps({"1": ["0xaaa"], "2": ["0xccc"]}))
    hyprctl = HyprctlMock(active_workspaces=[{"id": 3}])
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.pop()

    assert read_state(state_file) == {"1": ["0xaaa"], "2": ["0xccc"]}
    assert hyprctl.commands == [["hyprctl", "-j", "activeworkspace"]]


def test_pop_all_restores_only_current_workspace_in_lifo_order(state_file, monkeypatch):
    state_file.write_text(
        json.dumps({"1": ["0xaaa", "0xbbb", "0xddd"], "2": ["0xccc"]})
    )
    hyprctl = HyprctlMock(active_workspaces=[{"id": 1}])
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.pop_all()

    assert read_state(state_file) == {"2": ["0xccc"]}
    assert hyprctl.commands == [
        ["hyprctl", "-j", "activeworkspace"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xddd"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xbbb"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xaaa"],
    ]
