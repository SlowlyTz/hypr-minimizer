# Screens

Every monitor you ever plug in is remembered. Each one gets its own settings.

## Open the settings

Click the **monitor icon in the tray** (Omarchy: the `<` in the bar opens the tray).
Right-click: *Einstellungen öffnen* · *Festen Bildschirm tauschen* · *Beenden*.

From a terminal: `hypr-screens settings`

The window speaks English, German, Spanish, French or Italian (Settings → Language; English when a text is missing) and works with mouse or keyboard. Every change is saved and applied at once. Translations live in `hypr_screens/locales.json`, keyed by the English text.

## Page "Bildschirme"

1. Click a screen card at the top (● = connected, ★ = favorite).
2. Each setting has a short explanation and two dropdowns:
   - **Einstellung**: the value
   - **Gilt**: *Immer* (always) or *Nur mit „<other screen>“* (only while that screen is connected)

| Setting | Values |
|---|---|
| Drehung (rotation) | Standard · 0° · 90° · 180° · 270° |
| Größe (scale) | Standard · automatic · 100–200 % |
| Auflösung (resolution) | Standard · recommended · every mode the screen offers |
| Platz neben dem Laptop (position) | Standard · left · right · above · below (external screens only) |
| Nur ein Desktop | Standard · yes · no — see [one-desktop.md](one-desktop.md) |

"Standard" = hypr-screens leaves it to your Hyprland config.

**Gilt** only offers screens that are connected right now (plus one you already picked, marked *nicht angeschlossen*).

**Safety net:** when a change makes a screen take new values (rotation, scale, resolution, position), a dialog asks *Einstellung behalten?*. Without a click on **Behalten** it goes back after 20 seconds — like the display settings of other desktops.

Also on this page: **Favorit** switch, **Vergessen** (forget; only when the screen is unplugged, asks first).

## Conditions

Example: rotate the laptop only at the desk dock.
In the window: Laptop → Drehung → *180° – kopfüber* → Gilt → *Nur mit „HP 32f“*.
Or in a terminal:

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

- `hypr-screens tray` = the tray icon + window. `hypr-screens watch` = the background part that applies settings on plug/unplug and config reloads. Both start with Hyprland from `~/.config/hypr/hypr_screens.lua`.
- Settings are applied with `hl.monitor`. If a setting stops applying, the Hyprland config is reloaded once to get your normal values back.
- Screens are recognised by make, model and serial number, not by the port.
- The window needs GTK 4, libadwaita and PyGObject (on Omarchy: already there). It takes colors and font from your Omarchy theme.

| What | Where |
|---|---|
| settings, known screens, keys | `~/.config/hypr-screens/config.json` |
| what is applied right now | `$XDG_RUNTIME_DIR/hypr-screens/applied.json` |
