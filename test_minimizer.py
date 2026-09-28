import json
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

import minimizer


class HyprctlMock:
    def __init__(
        self,
        active_windows=None,
        active_workspaces=None,
        clients=None,
        monitors=None,
        options=None,
    ):
        self.active_windows = list(active_windows or [])
        self.active_workspaces = list(active_workspaces or [])
        self.clients = list(clients or [])
        self.monitors = list(monitors or [])
        self.options = dict(options or {})
        self.commands = []

    def __call__(self, args, check, text, capture_output):
        self.commands.append(args)

        if args == ["hyprctl", "-j", "activewindow"]:
            return Mock(stdout=json.dumps(self.active_windows.pop(0)))

        if args == ["hyprctl", "-j", "activeworkspace"]:
            return Mock(stdout=json.dumps(self.active_workspaces.pop(0)))

        if args == ["hyprctl", "-j", "clients"]:
            return Mock(stdout=json.dumps(self.clients.pop(0)))

        if args == ["hyprctl", "-j", "monitors"]:
            return Mock(stdout=json.dumps(self.monitors.pop(0)))

        if args[:3] == ["hyprctl", "-j", "getoption"]:
            return Mock(stdout=json.dumps(self.options[args[3]]))

        return Mock(stdout="")


@pytest.fixture(autouse=True)
def legacy_dispatch(monkeypatch):
    # Skip the Lua probe; tests assert the classic string dispatchers.
    monkeypatch.setattr(minimizer, "_LUA_DISPATCH", False)


@pytest.fixture(autouse=True)
def no_monitor_manager(monkeypatch):
    # Keep the host's hypr-workspace out of menu tests.
    monkeypatch.setattr(minimizer, "MONITOR_MANAGER", "hypr-minimizer-test-missing")


@pytest.fixture(autouse=True)
def isolated_applications(tmp_path, monkeypatch):
    # Keep the host's desktop files out of name and icon lookups.
    applications_dir = tmp_path / ".local" / "share" / "applications"
    monkeypatch.setattr(minimizer, "application_dirs", lambda: [applications_dir])
    monkeypatch.setattr(minimizer, "_WM_CLASS_INDEX", {})
    return applications_dir


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


def test_restore_address_here_moves_window_to_given_workspace(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa"], "2": ["0xccc"]}))
    hyprctl = HyprctlMock(
        active_workspaces=[{"id": 3}],
        clients=[
            [client("0xaaa"), client("0xccc")],
            [client("0xaaa"), client("0xccc", workspace_id=3, minimized=False)],
        ],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert minimizer.restore_address("0xccc", "3")

    assert read_state(state_file) == {"1": ["0xaaa"]}
    assert hyprctl.commands[-2:] == [
        ["hyprctl", "dispatch", "movetoworkspace", "3,address:0xccc"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xccc"],
    ]

    # Undo on the current workspace re-minimizes it there.
    minimizer.undo()

    assert read_state(state_file) == {"1": ["0xaaa"], "3": ["0xccc"]}
    assert hyprctl.commands[-1] == [
        "hyprctl",
        "dispatch",
        "movetoworkspacesilent",
        "special:minimized,address:0xccc",
    ]


def test_app_name_and_icon_resolve_through_startup_wm_class(isolated_applications):
    isolated_applications.mkdir(parents=True)
    (isolated_applications / "chrome-hnpf-Default.desktop").write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Name=WhatsApp Web",
                "Icon=/icons/whatsapp.png",
                "StartupWMClass=crx_hnpf",
            ]
        )
    )
    window = client("0xaaa", window_class="crx_hnpf")

    assert minimizer.client_app_name(window) == "WhatsApp Web"
    assert minimizer.client_icon(window) == "/icons/whatsapp.png"


def test_url_web_app_without_desktop_file_uses_host_and_browser_icon():
    window = client("0xaaa", window_class="chrome-web.whatsapp.com__-Default") | {
        "initialTitle": "web.whatsapp.com_/"
    }

    assert minimizer.client_app_name(window) == "web.whatsapp.com"
    assert minimizer.client_icon(window) == "web-browser"


