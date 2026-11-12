"""MuMu adapter: retain its established discovery, manager, boot and shutdown sequence."""

from roguebot import config
from roguebot.emulator import Emulator, EmulatorError
from roguebot.polling import wait_for


class MuMuProvider(Emulator):
    def connect(self) -> str:
        info = self._info()
        if not info.get("is_android_started"):
            raise EmulatorError("err_mumu_not_running")
        serial = self.serial or f"{info.get('adb_host_ip') or '127.0.0.1'}:{info.get('adb_port') or config.SERIAL.split(':')[1]}"
        if self.run([self.adb, "-s", serial, "get-state"], config.ADB_TIMEOUT).strip() != "device":
            self.run([self.adb, "connect", serial], config.ADB_TIMEOUT)
        if not wait_for(lambda: self._adb(serial, "getprop", "sys.boot_completed").strip() == "1",
                        config.EMULATOR_BOOT_TIMEOUT, self.stop):
            raise EmulatorError("err_mumu_adb", serial=serial)
        return serial

    def recover(self, *, restart_game: bool = False) -> None:
        self.shutdown()
