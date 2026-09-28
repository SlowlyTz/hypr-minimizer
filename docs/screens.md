# Screens

Every monitor you ever plug in is remembered. Each one gets its own settings.

## Open the menu

`SUPER + SHIFT + .` (or `hypr-screens menu`)

```
Laptop            eDP-1 · 180° if HP 32f · one desktop if HP 32f   ●
── Favorites ──
HP 32f            DP-3                                           ★ ●
── Known screens ──
Fujitsu B27-9     not connected                                    ○
```

| Key | Does |
|---|---|
| `↑↓` | pick a screen |
| `Enter` | open its settings |
| `f` | favorite / unfavorite |
| `x` `x` | forget it (must be unplugged) |
| `s` | swap the fixed screen ([one-desktop.md](one-desktop.md)) |
| `Tab` | keys & options |
| `Esc` | close |

## Settings of one screen

| Key | Does |
|---|---|
| `↑↓` | pick a setting |
| `←→` | change the value (**applied and saved at once**) |
| `c` / `C` | condition: *always* → *if <other screen> connected* → … |
| `Esc` | back |

| Setting | Values |
|---|---|
| Rotation | as configured · 0° · 90° · 180° · 270° |
| Scale | as configured · auto · 1 · 1.25 · 1.5 · 2 |
| Resolution | as configured · preferred · every mode the screen offers |
| Position | as configured · left · right · above · below (of the laptop; external screens only) |
| One desktop | default · yes · no |

"as configured" = hypr-screens leaves it to your Hyprland config.

## Conditions

A setting can be tied to another screen being connected. Example: rotate the laptop only at the desk dock.

```bash
hypr-screens set Laptop rotation 180
hypr-screens when Laptop rotation "HP 32f"
```

Unplug the HP → the laptop goes back to normal. Plug it in → rotated again.

## From the terminal

Screens can be named by name, connector or id:

```bash
hypr-screens list
hypr-screens set "HP 32f" scale 1.25
hypr-screens set DP-3 position left
hypr-screens set Laptop rotation unset
hypr-screens favorite "HP 32f"
hypr-screens forget "Fujitsu B27-9 TS QHD"
```

## How it works (short)

- A watcher (`hypr-screens watch`) listens for plug/unplug and config reloads and applies the settings.
- It is started by `~/.config/hypr/hypr_screens.lua` when Hyprland starts.
- Settings are applied with `hl.monitor`. If a setting stops applying, the Hyprland config is reloaded once to get your normal values back.
- Screens are recognised by make, model and serial number, not by the port.

| What | Where |
|---|---|
| settings, known screens, keys | `~/.config/hypr-screens/config.json` |
| what is applied right now | `$XDG_RUNTIME_DIR/hypr-screens/applied.json` |
| menu plugin | `omarchy-screens/` → `~/.config/omarchy/plugins/hypr-screens.menu` |
