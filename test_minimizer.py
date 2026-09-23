import json
from pathlib import Path
from unittest.mock import Mock

import pytest

import minimizer


class HyprctlMock:
    def __init__(self, active_windows=None, active_workspaces=None, clients=None):
        self.active_windows = list(active_windows or [])
        self.active_workspaces = list(active_workspaces or [])
        self.clients = list(clients or [])
        self.commands = []

    def __call__(self, args, check, text, capture_output):
        self.commands.append(args)

        if args == ["hyprctl", "-j", "activewindow"]:
            return Mock(stdout=json.dumps(self.active_windows.pop(0)))

        if args == ["hyprctl", "-j", "activeworkspace"]:
            return Mock(stdout=json.dumps(self.active_workspaces.pop(0)))

        if args == ["hyprctl", "-j", "clients"]:
            return Mock(stdout=json.dumps(self.clients.pop(0)))

        return Mock(stdout="")


@pytest.fixture(autouse=True)
def legacy_dispatch(monkeypatch):
    # Skip the Lua probe; tests assert the classic string dispatchers.
    monkeypatch.setattr(minimizer, "_LUA_DISPATCH", False)


@pytest.fixture()
def state_file(tmp_path, monkeypatch):
    path = tmp_path / "hypr-minimizer" / "state.json"
    monkeypatch.setattr(minimizer, "STATE_FILE", path)
    monkeypatch.setattr(minimizer, "LEGACY_STATE_FILE", tmp_path / "legacy-state.json")
    return path


