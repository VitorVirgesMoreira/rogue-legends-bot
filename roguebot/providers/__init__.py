"""Configured emulator selection. Old settings default to MuMu."""

import threading

from roguebot.emulator import EmulatorError
from roguebot.providers.base import Provider
from roguebot.providers.google_play_games import GooglePlayGamesProvider, find_adb as find_adb
from roguebot.providers.mumu import MuMuProvider
from roguebot.request import RunRequest

PROVIDERS = {"mumu": "MuMu Player 12", "google_play_games": "Google Play Games Developer Emulator"}


def create_provider(request: RunRequest, stop: threading.Event | None = None) -> Provider:
    if request.provider == "mumu":
        return MuMuProvider(request.mumu_folder, stop, adb_path=request.adb_path, serial=request.device_serial)
    if request.provider == "google_play_games":
        return GooglePlayGamesProvider(request.adb_path, request.device_serial, stop)
    raise EmulatorError("err_provider", provider=request.provider)
