"""Fixed elite costs must survive navigation, repeat loops, low energy and persistence."""

from types import SimpleNamespace

import numpy as np
import pytest

from roguebot import config, labels
from roguebot.navigation import Navigator, NoEnergyError
from roguebot.request import RunRequest, build_request
from roguebot.screens import Mode
from roguebot.vision import Text


@pytest.mark.parametrize("cost", [5, 10, 15])
def test_request_accepts_and_preserves_selected_cost(cost):
    request = build_request("elite", "latest", "", elite_energy=str(cost))
    assert request.elite_energy == cost and request.minimum_energy == cost
    assert build_request("normal", "latest", "", elite_energy=cost).minimum_energy == 5


@pytest.mark.parametrize("value", [0, 1, 20, -5, True, 5.0, "bad"])
def test_invalid_api_cost_is_rejected(value):
    with pytest.raises(ValueError, match="bad_elite_energy"):
        RunRequest(Mode.ELITE, None, elite_energy=value)


def test_automatic_mode_keeps_backwards_compatible_minimum():
    assert build_request("elite", "latest", "", elite_energy="auto").elite_energy is None
    assert RunRequest(Mode.ELITE, None).minimum_energy == 5


def dialog(cost, energy):
    return [Text("Elite Mode", 500, 600, 940, 650), Text("START", 600, 1880, 840, 1930),
            Text(f"X{cost}", 690, 1960, 750, 2000), Text(f"{energy}/36", 780, 60, 920, 110)]


def nav_with_dialog(start, energy, selected, monkeypatch):
    monkeypatch.setattr("roguebot.navigation.time.sleep", lambda seconds: None)
    state, taps = [start], []
    def tap(x, y):
        taps.append((x, y))
        state[0] += 5 if (x, y) == config.ELITE_COST_PLUS else -5
    nav = Navigator(SimpleNamespace(tap=tap), None, elite_energy=selected)
    nav._capture = lambda: (np.zeros((2560, 1440, 3), np.uint8), dialog(state[0], energy))
    return nav, state, taps


@pytest.mark.parametrize("start,target", [(5, 5), (15, 5), (5, 10), (15, 10), (5, 15), (15, 15)])
def test_navigation_sets_exact_cost_even_with_abundant_energy(monkeypatch, start, target):
    labels.set_language("en")
    try:
        nav, state, taps = nav_with_dialog(start, 100, target, monkeypatch)
        assert nav._set_elite_cost().text == "START"
        assert state[0] == target and len(taps) == abs(start-target)//5
    finally:
        labels.set_language(None)


def test_selected_cost_is_not_downgraded_when_energy_is_insufficient(monkeypatch):
    nav, _, taps = nav_with_dialog(5, 10, 15, monkeypatch)
    with pytest.raises(NoEnergyError):
        nav._set_elite_cost()
    assert not taps


def test_runner_stops_before_starting_a_cheaper_run(monkeypatch):
    import roguebot.runner as main
    from test_main import FakeNav, FakeEmulator, FakeRoutine, run_with
    monkeypatch.setattr(main, "create_provider", lambda request, stop: FakeEmulator(request.mumu_folder, stop))
    monkeypatch.setattr(main, "Routine", FakeRoutine)
    nav = FakeNav(energy=10)
    with pytest.raises(NoEnergyError):
        run_with(monkeypatch, nav, [], RunRequest(Mode.ELITE, 4, repeat=True, elite_energy=15))
    assert nav.started == ["detect"] and nav.claims == 1


def test_energy_wait_uses_selected_cost_instead_of_five():
    import roguebot.runner as main
    energy, waits = [5], []
    nav = SimpleNamespace(go_to_lobby=lambda: SimpleNamespace(energy=energy[0]))
    def wait(seconds):
        waits.append(energy[0])
        energy[0] += 5
    main._wait_for_energy(nav, SimpleNamespace(wait=wait), minimum=15)
    assert waits == [5, 10]
