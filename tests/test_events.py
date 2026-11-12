"""Goblin loot, HP-for-legendary choices and bounded event evidence, without gameplay."""

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from conftest import fixture_image
from roguebot import labels
from roguebot.events import EventChoices
from roguebot.play import Player
from roguebot.run_progress import RunProgress
from roguebot.screens import LevelScreen, classify_level_screen
from roguebot.skills import Catalog
from roguebot.vision import Text
from test_party import ReplayDevice, ReplayOcr, result


FIXTURES = Path(__file__).parent / "fixtures"


def captured(ocr, name):
    img = fixture_image(FIXTURES / name)
    return img, ocr.read(img)


@pytest.mark.parametrize(("name", "action", "option"), [
    ("knowledge", "read", "Read"),
    ("spoils", "steal", "Steal"),
    ("devil", "sign", "Sign"),
])
def test_requested_event_options_are_attempted_on_the_real_screens(ocr, name, action, option):
    img, texts = captured(ocr, f"en_event_{name}.png")
    choices = EventChoices()
    pick = choices.choose(img, texts)
    assert (pick.action, pick.option) == (action, option)
    assert pick.tap[0] < 600
    choices.tapped(pick, texts)
    assert choices.choose(img, texts).action == "wait"


def test_altar_needs_enough_tokens_after_reserving_shop_budget(ocr):
    img, texts = captured(ocr, "en_event_altar.png")  # 348 tokens, the option costs 50
    assert EventChoices().choose(img, texts, reserve=190).option == "Offer"
    assert EventChoices().choose(img, texts, reserve=285).option == "Leave"
    premium = [replace(t, text="Gems") if t.norm == "tokens" else t for t in texts]
    assert EventChoices().choose(img, premium).option == "Leave"


def test_named_event_declines_a_premium_price(ocr):
    img, texts = captured(ocr, "en_event_devil.png")
    sign = next(t for t in texts if t.norm == "sign")
    x, _ = sign.center
    price = Text("Pay 10 Diamonds", x - 50, 2250, x + 50, 2290)
    decision = EventChoices().choose(img, [*texts, price])
    assert decision.action == "leave" and decision.reason == "The option mentions premium currency"


def test_might_needs_a_passed_second_marker_and_current_health_and_attack(ocr):
    board, board_texts = captured(ocr, "level_board_ready.png")
    progress = RunProgress()
    progress.observe(board_texts)
    progress.observe_board(board, board_texts)
    assert progress.starting_attack and progress.second_boss_marker
    assert not progress.after_second_boss

    # The saved real board shows two skulls. Reproduce its fill moving above
    # the upper skull, using the blue strip color captured on an earlier roll.
    blue, _ = captured(ocr, "en_board_dice_unknown.png")
    late_board = board.copy()
    y = progress.second_boss_marker
    for top, bottom in ((y - 38, y - 24), (y + 25, y + 39)):
        late_board[top:bottom, 74:85] = blue[1160:1160+bottom-top, 74:85]

    img, texts = captured(ocr, "en_event_might.png")
    healthy = [replace(t, text="3,2m/3,9m") if t.norm == "2,3m/3,9m" else t for t in texts]
    assert EventChoices().choose(img, healthy, progress=progress).option == "Leave"
    progress.observe_board(late_board, board_texts)
    assert progress.after_second_boss
    assert EventChoices().choose(img, texts, progress=progress).option == "Leave"  # 59% HP
    assert EventChoices().choose(img, healthy, progress=progress).option == "Enter"
    progress.starting_attack = 1_000_000  # current attack is 1.1M, below the 25% growth gate
    assert EventChoices().choose(img, healthy, progress=progress).option == "Leave"


def test_one_skull_is_insufficient_even_if_the_board_counter_is_high(ocr):
    board, texts = captured(ocr, "level_board_auto_rolling.png")
    progress = RunProgress(rolls=26, total=30, starting_attack=30_000)
    progress.observe_board(board, texts)
    assert not progress.after_second_boss and progress.second_boss_marker is None


def test_player_logs_the_selected_option_and_waits_for_confirmation(ocr, tmp_path, caplog):
    from roguebot import play

    img, texts = captured(ocr, "en_event_devil.png")
    victory = result(LevelScreen.VICTORY)
    device = ReplayDevice([(img, texts), (img, texts), (img, texts), (img, victory), (img, victory)])
    caplog.set_level("INFO", logger="roguebot.observation")
    assert Player(device, ReplayOcr(device), catalog=Catalog(tmp_path / "skills.json")).play_level() is LevelScreen.VICTORY
    assert len(device.taps) == 2 and device.taps[0][0] < 600
    assert "Deal with the Devil → Sign" in caplog.text
    saved = json.loads(next(play.EVENT_DEBUG_DIR.glob("*.json")).read_text(encoding="utf-8"))
    assert saved["reason"] == "Sign the pact"


