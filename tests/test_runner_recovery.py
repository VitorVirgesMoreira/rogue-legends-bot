"""Progress remains cumulative when the routine starts a new cycle."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import fixture_image
from roguebot import config, runner
from roguebot.device import Stopped, ViewportUnavailable
from roguebot.navigation import Navigator
from roguebot.request import RunRequest
from roguebot.screens import Lobby, Mode
from roguebot.vision import Text
from test_main import FakeEmulator, FakeNav, FakeRoutine


def test_completed_parts_in_new_cycles_reset_the_recovery_budget(monkeypatch):
    nav = FakeNav(energy=0)
    cycles = []
    provider = FakeEmulator("")

    class Routine(FakeRoutine):
        def run_parts(self, progress, *, only=None):
            if not progress.parts:
                progress.parts.append(("vip", "done"))
                raise runner.NavigationError("connection lost")
            progress.parts.append(("raid", "done"))

    def next_cycle(*args, **kwargs):
        cycles.append(len(cycles))
        if len(cycles) > runner.config.MAX_SAME_ERROR + 1:
            raise Stopped("finished replay")

    monkeypatch.setattr(runner, "create_provider", lambda *args: provider)
    monkeypatch.setattr(runner, "Device", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(runner, "Ocr", object)
    monkeypatch.setattr(runner, "Catalog", object)
    monkeypatch.setattr(runner, "Navigator", lambda *args, **kwargs: nav)
    monkeypatch.setattr(runner, "Routine", Routine)
    monkeypatch.setattr(runner, "_wait_for_energy", next_cycle)
    monkeypatch.setattr(runner, "collect_events", lambda *args: 0)
    with pytest.raises(Stopped, match="finished replay"):
        runner.make_runner(False)(RunRequest(Mode.NORMAL, 4, repeat=True, full=True, loop=True))
    assert len(cycles) == runner.config.MAX_SAME_ERROR + 2


def test_run_report_is_a_snapshot_of_results_and_routine_progress():
    state = runner.RunState(RunRequest(Mode.NORMAL, 4), FakeEmulator(""))
    state.routine.parts.append(("vip", "done"))
    report = state.report()
    state.results.append(runner.LevelScreen.VICTORY)
    state.routine.parts.clear()
    assert report.results == [] and report.parts == [("vip", "done")]


def test_farm_waits_for_elite_and_uses_its_beaten_stage_after_a_dark_frame(ocr, monkeypatch):
    image = fixture_image(Path(__file__).parent / "fixtures" / "en_elite_stars_locked_28.png")
    texts = ocr.read(image)
    stars = Text("Star Challenge", 790, 1980, 990, 2040)
    normal = Lobby(Mode.NORMAL, "47. Normal Chapter", stars, stars, 46)
    elite = Lobby(Mode.ELITE, "28. The Great Sea (Elite) IV", stars, stars, 46)
    frames = iter((normal, ViewportUnavailable("dark transition"), normal, elite))
    taps, waits, started = [], [], []
    device = SimpleNamespace(tap=lambda *point: taps.append(point), wait=waits.append)
    nav = Navigator(device, ocr)

    def lobby():
        frame = next(frames)
        if isinstance(frame, Exception):
            raise frame
        return frame

    monkeypatch.setattr(nav, "go_to_lobby", lobby)
    monkeypatch.setattr(nav, "_capture", lambda: (image, texts))
    monkeypatch.setattr(nav, "_press_start", lambda button, mode: started.append((button, mode)))
    controller = runner.Runner(dry_run=True)
    monkeypatch.setattr(controller.history, "summary", lambda: [])
    state = runner.RunState(RunRequest(Mode.ELITE, None, farm=True), FakeEmulator(""))
    state.farm.target = 46  # an invalid target must not persist after the selected mode is confirmed

    assert controller._start_farm(state, nav) == 27
    assert taps == [config.ELITE_TOGGLE, stars.center]
    assert len(waits) == 2
    assert len(started) == 1 and started[0][0].norm == "ready" and started[0][1] is Mode.ELITE
