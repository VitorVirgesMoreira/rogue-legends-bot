"""Dungeon Dive depth changes must not restart a healthy game on dark frames."""

import pytest

from roguebot import config, labels, play
from roguebot.build import Build, BuildState
from roguebot.device import DeviceError, Stopped, ViewportUnavailable
from roguebot.screens import LevelScreen
from roguebot.skills import Catalog
from test_party import ReplayDevice, ReplayOcr, result
from test_skill_confirmation import offer


class TransitionDevice(ReplayDevice):
    def __init__(self, frames):
        super().__init__(frames)
        self.now = 0.
        self.waits = []

    def screenshot(self):
        frame = next(self.frames)
        if isinstance(frame, Exception):
            raise frame
        self.texts = frame
        return self.img

    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def language(monkeypatch):
    labels.set_language("en")
    monkeypatch.setattr(play.time, "sleep", lambda _: None)
    yield
    labels.set_language(None)


def player(monkeypatch, tmp_path, frames):
    device = TransitionDevice(frames)
    monkeypatch.setattr(play.time, "monotonic", lambda: device.now)
    state = BuildState()
    bot = play.Player(device, ReplayOcr(device), Build(profile="fire"),
                      Catalog(tmp_path / "skills.json"), build_state=state)
    return bot, device, state


def dark_frame(right=972):
    return ViewportUnavailable(f"Uncertain viewport on 1920x1080: measured x=836:{right}; "
                               "expected centered width 607.5. No input sent.")


def test_depth_transition_keeps_pending_skill_and_resumes_the_same_run(monkeypatch, tmp_path):
    victory = result(LevelScreen.VICTORY)
    bot, device, state = player(monkeypatch, tmp_path,
        [offer(), offer(), dark_frame(), dark_frame(976), victory, victory])

    assert bot.play_level() is LevelScreen.VICTORY
    assert state.taken == ["Fire Weapon"] and state.pending_skill is None
    assert len(device.waits) == 2
    assert len(device.taps) == 2  # one skill and Continue; no input on either dark frame


def test_each_depth_gets_a_new_wait_budget(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VIEWPORT_TRANSITION_TIMEOUT", 0.5, raising=False)
    victory = result(LevelScreen.VICTORY)
    bot, device, _ = player(monkeypatch, tmp_path,
        [dark_frame(), dark_frame(), victory, dark_frame(), dark_frame(), victory, victory])

    assert bot.play_level() is LevelScreen.VICTORY
    assert len(device.waits) == 4 and device.now > config.VIEWPORT_TRANSITION_TIMEOUT
    assert device.taps == [(720, 2315)]


def test_continuous_missing_viewport_still_times_out_without_input(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VIEWPORT_TRANSITION_TIMEOUT", 0.5, raising=False)
    bot, device, _ = player(monkeypatch, tmp_path, [dark_frame() for _ in range(10)])

    with pytest.raises(ViewportUnavailable, match="Uncertain viewport"):
        bot.play_level()
    assert config.VIEWPORT_TRANSITION_TIMEOUT <= device.now < 1
    assert not device.taps


def test_stop_interrupts_the_transition_wait(monkeypatch, tmp_path):
    bot, device, _ = player(monkeypatch, tmp_path, [dark_frame()])

    def stop(seconds):
        raise Stopped("Stopped during depth transition")

    monkeypatch.setattr(device, "wait", stop)
    with pytest.raises(Stopped, match="depth transition"):
        bot.play_level()
    assert not device.taps


def test_adb_failure_is_not_treated_as_a_dark_transition(monkeypatch, tmp_path):
    bot, device, _ = player(monkeypatch, tmp_path, [DeviceError("ADB screenshot failed: disconnected")])
    with pytest.raises(DeviceError, match="disconnected"):
        bot.play_level()
    assert not device.waits and not device.taps
