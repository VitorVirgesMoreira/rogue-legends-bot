"""User's burn equipment, health decisions, x4 and the ad-skip revive pass."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from roguebot import config, labels
from roguebot.build import BURN, Build, BuildState, choose, shop_order
from roguebot.play import Player
from roguebot.screens import LevelScreen, classify_level_screen, game_speed, health_fraction
from roguebot.skills import Catalog, Skill
from roguebot.vision import Text

FIXTURES = Path(__file__).parent / "fixtures"


def skill(name, damage_type=None, rarity="common", description=""):
    return Skill(name, "en", rarity, damage_type,
                 "magic" if damage_type in ("fire", "ice", "lightning") else "physical", "damage", description)


def test_burn_profile_combines_magic_fire_with_physical_critical_and_shuriken():
    fire = skill("Fire Weapon", "fire")
    critical = skill("Critical Hit Rate Up", rarity="legendary")
    shuriken = skill("Shuriken Throw", "shuriken", rarity="mythic")
    ice = skill("Ice Weapon", "ice", rarity="mythic")
    build = Build(profile=BURN)
    assert choose([ice, critical, shuriken, fire], build, BuildState(), False) == 3
    assert choose([ice, shuriken, critical], build, BuildState(), False) == 2
    assert choose([ice, shuriken], build, BuildState(), False) == 1


def test_burn_profile_breaks_ties_by_rarity_and_rerolls_off_build_skills():
    build = Build(profile=BURN)
    assert choose([skill("Fire Mastery", "fire"), skill("Fire Mastery", "fire", "legendary")],
                  build, BuildState(), False) == 1
    assert choose([skill("Ice Weapon", "ice"), skill("Non-Critical Damage Up")],
                  build, BuildState(), True) is None
    assert choose([skill("Daño Crítico"), skill("Poison Strike", "venom")], build, BuildState(), False) == 0


def test_burn_shop_saves_coins_for_fire_critical_and_shuriken():
    offer = [skill("Ice Weapon", "ice", "mythic"), skill("Fire Weapon", "fire"),
             skill("Critical Mastery"), skill("Shuriken", "shuriken")]
    build = Build(profile=BURN)
    assert shop_order(offer, build, BuildState(), False) == [1, 2]  # establish fire before adding a secondary
    assert shop_order(offer[:1], build, BuildState(), True) is None
    assert shop_order(offer[:1], build, BuildState(), False) == []


def event(hp, *, max_hp=False):
    image = np.full((2560, 1440, 3), (40, 100, 200), dtype=np.uint8)
    texts = [Text("A Moment of Rest", 400, 1370, 1040, 1430),
             Text("Rest", 240, 1760, 360, 1820), Text("Train", 660, 1760, 780, 1820),
             Text("Restore 39% HP", 180, 2240, 420, 2300),
             Text("Gain 10% Max HP" if max_hp else "Upgrade 1 Existing Skill", 580, 2240, 860, 2300)]
    if hp is not None:
        texts.append(Text(hp, 420, 50, 670, 110))
    return image, texts


@pytest.mark.parametrize("hp,expected_x", [("100k/100k", 720), ("25k/100k", 300),
    ("24.9k/100k", 300), ("0/100k", 300), (None, 720), ("garbled HP", 720)])
@pytest.mark.parametrize("max_hp", [False, True])
def test_event_heals_at_or_below_one_quarter(hp, expected_x, max_hp):
    image, texts = event(hp, max_hp=max_hp)
    state = classify_level_screen(image, texts)
    assert state.kind is LevelScreen.EVENT and state.tap == (expected_x, 2028)


def test_disabled_heal_is_not_selected_even_at_low_hp():
    image, texts = event("10k/100k")
    image[1908:2148, 180:420] = 80
    assert classify_level_screen(image, texts).tap == (720, 2028)


def test_unknown_hp_never_chooses_healing_when_leave_is_available():
    image, texts = event(None)
    texts[2] = Text("Exit", 660, 1760, 780, 1820)
    texts.pop(4)
    assert classify_level_screen(image, texts).tap == (720, 2028)


@pytest.mark.parametrize("hp,fraction", [("107,2k/152,5k", 107.2/152.5), ("1.3m / 2m", .65),
    ("2k/1k", None), ("0/0", None), ("unreadable", None)])
def test_hp_ratio_parsing_and_validation(hp, fraction):
    found = health_fraction([Text(hp, 420, 50, 670, 110)])
    assert found == pytest.approx(fraction) if fraction is not None else found is None
    assert health_fraction([Text("1/30", 10, 1300, 140, 1400)]) is None


def test_real_rest_screen_selects_upgrade_at_seventy_percent_hp(ocr):
    image = cv2.imread(str(FIXTURES / "level_event_rest.png"))
    texts = ocr.read(image)
    assert health_fraction(texts) == pytest.approx(107.2/152.5)
    assert classify_level_screen(image, texts).tap[0] > 720


@pytest.mark.parametrize("read_hp", [True, False])
def test_sole_central_rest_advances_even_at_full_or_unreadable_hp(ocr, read_hp):
    image = cv2.imread(str(FIXTURES / "en_level_rest_only.png"))
    texts = ocr.read(image)
    if read_hp:
        assert health_fraction(texts) == 1
    else:
        texts = [t for t in texts if t.center[1] > 200]
    state = classify_level_screen(image, texts)
    assert state.kind is LevelScreen.EVENT
    assert 680 < state.tap[0] < 760 and 2000 < state.tap[1] < 2100


def test_missing_train_label_does_not_turn_an_off_center_heal_into_mandatory_rest():
    image, texts = event("100k/100k")
    texts = [t for t in texts if t.norm not in ("train", "upgrade 1 existing skill")]
    assert classify_level_screen(image, texts).kind is LevelScreen.UNKNOWN


def speed_text(speed):
    return [Text(f">>x{speed}", 80, 2410, 230, 2460)]


class TapDevice:
    def __init__(self):
        self.taps = []

    def tap(self, x, y, settle=0):
        self.taps.append((x, y))


def test_x4_is_recognized_only_on_the_actual_speed_button():
    assert game_speed(speed_text(4)) == 4
    assert game_speed([Text("x4", 50, 2250, 160, 2330)]) is None


def test_real_google_x4_capture_is_recognized(ocr):
    image = cv2.imread(str(FIXTURES / "en_google_level_victory_x2.png"))
    assert game_speed(ocr.read(image)) == 4


def test_already_x4_is_preserved_and_x2_advances_once():
    device = TapDevice()
    player = Player(device, None)
    assert not player._ensure_speed(speed_text(4)) and not device.taps
    assert player._ensure_speed(speed_text(2))
    assert not player._ensure_speed(speed_text(4))
    assert device.taps == [config.SPEED_BUTTON]


def test_speed_does_not_retap_a_stale_frame_and_restores_x2_if_x4_is_locked():
    device = TapDevice()
    player = Player(device, None)
    assert player._ensure_speed(speed_text(1))
    assert not player._ensure_speed(speed_text(1))  # read before the label has changed
    assert player._ensure_speed(speed_text(2))
    assert player._ensure_speed(speed_text(1))      # cycle without x4: restore x2
    assert not player._ensure_speed(speed_text(2))
    assert device.taps == [config.SPEED_BUTTON] * 3


@pytest.mark.parametrize("ads", [True, False])
def test_real_revive_uses_only_free_button_when_pass_rewards_are_enabled(ocr, tmp_path, monkeypatch, ads):
    monkeypatch.setattr("roguebot.play.time.sleep", lambda seconds: None)
    class Device(TapDevice):
        frames = iter(["level_revive.png", "level_victory.png", "level_victory.png"])
        def screenshot(self):
            return cv2.imread(str(FIXTURES / next(self.frames)))
    device = Device()
    try:
        labels.set_language("es")
        assert Player(device, ocr, catalog=Catalog(tmp_path / "skills.json"), ads=ads).play_level() is LevelScreen.VICTORY
        assert len(device.taps) == (2 if ads else 1)
        if ads:
            assert device.taps[0][0] > 720 and 1400 < device.taps[0][1] < 1500
    finally:
        labels.set_language(None)
