"""A connection check never starts a game or sends input, including on setup failures."""

from types import SimpleNamespace

import pytest

from roguebot import config, diagnostics
from roguebot.emulator import EmulatorError
from roguebot.request import RunRequest
from roguebot.screens import Mode
from roguebot.viewport import Viewport


def test_connection_check_reports_real_capture_geometry_without_launch_or_input(monkeypatch):
    calls = []
    provider = SimpleNamespace(adb="selected-adb.exe", connect=lambda: "localhost:6520")
    monkeypatch.setattr(diagnostics, "create_provider", lambda request: provider)
    class Device:
        def __init__(self, serial, adb):
            calls.append((serial, adb))
            self.viewport = None

        def installed(self):
            return True

        def capture_raw(self):
            self.viewport = Viewport(656, 0, 608, 1080, 1920, 1080)
    monkeypatch.setattr(diagnostics, "Device", Device)
    status = diagnostics.inspect_emulator(RunRequest(Mode.NORMAL, None, provider="google_play_games"))
    assert status.installed and status.serial == "localhost:6520" and status.viewport.left == 656
    assert calls == [("localhost:6520", "selected-adb.exe")]


def test_missing_package_is_reported_before_viewport_detection(monkeypatch):
    provider = SimpleNamespace(adb="adb.exe", connect=lambda: "localhost:6520")
    monkeypatch.setattr(diagnostics, "create_provider", lambda request: provider)
    device = SimpleNamespace(installed=lambda: False)
    monkeypatch.setattr(diagnostics, "Device", lambda *a, **k: device)
    with pytest.raises(EmulatorError, match="err_game_missing"):
        diagnostics.inspect_emulator(RunRequest(Mode.NORMAL, None, provider="google_play_games"))
