"""Progress owned by a run, retained across connection recovery."""

from dataclasses import dataclass, field

from roguebot.screens import LevelScreen


@dataclass
class RoutineProgress:
    parts: list[tuple[str, str]] = field(default_factory=list)
    tries: dict[str, int] = field(default_factory=dict)


@dataclass
class PartyProgress:
    results: list[LevelScreen] = field(default_factory=list)
    started: int = 0
    pending: bool = False
    stage: int | None = None