def read_state(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    if isinstance(raw, dict) and "stacks" in raw:
        return raw["stacks"]
    return raw


def read_history(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        return []
    return raw.get("history", [])


def history_workspace_ids(path: Path) -> list[str | None]:
    return [entry.get("workspace_id") for entry in read_history(path)]


def client(
    address,
    workspace_id=1,
    window_class="app",
    title="Window",
    pid=1234,
    minimized=True,
):
    workspace = (
        {"id": -98, "name": "special:minimized"}
        if minimized
        else {"id": workspace_id, "name": str(workspace_id)}
    )
    return {
        "address": address,
        "workspace": workspace,
        "class": window_class,
        "title": title,
        "pid": pid,
    }


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


def test_stash_deduplicates_existing_window(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa", "0xbbb"]}))
    hyprctl = HyprctlMock(active_windows=[{"address": "0xaaa", "workspace": {"id": 1}}])
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.stash()

    assert read_state(state_file) == {"1": ["0xbbb", "0xaaa"]}


def test_undo_restores_last_stash(state_file, monkeypatch):
    hyprctl = HyprctlMock(
        active_windows=[{"address": "0xaaa", "workspace": {"id": 1}}],
        active_workspaces=[{"id": 1}],
        clients=[[client("0xaaa")]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.stash()
    minimizer.undo()

    assert read_state(state_file) == {}
    assert read_history(state_file) == []
    assert hyprctl.commands == [
        ["hyprctl", "-j", "activewindow"],
        [
            "hyprctl",
            "dispatch",
            "movetoworkspacesilent",
            "special:minimized,address:0xaaa",
        ],
        ["hyprctl", "-j", "activeworkspace"],
        ["hyprctl", "-j", "clients"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xaaa"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xaaa"],
    ]


def test_pop_uses_lifo_order_for_current_workspace_only(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa", "0xbbb"], "2": ["0xccc"]}))
    hyprctl = HyprctlMock(
        active_workspaces=[{"id": 1}],
        clients=[[client("0xaaa"), client("0xbbb"), client("0xccc", workspace_id=2)]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.pop()

    assert read_state(state_file) == {"1": ["0xaaa"], "2": ["0xccc"]}
    assert hyprctl.commands == [
        ["hyprctl", "-j", "activeworkspace"],
        ["hyprctl", "-j", "clients"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xbbb"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xbbb"],
    ]


def test_pop_prunes_closed_windows(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa", "0xmissing"], "2": ["0xccc"]}))
    hyprctl = HyprctlMock(
        active_workspaces=[{"id": 1}],
        clients=[[client("0xaaa"), client("0xccc", workspace_id=2)]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.pop()

    assert read_state(state_file) == {"2": ["0xccc"]}
    assert hyprctl.commands[-2:] == [
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xaaa"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xaaa"],
    ]


def test_undo_re_minimizes_last_pop(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa"]}))
    hyprctl = HyprctlMock(
        active_workspaces=[{"id": 1}, {"id": 1}],
        clients=[[client("0xaaa")], [client("0xaaa")]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.pop()
    minimizer.undo()

    assert read_state(state_file) == {"1": ["0xaaa"]}
    assert read_history(state_file) == []
    assert hyprctl.commands == [
        ["hyprctl", "-j", "activeworkspace"],
        ["hyprctl", "-j", "clients"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xaaa"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xaaa"],
        ["hyprctl", "-j", "activeworkspace"],
        ["hyprctl", "-j", "clients"],
        [
            "hyprctl",
            "dispatch",
            "movetoworkspacesilent",
            "special:minimized,address:0xaaa",
        ],
    ]


def test_stash_others_minimizes_current_workspace_except_active(
    state_file, monkeypatch
):
    hyprctl = HyprctlMock(
        active_windows=[{"address": "0xbbb", "workspace": {"id": 1}}],
        clients=[
            [
                client("0xaaa", minimized=False),
                client("0xbbb", minimized=False),
                client("0xccc", workspace_id=2, minimized=False),
                client("0xddd", minimized=False),
            ]
        ],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.stash_others()

    assert read_state(state_file) == {"1": ["0xaaa", "0xddd"]}
    assert hyprctl.commands == [
        ["hyprctl", "-j", "activewindow"],
        ["hyprctl", "-j", "clients"],
        [
            "hyprctl",
            "dispatch",
            "movetoworkspacesilent",
            "special:minimized,address:0xaaa",
        ],
        [
            "hyprctl",
            "dispatch",
            "movetoworkspacesilent",
            "special:minimized,address:0xddd",
        ],
        ["hyprctl", "dispatch", "focuswindow", "address:0xbbb"],
    ]


def test_pop_does_not_cross_workspace_boundaries(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa"], "2": ["0xccc"]}))
    hyprctl = HyprctlMock(
        active_workspaces=[{"id": 3}],
        clients=[[client("0xaaa"), client("0xccc", workspace_id=2)]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.pop()

    assert read_state(state_file) == {"1": ["0xaaa"], "2": ["0xccc"]}
    assert hyprctl.commands == [
        ["hyprctl", "-j", "activeworkspace"],
        ["hyprctl", "-j", "clients"],
    ]


def test_pop_all_restores_only_current_workspace_in_lifo_order(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(
        json.dumps({"1": ["0xaaa", "0xbbb", "0xddd"], "2": ["0xccc"]})
    )
    hyprctl = HyprctlMock(
        active_workspaces=[{"id": 1}],
        clients=[
            [
                client("0xaaa"),
                client("0xbbb"),
                client("0xccc", workspace_id=2),
                client("0xddd"),
            ]
        ],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.pop_all()

    assert read_state(state_file) == {"2": ["0xccc"]}
    assert hyprctl.commands == [
        ["hyprctl", "-j", "activeworkspace"],
        ["hyprctl", "-j", "clients"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xddd"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xbbb"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xaaa"],
    ]


def test_restore_address_restores_original_workspace(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa"], "2": ["0xccc"]}))
    hyprctl = HyprctlMock(clients=[[client("0xaaa"), client("0xccc", workspace_id=2)]])
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert minimizer.restore_address("0xccc")

    assert read_state(state_file) == {"1": ["0xaaa"]}
    assert hyprctl.commands == [
        ["hyprctl", "-j", "clients"],
        ["hyprctl", "dispatch", "movetoworkspace", "2,address:0xccc"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xccc"],
    ]


def test_undo_is_stackable_and_capped_to_five_steps(state_file, monkeypatch):
    hyprctl = HyprctlMock(
        active_windows=[
            {"address": "0x001", "workspace": {"id": 1}},
            {"address": "0x002", "workspace": {"id": 1}},
            {"address": "0x003", "workspace": {"id": 1}},
            {"address": "0x004", "workspace": {"id": 1}},
            {"address": "0x005", "workspace": {"id": 1}},
            {"address": "0x006", "workspace": {"id": 1}},
        ],
        active_workspaces=[
            {"id": 1},
            {"id": 1},
            {"id": 1},
            {"id": 1},
            {"id": 1},
        ],
        clients=[
            [client("0x001"), client("0x002"), client("0x003"), client("0x004"), client("0x005"), client("0x006")],
            [client("0x001"), client("0x002"), client("0x003"), client("0x004"), client("0x005"), client("0x006")],
            [client("0x001"), client("0x002"), client("0x003"), client("0x004"), client("0x005"), client("0x006")],
            [client("0x001"), client("0x002"), client("0x003"), client("0x004"), client("0x005"), client("0x006")],
            [client("0x001"), client("0x002"), client("0x003"), client("0x004"), client("0x005"), client("0x006")],
        ],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    for _ in range(6):
        minimizer.stash()

    assert len(read_history(state_file)) == 5

    for _ in range(5):
        minimizer.undo()

    assert read_state(state_file) == {"1": ["0x001"]}
    assert read_history(state_file) == []


def test_undo_only_consumes_history_for_current_workspace(state_file, monkeypatch):
    hyprctl = HyprctlMock(
        active_windows=[
            {"address": "0xaaa", "workspace": {"id": 1}},
            {"address": "0xbbb", "workspace": {"id": 2}},
        ],
        active_workspaces=[{"id": 1}, {"id": 2}],
        clients=[[client("0xaaa"), client("0xbbb", workspace_id=2)]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.stash()
    minimizer.stash()

    assert history_workspace_ids(state_file) == ["1", "2"]

    minimizer.undo()

    assert read_state(state_file) == {"2": ["0xbbb"]}
    assert history_workspace_ids(state_file) == ["2"]
    assert hyprctl.commands == [
        ["hyprctl", "-j", "activewindow"],
        [
            "hyprctl",
            "dispatch",
            "movetoworkspacesilent",
            "special:minimized,address:0xaaa",
        ],
        ["hyprctl", "-j", "activewindow"],
        [
            "hyprctl",
            "dispatch",
            "movetoworkspacesilent",
            "special:minimized,address:0xbbb",
        ],
        ["hyprctl", "-j", "activeworkspace"],
        ["hyprctl", "-j", "clients"],
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xaaa"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xaaa"],
    ]


def test_minimized_entries_include_window_metadata_and_prune_missing(
    state_file, monkeypatch
):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa", "0xmissing"]}))
    hyprctl = HyprctlMock(
        clients=[[client("0xaaa", window_class="Alacritty", title="shell", pid=42)]]
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert minimizer.minimized_entries(prune=True) == [
        {
            "workspace_id": "1",
            "address": "0xaaa",
            "stack_index": 0,
            "app_name": "Alacritty",
            "class": "Alacritty",
            "icon": "Alacritty",
            "title": "shell",
            "pid": 42,
            "label": "Alacritty - shell pid:42",
        }
    ]
    assert read_state(state_file) == {"1": ["0xaaa"]}


def test_brave_web_app_uses_desktop_file_name_and_icon(
    state_file, tmp_path, monkeypatch
):
    applications_dir = tmp_path / ".local" / "share" / "applications"
    applications_dir.mkdir(parents=True)
    desktop_file = applications_dir / "brave-iaaomclhaojnjcbgngbodcfnkgamlimo-Default.desktop"
    desktop_file.write_text(
        "\n".join(
            [
                "#!/usr/bin/env xdg-open",
                "[Desktop Entry]",
                "Name=Notion",
                "Icon=brave-iaaomclhaojnjcbgngbodcfnkgamlimo-Default",
                "StartupWMClass=crx_iaaomclhaojnjcbgngbodcfnkgamlimo",
            ]
        )
    )

    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa"]}))
    monkeypatch.setattr(minimizer.Path, "home", lambda: tmp_path)
    hyprctl = HyprctlMock(
        clients=[
            [
                client(
                    "0xaaa",
                    window_class="brave-iaaomclhaojnjcbgngbodcfnkgamlimo-Default",
                    title="Notion - Wiki | Startseite | Notion",
                    pid=4239,
                )
                | {"initialTitle": "Notion"}
            ]
        ]
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert minimizer.minimized_entries(prune=True) == [
        {
            "workspace_id": "1",
            "address": "0xaaa",
            "stack_index": 0,
            "app_name": "Notion",
            "class": "brave-iaaomclhaojnjcbgngbodcfnkgamlimo-Default",
            "icon": "brave-iaaomclhaojnjcbgngbodcfnkgamlimo-Default",
            "title": "Notion - Wiki | Startseite | Notion",
            "pid": 4239,
            "label": "Notion - Wiki | Startseite | Notion pid:4239",
        }
    ]


def test_menu_label_includes_workspace_number():
    entry = {
        "app_name": "Notion",
        "workspace_id": "3",
        "title": "Notion - Wiki | Startseite | Notion",
        "address": "0xaaa",
    }

    assert minimizer.menu_label(entry, set()) == "Notion  [ws 3]"
    assert (
        minimizer.menu_label(entry, {"Notion"})
        == "Notion  [ws 3]  Wiki | Startseite | Notion"
    )


def test_sort_menu_entries_prioritizes_current_workspace():
    entries = [
        {"workspace_id": "2", "stack_index": 1, "address": "0xbbb"},
        {"workspace_id": "1", "stack_index": 0, "address": "0xaaa"},
        {"workspace_id": "2", "stack_index": 0, "address": "0xccc"},
        {"workspace_id": "3", "stack_index": 0, "address": "0xddd"},
    ]

    sorted_entries = minimizer.sort_menu_entries(entries, "2")

    assert [entry["address"] for entry in sorted_entries] == [
        "0xccc",
        "0xbbb",
        "0xaaa",
        "0xddd",
    ]


def test_menu_does_not_auto_restore_single_entry_without_confirmation(
    state_file, monkeypatch
):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa"]}))

    hyprctl = HyprctlMock(
        active_workspaces=[{"id": 1}],
        clients=[
            [client("0xaaa", window_class="Alacritty", title="shell", pid=42)]
        ],
    )
    menu_calls = []

    def subprocess_run(args, check=False, text=True, capture_output=True, input=None):
        if args[:2] == ["hyprctl", "-j"]:
            return hyprctl(args, check=check, text=text, capture_output=capture_output)

        menu_calls.append({"args": args, "input": input})
        return Mock(returncode=0, stdout="")

    restore_calls = []

    monkeypatch.setattr(minimizer.subprocess, "run", subprocess_run)
    monkeypatch.setattr(
        minimizer.shutil,
        "which",
        lambda cmd: "/usr/bin/walker" if cmd == "walker" else None,
    )
    monkeypatch.setattr(
        minimizer, "restore_address", lambda address: restore_calls.append(address) or True
    )

    assert minimizer.menu_command() == 0
    assert restore_calls == []
    assert menu_calls == [
        {
            "args": [
                "/usr/bin/walker",
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
            ],
            "input": "Alacritty  [ws 1]\n",
        }
    ]


def test_lua_dispatch_moves_and_focuses_window(monkeypatch):
    monkeypatch.setattr(minimizer, "_LUA_DISPATCH", True)
    hyprctl = HyprctlMock()
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.move_window("0xaaa", "special:minimized", silent=True)
    minimizer.focus_window("0xaaa")

    assert hyprctl.commands == [
        [
            "hyprctl",
            "dispatch",
            "hl.dsp.window.move({ workspace = 'special:minimized', follow = false, window = 'address:0xaaa' })",
        ],
        ["hyprctl", "dispatch", "hl.dsp.focus({ window = 'address:0xaaa' })"],
    ]


def test_pop_skips_windows_restored_outside_the_minimizer(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa", "0xbbb"]}))
    hyprctl = HyprctlMock(
        active_workspaces=[{"id": 1}],
        clients=[[client("0xaaa"), client("0xbbb", workspace_id=4, minimized=False)]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.pop()

    assert read_state(state_file) == {}
    assert hyprctl.commands[-2:] == [
        ["hyprctl", "dispatch", "movetoworkspace", "1,address:0xaaa"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xaaa"],
    ]


def test_restore_address_rejects_window_no_longer_minimized(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa"], "2": ["0xccc"]}))
    hyprctl = HyprctlMock(
        clients=[[client("0xaaa"), client("0xccc", workspace_id=2, minimized=False)]]
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert not minimizer.restore_address("0xccc")

    assert read_state(state_file) == {"1": ["0xaaa"]}
    assert hyprctl.commands == [["hyprctl", "-j", "clients"]]
