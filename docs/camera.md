# Camera

The **Camera** page turns the camera picture for every app — by 0°, 90°, 180° or 270°, like a monitor.

## How it works

The one-time **Set up…** (password, about a minute) installs `v4l2loopback` and creates a virtual camera called **Rotated Camera** on every boot. In Discord, the browser, Zoom … pick **Rotated Camera** as the camera.

- **On/off switch** above the preview: off, nothing feeds the virtual camera, so apps do not list it any more; on, it is back.
- While no app uses it, the real camera is **off** (LED off); the virtual camera shows black.
- As soon as an app opens it, `hypr-screens watch` starts the real camera and passes its picture through, turned. Two seconds after the last app lets go, the camera is off again.
- The picture is always 1280 × 720, so turning it never breaks a running call; at 90° and 270° the upright picture sits between black bars.

**The preview** shows what apps get. It is a small picture the camera service writes next to the one for the apps, so the page never opens a camera itself: the preview and an app (say a Discord call) work at the same time.

**One app at a time:** v4l2loopback lets one app read the virtual camera at a time, and the real camera only serves one program. Pick **Rotated Camera** in the app; if an app uses the real camera directly, the page says so and the virtual camera stays black until it lets go.

## Commands

```bash
hypr-screens camera status      # set up? which devices, which rotation
hypr-screens camera rotate 180  # 0 | 90 | 180 | 270
hypr-screens camera setup       # one-time, as root
hypr-screens camera teardown    # remove the virtual camera again (the package stays)
```

Setup writes `/etc/modprobe.d/hypr-screens-camera.conf` and `/etc/modules-load.d/hypr-screens-camera.conf`. The rotation is saved in `~/.config/hypr-screens/config.json` under `camera`.
