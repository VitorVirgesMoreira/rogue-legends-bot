"""Regression for the real Potion Maker's Hut screen that stopped the user's run."""

from pathlib import Path

import cv2
import pytest

from roguebot import labels
from roguebot.play import Player
from roguebot.screens import LevelScreen, classify_level_screen, health_fraction
from roguebot.event_rules import event_effect
from roguebot.skills import Catalog
from roguebot.vision import Text

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def language():
    labels.set_language("en")
    yield
    labels.set_language(None)


def potion():
    return cv2.imread(str(FIXTURES / "en_level_potion_makers_hut.png"))


def test_real_potion_screen_selects_strength_at_sixty_one_percent_hp(ocr):
    image = potion()
    texts = ocr.read(image)
    assert health_fraction(texts) == pytest.approx(1.4 / 2.3)
    state = classify_level_screen(image, texts)
    assert state.kind is LevelScreen.EVENT
    assert state.tap == (922, 2031)


@pytest.mark.parametrize("hp,healing", [("574.9k/2.3m", True), ("575k/2.3m", True),
    ("575.1k/2.3m", False), ("2.3m/2.3m", False), ("unreadable HP", False)])
def test_real_potion_options_at_the_hp_threshold_and_with_unknown_hp(ocr, hp, healing):
    image = potion()
    texts = [Text(hp, t.x1, t.y1, t.x2, t.y2) if "/" in t.text else t for t in ocr.read(image)]
    state = classify_level_screen(image, texts)
    assert state.kind is LevelScreen.EVENT
    assert state.tap == ((510, 2031) if healing else (922, 2031))


def test_disabled_healing_is_skipped_even_at_low_hp(ocr):
    image = potion()
    image[1911:2151, 390:630] = 80
    texts = [Text("10k/2.3m", t.x1, t.y1, t.x2, t.y2) if "/" in t.text else t for t in ocr.read(potion())]
    assert classify_level_screen(image, texts).tap == (922, 2031)


@pytest.mark.parametrize("text,effect", [("Strength Potion +15% ATK", "damage"),
    ("+15% ATK", "damage"), ("Poción de Fuerza +15% ATQ", "damage"),
    ("Take 15% damage", None), ("Lose 15% ATK", None)])
def test_damage_bonus_is_distinct_from_damage_taken(text, effect):
    from roguebot.vision import normalize
    assert event_effect(normalize(text)) == effect


def test_player_advances_past_the_real_potion_screen_without_recovery(ocr, tmp_path):
    class Device:
        def __init__(self):
            victory = cv2.imread(str(FIXTURES / "en_google_level_victory_x2.png"))
            self.frames = iter([potion(), potion(), victory, victory])
            self.taps = []

        def screenshot(self):
            return next(self.frames)

        def tap(self, x, y):
            self.taps.append((x, y))
    device = Device()
    result = Player(device, ocr, catalog=Catalog(tmp_path / "skills.json"), ads=False).play_level()
    assert result is LevelScreen.VICTORY
    assert len(device.taps) == 2 and device.taps[0] == (922, 2031)
