"""Only an observed transition commits a skill pick to the build."""

import pytest

from roguebot import labels, play
from roguebot.build import Build, BuildState
from roguebot.device import DeviceError
from roguebot.screens import LevelScreen
from roguebot.skills import Catalog
from test_party import ReplayDevice, ReplayOcr, result
from test_skill_screens import PROMPT, card


@pytest.fixture(autouse=True)
def language(monkeypatch):
    labels.set_language("en")
    monkeypatch.setattr(play.time, "sleep", lambda _: None)
    yield
    labels.set_language(None)


def offer(rarity="Common"):
    return [PROMPT, *card(rarity, "Fire Weapon", "Weapon Attacks deal fire damage.", 928)]


def test_failed_dispatch_does_not_add_an_unlearned_skill(tmp_path):
    class Disconnected(ReplayDevice):
        def tap(self, x, y):
            raise DeviceError("disconnected before input")

    device = Disconnected([offer(), offer()])
    state = BuildState()
    player = play.Player(device, ReplayOcr(device), Build(profile="fire"), Catalog(tmp_path / "skills.json"),
                         build_state=state)
    with pytest.raises(DeviceError):
        player.play_level()
    assert state.taken == [] and state.pending_skill is None


def test_recovery_keeps_a_pending_pick_until_a_confirmed_transition(tmp_path):
    class LoseCapture(ReplayDevice):
        def screenshot(self):
            try:
                return super().screenshot()
            except StopIteration:
                raise DeviceError("connection lost after input")

    state = BuildState()
    catalog = Catalog(tmp_path / "skills.json")
    device = LoseCapture([offer(), offer()])
    with pytest.raises(DeviceError):
        play.Player(device, ReplayOcr(device), Build(profile="fire"), catalog, build_state=state).play_level()
    assert state.taken == [] and state.pending_skill is not None
    recovered = ReplayDevice([offer(), offer(), result(LevelScreen.VICTORY), result(LevelScreen.VICTORY)])
    player = play.Player(recovered, ReplayOcr(recovered), Build(profile="fire"), catalog, build_state=state)
    assert player.play_level() is LevelScreen.VICTORY
    assert state.taken == ["Fire Weapon"] and state.pending_skill is None


def test_an_upgrade_offer_with_the_same_name_is_a_new_choice(tmp_path):
    victory = result(LevelScreen.VICTORY)
    device = ReplayDevice([offer(), offer(), offer("Legendary"), offer("Legendary"), victory, victory])
    state = BuildState()
    player = play.Player(device, ReplayOcr(device), Build(profile="fire"), Catalog(tmp_path / "skills.json"),
                         build_state=state)
    assert player.play_level() is LevelScreen.VICTORY
    assert state.taken == ["Fire Weapon", "Fire Weapon"]
    assert state.owned["fireweapon"].rarity == "legendary"