def test_cursed_fountain_can_be_skipped_and_resumed(ocr, monkeypatch, tmp_path):
    from roguebot.navigation import Navigator

    img, texts = fountain(ocr, "2m / 5,6m")
    nav = Navigator(None, ocr)
    monkeypatch.setattr(nav, "_capture", lambda: (img, texts))
    assert nav.level_in_progress()

    victory = result(LevelScreen.VICTORY)
    device = ReplayDevice([(img, texts), (img, texts), (img, victory), (img, victory)])
    assert Player(device, ReplayOcr(device), catalog=Catalog(tmp_path / "skills.json")).play_level() is LevelScreen.VICTORY
    assert device.taps == [(924, 2032), victory[-1].center]


def fountain(ocr, hp=None):
    img, texts = captured(ocr, "en_elite_cursed_fountain.png")
    return img, [replace(t, text=hp or "") if t.center[1] < 110 and "/" in t.text else t for t in texts]


@pytest.mark.parametrize(("hp", "target"), [
    ("41/100", (513, 2030)), ("40/100", (924, 2032)),
    ("2m / 5,6m", (924, 2032)), (None, (924, 2032)),
])
def test_cursed_fountain_preserves_the_hp_reserve(ocr, hp, target):
    assert classify_level_screen(*fountain(ocr, hp)).tap == target


def test_cursed_fountain_does_not_drink_again_if_the_screen_lingers(ocr, monkeypatch):
    now = [0.]
    monkeypatch.setattr("roguebot.events.time.monotonic", lambda: now[0])
    img, texts = fountain(ocr, "100/100")
    choices = EventChoices()
    pick = choices.choose(img, texts)
    assert (pick.action, pick.option) == ("drink", "Drink")
    choices.tapped(pick, texts)
    assert choices.choose(img, texts).action == "wait"
    now[0] = 6.
    assert choices.choose(img, texts).option == "Pass"
    choices.reset()
    assert choices.choose(img, texts).option == "Drink"


def test_player_drinks_from_the_cursed_fountain_and_continues(ocr, tmp_path):
    img, texts = fountain(ocr, "80/100")
    victory = result(LevelScreen.VICTORY)
    device = ReplayDevice([(img, texts), (img, texts), (img, texts), (img, victory), (img, victory)])
    assert Player(device, ReplayOcr(device), catalog=Catalog(tmp_path / "skills.json")).play_level() is LevelScreen.VICTORY
    assert device.taps == [(513, 2030), victory[-1].center]


@pytest.fixture(autouse=True)
def language():
    labels.set_language("en")
    yield
    labels.set_language(None)


def event(*, money=100, hp="100/100", sacrifice=False, cost="-20% HP", disabled=False):
    image = np.full((2560, 1440, 3), (50, 90, 190), np.uint8)
    title = "Ancient Altar" if sacrifice else "Goblin's Hut"
    texts = [Text(title, 360, 1370, 1080, 1430), Text(str(money), 70, 155, 150, 195),
             Text("Offer Life" if sacrifice else "Raid", 400, 1760, 600, 1820),
             Text("Leave", 820, 1760, 1020, 1820),
             Text(f"{cost} Chance to learn a Legendary Skill" if sacrifice else "50% Gain Coins 50% Battle",
                  220, 2240, 700, 2310)]
    if hp:
        texts.append(Text(hp, 400, 50, 670, 110))
    if disabled:
        image[1908:2148, 380:620] = 80
    return image, texts


LOOT, LEAVE = (500, 2028), (920, 2028)


def test_loot_uses_three_confirmed_attempts_then_leaves():
    choices = EventChoices()
    for index in range(3):
        image, texts = event(money=100+10*index)
        pick = choices.choose(image, texts)
        assert pick.action == "loot" and pick.tap == LOOT
        choices.tapped(pick, texts)
        stale = choices.choose(image, texts)
        assert stale.action == "wait" and stale.tap is None
    pick = choices.choose(*event(money=130))
    assert pick.action == "leave" and pick.tap == LEAVE
    assert choices.attempts == 3