def fake_omarchy_shell(monkeypatch, reply, selection=None):
    """Stand in for `omarchy-shell shell summon`, answering like the picker plugin."""
    summons = []

    def subprocess_run(args, check=False, text=True, capture_output=True, input=None):
        payload = json.loads(args[-1])
        summons.append({"args": args[:-1], "payload": payload})
        if reply == "ok":
            if selection is not None:
                Path(payload["selectionFile"]).write_text(selection + "\n")
            Path(payload["doneFile"]).touch()
        return Mock(returncode=0, stdout=reply + "\n")

    monkeypatch.setattr(minimizer.subprocess, "run", subprocess_run)
    monkeypatch.setattr(
        minimizer.shutil,
        "which",
        lambda cmd: "/usr/bin/omarchy-shell" if cmd == "omarchy-shell" else None,
    )
    return summons


MENU_ENTRY = {
    "workspace_id": "2",
    "address": "0xaaa",
    "stack_index": 0,
    "app_name": "Foot",
    "class": "foot",
    "icon": "foot",
    "title": "Foot - vim",
    "pid": 42,
    "label": "Foot - vim pid:42",
}


def test_shell_picker_sends_entries_and_returns_selection(monkeypatch):
    summons = fake_omarchy_shell(monkeypatch, "ok", selection="here\t0xaaa")

    assert minimizer.shell_picker_selection([MENU_ENTRY]) == "here\t0xaaa"
    assert summons[0]["args"] == [
        "/usr/bin/omarchy-shell",
        "shell",
        "summon",
        "hypr-minimizer.picker",
    ]
    assert summons[0]["payload"]["entries"] == [
        {
            "address": "0xaaa",
            "name": "Foot",
            "detail": "vim",
            "icon": "foot",
            "windowClass": "foot",
            "workspace": "2",
        }
    ]


def test_shell_picker_cancel_returns_empty_selection(monkeypatch):
    fake_omarchy_shell(monkeypatch, "ok")

    assert minimizer.shell_picker_selection([MENU_ENTRY]) == ""


def test_shell_picker_unavailable_falls_back(monkeypatch):
    fake_omarchy_shell(monkeypatch, "unknown")

    assert minimizer.shell_picker_selection([MENU_ENTRY]) is None


@pytest.mark.parametrize(
    ("selection", "expected_workspace"),
    [("origin\t0xaaa", None), ("here\t0xaaa", "5")],
)
def test_restore_selection_targets_origin_or_current_workspace(
    monkeypatch, selection, expected_workspace
):
    calls = []
    monkeypatch.setattr(
        minimizer,
        "restore_address",
        lambda address, workspace_id=None: calls.append((address, workspace_id)) or True,
    )

    assert minimizer.restore_selection(selection, "5") == 0
    assert calls == [("0xaaa", expected_workspace)]


def test_restore_selection_ignores_cancel(monkeypatch):
    monkeypatch.setattr(minimizer, "restore_address", Mock())

    assert minimizer.restore_selection("", "5") == 0
    minimizer.restore_address.assert_not_called()


def peek_client(address, workspace_id=5):
    peeked = client(address, workspace_id=workspace_id, minimized=False)
    peeked["floating"] = True
    return peeked


OMARCHY_OPTIONS = {
    "general:gaps_out": {"option": "general:gaps_out", "css": "10 10 10 10", "set": True},
    "general:border_size": {"option": "general:border_size", "int": 2, "set": True},
}


def focused_monitor(workspace_id=5, **overrides):
    return {
        "focused": True,
        "x": 0,
        "y": 0,
        "width": 1920,
        "height": 1080,
        "scale": 1,
        "transform": 0,
        "reserved": [0, 26, 0, 0],
        "activeWorkspace": {"id": workspace_id},
        **overrides,
    }


def write_peek(state_file, stacks, peek):
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"stacks": stacks, "history": [], "peek": peek}))


PEEK = {
    "address": "0xbbb",
    "origin": "1",
    "workspace": "5",
    "index": 0,
    "floating": False,
    "geometry": None,
}


