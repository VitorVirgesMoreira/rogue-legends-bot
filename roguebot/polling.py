"""Interruptible polling shared by emulator providers."""

import threading
import time
from typing import Callable, TypeVar

from roguebot import config
from roguebot.device import Stopped

T = TypeVar("T")


def wait_for(check: Callable[[], T], timeout: float, stop: threading.Event | None = None) -> T | None:
    """Return the first truthy result, or None on timeout. Check cancellation before each probe."""
    deadline = time.monotonic() + timeout
    while True:
        if stop is not None and stop.is_set():
            raise Stopped("Stopped by the user")
        result = check()
        if result:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        delay = min(config.EMULATOR_POLL, remaining)
        if stop is None:
            time.sleep(delay)
        elif stop.wait(delay):
            raise Stopped("Stopped by the user")