def test_loot_does_not_repeat_without_a_confirmed_reward(monkeypatch):
    monkeypatch.setattr("roguebot.events.time.monotonic", lambda: 100)
    choices = EventChoices()
    image, texts = event()
    choices.tapped(choices.choose(image, texts), texts)
    monkeypatch.setattr("roguebot.events.time.monotonic", lambda: 106)
    assert choices.choose(image, texts).tap == LEAVE
    assert choices.attempts == 1


def test_loot_respects_low_hp_disabled_options_and_new_visits():
    choices = EventChoices()
    assert choices.choose(*event(hp="25/100")).tap == LEAVE
    assert choices.choose(*event(disabled=True)) is None
    image, texts = event()
    choices.tapped(choices.choose(image, texts), texts)
    choices.reset()
    assert choices.choose(image, texts).tap == LOOT and choices.attempts == 0


@pytest.mark.parametrize("hp,action", [("100/100", "sacrifice"), ("46/100", "sacrifice"),
    ("45/100", "leave"), ("20/100", "leave"), (None, "leave")])
def test_legendary_sacrifice_preserves_more_than_one_quarter_hp(hp, action):
    pick = EventChoices().choose(*event(sacrifice=True, hp=hp))
    assert pick.action == action
    assert pick.tap == (LOOT if action == "sacrifice" else LEAVE)


def test_current_hp_percentage_and_max_hp_percentage_have_different_costs():
    assert EventChoices().choose(*event(sacrifice=True, hp="40/100", cost="Sacrifice 20% of current HP")).action == "sacrifice"
    assert EventChoices().choose(*event(sacrifice=True, hp="40/100", cost="Sacrifice 20% HP")).action == "leave"


@pytest.mark.parametrize("cost", ["20% HP Cost", "HP -20%", "Offer 20% of your life"])
def test_explicit_hp_cost_wording_is_read_without_using_the_skill_chance_as_a_cost(cost):
    assert EventChoices().choose(*event(sacrifice=True, cost=cost)).action == "sacrifice"


@pytest.mark.parametrize("cost", ["Sacrifice HP", "20 Gems", "HP -80%", "Sacrifice 30% HP"])
def test_unreadable_premium_or_excessive_sacrifice_cost_is_left(cost):
    assert EventChoices().choose(*event(sacrifice=True, hp="55/100", cost=cost)).tap == LEAVE


def test_a_failed_sacrifice_does_not_keep_spending_hp_on_the_same_event():
    choices = EventChoices()
    image, texts = event(sacrifice=True)
    choices.tapped(choices.choose(image, texts), texts)
    assert choices.choose(*event(sacrifice=True, hp="80/100")).tap == LEAVE


def test_unknown_events_keep_the_existing_leave_policy():
    image, texts = event()
    texts[0] = Text("Mysterious Cabin", 360, 1370, 1080, 1430)
    assert EventChoices().choose(image, texts) is None
    assert classify_level_screen(image, texts).tap == LEAVE


def test_player_replays_looting_rewards_without_a_fourth_attempt_and_saves_evidence(tmp_path):
    from roguebot import play
    frames = [event(money=n) for n in (100, 100, 110, 120, 130)]
    frames.append((frames[0][0], result(LevelScreen.VICTORY)))
    frames = [frame for frame in frames for _ in range(2)]  # two observations confirm each offer
    device = ReplayDevice(frames)
    player = Player(device, ReplayOcr(device), catalog=Catalog(tmp_path / "skills.json"))
    assert player.play_level() is LevelScreen.VICTORY
    assert device.taps == [LOOT]*3 + [LEAVE, result(LevelScreen.VICTORY)[-1].center]
    records = sorted(play.EVENT_DEBUG_DIR.glob("*.json"))
    assert len(records) == 4
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["title"] == "Goblin's Hut" and record["tap"] == list(LOOT)
    assert record["texts"] and records[0].with_suffix(".png").exists()


def test_event_capture_retention_and_write_failure_do_not_break_decisions(tmp_path, monkeypatch):
    from roguebot import play
    monkeypatch.setattr(play, "MAX_EVENT_CAPTURES", 2)
    player = Player(None, None, catalog=Catalog(tmp_path / "skills.json"))
    for money in (100, 110, 120):
        image, texts = event(money=money)
        player._trace_event(image, texts, LOOT, "Loot")
    assert len(list(play.EVENT_DEBUG_DIR.glob("*.png"))) == 2
    assert len(list(play.EVENT_DEBUG_DIR.glob("*.json"))) == 2
    monkeypatch.setattr(play.cv2, "imwrite", lambda *a: False)
    player._trace_event(*event(money=130), LOOT, "Loot")
