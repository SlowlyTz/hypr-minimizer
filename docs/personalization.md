# Personalization

The **Personalization** page of the settings window (tray icon) starts with two buttons, **Window** and **Widgets**; each opens its page, and the arrow at the top left goes back.

## Window

Gaps between windows and at the screen edge, corner rounding, border width, blur (on/off, strength, quality) and the transparency of the active and the other windows.

- Nothing changes while you move the sliders. **Apply** (in the bar at the bottom of the window, always in reach) shows the new look; a dialog asks **Keep?** and puts the old look back after 15 seconds without an answer.
- **Presets** (Clean, Soft, Glass) only fill in the sliders.
- **Border colors:** "Own border colors" draws the active window's border as a gradient of two colors (with transparency) at an angle; off, the theme's border is back.
- **Animation speed:** Omarchy's animations (from its `looknfeel.lua`, and yours where you changed one) run 0.25× to 3× as fast.
- **See-through apps:** pick an open app and give its windows their own transparency, for the active window and the others (a window rule by window class).
- Taking app rules or the own border back takes a short reload of Hyprland; everything else changes live.
- **Reset to Omarchy default** (next to Apply) forgets the look; the Omarchy theme decides again (Hyprland reloads its config for that).

The look is saved in `~/.config/hypr-screens/config.json` under `look` and written into `~/.config/hypr/hypr_screens.lua`, which loads after the Omarchy theme and so wins over it.

## Widgets

Widgets sit on the desktop **behind the windows**. The Widgets page lists them with their switch and a short summary; each opens its own page with its settings in three parts – **Placement** (screens, size and place), **Content** and **Look**:

| Widget | Shows | Settings |
|---|---|---|
| **Visualizer** | bars moving with the sound playing (cava) | in the bar, on the desktop or both; bars, style (from the bottom or mirrored from the middle) |
| **Lyrics** | the words of the song playing, in time with the music (from lrclib.net) | highlight (current line, word by word, off), alignment, lines (1–10, typed in), hide while paused |
| **Clock** | time and date | 24 or 12 hours, date, seconds |
| **System** | CPU, memory and temperature with a curve of the last two minutes | each gauge on or off, curves on or off |

Every widget has its own **look**:

- an **accent color** (theme accent, theme text or white; the visualizer also a gradient) and an **opacity**,
- **colors** for each part on their own, on a page of their own: e.g. the clock's hours, colon, minutes, seconds, AM/PM, weekday and date, each gauge's label, value, curve and area, the visualizer's bars and tips. A part takes the widget's accent, a theme color (it follows a theme change) or an own color with transparency, or stays on its default,
- the **font**: family, weight and letter spacing,
- an **effect**: outline, shadow or glow, with its strength,
- a **background card**: corners, room around, opacity, and on request a blur of what is behind it.

Every widget can show on the laptop screen, all external screens, all screens, or one particular external monitor (recognised by its make, model and serial, whatever port it is on).

- **Placing:** a widget switched on for the first time appears in the middle of the screen and arranging starts. While arranging, every screen with a widget shows just the wallpaper – an empty desktop – with the widgets on it: drag them, pull the handles on their frame to resize them, turn them with the wheel (5° a notch, 1° with Shift), then **Save** or **Cancel** in the bar at the top of the screen (Enter saves, Esc cancels). **Arrange** in the app starts it again later.
- **Resizing:** a corner scales the whole widget; an edge makes it only wider or taller (the visualizer's bars get thicker or longer, the system widget wider). The lyrics' box is their text: its height is shared by the visible lines and the font fills each line, a line too long for the width gets smaller or takes two rows. The clock always scales. The opposite side stays where it is, also on a turned widget. The size is set only here, not in the app.
- The place is a point on the screen as a fraction of its size, so it fits every chosen screen.
- **Lyrics:** the lines scroll – the next one slides up from below into the middle and grows, the last one moves on up and fades. At the start and end of a song the lines fill the box from the top or down to the bottom, so no slot stays empty. With "Current line" the line being sung is in the accent color. "Word by word" colors each word as it is sung: from the word times of the lyrics when lrclib has them (enhanced LRC), otherwise spread over the line by the length of the words – most songs only have times per line, so it is an estimate.
- The lyrics follow the player that is playing; while none plays, the one from before (or one with music rather than a video).
- The visualizer fades out after two seconds of silence (cava sleeps then) and the desktop widgets hide while a window is fullscreen.
- The bar visualizer sits right after the desktops. cava gets installed from the Widgets tab when it is missing (password).

Under the hood: the shell plugin `omarchy-widgets/` (`hypr-screens.widgets`, a service plus a bar widget) reads `~/.config/hypr-screens/widgets.json`, which the app writes; the app talks to it with `omarchy-shell hypr-screens.widgets edit | editing | placements | done | cancel`, and the overlay saves through `hypr-screens widgets save`.
