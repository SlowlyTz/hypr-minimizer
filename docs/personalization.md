# Personalization

The **Personalization** page of the settings window (tray icon).

## Window

Gaps between windows and at the screen edge, corner rounding, border width, blur (on/off, strength, quality) and the transparency of the active and the other windows.

- Nothing changes while you move the sliders. **Apply** shows the new look; a dialog asks **Keep?** and puts the old look back after 15 seconds without an answer.
- **Presets** (Clean, Soft, Glass) only fill in the sliders.
- **Reset to Omarchy default** forgets the look; the Omarchy theme decides again (Hyprland reloads its config for that).

The look is saved in `~/.config/hypr-screens/config.json` under `look` and written into `~/.config/hypr/hypr_screens.lua`, which loads after the Omarchy theme and so wins over it.
