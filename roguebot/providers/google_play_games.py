"""Google Play Games Developer Emulator, controlled only through its bundled ADB."""

import logging
import os
from pathlib import Path
import threading
from typing import Callable

from roguebot import config
from roguebot.device import focused_package
from roguebot.emulator import EmulatorError, _run
from roguebot.polling import wait_for

log = logging.getLogger(__name__)
DEFAULT_SERIAL = "localhost:6520"


def find_adb() -> Path | None:
    for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if root:
            candidate = Path(root) / "Google" / "Play Games Developer Emulator" / "current" / "emulator" / "adb.exe"
            if candidate.is_file():
                return candidate
    return None


class GooglePlayGamesProvider:
    def __init__(self, adb_path: str = "", serial: str = "", stop: threading.Event | None = None,
                 run: Callable[[list[str], float], str] = _run):
        adb = Path(adb_path) if adb_path.strip() else find_adb()
        if not adb or not adb.is_file():
            raise EmulatorError("err_google_adb", path=adb_path or "(auto-detect)")
        self.adb, self.serial = str(adb), serial.strip() or DEFAULT_SERIAL
        self.stop, self.run = stop, run

    def _adb(self, *args: str) -> str:
        return self.run([self.adb, "-s", self.serial, *args], config.ADB_TIMEOUT)

    def _shell(self, *args: str) -> str:
        return self._adb("shell", *args)

    def connected(self) -> bool:
        return self._adb("get-state").strip() == "device"

    def connect(self) -> str:
        if not self.connected():
            # One connect starts a transport handshake. Repeating connect while it is still offline
            # resets Google's handshake, so poll state without issuing another connect each time.
            self.run([self.adb, "connect", self.serial], config.ADB_TIMEOUT)
        if not wait_for(self.connected, config.GOOGLE_CONNECT_TIMEOUT, self.stop):
            raise EmulatorError("err_google_connection", serial=self.serial)
        if not wait_for(lambda: self._shell("getprop", "sys.boot_completed").strip() == "1",
                        config.EMULATOR_BOOT_TIMEOUT, self.stop):
            raise EmulatorError("err_google_boot", serial=self.serial)
        return self.serial

    def installed(self, package: str = config.PACKAGE) -> bool:
        return f"package:{package}" in self._shell("pm", "list", "packages", package).splitlines()

    def in_front(self, package: str = config.PACKAGE) -> bool:
        return focused_package(self._shell("dumpsys", "window")) == package

    def start(self, package: str = config.PACKAGE) -> tuple[str, str, bool]:
        self.connect()
        if not self.installed(package):
            if not self.connected():
                raise EmulatorError("err_google_connection", serial=self.serial)
            raise EmulatorError("err_game_missing")
        launched = not self.in_front(package)
        if launched:
            log.info("Opening Rogue Legend through Google emulator ADB")
            self._shell("monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
            if not wait_for(lambda: self.in_front(package), config.GAME_OPEN_TIMEOUT, self.stop):
                raise EmulatorError("err_game_open")
        return self.serial, self.adb, launched

    def recover(self, *, restart_game: bool = False) -> None:
        """Reconnect first. Foreground a background app; restart only a stuck foreground game.

        Never shut down the emulator, kill the shared ADB server or touch other Windows processes.
        The runner creates a new Device/viewport on the next attempt.
        """
        self.connect()
        if restart_game and self.in_front():
            self._shell("am", "force-stop", config.PACKAGE)
        # The runner calls start() next, preserving its game_was_launched result so splash/loading
        # gets the full lobby timeout after a relaunch.

    def shutdown(self) -> None:
        log.info("Close Google Play Games Developer Emulator manually if a full restart is needed")
