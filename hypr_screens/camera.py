"""A turned camera for every app: the virtual camera "Rotated Camera".

`setup()` installs v4l2loopback once (root) and makes it create the virtual
camera on every boot. `guard()` runs inside `hypr-screens watch` and keeps it
fed:

- While no app has the virtual camera open, it gets a black frame five times a
  second -- the real camera stays off (LED off).
- As soon as an app opens it (or the settings window shows its preview), the
  real camera starts and its picture goes through, turned by the chosen
  rotation; two seconds after the last one let go, the real camera is off again.
- Switched off (config camera.enabled), nothing feeds it: v4l2loopback with
  exclusive_caps then does not offer it as a camera, so apps cannot pick it.

The preview is a small JPEG the same ffmpeg writes next to the picture for the
apps (preview_file()), so the settings window never opens a camera itself --
v4l2loopback lets only one reader set the format, and that is the app.

The picture is always 1280 x 720, so turning it never changes the size an app
sees mid-call; at 90° and 270° the upright picture sits between black bars.
"""
import os
import json
import select
import subprocess
import sys
import time
from pathlib import Path

from hypr_screens import config
from hypr_screens.root import run_as_root

PREVIEW_WIDTH, PREVIEW_FPS = 480, 10
# The settings window touches this while it shows the preview; it counts as a user for this long.
PREVIEW_HOLD_SECONDS = 2.0

SYSFS = Path("/sys")
PROC = Path("/proc")
DEV = Path("/dev")
CARD_LABEL = "Rotated Camera"
VIDEO_NR = 42
WIDTH, HEIGHT, FPS = 1280, 720, 30
FRAME_BYTES = WIDTH * HEIGHT * 2  # yuyv422
IDLE_SECONDS = 0.2
RELEASE_SECONDS = 2.0
ROTATIONS = [0, 90, 180, 270]
MODPROBE = Path("/etc/modprobe.d/hypr-screens-camera.conf")
MODULES_LOAD = Path("/etc/modules-load.d/hypr-screens-camera.conf")


# --- devices -------------------------------------------------------------------------


def nodes() -> list[tuple[Path, str, int]]:
    """(/dev/videoN, name, index) for every video node."""
    found = []
    for node in sorted((SYSFS / "class/video4linux").glob("video*")):
        try:
            name = (node / "name").read_text().strip()
            index = int((node / "index").read_text().strip() or 0)
        except (OSError, ValueError):
            continue
        found.append((DEV / node.name, name, index))
    return found


def virtual_device() -> Path | None:
    return next((path for path, name, _index in nodes() if name == CARD_LABEL), None)


def real_device() -> Path | None:
    """The first real camera's capture node (index 0; index 1 is metadata)."""
    return next((path for path, name, index in nodes() if name != CARD_LABEL and index == 0), None)


def preview_file() -> Path:
    return config.runtime_dir() / "camera-preview.jpg"


def preview_request_file() -> Path:
    return config.runtime_dir() / "camera-preview-wanted"


def request_preview() -> None:
    """Called by the settings window while it shows the preview."""
    preview_request_file().touch()


def preview_requested() -> bool:
    try:
        return time.time() - preview_request_file().stat().st_mtime < PREVIEW_HOLD_SECONDS
    except OSError:
        return False


def status_file() -> Path:
    return config.runtime_dir() / "camera-status.json"


def write_status(state: str, users: int = 0) -> None:
    """off | idle | live | busy (another app has the real camera itself)."""
    text = json.dumps({"state": state, "users": users})
    try:
        if status_file().read_text() == text:
            return
    except OSError:
        pass
    status_file().write_text(text)


def status() -> dict:
    """What the feeder last reported; nothing while the watcher does not run."""
    try:
        data = json.loads(status_file().read_text())
        if time.time() - status_file().stat().st_mtime < 3600:
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def enabled(cfg: dict | None = None) -> bool:
    return bool(((cfg if cfg is not None else config.load()).get("camera") or {}).get("enabled", True))


def rotation(cfg: dict | None = None) -> int:
    value = ((cfg if cfg is not None else config.load()).get("camera") or {}).get("rotation", 0)
    return value if value in ROTATIONS else 0