def test_peek_shows_window_in_the_tiled_area_of_current_workspace(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xaaa", "0xbbb", "0xccc"]}))
    tiled = client("0xbbb")
    tiled["floating"] = False
    hyprctl = HyprctlMock(
        clients=[[client("0xaaa"), tiled, client("0xccc")]],
        monitors=[[focused_monitor(workspace_id=6, focused=False), focused_monitor()]],
        options=OMARCHY_OPTIONS,
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)
    watchers = []
    monkeypatch.setattr(minimizer, "spawn_peek_watcher", watchers.append)

    assert minimizer.peek_address("0xbbb")

    # Same box a lone tiled window gets: bar, gaps_out and border left free.
    assert hyprctl.commands[-5:] == [
        ["hyprctl", "dispatch", "setfloating", "address:0xbbb"],
        ["hyprctl", "dispatch", "resizewindowpixel", "exact 1896 1030,address:0xbbb"],
        ["hyprctl", "dispatch", "movewindowpixel", "exact 12 38,address:0xbbb"],
        ["hyprctl", "dispatch", "movetoworkspace", "5,address:0xbbb"],
        ["hyprctl", "dispatch", "focuswindow", "address:0xbbb"],
    ]
    storage = json.loads(state_file.read_text())
    assert storage["stacks"] == {"1": ["0xaaa", "0xccc"]}
    assert storage["peek"] == {**PEEK, "index": 1}
    assert storage["history"] == []
    assert watchers == ["0xbbb"]


def test_peek_target_follows_monitor_offset_scale_and_gaps(monkeypatch):
    hyprctl = HyprctlMock(
        monitors=[[focused_monitor(x=1920, width=3840, height=2160, scale=2, reserved=[0, 0, 0, 30])]],
        options={
            "general:gaps_out": {"css": "5 20"},
            "general:border_size": {"int": 1},
        },
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert minimizer.peek_target() == ("5", [1920 + 21, 6, 1920 - 42, 1080 - 30 - 12])


def test_peek_restores_floating_window_geometry(state_file, monkeypatch):
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({"1": ["0xbbb"]}))
    floating = client("0xbbb")
    floating.update(floating=True, at=[300, 200], size=[800, 600])
    hyprctl = HyprctlMock(
        clients=[[floating], [peek_client("0xbbb")]],
        monitors=[[focused_monitor()]],
        options=OMARCHY_OPTIONS,
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)
    monkeypatch.setattr(minimizer, "spawn_peek_watcher", lambda address: None)

    assert minimizer.peek_address("0xbbb")
    assert ["hyprctl", "dispatch", "setfloating", "address:0xbbb"] not in hyprctl.commands
    assert json.loads(state_file.read_text())["peek"]["geometry"] == [300, 200, 800, 600]

    assert minimizer.end_peek() == "0xbbb"
    assert hyprctl.commands[-3:] == [
        ["hyprctl", "dispatch", "movetoworkspacesilent", "special:minimized,address:0xbbb"],
        ["hyprctl", "dispatch", "resizewindowpixel", "exact 800 600,address:0xbbb"],
        ["hyprctl", "dispatch", "movewindowpixel", "exact 300 200,address:0xbbb"],
    ]


def test_stash_on_peeked_window_minimizes_it_back_into_place(state_file, monkeypatch):
    write_peek(state_file, {"1": ["0xaaa"]}, PEEK)
    hyprctl = HyprctlMock(
        active_windows=[{"address": "0xbbb", "workspace": {"id": 5}}],
        clients=[[client("0xaaa"), peek_client("0xbbb")]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.stash()

    assert hyprctl.commands[-2:] == [
        ["hyprctl", "dispatch", "movetoworkspacesilent", "special:minimized,address:0xbbb"],
        ["hyprctl", "dispatch", "settiled", "address:0xbbb"],
    ]
    storage = json.loads(state_file.read_text())
    assert storage["stacks"] == {"1": ["0xbbb", "0xaaa"]}
    assert storage["peek"] is None
    assert storage["history"] == []


def test_stash_on_other_window_ends_peek_and_minimizes_it(state_file, monkeypatch):
    write_peek(state_file, {}, {**PEEK, "floating": True})
    hyprctl = HyprctlMock(
        active_windows=[{"address": "0xddd", "workspace": {"id": 5}}],
        clients=[[peek_client("0xbbb")]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    minimizer.stash()

    assert hyprctl.commands[-2:] == [
        ["hyprctl", "dispatch", "movetoworkspacesilent", "special:minimized,address:0xbbb"],
        ["hyprctl", "dispatch", "movetoworkspacesilent", "special:minimized,address:0xddd"],
    ]
    assert read_state(state_file) == {"1": ["0xbbb"], "5": ["0xddd"]}


def test_lua_end_peek_hides_then_retiles(state_file, monkeypatch):
    monkeypatch.setattr(minimizer, "_LUA_DISPATCH", True)
    write_peek(state_file, {}, PEEK)
    hyprctl = HyprctlMock(clients=[[peek_client("0xbbb")]])
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert minimizer.end_peek() == "0xbbb"

    assert hyprctl.commands[1:] == [
        [
            "hyprctl",
            "dispatch",
            "hl.dsp.window.move({ workspace = 'special:minimized', follow = false, window = 'address:0xbbb' })",
        ],
        [
            "hyprctl",
            "dispatch",
            "hl.dsp.window.float({ action = 'disable', window = 'address:0xbbb' })",
        ],
    ]


def test_end_peek_keeps_window_moved_elsewhere_by_hand(state_file, monkeypatch):
    write_peek(state_file, {}, {**PEEK, "floating": True})
    hyprctl = HyprctlMock(clients=[[peek_client("0xbbb", workspace_id=7)]])
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert minimizer.end_peek() is None

    assert hyprctl.commands == [["hyprctl", "-j", "clients"]]
    storage = json.loads(state_file.read_text())
    assert storage["stacks"] == {}
    assert storage["peek"] is None


def test_end_peek_forgets_closed_window(state_file, monkeypatch):
    write_peek(state_file, {"1": ["0xaaa"]}, PEEK)
    hyprctl = HyprctlMock(clients=[[client("0xaaa")]])
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert minimizer.end_peek() is None

    storage = json.loads(state_file.read_text())
    assert storage["stacks"] == {"1": ["0xaaa"]}
    assert storage["peek"] is None


def test_check_peek_keeps_window_while_its_workspace_is_shown(state_file, monkeypatch):
    write_peek(state_file, {}, PEEK)
    hyprctl = HyprctlMock(
        clients=[[peek_client("0xbbb")]],
        monitors=[[{"activeWorkspace": {"id": 5}}]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert minimizer.check_peek("0xbbb")
    assert json.loads(state_file.read_text())["peek"] == PEEK


def test_check_peek_minimizes_window_after_workspace_switch(state_file, monkeypatch):
    write_peek(state_file, {}, PEEK)
    hyprctl = HyprctlMock(
        clients=[[peek_client("0xbbb")], [peek_client("0xbbb")]],
        monitors=[[{"activeWorkspace": {"id": 6}}]],
    )
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert not minimizer.check_peek("0xbbb")

    assert [
        "hyprctl",
        "dispatch",
        "movetoworkspacesilent",
        "special:minimized,address:0xbbb",
    ] in hyprctl.commands
    storage = json.loads(state_file.read_text())
    assert storage["stacks"] == {"1": ["0xbbb"]}
    assert storage["peek"] is None


def test_check_peek_stops_watching_a_replaced_peek(state_file, monkeypatch):
    write_peek(state_file, {}, PEEK)
    hyprctl = HyprctlMock()
    monkeypatch.setattr(minimizer.subprocess, "run", hyprctl)

    assert not minimizer.check_peek("0xaaa")
    assert hyprctl.commands == []


def test_save_state_keeps_active_peek(state_file):
    write_peek(state_file, {}, PEEK)

    minimizer.save_state({"2": ["0xccc"]})

    storage = json.loads(state_file.read_text())
    assert storage["stacks"] == {"2": ["0xccc"]}
    assert storage["peek"] == PEEK


def test_restore_selection_peeks(monkeypatch):
    calls = []
    monkeypatch.setattr(minimizer, "peek_address", lambda address: calls.append(address) or True)

    assert minimizer.restore_selection("peek\t0xaaa", "5") == 0
    assert calls == ["0xaaa"]


def test_watch_peek_rechecks_on_workspace_events(tmp_path, monkeypatch):
    socket_path = tmp_path / ".socket2.sock"
    server = minimizer.socket.socket(minimizer.socket.AF_UNIX, minimizer.socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(1)
    monkeypatch.setattr(minimizer, "hyprland_event_socket", lambda: socket_path)
    checks = iter([True, False])
    calls = []
    monkeypatch.setattr(
        minimizer, "check_peek", lambda address: calls.append(address) or next(checks)
    )

    def send_events():
        connection, _ = server.accept()
        with connection:
            # Unrelated events are skipped; a split workspace event triggers the check.
            connection.sendall(b"activelayout>>kb,German\nworkspa")
            connection.sendall(b"cev2>>6,6\n")

    sender = threading.Thread(target=send_events)
    sender.start()
    minimizer.watch_peek("0xbbb")
    sender.join()
    server.close()

    assert calls == ["0xbbb", "0xbbb"]


MONITORS = {
    "panel": "eDP-1",
    "external": "HDMI-A-1",
    "description": "Fujitsu B27-9",
    "fixed": "external",
}


def fake_monitor_manager(monkeypatch, stdout, returncode=0):
    calls = []

    def subprocess_run(args, check=False, text=True, capture_output=True):
        calls.append(args)
        return Mock(returncode=returncode, stdout=stdout)

    monkeypatch.setattr(minimizer.subprocess, "run", subprocess_run)
    monkeypatch.setattr(
        minimizer.shutil,
        "which",
        lambda cmd: "/bin/hypr-workspace" if cmd == minimizer.MONITOR_MANAGER else None,
    )
    return calls


def test_monitor_status_reads_manager_json(monkeypatch):
    calls = fake_monitor_manager(monkeypatch, json.dumps(MONITORS))

    assert minimizer.monitor_status() == MONITORS
    assert calls == [["/bin/hypr-workspace", "status"]]


@pytest.mark.parametrize(
    ("stdout", "returncode"),
    [(json.dumps({"panel": "eDP-1", "external": None}), 0), ("garbage", 0), ("", 1)],
)
def test_monitor_status_is_none_without_external_monitor(monkeypatch, stdout, returncode):
    fake_monitor_manager(monkeypatch, stdout, returncode)

    assert minimizer.monitor_status() is None


def test_monitor_status_is_none_without_manager():
    assert minimizer.monitor_status() is None


def test_restore_selection_sets_fixed_screen(monkeypatch):
    calls = fake_monitor_manager(monkeypatch, "")

    assert minimizer.restore_selection("fixed\tpanel", "5") == 0
    assert calls == [["/bin/hypr-workspace", "fixed", "panel"]]
    assert minimizer.restore_selection("fixed\tbogus", "5") == 1
    assert len(calls) == 1


def test_menu_opens_monitor_page_without_minimized_windows(monkeypatch):
    monkeypatch.setattr(minimizer, "minimized_entries", lambda prune=False: [])
    monkeypatch.setattr(minimizer, "monitor_status", lambda: MONITORS)
    monkeypatch.setattr(minimizer, "get_active_workspace_id", lambda: "1")
    summons = []
    monkeypatch.setattr(
        minimizer,
        "shell_picker_selection",
        lambda entries, monitors=None: summons.append((entries, monitors)) or "",
    )
    notify = Mock()
    monkeypatch.setattr(minimizer, "notify", notify)

    assert minimizer.menu_command() == 0
    assert summons == [([], MONITORS)]
    notify.assert_not_called()


def test_shell_picker_passes_monitors(monkeypatch):
    summons = fake_omarchy_shell(monkeypatch, "ok", selection="fixed\tpanel")

    assert minimizer.shell_picker_selection([], MONITORS) == "fixed\tpanel"
    assert summons[0]["payload"]["monitors"] == MONITORS
    assert summons[0]["payload"]["entries"] == []
