# Personalization

The **Appearance** section of the settings window (tray icon) has two pages, **Windows** and **Widgets**. A widget opens its own page and its colors a page under that one; the arrow in the title bar goes back.

## Windows

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
| **Visualizer** | bars moving with the sound playing (cava) | in the bar, on the desktop or both; the app it listens to; bars, style (from the bottom, mirrored from the middle, wave, dots, circle), room between bars, sensitivity, smoothing, peak marks |
| **Lyrics** | the words of the song playing, in time with the music (from lrclib.net) | highlight (current line, word by word, off), alignment, lines (1–10, typed in), hide while paused |
| **Clock** | time and date | style (digital, analog, flip cards, in words – "quarter past six" in the app's language), 24 or 12 hours, seconds, weekday, date format (long, medium, short, ISO or an own Qt pattern), a second time zone |
| **System** | CPU, memory and temperature with a curve of the last two minutes | each gauge on or off, curves on or off |
| **Now Playing** | the song playing: cover, title, artist, album, progress, time, buttons (back, play/pause, next – they take clicks, the rest of the desktop stays clickable) | the app it follows, cover beside or above the text, each part on or off, hide while nothing plays |
| **Weather** | the weather at the place set in Omarchy's weather panel (open-meteo): icon, temperature, place, feels like, humidity, wind, the next three days | Celsius or Fahrenheit, place, details, next days |
| **Calendar** | this month, today marked, the neighbouring months' days dimmed | week starts on Monday or Sunday, month name, week numbers |
| **Battery** | the charge as a ring (charging and low colors), percent, time left or until full | percent, time left, low at |
| **Network** | download and upload right now (all devices but loopback) with curves | curves |
| **Disks** | every disk once (btrfs subvolumes count as one; small boot partitions left out): used of its size, a bar | free space instead of used |

Every widget has its own **look**:

- an **accent color** (theme accent, theme text or white; the visualizer also a gradient) and an **opacity**,
- a **base color** that every part on the widget accent takes, and **colors** for each part on their own, on a page of their own: e.g. the clock's hours, colon, minutes, seconds, AM/PM, weekday and date, each gauge's label, value, curve and area, the visualizer's bars and tips. A part takes the widget's accent, a theme color (it follows a theme change) or an own color with transparency, or stays on its default,
- the **font**: family, weight and letter spacing,
- an **effect**: outline, shadow or glow, with its strength,
- a **background card**: corners, room around, opacity, and on request a blur of what is behind it.

When a widget shows (**Visibility**): only on some desktops (1–10 or the fixed screen; none picked: on every one), only while its desktop has no window, not on battery, and **above the windows** instead of behind them.

Every widget can show on the laptop screen, all external screens, all screens, or one particular external monitor (recognised by its make, model and serial, whatever port it is on).

- **Placing:** a widget switched on for the first time appears in the middle of the screen and arranging starts. While arranging, every screen with a widget shows just the wallpaper – an empty desktop – with the widgets on it: drag them, pull the handles on their frame to resize them, turn them with the wheel (5° a notch, 1° with Shift), then **Save** or **Cancel** in the bar at the top of the screen (Enter saves, Esc cancels). **Arrange** in the app starts it again later.
- **Colors while arranging:** "Colors" in the bar at the top switches from moving to coloring. A click on a widget opens a palette beside it – it never covers the widget or the bar, and it can be dragged by its title (it stays there while it does not hide the widget picked). First it colors the whole widget: its **base color**, which every part on "Widget accent" takes, from the theme's colors, the **wallpaper's** main colors, the own colors used last or an **own color** (saturation and brightness, hue, opacity, or typed as #rrggbb[aa]). **Color schemes** make all parts at once from the base: Theme (all defaults back), One color, Contrast, Pastel, Colorful, Muted. **Apply to all widgets** gives the others the same base and colors for the same kind of part (text, quieter parts). **Fine-tuning** opens the single parts (• marks the ones with an own color); then a click on a part of the widget – the clock's colon, a gauge's curve, the card – picks it directly. A color or scheme under the pointer shows on the widget at once; a click takes it. **Ctrl+Z** or ↶ takes back the last color change, "Reset" gives the whole widget its defaults back, "Default" one part. Esc closes the palette, a second Esc cancels. Save keeps colors and places together.
- **Resizing:** a corner scales the whole widget; an edge makes it only wider or taller (the visualizer's bars get thicker or longer, the system widget wider). The lyrics' box is their text: its height is shared by the visible lines and the font fills each line, a line too long for the width gets smaller or takes two rows. The clock always scales. The opposite side stays where it is, also on a turned widget. The size is set only here, not in the app.
- The place is a point on the screen as a fraction of its size, so it fits every chosen screen. With **Same place on every screen** off, each screen keeps its own place and size: arranging on a screen changes only that screen (a screen not arranged yet uses the widget's common place).
- **Layouts** (in the Widgets overview) keep all widgets as they are – settings, places, colors – under a name. Load one by hand, or let it load by itself: "Load with the screens connected now" ties it to exactly the connected screens, and the watcher loads it whenever those screens are connected again.
- **Lyrics:** the lines scroll – the next one slides up from below into the middle and grows, the last one moves on up and fades. At the start and end of a song the lines fill the box from the top or down to the bottom, so no slot stays empty. With "Current line" the line being sung is in the accent color. "Word by word" colors each word as it is sung: from the word times of the lyrics when lrclib has them (enhanced LRC), otherwise spread over the line by the length of the words – most songs only have times per line, so it is an estimate.
- The lyrics follow the player that is playing; while none plays, the one from before (or one with music rather than a video). **React to** picks one app instead (e.g. Spotify) for the lyrics and the visualizer; the visualizer then listens only to that app's sound (its PipeWire stream) and stays still while that app plays nothing here – it never listens to the microphone.
- With "Word by word" the word being sung fills up letter by letter. **Scroll time** sets how long a line takes to move on, **Size of the line being sung** how much bigger it is than the others.
- The visualizer fades out after two seconds of silence (cava sleeps then) and the desktop widgets hide while a window is fullscreen.
- The bar visualizer sits right after the desktops. cava gets installed from the Widgets tab when it is missing (password).

Under the hood: the shell plugin `omarchy-widgets/` (`hypr-screens.widgets`, a service plus a bar widget) reads `~/.config/hypr-screens/widgets.json`, which the app writes; the app talks to it with `omarchy-shell hypr-screens.widgets edit | editing | placements | done | cancel`, and the overlay saves through `hypr-screens widgets save`.
