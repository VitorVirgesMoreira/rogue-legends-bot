"""Tower runs through the countdown and claims the final chest."""

from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from conftest import fixture_image
from roguebot import config, labels
from roguebot.mode_screens import parse_fight_result, parse_fight_skip, parse_tower
from roguebot.routine import DONE, Routine
from roguebot.vision import find
from test_routine import FakeDevice, FakeNav


def read(ocr, name):
    img = fixture_image(Path(__file__).parent / "fixtures" / name)
    img = cv2.resize(img, config.SCREEN_SIZE, interpolation=cv2.INTER_CUBIC)
    return img, ocr.read(img)


@pytest.mark.parametrize(("name", "checked"), [
    ("tower_current_unchecked.png", False),
    ("tower_current_next_tower.png", True),
    ("tower_auto_advance.png", False),
])
def test_tower_checkbox_recognizes_checked_and_unchecked(ocr, name, checked):
    img, texts = read(ocr, name)
    screen = parse_tower(texts, img)
    assert screen.auto_next.checked is checked
    assert abs(screen.auto_next.point[0] - 625) < 12


@pytest.mark.parametrize("tickets_left", [19, 0])
def test_auto_next_claims_the_chest_and_challenges_the_next_tower_if_possible(ocr, monkeypatch, tickets_left):
    monkeypatch.setattr(config, "POLL_INTERVAL", 0)
    board, texts = read(ocr, "tower_current_unchecked.png")
    next_board, next_texts = read(ocr, "tower_current_next_tower.png")
    initial = parse_tower(texts, board)
    x, y = initial.auto_next.point
    checked_x, checked_y = parse_tower(next_texts, next_board).auto_next.point
    checked = board.copy()
    checked[y-20:y+20, x-20:x+20] = next_board[checked_y-20:checked_y+20, checked_x-20:checked_x+20]

    fight = read(ocr, "tower_current_fight.png")
    skip = parse_fight_skip(fight[1]).center
    countdown = read(ocr, "tower_current_countdown.png")
    boss_win = read(ocr, "tower_current_boss_win.png")
    chest = read(ocr, "tower_current_clear_chest.png")
    claim = read(ocr, "tower_current_chest_reward.png")
    defeat = read(ocr, "en_tower_defeat.png")
    assert parse_fight_result(countdown[1]).next_floor.norm == "next (2)"
    assert parse_fight_result(boss_win[1]).next_floor is None
    assert find(claim[1], labels.TAP_TO_CLAIM)

    if not tickets_left:
        next_texts = [replace(t, text="0/10") if t.norm == "19/10" else t for t in next_texts]
    next_tower = parse_tower(next_texts, next_board)
    assert next_tower.tickets == tickets_left
    frames = [(board, texts), (checked, texts), fight, fight, countdown, countdown, fight,
              boss_win, chest, chest, claim, (next_board, next_texts)]
    expected_taps = [(x, y), initial.challenge.center, skip, skip, parse_fight_result(boss_win[1]).button.center,
                     config.TOWER_CHEST, config.TOWER_CHEST_CLAIM]
    if tickets_left:
        frames.extend([fight, fight, defeat])
        expected_taps.extend([next_tower.challenge.center, skip, parse_fight_result(defeat[1]).button.center])
    captures = iter(frames)
    routine = Routine(FakeDevice(), ocr, FakeNav())
    monkeypatch.setattr(routine, "_open_mode", lambda label: True)
    monkeypatch.setattr(routine, "_capture", lambda: next(captures))

    assert routine.tower() == DONE
    assert routine.device.taps == expected_taps


def test_auto_next_stops_at_the_first_defeat(ocr, monkeypatch):
    monkeypatch.setattr(config, "POLL_INTERVAL", 0)
    board = read(ocr, "tower_current_next_tower.png")
    fight = read(ocr, "tower_current_fight.png")
    countdown = read(ocr, "tower_current_countdown.png")
    defeat = read(ocr, "en_tower_defeat.png")
    frames = iter([board, fight, countdown, defeat])
    routine = Routine(FakeDevice(), ocr, FakeNav())
    monkeypatch.setattr(routine, "_open_mode", lambda label: True)
    monkeypatch.setattr(routine, "_capture", lambda: next(frames))

    assert routine.tower() == DONE
    assert routine.device.taps == [
        parse_tower(board[1], board[0]).challenge.center, parse_fight_result(defeat[1]).button.center,
    ]
