"""Binary captures and every gesture share the viewport, including after resolution changes."""

import cv2
import numpy as np
import pytest
import subprocess

from roguebot import config
from roguebot.device import Device, DeviceError
from test_viewport import letterbox


class Adb:
    def __init__(self):
        self.image = letterbox()
        self.calls = []
        self.failure = None

    def shell(self, cmd, encoding="utf-8", timeout=None):
        self.calls.append(cmd)
        assert timeout is not None
        if cmd == "screencap -p":
            assert encoding is None
            if self.failure:
                raise self.failure
            return cv2.imencode(".png", self.image)[1].tobytes()
        return ""


@pytest.fixture
def device(monkeypatch):
    adb = Adb()
    monkeypatch.setattr("roguebot.device.subprocess.run", lambda *a, **k: subprocess.CompletedProcess(a, 0, b"device\n"))
    class Client:
        def device(self, serial):
            assert serial == "localhost:6520"
            return adb
    monkeypatch.setattr("roguebot.device.adbutils.AdbClient", Client)
    return Device("localhost:6520", adb="google-adb.exe")


def test_init_and_decode_use_actual_landscape_not_window_size(device):
    image = device.screenshot()
    assert image.shape == (2560, 1440, 3) and np.all(image == 80)
    assert device.viewport.left == 656


def test_tap_swipe_hold_and_screen_edges_share_mapping(device):
    device.screenshot()
    device.tap(720, 1280, settle=0)
    device.swipe((0, 0), (1440, 2560), duration=0.7, settle=0)
    device.hold(720, 1280, 2, settle=0)
    assert ["input", "tap", "960", "540"] in device._d.calls
    assert ["input", "swipe", "656", "0", "1263", "1079", "700"] in device._d.calls
    assert ["input", "swipe", "960", "540", "960", "540", "2000"] in device._d.calls


def test_invalid_frame_or_disconnection_invalidates_mapping_and_blocks_taps(device):
    device.screenshot()
    device._d.image = np.zeros((1080, 1920, 3), np.uint8)
    with pytest.raises(DeviceError):
        device.tap(720, 1280, settle=0)
    assert device.viewport is None
    assert not any(isinstance(c, list) and c[:2] == ["input", "tap"] for c in device._d.calls)
    device._d.failure = OSError("disconnected")
    with pytest.raises(DeviceError, match="disconnected"):
        device.screenshot()


def test_resolution_change_requires_fresh_recognition_before_tapping(device):
    device.screenshot()
    device._d.image = letterbox(2560, 1440)
    with pytest.raises(DeviceError, match="changed since recognition"):
        device.tap(720, 1280, settle=0)
    device.screenshot()
    device.tap(720, 1280, settle=0)
    assert device._d.calls[-1] == ["input", "tap", "1280", "720"]


def test_corrupt_png_has_clear_error_and_no_input(device, monkeypatch):
    monkeypatch.setattr(device._d, "shell", lambda *a, **k: b"not a png")
    with pytest.raises(DeviceError, match="Invalid PNG"):
        device.screenshot()


def test_back_and_launch_use_bounded_adb_calls(device):
    device.back(settle=0)
    device.launch(config.PACKAGE, settle=0)
    assert ["input", "keyevent", "4"] in device._d.calls
    assert any(c[:2] == ["monkey", "-p"] for c in device._d.calls if isinstance(c, list))


def test_pinch_uses_two_pointers_in_the_same_landscape_viewport(device, monkeypatch):
    uploads = []
    monkeypatch.setattr("roguebot.device.subprocess.run", lambda cmd, **kw:
                        uploads.append(cmd) or subprocess.CompletedProcess(cmd, 0, b""))
    shell = device._d.shell
    def reply(cmd, **kwargs):
        result = shell(cmd, **kwargs)
        return "ROGUEBOT_PINCH_OK" if isinstance(cmd, list) and cmd[:1] == ["env"] else result
    monkeypatch.setattr(device._d, "shell", reply)
    device.screenshot()
    points = ((270, 1200), (1170, 1200), (490, 1200), (950, 1200))
    expected = [str(v) for point in points for v in device.viewport.to_device(*point)]
    device.pinch(*points, duration=.6, settle=0)
    command = device._d.calls[-1]
    assert command[:1] == ["env"] and command[2:5] == ["app_process", "/", "com.roguebot.input.TreeGesture"]
    assert command[5:] == expected + ["600"]
    assert uploads[0][:4] == ["google-adb.exe", "-s", "localhost:6520", "push"]
    device.pinch(*points, duration=.6, settle=0)
    assert len(uploads) == 1


