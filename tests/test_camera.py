"""The virtual camera: finding devices, who uses it, turning, setup."""
import os
import time

import pytest

from hypr_screens import camera, config


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{value}\n")


@pytest.fixture()
def devices(tmp_path, monkeypatch):
    sysfs = tmp_path / "sys"
    for node, name, index in (("video0", "1080p FHD Camera: 1080p FHD Cam", 0),
                              ("video1", "1080p FHD Camera: 1080p FHD Cam", 1),
                              ("video42", camera.CARD_LABEL, 0)):
        put(sysfs / "class/video4linux" / node / "name", name)
        put(sysfs / "class/video4linux" / node / "index", index)
    monkeypatch.setattr(camera, "SYSFS", sysfs)
    monkeypatch.setattr(camera, "DEV", tmp_path / "dev")
    return tmp_path


def test_finds_the_real_and_the_virtual_camera(devices):
    assert camera.real_device() == devices / "dev/video0"
    assert camera.virtual_device() == devices / "dev/video42"


def test_no_virtual_camera_before_the_setup(devices):
    (devices / "sys/class/video4linux/video42/name").write_text("Something else\n")
    assert camera.virtual_device() is None


def test_who_has_the_virtual_camera_open(tmp_path, monkeypatch):
    proc = tmp_path / "proc"
    for pid, target in ((100, "/dev/video42"), (200, "/dev/null"), (300, "/dev/video42")):
        (proc / str(pid) / "fd").mkdir(parents=True)
        os.symlink(target, proc / str(pid) / "fd" / "3")
    (proc / "self").mkdir()
    monkeypatch.setattr(camera, "PROC", proc)
    assert camera.openers(camera.Path("/dev/video42"), ignore={300}) == {100}


@pytest.mark.parametrize("degrees, turn", [(0, ""), (90, "transpose=1,"), (180, "hflip,vflip,"),
                                           (270, "transpose=2,")])
def test_turning_always_ends_in_the_same_size(degrees, turn):
    vf = camera.video_filter(degrees)
    assert vf.startswith(turn + "scale=1280:720:force_original_aspect_ratio=decrease")
    assert "pad=1280:720" in vf and vf.endswith("format=yuyv422")


def test_rotation_comes_from_the_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert camera.rotation() == 0
    cfg = config.load()
    cfg["camera"]["rotation"] = 180
    config.save(cfg)
    assert camera.rotation() == 180
    assert config.normalize({"camera": {"rotation": 45}})["camera"] == {"rotation": 0, "enabled": True}
    assert config.normalize({"camera": {"enabled": False}})["camera"]["enabled"] is False


def test_black_frame_fits_the_virtual_camera():
    frame = camera.black_frame()
    assert len(frame) == camera.FRAME_BYTES and frame[:4] == bytes([16, 128, 16, 128])


def test_setup_names_the_camera_and_loads_it_on_boot():
    script = camera.setup_script()
    assert "pacman -S --needed --noconfirm v4l2loopback-dkms" in script
    assert f'card_label="{camera.CARD_LABEL}" exclusive_caps=1' in script
    assert f"echo v4l2loopback > {camera.MODULES_LOAD}" in script
    assert f"rm -f {camera.MODPROBE} {camera.MODULES_LOAD}" in camera.teardown_script()




def test_the_feeder_writes_the_preview_next_to_the_picture(tmp_path):
    command = camera.reader_command(camera.Path("/dev/video0"), 180, tmp_path / "p.jpg")
    graph = command[command.index("-filter_complex") + 1]
    assert graph.startswith("[0:v]hflip,vflip,") and "split=2[cam][small]" in graph
    assert command[command.index("[cam]") + 1:command.index("[cam]") + 7] == [
        "-pix_fmt", "yuyv422", "-f", "rawvideo", "pipe:1", "-map"]
    assert "-atomic_writing" in command and command[-1] == str(tmp_path / "p.jpg")


def test_direct_preview_turns_like_the_feeder(tmp_path):
    command = camera.direct_preview_command(camera.Path("/dev/video0"), 90, tmp_path / "p.jpg")
    vf = command[command.index("-vf") + 1]
    assert vf.startswith("transpose=1,") and "format=yuyv422" not in vf and command[-1].endswith("p.jpg")


def test_preview_requests_hold_for_a_moment(tmp_path, monkeypatch):
    monkeypatch.setattr(camera.config, "runtime_dir", lambda: tmp_path)
    assert not camera.preview_requested()
    camera.request_preview()
    assert camera.preview_requested()
    old = time.time() - camera.PREVIEW_HOLD_SECONDS - 1
    os.utime(camera.preview_request_file(), (old, old))
    assert not camera.preview_requested()


def test_status_is_reported_and_read_back(tmp_path, monkeypatch):
    monkeypatch.setattr(camera.config, "runtime_dir", lambda: tmp_path)
    assert camera.status() == {}
    camera.write_status("live", 2)
    assert camera.status() == {"state": "live", "users": 2}


def test_the_camera_is_on_unless_switched_off():
    assert camera.enabled(config.default_config())
    assert not camera.enabled({"camera": {"enabled": False}})