def video_filter(degrees: int) -> str:
    """ffmpeg filter: turn clockwise by `degrees`, then fit into WIDTH x HEIGHT."""
    fit = f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2"
    turn = {0: "", 90: "transpose=1,", 180: "hflip,vflip,", 270: "transpose=2,"}[degrees]
    return f"{turn}{fit},format=yuyv422"


def openers(device: Path, ignore: set[int]) -> set[int]:
    """Processes that have `device` open, apart from `ignore`."""
    found = set()
    target = str(device)
    for proc in PROC.iterdir():
        if not proc.name.isdigit() or int(proc.name) in ignore:
            continue
        try:
            for fd in (proc / "fd").iterdir():
                if os.readlink(fd) == target:
                    found.add(int(proc.name))
                    break
        except OSError:
            continue
    return found


# --- feeding the virtual camera ---------------------------------------------------------


def writer_command(device: Path) -> list[str]:
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "yuyv422",
            "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS), "-i", "pipe:0", "-f", "v4l2", str(device)]


def preview_output(path: Path) -> list[str]:
    """ffmpeg output options: a small JPEG, replaced in one step a few times a second."""
    return ["-f", "image2", "-update", "1", "-atomic_writing", "1", "-q:v", "6", str(path)]


def reader_command(device: Path, degrees: int, preview: Path) -> list[str]:
    """The turned picture for the virtual camera on stdout, plus the preview JPEG."""
    graph = (f"[0:v]{video_filter(degrees)},split=2[cam][small];"
             f"[small]fps={PREVIEW_FPS},scale={PREVIEW_WIDTH}:-2,format=yuvj420p[preview]")
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-input_format", "mjpeg",
            "-video_size", f"{WIDTH}x{HEIGHT}", "-framerate", str(FPS), "-i", str(device),
            "-filter_complex", graph,
            "-map", "[cam]", "-pix_fmt", "yuyv422", "-f", "rawvideo", "pipe:1",
            "-map", "[preview]", *preview_output(preview)]


def direct_preview_command(device: Path, degrees: int, preview: Path) -> list[str]:
    """Before the setup there is no virtual camera: the window's own preview,
    straight from the real camera, turned the same way."""
    vf = (video_filter(degrees).removesuffix(",format=yuyv422")
          + f",fps={PREVIEW_FPS},scale={PREVIEW_WIDTH}:-2,format=yuvj420p")
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "v4l2", "-input_format", "mjpeg",
            "-video_size", f"{WIDTH}x{HEIGHT}", "-i", str(device), "-vf", vf, *preview_output(preview)]


def black_frame() -> bytes:
    """Black in yuyv422: Y=16, U=V=128."""
    return bytes([16, 128]) * (WIDTH * HEIGHT)