def test_new_device_reuses_a_verified_read_only_gesture_helper(device, monkeypatch):
    import hashlib
    from pathlib import Path
    asset = Path(__file__).parents[1] / "roguebot/assets/tree-gesture.jar"
    checksum = hashlib.sha256(asset.read_bytes()).hexdigest()
    shell = device._d.shell
    def reply(cmd, **kwargs):
        result = shell(cmd, **kwargs)
        if isinstance(cmd, list) and cmd[0] == "sha256sum":
            return checksum + "  " + cmd[1]
        return "ROGUEBOT_PINCH_OK" if isinstance(cmd, list) and cmd[0] == "env" else result
    monkeypatch.setattr(device._d, "shell", reply)
    monkeypatch.setattr("roguebot.device.subprocess.run", lambda *a, **k: pytest.fail("Verified helper must not be uploaded again"))
    device.pinch((270, 1200), (1170, 1200), (490, 1200), (950, 1200), settle=0)


def test_pinch_does_not_run_after_stop_or_viewport_loss(device):
    import threading
    from roguebot.device import Stopped
    device._stop = threading.Event()
    device._stop.set()
    with pytest.raises(Stopped):
        device.pinch((270, 1200), (1170, 1200), (490, 1200), (950, 1200), settle=0)
    device._stop.clear()
    device._d.image[:] = 0
    with pytest.raises(DeviceError):
        device.pinch((270, 1200), (1170, 1200), (490, 1200), (950, 1200), settle=0)
    assert not any(isinstance(cmd, list) and cmd[0] == "env" for cmd in device._d.calls)


def test_android_must_confirm_the_pinch(device):
    with pytest.raises(DeviceError, match="did not confirm"):
        device.pinch((270, 1200), (1170, 1200), (490, 1200), (950, 1200), settle=0)


def test_healthy_device_is_not_reconnected(device, monkeypatch):
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"device\n")
    monkeypatch.setattr("roguebot.device.subprocess.run", run)
    Device("localhost:6520", adb="selected-adb.exe")
    assert calls == [["selected-adb.exe", "-s", "localhost:6520", "get-state"]]


def test_stop_during_capture_blocks_the_following_input(device, monkeypatch):
    import threading
    from roguebot.device import Stopped

    device._stop = threading.Event()
    capture = device.capture_raw

    def stop_after_capture():
        image = capture()
        device._stop.set()
        return image

    monkeypatch.setattr(device, "capture_raw", stop_after_capture)
    with pytest.raises(Stopped):
        device.tap(720, 1280, settle=0)
    assert not any(isinstance(cmd, list) and cmd[:2] == ["input", "tap"] for cmd in device._d.calls)


def test_stop_interrupts_input_settling(device):
    import threading
    from roguebot.device import Stopped

    class StopOnWait(threading.Event):
        def wait(self, timeout):
            self.set()
            return True

    device._stop = StopOnWait()
    with pytest.raises(Stopped):
        device.back(settle=60)
    assert device._d.calls[-1] == ["input", "keyevent", "4"]


def test_installed_package_uses_a_bounded_exact_query(device, monkeypatch):
    calls = []

    def shell(command, timeout):
        calls.append((command, timeout))
        return f"package:{config.PACKAGE}.other\n"

    monkeypatch.setattr(device._d, "shell", shell)
    assert not device.installed()
    assert calls == [(["pm", "list", "packages", config.PACKAGE], config.ADB_TIMEOUT)]


def test_disconnected_device_connects_then_waits_for_transport(device, monkeypatch):
    calls = []
    def run(cmd, **kwargs):
        assert kwargs["timeout"] == config.ADB_TIMEOUT
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"offline\n")
    monkeypatch.setattr("roguebot.device.subprocess.run", run)
    Device("localhost:6520", adb="selected-adb.exe")
    assert calls[1:] == [["selected-adb.exe", "connect", "localhost:6520"],
                         ["selected-adb.exe", "-s", "localhost:6520", "wait-for-device"]]


def test_lobby_startup_waits_through_black_frames_without_input():
    from types import SimpleNamespace
    from roguebot.device import ViewportUnavailable
    from roguebot.navigation import Navigator
    waits = []
    nav = Navigator(SimpleNamespace(wait=lambda seconds: waits.append(seconds)), None)
    attempts = [0]
    lobby = object()
    def read():
        attempts[0] += 1
        if attempts[0] <= 3:
            raise ViewportUnavailable("Black startup frame")
        return lobby
    nav.go_to_lobby = read
    assert nav.wait_for_lobby(60) is lobby
    assert waits == [config.EMULATOR_POLL] * 3


def test_lobby_startup_stops_after_timeout_with_no_input():
    from types import SimpleNamespace
    from roguebot.device import ViewportUnavailable
    from roguebot.emulator import EmulatorError
    from roguebot.navigation import Navigator
    nav = Navigator(SimpleNamespace(), None)
    def read():
        raise ViewportUnavailable("Black startup frame")
    nav.go_to_lobby = read
    with pytest.raises(EmulatorError, match="err_game_load"):
        nav.wait_for_lobby(-1)
