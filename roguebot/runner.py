"""Run orchestration and bounded recovery, independent of the command-line UI."""

import logging
import re
import threading
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from typing import Callable

from roguebot import config
from roguebot.build import BuildState
from roguebot.device import Device, Stopped
from roguebot.emulator import PERMANENT_ERRORS, EmulatorError
from roguebot.providers import create_provider, PROVIDERS
from roguebot.navigation import LevelUnavailable, StarsUnavailable, NavigationError, Navigator, NoEnergyError
from roguebot.play import Player, PlayError
from roguebot.observation import Observation, StatusPublisher
from roguebot.party import PartyExpedition
from roguebot.progress import PartyProgress, RoutineProgress
from roguebot.providers.base import Provider
from roguebot.report import Report
from roguebot.request import RunRequest
from roguebot.routine import Routine
from roguebot.screens import LevelScreen, Mode
from roguebot.skills import Catalog
from roguebot.vision import Ocr
from roguebot.metrics import History, RunRecord, build_signature
from roguebot.farming import FarmPolicy
from roguebot.schedule import RoutineSchedule
from roguebot.rewards import collect_events
from roguebot.event_modes import EventMode

log = logging.getLogger("roguebot")
ENERGY_READS = 3
PATROL_FAILS_TO_BACK_OFF = 2  # after-level patrol failures in a row before trying it only hours later


@dataclass
class ActiveLevel:
    level: int | None
    energy: int | None
    started: float = field(default_factory=time.monotonic)


@dataclass
class RunState:
    request: RunRequest
    provider: Provider
    results: list[LevelScreen] = field(default_factory=list)
    routine: RoutineProgress = field(default_factory=RoutineProgress)
    party: PartyProgress = field(default_factory=PartyProgress)
    build: BuildState | None = None
    routine_done: bool = False
    patrol_next: float = 0.0
    patrol_fails: int = 0
    resumed: int = 0
    previous_parts: int = 0
    farm: FarmPolicy = field(default_factory=FarmPolicy)
    schedule: RoutineSchedule = field(default_factory=RoutineSchedule)
    active_level: ActiveLevel | None = None
    farm_stopped: bool = False
    events_next: float = 0.

    @property
    def completed(self) -> int:
        return len(self.results) + len(self.routine.parts) + self.previous_parts + self.resumed

    def next_cycle(self) -> None:
        self.previous_parts += len(self.routine.parts)
        self.routine = RoutineProgress()
        self.routine_done = False

    def report(self) -> Report:
        return Report(list(self.results), repeat=self.request.repeat, parts=list(self.routine.parts))


def _start_level(nav: Navigator, request: RunRequest) -> int | None:
    """Start the requested level; returns its number when known."""
    if request.pending_stars:
        played = nav.start_pending_stars(request.mode)
        if played is not None:
            return played
    if request.last_beaten:
        return nav.start_last_beaten(request.mode)
    if request.level is None:
        # Keep this dynamic: a victory can unlock a new lobby stage before the next run.
        return nav.start_latest(request.mode)
    nav.start_star_challenge(request.mode, request.level)
    return request.level


def _error_key(e: Exception) -> str:
    """Errors that differ only in numbers or screenshot paths count as the same error."""
    return re.sub(r"\(screenshot:.*?\)|\d+", "", f"{type(e).__name__}: {e}").strip()


def _energy(nav: Navigator) -> int:
    """Lobby energy. An unreadable counter is read again, never taken as 0 (that would waste the
    free energy claims and could end the run early)."""
    for _ in range(ENERGY_READS):
        energy = nav.go_to_lobby().energy
        if energy is not None:
            return energy
    raise NavigationError("Could not read the energy counter")


