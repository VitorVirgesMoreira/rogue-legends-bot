"""Provider polling honors Stop and its deadline, including a successful first probe."""

import threading

import pytest

from roguebot import polling
from roguebot.device import Stopped


def test_cancelled_poll_never_performs_another_probe():
    stop = threading.Event()
    stop.set()
    with pytest.raises(Stopped):
        polling.wait_for(lambda: pytest.fail("probe ran after Stop"), 60, stop)


def test_poll_wait_does_not_overshoot_the_remaining_timeout(monkeypatch):
    clock = [100.0]
    waits = []
    monkeypatch.setattr(polling.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(polling.config, "EMULATOR_POLL", 5)

    def sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(polling.time, "sleep", sleep)
    assert polling.wait_for(lambda: False, 2) is None
    assert waits == [2]


def test_stop_during_a_probe_interrupts_the_wait():
    stop = threading.Event()

    def check():
        stop.set()
        return False

    with pytest.raises(Stopped):
        polling.wait_for(check, 60, stop)
