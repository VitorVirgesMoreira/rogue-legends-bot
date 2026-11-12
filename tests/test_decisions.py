"""Two reads confirm the offer itself; card dispatch never proves a flip."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from roguebot import labels
from roguebot.decisions import CardFlipError, CardFlips, DecisionGuard
from roguebot.play import Player, PlayError
from roguebot.screens import LevelScreen, LevelState, classify_level_screen
from roguebot.skills import Catalog
from roguebot.vision import Text
from test_events import event, LEAVE
from test_party import ReplayDevice, ReplayOcr, result


def test_offer_change_and_target_movement_restart_confirmation():
    guard = DecisionGuard()
    image, texts = event()
    state = LevelState(LevelScreen.EVENT, LEAVE)
    assert not guard.observe(state, image, texts)
    assert guard.observe(state, image, texts)
    changed = [Text("Raid Again", *[t.x1, t.y1, t.x2, t.y2]) if t.text == "Raid" else t for t in texts]
    assert not guard.observe(state, image, changed)
    assert guard.observe(state, image, changed)
    assert not guard.observe(LevelState(state.kind, (LEAVE[0]-100, LEAVE[1])), image, changed)


def test_small_position_jitter_is_stable_and_repeated_action_waits(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("roguebot.decisions.time.monotonic", lambda: clock[0])
    image, texts = event()
    guard, state = DecisionGuard(), LevelState(LevelScreen.EVENT, LEAVE)
    assert not guard.observe(state, image, texts)
    jitter = [Text(t.text, t.x1+2, t.y1+3, t.x2+2, t.y2+3) for t in texts]
    assert guard.observe(LevelState(state.kind, (LEAVE[0]+2, LEAVE[1]+3)), image, jitter)
    guard.acted()
    assert not guard.observe(state, image, texts) and guard.reason == "decision_wait_change"
    clock[0] += 3
    assert guard.observe(state, image, texts)


def test_transitions_break_consecutive_confirmation():
    image, texts = event()
    guard, state = DecisionGuard(), LevelState(LevelScreen.EVENT, LEAVE)
    assert not guard.observe(state, image, texts)
    assert guard.observe(LevelState(LevelScreen.UNKNOWN), image, texts)
    assert not guard.observe(state, image, texts)


def test_real_skill_offer_stabilizes_across_ocr_spelling_variations(ocr):
    from conftest import fixture_image

    guard = DecisionGuard()
    for variant, stable in (("a", False), ("b", True)):
        img = fixture_image(Path(__file__).parent / "fixtures" / f"en_elite_skill_ocr_{variant}.png")
        texts = ocr.read(img)
        state = classify_level_screen(img, texts)
        assert state.kind is LevelScreen.SKILL_PICK
        assert guard.observe(state, img, texts) is stable
    texts = [Text(t.text.replace("+", ""), t.x1, t.y1, t.x2, t.y2) if "opening" in t.norm else t for t in texts]
    assert not guard.observe(state, img, texts)


def test_player_never_acts_on_a_single_transient_offer(tmp_path):
    labels.set_language("en")
    try:
        image, texts = event()
        texts[0] = Text("Unknown Shrine", 360, 1370, 1080, 1430)
        frames = [(image, texts), (image, result(LevelScreen.VICTORY)), (image, result(LevelScreen.VICTORY))]
        device = ReplayDevice(frames)
        assert Player(device, ReplayOcr(device), catalog=Catalog(tmp_path/'skills.json')).play_level() is LevelScreen.VICTORY
        assert device.taps == [result(LevelScreen.VICTORY)[-1].center]
    finally:
        labels.set_language(None)


def test_unstable_known_screen_has_a_bounded_timeout(monkeypatch, tmp_path):
    from roguebot import play
    ticks = iter(range(1000))
    monkeypatch.setattr(play.time, "monotonic", lambda: next(ticks)*5)
    monkeypatch.setattr(play.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(play, "DEBUG_DIR", tmp_path)
    image, texts = event()
    frames = []
    for i in range(30):
        changed = [texts[0], Text(str(i), 70, 155, 150, 195), *texts[2:]]
        frames.append((image, changed))
    device = ReplayDevice(frames)
    with pytest.raises(PlayError, match="stabilize"):
        Player(device, ReplayOcr(device), catalog=Catalog(tmp_path/'skills.json')).play_level()
    assert device.taps == []


def test_cards_wait_for_the_pending_card_instead_of_picking_another(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("roguebot.decisions.time.monotonic", lambda: clock[0])
    image = np.zeros((2560, 1440, 3), np.uint8)
    first, second = (299, 1280), (579, 1280)
    for x, y in (first, second):
        image[y-60:y+60, x-50:x+50] = (255, 200, 80)
    cards = CardFlips()
    assert cards.choose(image, first) == first
    cards.tapped(first)
    assert cards.choose(image, second) is None  # animation still shows the closed first card
    clock[0] += 3
    assert cards.choose(image, second) == first  # retry the missed tap, not a different card
    cards.tapped(first)
    image[1220:1340, 249:349] = 0
    assert cards.choose(image, second) == second
    cards.reset()
    assert cards.pending is None and cards.attempts == 0


def test_unconfirmed_card_and_finished_grid_cannot_wait_forever(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("roguebot.decisions.time.monotonic", lambda: clock[0])
    image = np.full((2560, 1440, 3), (255, 200, 80), np.uint8)
    cards, point = CardFlips(), (299, 1280)
    for _ in range(3):
        assert cards.choose(image, point) == point
        cards.tapped(point)
        clock[0] += 3
    with pytest.raises(CardFlipError, match="3 attempts"):
        cards.choose(image, point)
    cards.reset()
    assert cards.choose(image, None) is None
    clock[0] += 21
    with pytest.raises(CardFlipError, match="last flip"):
        cards.choose(image, None)
