"""Provider contract; gameplay and Device remain independent of emulator lifecycle tools."""

from typing import Protocol

from roguebot import config


class Provider(Protocol):
    adb: str

    def connect(self) -> str:
        """Connect to ready Android without starting the emulator or game; return its serial."""
        ...

    def start(self, package: str = config.PACKAGE) -> tuple[str, str, bool]:
        """Return the connected serial, ADB executable and whether the game was opened."""
        ...

    def recover(self, *, restart_game: bool = False) -> None:
        """Prepare the next start attempt using this provider's supported lifecycle."""
        ...
