# One desktop on one screen

With an external monitor connected:

- **one screen is fixed**: it always shows the same workspace (`99`), shown as `1` in the bar
- **the other screen has the desktops 1–10**; `SUPER + 1…0` only change that one

Only for **one** external monitor. Without one, everything is normal Hyprland.

## Which screen is fixed?

In this order:

1. **Swap** (tray right-click, *Ein Desktop → Jetzt tauschen* in the window, or `hypr-screens swap`), until you unplug
2. the **One desktop** setting of a screen (laptop wins if both say yes)
3. the default for new screens (window → *Ein Desktop → Bei neuen Monitoren*): off · external screen · laptop

Example: laptop fixed only at the desk dock, any other monitor fixed itself:

```bash
hypr-screens set Laptop one_desktop yes
hypr-screens when Laptop one_desktop "HP 32f"
hypr-screens option default_fixed external
```

## What happens when…

| …you | then |
|---|---|
| plug in (laptop fixed) | the windows you had on the laptop stay on the laptop |
| plug in (external fixed) | the external screen starts empty; move windows there with `SUPER + Y` |
| swap | the screens trade places; windows and layouts stay as they are |
| unplug | windows of the fixed screen go to the desktop the laptop shows |

## Needed for it

- "Desktop keys" on (window → *Ein Desktop → Desktop-Tasten*, or `hypr-screens option desktop_keys on`)
- Omarchy bar: the `hypr-screens.workspaces` widget (the wizard sets it)

```bash
hypr-screens status        # who is fixed right now
```
