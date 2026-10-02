# Samsung Galaxy Book

On a Samsung Galaxy Book, the settings window gets a **Samsung** page with what Samsung Settings offers on Windows. It needs the `samsung-galaxybook` kernel driver (in Linux since 6.14); on other laptops the page does not show.

## What it does

| Part | You can |
|---|---|
| **Battery** | set the charge limit (50–100 %), **charge to 100 % once**, see level, health, charge cycles and power |
| **Performance mode** | Saver · Quiet · Balanced · Performance — how fast and how loud (the fan); shows whether the fan runs and the CPU temperature |
| **Device** | power on when the lid opens, USB charging while off, keyboard backlight |

**Charge to 100 % once:** lifts the limit for one charge. The limit comes back when the battery is full or the charger is unplugged — also after a restart in between.

## Performance mode in one place

The mode is set in the window, in the **battery panel** in the bar (four buttons instead of Omarchy's three) and with the keyboard's mode key. All three stay in sync.

- Linux has no free fan curve on these laptops; the four modes are what the firmware offers, the same as on Windows.
- `power-profiles-daemon` only knows three modes, and Omarchy switches it on boot and when the charger goes in or out. So the setup keeps the daemon off the platform profile (it still tunes the CPU), and `hypr-screens watch` keeps the chosen mode. Quiet runs the CPU on *balanced*.
- The battery panel is Omarchy's own, copied to `omarchy-power/` (`hypr-screens.power`) with the buttons going through `hypr-screens power`. It is in the bar only while Samsung control is active (a Galaxy Book, setup done): setting up puts it there, turning off puts Omarchy's back, and `hypr-screens watch` checks it on every start.

## One-time setup

Writing these settings needs root once. In the window: **Set up…** (password dialog); in a terminal:

```bash
hypr-screens samsung setup
```

It installs:

| File | Why |
|---|---|
| `/etc/udev/rules.d/90-hypr-screens-samsung.rules` | hands the charge limit, the platform profile and the firmware switches to your user |
| `/etc/systemd/system/power-profiles-daemon.service.d/hypr-screens.conf` | starts `power-profiles-daemon --block-driver platform_profile` |

**Turn off** (Samsung page, or `hypr-screens samsung teardown`) undoes it: both files go, the files belong to root again, Omarchy gets its battery panel and the performance mode back, and a running full charge ends at the old limit.

## Commands

```bash
hypr-screens samsung status        # everything as JSON
hypr-screens samsung setup         # turn Samsung control on (password once)
hypr-screens samsung teardown      # turn it off again
hypr-screens samsung limit 80      # charge limit
hypr-screens samsung full-once on  # charge to 100 % once
hypr-screens power list            # modes, active one marked (used by the battery panel)
hypr-screens power set quiet       # low-power | quiet | balanced | performance
```

Settings are saved in `~/.config/hypr-screens/config.json` under `samsung`.
