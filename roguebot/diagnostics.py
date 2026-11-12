"""Read-only connection check used by the GUI and the command-line validation tool."""

from dataclasses import dataclass

from roguebot.device import Device
from roguebot.emulator import EmulatorError
from roguebot.providers import create_provider
from roguebot.request import RunRequest
from roguebot.viewport import Viewport


@dataclass(frozen=True)
class ConnectionStatus:
    serial: str
    installed: bool
    viewport: Viewport


def inspect_emulator(request: RunRequest) -> ConnectionStatus:
    """Connect and capture; never boot, launch, accept a dialog, close overlays or send input."""
    provider = create_provider(request)
    serial = provider.connect()
    device = Device(serial, adb=provider.adb)
    installed = device.installed()
    if not installed:
        raise EmulatorError("err_game_missing")
    device.capture_raw()
    return ConnectionStatus(serial, installed, device.viewport)
