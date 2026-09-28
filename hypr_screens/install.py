"""Wiring into the system: launchers, Omarchy shell plugins, the bar widget."""
import json
import shutil
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BIN = Path.home() / ".local" / "bin"
LAUNCHERS = {"hypr-minimizer": REPO / "minimizer.py", "hypr-screens": REPO / "hypr-screens"}
PLUGINS = {
    "hypr-minimizer.picker": REPO / "omarchy-plugin",
    "hypr-screens.menu": REPO / "omarchy-screens",
    "hypr-screens.workspaces": REPO / "omarchy-workspaces",
}
WORKSPACES_WIDGET = "hypr-screens.workspaces"


def plugins_dir() -> Path:
    return Path.home() / ".config" / "omarchy" / "plugins"


def shell_json() -> Path:
    return Path.home() / ".config" / "omarchy" / "shell.json"


def has_omarchy_shell() -> bool:
    return shutil.which("omarchy-shell") is not None and shutil.which("omarchy") is not None


def link(target: Path, link_path: Path) -> str:
    """Symlink link_path -> target; leaves foreign files alone."""
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink() or not link_path.exists():
        if link_path.is_symlink() and link_path.resolve() == target.resolve():
            return "ok"
        if link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(target)
        return "linked"
    backup = link_path.with_name(link_path.name + ".bak-hypr-screens")
    if not backup.exists():
        link_path.rename(backup)
        link_path.symlink_to(target)
        return f"linked (old one kept as {backup.name})"
    return "skipped: exists"


def install_launchers() -> dict[str, str]:
    return {name: link(target, BIN / name) for name, target in LAUNCHERS.items()}


def install_plugins(ids: list[str]) -> dict[str, str]:
    results = {plugin: link(PLUGINS[plugin], plugins_dir() / plugin) for plugin in ids}
    subprocess.run(["omarchy-shell", "shell", "rescanPlugins"], capture_output=True, text=True)
    for plugin in ids:
        if plugin == WORKSPACES_WIDGET:
            continue
        # A fresh rescan takes a moment before the plugin is known.
        for _ in range(10):
            done = subprocess.run(["omarchy", "plugin", "enable", plugin], capture_output=True, text=True)
            if done.returncode == 0:
                break
            time.sleep(0.5)
        else:
            results[plugin] += "; enable failed"
    return results


def use_bar_widget() -> str:
    """Swap the bar's workspaces widget for ours (shell.json reloads itself)."""
    path = shell_json()
    try:
        cfg = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return "no shell.json"
    layout = (cfg.get("bar") or {}).get("layout") or {}
    replaced = None
    for section in layout.values():
        for widget in section if isinstance(section, list) else []:
            if isinstance(widget, dict) and str(widget.get("id", "")).endswith(".workspaces"):
                replaced = widget["id"]
                widget["id"] = WORKSPACES_WIDGET
    if replaced is None:
        return "no workspaces widget in the bar"
    if replaced == WORKSPACES_WIDGET:
        return "ok"
    backup = path.with_name("shell.json.bak-hypr-screens")
    if not backup.exists():
        backup.write_text(path.read_text())
    path.write_text(json.dumps(cfg, indent=2) + "\n")
    return f"replaced {replaced}"


def start_watcher() -> None:
    subprocess.Popen(
        [str(LAUNCHERS["hypr-screens"]), "watch"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