def _patrol_next(wait: float | None, now: float) -> float:
    """When the patrol is worth opening again: its reward reaches PATROL_CLAIM_AFTER, or local midnight
    (the daily quick patrols come back), whichever is first. Unknown wait: next time."""
    if wait is None:
        return now
    midnight = (datetime.fromtimestamp(now) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return min(now + wait, midnight.timestamp())


def _claim_patrol(routine: Routine, state: RunState) -> None:
    """Before each level: patrol reward and free/energy quick patrols. A problem here never stops the run.
    Skipped while nothing can be there (it costs ~10 s per level otherwise)."""
    if time.time() < state.patrol_next:
        return
    try:
        routine.patrol()
        state.patrol_next = _patrol_next(routine.patrol_wait, time.time())
        state.patrol_fails = 0
    except (NavigationError, PlayError) as e:
        log.error("Patrol failed: %s", e)
        state.patrol_fails += 1
        if state.patrol_fails >= PATROL_FAILS_TO_BACK_OFF:  # likely not unlocked on this account: much later
            state.patrol_next = _patrol_next(config.PATROL_CLAIM_AFTER, time.time())
        routine.nav.go_to_lobby()


def _wait_for_energy(nav: Navigator, device: Device, minimum: int = config.MIN_RUN_ENERGY, maintenance=None) -> None:
    """Loop mode: idle in the lobby until a run is affordable again (energy refills over time)."""
    while True:
        if maintenance:
            maintenance()
        try:
            energy = nav.go_to_lobby().energy or 0
            if energy >= minimum:
                return
            log.info("Waiting for energy (%d/%d)", energy, minimum)
        except NavigationError as e:  # e.g. a screen that settles later: check again next time
            log.error("Waiting for energy: %s", e)
        device.wait(config.ENERGY_WAIT_POLL)


def make_runner(dry_run: bool, stop: threading.Event | None = None) -> Callable[[RunRequest], Report]:
    """Build the UI's Start action without touching the emulator until it is called."""
    return Runner(dry_run, stop).run


class Runner:
    def __init__(self, dry_run: bool, stop: threading.Event | None = None):
        self.dry_run, self.stop = dry_run, stop
        self.ocr: Ocr | None = None
        self.catalog: Catalog | None = None
        self.status = StatusPublisher()
        self.history = History()

    def _play_level(self, state: RunState, device: Device, nav: Navigator) -> LevelScreen:
        if state.build is None:
            state.build = BuildState()
        if state.request.mode is Mode.ELITE and nav.level_modifiers:
            state.build.set_modifiers(nav.level_modifiers)
            nav.level_modifiers = None  # consume the preview; routine modes share this callback
        active_build = state.build
        player = Player(device, self.ocr, state.request.build, self.catalog, state.request.ads,
                        build_state=active_build, inspect_modifiers=state.request.mode is Mode.ELITE)
        result = player.play_level()
        if state.active_level is not None:
            values = getattr(player, "result_values", (None, {}))
            self._record_level(state, result.value, values)
            state.results.append(result)
            log.info("Level finished: %s (run %d)", result.value, len(state.results))
            request = state.request
            if request.farm:
                state.farm_stopped = state.farm.observe(result is LevelScreen.VICTORY)
                if state.farm_stopped:
                    log.warning("Farm stopped after repeated defeats on stage 1")
        state.build = None
        return result

    def _record_level(self, state: RunState, outcome: str, values=(None, {})) -> None:
        request, active, build = state.request, state.active_level, state.build
        assert active is not None and build is not None
        damage, rewards = values
        self.history.record(RunRecord(request.mode.value, request.build.profile, outcome,
            max(0., time.monotonic() - active.started), level=active.level, energy=active.energy,
            skills=list(build.taken), modifiers=[m.name for m in build.modifiers or ()],
            damage=damage, rewards=rewards, loadout=asdict(request.build.loadout),
            build_config=build_signature(request.build), id=build.run_id,
            progress={"current": build.run_progress.rolls, "total": build.run_progress.total,
                      "unit": build.run_progress.unit}, revives_seen=build.context.revives_seen))
        state.active_level = None

    def _attempt(self, state: RunState) -> Report:
        request = state.request
        self.status.publish(Observation("connection", reason="decision_connecting", source="phase"))
        serial, adb, launched = state.provider.start()
        device = Device(serial, stop=self.stop, adb=adb)
        if self.ocr is None:
            self.ocr = Ocr()
        if self.catalog is None:
            self.catalog = Catalog()
        ocr, catalog = self.ocr, self.catalog
        dry_run = self.dry_run
        nav = Navigator(device, ocr, dry_run=dry_run, ads=request.ads, elite_energy=request.elite_energy)
        if request.mode in (Mode.CHAOS, Mode.CONQUEST):
            if launched:
                nav.wait_for_lobby(config.GAME_LOAD_TIMEOUT)
            return EventMode(device, ocr, nav, request.mode.value).run(dry_run=dry_run)
        if request.mode is Mode.PARTY_EXPEDITION:
            if launched:
                nav.wait_for_lobby(config.GAME_LOAD_TIMEOUT)
            return PartyExpedition(device, ocr, nav, request.build, catalog, request.party_role, state.party).run(
                request.party_runs, dry_run=dry_run)

        def play_level():
            return self._play_level(state, device, nav)

        def resume_level():
            leftover = state.active_level is None
            play_level()
            if leftover:
                state.resumed += 1

        if not dry_run:
            nav.resume_level = resume_level
        if not launched and nav.level_in_progress():  # left running by a stopped bot: play it out first
            if dry_run:
                raise NavigationError("An adventure is already in progress. Finish it before running a simulation.")
            log.info("A level is in progress: playing it out")
            resume_level()
        elif launched:
            nav.wait_for_lobby(config.GAME_LOAD_TIMEOUT)
        nav.detect_language()
        if state.active_level is not None:
            active = state.active_level
            log.warning("Level interrupted: stage %s, energy spent %s, no result after recovery",
                        active.level, active.energy)
            self._record_level(state, "abandoned")
            state.build = None
        if dry_run:
            if request.farm:
                self._start_farm(state, nav)
            else:
                _start_level(nav, request)
            return Report(dry_run=True)
        return self._run_levels(state, device, nav, play_level)

    def _start_farm(self, state: RunState, nav: Navigator) -> int:
        request = state.request

        def choose(latest):
            level = state.farm.choose(self.history.summary(), request.mode.value, request.build.profile,
                                      latest, objective=request.farm_objective, loadout=asdict(request.build.loadout),
                                      build_config=build_signature(request.build))
            if row := state.farm.evidence:
                log.info("Farm %s: stage %d, %d runs, %.0f%% wins, reward samples %s, rewards/energy %s, rewards/min %s",
                         request.farm_objective, level, row["runs"], row["win_rate"] * 100,
                         row.get("reward_samples", {}), row.get("rewards_per_energy", {}),
                         row.get("rewards_per_minute", {}))
            else:
                log.info("Farm %s: stage %d, collecting comparable results", request.farm_objective, level)
            return level

        return nav.start_farm(request.mode, choose)

    def _run_levels(self, state: RunState, device: Device, nav: Navigator,
                    play_level: Callable[[], LevelScreen]) -> Report:
        request, results = state.request, state.results
        selected = request.routine_parts
        run_routine = request.full if selected is None else bool(selected)
        cycle = 0
        def routine_instance():
            routine = Routine(device, self.ocr, nav, request.ads, play_level, request.build, self.catalog)
            routine.schedule = state.schedule
            return routine

        def maintenance():
            due = state.schedule.due(time.time()) if run_routine else ()
            if due:
                routine_instance().run_parts(RoutineProgress(), only=due)
            if run_routine and request.claim_events and time.time() >= state.events_next:
                state.events_next = time.time() + 1800
                collect_events(device, self.ocr, nav)

        while True:
            cycle += 1
            if run_routine and not state.routine_done:  # a retry resumes at the part that broke
                routine = routine_instance()
                routine.run_parts(state.routine, only=selected)
                if routine.patrol_wait is not None:  # just opened by the routine: not again before the first level
                    state.patrol_next = _patrol_next(routine.patrol_wait, time.time())
            state.routine_done = True
            while True:
                if state.farm_stopped or not request.repeat and results:
                    return state.report()
                _claim_patrol(Routine(device, self.ocr, nav, request.ads), state)  # quick patrols spend energy
                maintenance()
                if request.repeat and _energy(nav) < request.minimum_energy:
                    if nav.claim_free_energy() < request.minimum_energy:
                        break
                try:
                    state.build = BuildState()  # each new level starts a fresh line
                    self.status.publish(Observation("lobby", reason="decision_start_level", source="phase"))
                    played = self._start_farm(state, nav) if request.farm else _start_level(nav, request)
                except StarsUnavailable as e:  # no star list or no beaten level on this account (yet)
                    if request.farm:
                        raise
                    log.warning("%s: playing the last unlocked level instead", e)
                    request = state.request = replace(request, level=None, last_beaten=False, pending_stars=False)
                    played = nav.start_latest(request.mode)
                state.active_level = ActiveLevel(played, getattr(nav, "last_energy_cost", None))
                play_level()
                nav.go_to_lobby()
                request = state.request
                if state.farm_stopped or not request.repeat:
                    return state.report()
            if not request.loop:
                break
            log.info("Cycle %d finished (%d runs so far), waiting for energy", cycle, len(results))
            if run_routine:
                _wait_for_energy(nav, device, request.minimum_energy, maintenance=maintenance)
            else:
                _wait_for_energy(nav, device, request.minimum_energy)
            state.next_cycle()
        if not results and not run_routine:
            raise NoEnergyError("Not enough energy to start a run, and no free energy to claim")
        return state.report()

    def run(self, request: RunRequest) -> Report:
        """attempt() until it finishes. On an error the provider reconnects/relaunches as supported
        (MuMu restarts its emulator; Google reconnects and may restart only the game). The same error more than
        MAX_SAME_ERROR times in a row (no level or routine part finished in between) stops the bot with that error."""
        if self.stop is not None:
            self.stop.clear()
        state = RunState(request, create_provider(request, self.stop))
        errors: dict[str, int] = {}
        progress = 0
        while True:
            try:
                return self._attempt(state)
            except Stopped:
                raise
            except Exception as e:
                if self.dry_run or request.mode in (Mode.PARTY_EXPEDITION, Mode.CHAOS, Mode.CONQUEST) or isinstance(e, (NoEnergyError, LevelUnavailable)) or (
                        isinstance(e, EmulatorError) and e.key in PERMANENT_ERRORS):
                    raise
                done = state.completed
                if done > progress:  # a level or routine part finished since the last error: start counting again
                    errors.clear()
                    progress = done
                key = _error_key(e)
                errors[key] = errors.get(key, 0) + 1
                if errors[key] > config.MAX_SAME_ERROR:
                    log.error("Same error %d times, giving up: %s", errors[key], e)
                    raise
                log.error("Error: %s. Recovering %s and trying again (%d/%d)",
                          e, PROVIDERS[request.provider], errors[key], config.MAX_SAME_ERROR)
                try:
                    state.provider.recover(restart_game=errors[key] > 1)
                except Stopped:
                    raise
                except EmulatorError as recovery_error:
                    # A disconnected emulator must not escape the runner's bounded retry policy.
                    log.error("Provider recovery failed: %s", recovery_error)