class Feeder:
    """Keeps the virtual camera fed; the real camera only runs while it is used."""

    def __init__(self, virtual: Path, real: Path):
        self.virtual, self.real = virtual, real
        self.writer: subprocess.Popen | None = None
        self.reader: subprocess.Popen | None = None
        self.degrees = rotation()
        self.last_used = 0.0
        self.started = 0.0
        self.busy_until = 0.0  # the real camera is taken by another app: wait before trying again
        self.black = black_frame()

    def stop_writer(self) -> None:
        if self.writer is not None:
            try:
                self.writer.stdin.close()
            except OSError:
                pass
            self.writer.terminate()
            try:
                self.writer.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.writer.kill()
            self.writer = None

    def start_writer(self) -> None:
        self.writer = subprocess.Popen(writer_command(self.virtual), stdin=subprocess.PIPE,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_reader(self) -> None:
        self.started = time.monotonic()
        self.reader = subprocess.Popen(reader_command(self.real, self.degrees, preview_file()),
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)

    def stop_reader(self) -> None:
        if self.reader is not None:
            self.reader.terminate()
            try:
                self.reader.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.reader.kill()
            self.reader = None
        preview_file().unlink(missing_ok=True)

    def ours(self) -> set[int]:
        return {os.getpid(), *(p.pid for p in (self.writer, self.reader) if p is not None)}

    def write(self, frame: bytes) -> bool:
        try:
            self.writer.stdin.write(frame)
            self.writer.stdin.flush()
            return True
        except (BrokenPipeError, OSError, ValueError):
            return False

    def read_frame(self, timeout: float) -> bytes | None:
        """One whole frame from the camera, or None if none came in time."""
        stdout = self.reader.stdout
        ready, _, _ = select.select([stdout], [], [], timeout)
        if not ready:
            return None
        chunks, missing = [], FRAME_BYTES
        while missing:
            chunk = stdout.read(missing)
            if not chunk:
                return b""  # the camera went away
            chunks.append(chunk)
            missing -= len(chunk)
        return b"".join(chunks)

    def run(self) -> None:
        checked = 0.0
        on = False
        while True:
            now = time.monotonic()
            if now - checked >= 1.0:
                checked = now
                cfg = config.load()
                on = enabled(cfg)
                if not on:
                    # Nothing feeds it: apps cannot pick it until it is on again.
                    self.stop_reader()
                    self.stop_writer()
                    write_status("off")
                    time.sleep(1.0)
                    continue
                users = openers(self.virtual, self.ours())
                in_use = bool(users) or preview_requested()
                wanted = rotation(cfg)
                if in_use:
                    self.last_used = now
                if self.reader is not None and wanted != self.degrees:
                    self.stop_reader()  # restarts turned the new way below
                self.degrees = wanted
                if in_use and self.reader is None and now >= self.busy_until:
                    self.start_reader()
                elif self.reader is not None and now - self.last_used > RELEASE_SECONDS:
                    self.stop_reader()
                if self.reader is not None:
                    write_status("live", len(users))
                else:
                    write_status("busy" if in_use and now < self.busy_until else "idle", len(users))
            if not on:
                continue
            if self.writer is None or self.writer.poll() is not None:
                self.start_writer()
            if self.reader is None:
                self.write(self.black)
                time.sleep(IDLE_SECONDS)
                continue
            frame = self.read_frame(timeout=1.0)
            if frame is None:
                continue
            if frame == b"":
                # ffmpeg ended. Right after starting, that means the real camera
                # is taken by another app: black for now, try again in a while.
                if time.monotonic() - self.started < 3.0:
                    self.busy_until = time.monotonic() + 5.0
                self.stop_reader()
                continue
            self.write(frame)


def guard() -> None:
    """Watcher thread: feed the virtual camera when it exists (after setup)."""
    while True:
        virtual, real = virtual_device(), real_device()
        if virtual is None or real is None:
            time.sleep(10)
            continue
        try:
            Feeder(virtual, real).run()
        except Exception as error:  # never take the watcher down
            print(f"hypr-screens camera: {error}", file=sys.stderr, flush=True)
            time.sleep(5)


# --- one-time root setup -----------------------------------------------------------------


def setup_script() -> str:
    return "\n".join([
        "set -e",
        "pacman -S --needed --noconfirm v4l2loopback-dkms",
        f"cat > {MODPROBE} <<'EOF'",
        "# hypr-screens: the virtual camera apps can pick; hypr-screens watch feeds it.",
        f'options v4l2loopback devices=1 video_nr={VIDEO_NR} card_label="{CARD_LABEL}" exclusive_caps=1',
        "EOF",
        f"echo v4l2loopback > {MODULES_LOAD}",
        "modprobe -r v4l2loopback 2>/dev/null || true",
        "modprobe v4l2loopback",
        "",
    ])


def teardown_script() -> str:
    return "\n".join([
        f"rm -f {MODPROBE} {MODULES_LOAD}",
        "modprobe -r v4l2loopback 2>/dev/null || true",
        "",
    ])


def is_set_up() -> bool:
    return MODPROBE.exists() and virtual_device() is not None


def setup(graphical: bool = False) -> bool:
    return run_as_root(setup_script(), graphical)


def teardown(graphical: bool = False) -> bool:
    return run_as_root(teardown_script(), graphical)
