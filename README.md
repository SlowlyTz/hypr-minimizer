# hypr-minimizer + hypr-screens

Two small tools for [Hyprland](https://hyprland.org/), made for [Omarchy](https://omarchy.org/), in one repo:

- **hypr-minimizer** — minimize windows per desktop and get them back (last in, first out), undo, a window menu with icons, and **peek**: a minimized window slides in over your desktop without touching the layout.
- **hypr-screens** — remembers every monitor you plug in and gives each one its own **rotation, scale, resolution and position**, optionally only while another monitor is connected. Plus **one desktop**: with an external monitor, one screen keeps a single fixed desktop and desktops 1–10 live on the other.

Only window keys go on the keyboard. All settings are in a window (German UI, mouse or keyboard) that opens from a **tray icon**.

## Install

```bash
git clone https://github.com/SlowlyTz/hypr-minimizer.git ~/hypr-minimizer
~/hypr-minimizer/install.sh
```

The setup wizard asks for your shortcuts and writes everything else. Details: [docs/install.md](docs/install.md).

## Use

| Key | Does |
|---|---|
| `SUPER + M` | minimize window |
| `SUPER + I` | bring it back |
| `SUPER + .` | window menu (`-` = peek) |
| tray icon | settings: screens, one desktop, keys |

Everything else: **[docs/](docs/README.md)** — [daily cheat sheet](docs/daily.md) · [minimizer](docs/minimizer.md) · [screens](docs/screens.md) · [one desktop](docs/one-desktop.md) · [keys](docs/keys.md) · [troubleshooting](docs/troubleshooting.md)

## Requirements

- Hyprland ≥ 0.56 with a Lua config (the minimizer alone also works with older, string-dispatcher versions)
- Python ≥ 3.10; for the settings window GTK 4, libadwaita and PyGObject (Omarchy has them)
- Omarchy for the window menu and the bar widget; without it the window menu falls back to walker, wofi or rofi

## Repo layout

| Path | What |
|---|---|
| `minimizer.py` | hypr-minimizer |
| `hypr-screens`, `hypr_screens/` | hypr-screens (`hypr_screens/gui/`: tray + settings window) |
| `omarchy-plugin/` | window menu (Omarchy shell plugin) |
| `omarchy-workspaces/` | bar widget that knows the fixed screen |
| `install.sh` | installer + setup wizard |
| `docs/` | documentation |
| `tests/` | tests |

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

The tests fake `hyprctl`; nothing touches a running Hyprland. After editing QML, run `omarchy-restart-shell`.

## License

MIT — see [LICENSE](LICENSE).
