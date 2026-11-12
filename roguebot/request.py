"""What the user asked to run, validated from the UI form values."""

from dataclasses import dataclass

from roguebot.build import Build
from roguebot import config
from roguebot.screens import Mode
from roguebot.party_build import ROLES
from roguebot.farming import OBJECTIVES

LATEST = "latest"
STARS = "stars"
BEATEN = "beaten"
PENDING = "pending"  # beaten levels that still miss stars, then the last beaten one
FARM = "farm"
ROUTINE_CHOICES = ("vip", "arena", "dojo", "tower", "dive", "mines", "pets")


def positive_integer(value: str | int) -> int | None:
    raw = str(value).strip()
    if not raw.isdecimal():
        return None
    try:
        number = int(raw)
    except ValueError:
        return None
    return number if number > 0 else None


@dataclass(frozen=True)
class RunRequest:
    mode: Mode
    level: int | None  # None = last unlocked level (lobby INICIO/LISTO)
    repeat: bool = False  # keep playing the selected stage source until energy runs out (always, from the UI)
    full: bool = False    # legacy callers: run all supported routine parts before the levels
    build: Build = Build()  # skill preferences for level skill picks and shops
    last_beaten: bool = False  # the level before the last unlocked one (from Desafío de Estrellas)
    pending_stars: bool = False  # levels with missing stars first (star rewards), then the last beaten
    mumu_folder: str = ""  # MuMu Player installation folder (started and Rogue Legend opened on Start)
    loop: bool = False    # keep running: out of energy -> wait for energy -> (routine ->) levels again
    ads: bool = False     # watch ads (energy, x2 rewards, revive, tickets); only for accounts that skip them
    provider: str = "mumu"
    adb_path: str = ""     # blank uses the selected provider's bundled ADB
    device_serial: str = ""  # blank uses the provider's default/discovered device
    elite_energy: int | None = None  # None: highest affordable cost; otherwise exactly 5/10/15
    party_role: str = "striker"
    party_runs: int = 20
    farm: bool = False
    farm_objective: str = "reliable"
    claim_events: bool = True
    routine_parts: tuple[str, ...] | None = None  # None preserves the legacy full flag

    def __post_init__(self) -> None:
        if self.routine_parts is not None and (
                not isinstance(self.routine_parts, tuple) or any(part not in ROUTINE_CHOICES for part in self.routine_parts)):
            raise ValueError("bad_routine_parts")
        if self.elite_energy is not None and (not isinstance(self.elite_energy, int) or isinstance(self.elite_energy, bool)
                                               or self.elite_energy not in config.ELITE_COSTS):
            raise ValueError("bad_elite_energy")
        if self.party_role not in ROLES:
            raise ValueError("bad_party_role")
        if type(self.party_runs) is not int or not 1 <= self.party_runs <= 20:
            raise ValueError("bad_party_runs")
        if self.farm_objective not in OBJECTIVES:
            raise ValueError("bad_farm_objective")
        if self.farm and (self.level is not None or self.last_beaten or self.pending_stars):
            raise ValueError("bad_farm_objective")

    @property
    def minimum_energy(self) -> int:
        return self.elite_energy if self.mode is Mode.ELITE and self.elite_energy is not None else config.MIN_RUN_ENERGY


def build_request(mode: str, source: str, level: str, full: bool = False, build: Build = Build(),
                  loop: bool = False, mumu_folder: str = "", ads: bool = False, *, provider: str = "mumu",
                  adb_path: str = "", device_serial: str = "", elite_energy: str | int | None = None,
                  party_role: str = "striker", party_runs: str | int = 20,
                  farm_objective: str = "reliable", claim_events: bool = True,
                  routine_parts: tuple[str, ...] | None = None) -> RunRequest:
    """Validate the form values. Raises ValueError with a user-facing message.
    Levels always run until out of energy; `loop` then waits for energy and starts again."""
    if elite_energy in (None, "auto"):
        cost = None
    elif isinstance(elite_energy, int) and not isinstance(elite_energy, bool):
        cost = elite_energy
    elif isinstance(elite_energy, str) and elite_energy in {str(c) for c in config.ELITE_COSTS}:
        cost = int(elite_energy)
    else:
        raise ValueError("bad_elite_energy")
    common = dict(repeat=True, full=full, build=build, mumu_folder=mumu_folder, loop=loop, ads=ads,
                  provider=provider, adb_path=adb_path.strip(), device_serial=device_serial.strip(), elite_energy=cost,
                  farm_objective=farm_objective, claim_events=claim_events, routine_parts=routine_parts)
    if mode in (Mode.CHAOS.value, Mode.CONQUEST.value):
        common.update(full=False, loop=False, repeat=False, routine_parts=())
        return RunRequest(Mode(mode), None, **common)
    if mode == Mode.PARTY_EXPEDITION.value:
        runs = positive_integer(party_runs)
        if runs is None:
            raise ValueError("bad_party_runs")
        common.update(full=False, loop=False, routine_parts=(), party_role=party_role, party_runs=runs)
        return RunRequest(Mode.PARTY_EXPEDITION, None, **common)
    if source == FARM:
        return RunRequest(Mode(mode), None, farm=True, **common)
    if source in (LATEST, BEATEN, PENDING):
        return RunRequest(Mode(mode), None, last_beaten=source in (BEATEN, PENDING),
                          pending_stars=source == PENDING, **common)
    stage = positive_integer(level)
    if stage is None:
        raise ValueError("bad_level")  # i18n key
    return RunRequest(Mode(mode), stage, **common)
