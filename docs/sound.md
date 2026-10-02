# Sound

The **Sound** page in the settings window (tray icon) controls every output, input and app — not only the default device.

## What is on the page

| Part | Shows | You can |
|---|---|---|
| **Ausgabe** | speakers, headphones, Bluetooth, monitors | volume, mute, make it the default, **Force Mute** |
| **Eingabe** | microphones | the same |
| **Apps** | apps playing sound right now, with icon and name | volume, mute, pick the output it plays on |

Sinks on an unplugged jack (e.g. headphones not plugged in, HDMI without a screen) are left out.

## Switched-off speakers

On some laptops the sound card drives *either* the speakers *or* the headphone jack, one profile each. While the headphone profile is active, the speakers show up grey with **Einschalten**: it switches the card to the speaker profile. The default output stays where it was, so Bluetooth keeps playing and you can set the speaker volume for later.

## Force Mute

Keeps a device silent for good: muted and at 0 %.

- Checked on every PipeWire device change and once a second, by `hypr-screens watch` (it starts with Hyprland), so it also works with the window closed.
- Anything that turns it back up — a volume key, an app, a profile switch, reconnecting — is undone right away.
- A force-muted device that is not there right now stays listed ("Nicht verbunden") and is silenced the moment it shows up.
- Switching it off brings back the volume and mute from before.

Saved in `~/.config/hypr-screens/config.json` under `sound.force_mute`, keyed by sound card and port, so it survives profile switches and reboots.

## Needs

`pactl` (PipeWire's `pipewire-pulse`, standard on Omarchy).
