"""Skills/rerolls before stats, reserve at earlier bosses, spend useful coins at the end."""

from pathlib import Path

import pytest

from conftest import fixture_image
from roguebot import labels
from roguebot.build import Build
from roguebot.run_progress import RunProgress
from roguebot.screens import parse_shop
from roguebot.vision import Text
from test_shop_strategy import STAT_PRICE, supply_screen
from test_skill_screens import FIRE_WAVE, RECOVERY, player, price_at

ROLL = (855, 2385)
ICE = ("Mythic", "Ice Weapon", "Your attacks deal ice damage.", 95, False)


@pytest.fixture(autouse=True)
def language():
    labels.set_language("en")
    yield
    labels.set_language(None)


def test_full_final_shop_flow_rolls_free_then_ten_buys_skills_then_spends_on_stats(tmp_path):
    offers = [(*FIRE_WAVE, False), (*RECOVERY, False), ICE]
    sold_fire = [(*FIRE_WAVE, True), (*RECOVERY, False), ICE]
    sold_both = [(*FIRE_WAVE, True), (*RECOVERY, True), ICE]
    frames = [supply_screen(200, cards=[ICE], reroll_cost=10),
              supply_screen(190, cards=offers),
              supply_screen(95, cards=sold_fire),
              supply_screen(47, cards=sold_both),
              supply_screen(28, cards=sold_both, stock="2/3"),
              supply_screen(9, cards=sold_both, stock="1/3")]
    p = player(tmp_path, Build(profile="fire"), frames)
    p._shop(supply_screen(200, cards=[ICE], free=True))
    assert p.device.taps == [ROLL, ROLL, price_at(0), price_at(1), STAT_PRICE, STAT_PRICE]
    assert p._state.taken == ["Fire Wave", "Recovery"]


@pytest.mark.parametrize("rolls", [9, 19, 24, None])
def test_earlier_or_unknown_shop_keeps_savings_after_buying_a_build_skill(tmp_path, rolls):
    offers = [(*FIRE_WAVE, False), (*RECOVERY, False)]
    after = supply_screen(205, cards=[(*FIRE_WAVE, True), (*RECOVERY, False)])
    p = player(tmp_path, Build(profile="fire"), [after], final_shop=False)
    p._state.run_progress = RunProgress(rolls, 30 if rolls is not None else None)
    p._shop(supply_screen(300, cards=offers))
    assert p.device.taps == [price_at(0)]  # keep 205 for a later premium skill


def test_savings_do_not_block_an_affordable_legendary_build_skill(tmp_path):
    legendary = ("Legendary", "Fire Wave", "Every turn cast Fire Wave.", 190)
    p = player(tmp_path, Build(profile="fire"), [supply_screen(0, cards=[(*legendary, True)])], final_shop=False)
    p._shop(supply_screen(190, cards=[(*legendary, False)]))
    assert p.device.taps == [price_at(0)]


@pytest.mark.parametrize("modifier", ["Vampiric Monsters", "Unkillable"])
def test_legendary_dispel_is_bought_before_fire_skills_rerolls_and_stats_even_in_early_shops(tmp_path, modifier):
    from roguebot.modifiers import Modifier
    dispel = ("Legendary", "Dispel", "Enemy heals and shields are 50% less effective", 190)
    cards = [(*FIRE_WAVE, False), (*dispel, False)]
    after = supply_screen(10, cards=[(*FIRE_WAVE, False), (*dispel, True)], free=True)
    p = player(tmp_path, Build(profile="fire"), [after], final_shop=False)
    p._state.set_modifiers((Modifier(modifier, ""),))
    p._shop(supply_screen(200, cards=cards, free=True))
    assert p.device.taps[0] == price_at(1)
    assert p._state.taken == ["Dispel"]


def test_earlier_shop_only_spends_surplus_on_stats(tmp_path):
    p = player(tmp_path, Build(profile="fire"), [supply_screen(190, stock="2/3")], final_shop=False)
    p._shop(supply_screen(209))
    assert p.device.taps == [STAT_PRICE]


def test_seen_mythic_price_is_remembered_when_the_next_shop_has_cheaper_stock(tmp_path):
    mythic = ("Mythic", "Fire Wave", "Every turn cast Fire Wave.", 380, False)
    p = player(tmp_path, Build(profile="fire"), final_shop=False)
    p._shop(supply_screen(200, cards=[mythic], stock="0/3"))
    assert p.device.taps == [] and p._state.premium_shop_price == 380
    p._shop(supply_screen(390))
    assert p.device.taps == []  # don't spend the useful premium reserve in the next shop


@pytest.mark.parametrize("cost", [11, 20, 30, "?", "-10"])
def test_reroll_above_ten_or_unreadable_is_never_pressed(tmp_path, cost):
    p = player(tmp_path, Build(profile="fire"))
    p._shop(supply_screen(1000, cards=[ICE], stat=None, reroll_cost=cost))
    assert not p.device.taps


def test_explicit_gem_reroll_is_never_pressed(tmp_path):
    screen = supply_screen(1000, cards=[ICE], stat=None, reroll_cost=10)
    screen.append(Text("Gems", 920, 2435, 990, 2475))
    assert parse_shop(screen).reroll_cost is None
    p = player(tmp_path, Build(profile="fire"))
    p._shop(screen)
    assert not p.device.taps


def test_ten_coin_reroll_waits_for_the_full_coin_drop_and_never_repeats_the_same_price(tmp_path):
    after = supply_screen(190, cards=[ICE], stat=None, reroll_cost=10)
    p = player(tmp_path, Build(profile="fire"),
               [supply_screen(195, cards=[ICE], stat=None, reroll_cost=10), after])
    p._shop(supply_screen(200, cards=[ICE], stat=None, reroll_cost=10))
    assert p.device.taps == [ROLL]


def test_purchase_waits_for_the_balance_before_a_free_reroll(tmp_path):
    offer = (*FIRE_WAVE[:3], 428)
    sold = [(*offer, True)]
    p = player(tmp_path, Build(profile="fire"), [
        supply_screen(90, cards=sold, stat=None, free=True),
        supply_screen(60, cards=sold, stat=None, free=True),
        supply_screen(60, cards=[ICE], stat=None),
    ])
    p._shop(supply_screen(488, cards=[(*offer, False)], stat=None, free=True))
    assert p.device.taps == [price_at(0), ROLL]
    assert p._state.taken == ["Fire Wave"]


@pytest.mark.parametrize("free,after_balance", [(True, 170), (False, 178)])
def test_reroll_with_an_unexpected_debit_ends_the_visit(tmp_path, free, after_balance):
    after = supply_screen(after_balance, cards=[(*FIRE_WAVE, False)])
    p = player(tmp_path, Build(profile="fire"), [after])
    p._shop(supply_screen(200, cards=[ICE], free=free, reroll_cost=10))
    assert p.device.taps == [ROLL]
    assert not p._state.taken


def test_inflated_price_rounding_requires_two_matching_balances(tmp_path):
    from roguebot.modifiers import Modifier
    offer = (*FIRE_WAVE[:3], 142)
    sold = [(*offer, True)]
    frames = [supply_screen(balance, cards=sold, stat=None) for balance in (59, 57, 57)]
    p = player(tmp_path, Build(profile="fire"), frames)
    p._state.set_modifiers((Modifier("Inflated Prices", ""),))
    p._shop(supply_screen(200, cards=[(*offer, False)], stat=None))
    assert p.ocr.last == frames[-1]
    assert p._state.taken == ["Fire Wave"]


def test_unconfirmed_free_reroll_stops_without_repeated_taps_or_stat_buys(tmp_path):
    screen = supply_screen(200, cards=[ICE], free=True)
    p = player(tmp_path, Build(profile="fire"), [screen])
    p._shop(screen)
    assert p.device.taps == [ROLL]


def test_unreadable_reroll_price_is_not_confirmation_that_a_free_roll_worked(tmp_path):
    after = supply_screen(200, cards=[ICE], reroll_cost="?")
    p = player(tmp_path, Build(profile="fire"), [after])
    p._shop(supply_screen(200, cards=[ICE], free=True))
    assert p.device.taps == [ROLL]


def test_paid_rerolls_accept_five_and_ten_but_stop_at_twenty(tmp_path):
    frames = [supply_screen(195, cards=[ICE], stat=None, reroll_cost=10),
              supply_screen(185, cards=[ICE], stat=None, reroll_cost=20)]
    p = player(tmp_path, Build(profile="fire"), frames)
    p._shop(supply_screen(200, cards=[ICE], stat=None, reroll_cost=5))
    assert p.device.taps == [ROLL, ROLL]


def test_reroll_can_offer_another_upgrade_of_the_same_skill_bought_in_this_shop(tmp_path):
    frames = [supply_screen(305, stat=None, cards=[(*FIRE_WAVE, True)], free=True),
              supply_screen(305, stat=None, cards=[(*FIRE_WAVE, False)], reroll_cost=10),
              supply_screen(210, stat=None, cards=[(*FIRE_WAVE, True)], reroll_cost=10),
              supply_screen(200, stat=None, cards=[ICE])]
    p = player(tmp_path, Build(profile="fire"), frames)
    p._shop(supply_screen(400, stat=None, cards=[(*FIRE_WAVE, False)], free=True))
    assert p.device.taps == [price_at(0), ROLL, price_at(0), ROLL]
    assert p._state.taken == ["Fire Wave", "Fire Wave"]


@pytest.mark.parametrize("rolls", [25, 29])
def test_small_balance_is_used_for_stats_instead_of_a_roll_that_cannot_leave_skill_money(tmp_path, rolls):
    p = player(tmp_path, Build(profile="fire"), [supply_screen(15, stock="0/3", cards=[ICE], reroll_cost=10)])
    p._state.run_progress.rolls = rolls
    p._shop(supply_screen(34, stock="1/3", cards=[ICE], reroll_cost=10))
    assert p.device.taps == [STAT_PRICE]


@pytest.mark.parametrize("name,expected", [("en_level_shop.png", 0), ("en_level_shop_rerolled.png", 10)])
def test_real_shop_reroll_cost(ocr, name, expected):
    texts = ocr.read(fixture_image(Path(__file__).parent / "fixtures" / name))
    assert parse_shop(texts).reroll_cost == expected


def test_real_roll_counter_is_read_from_the_board_not_fight_or_hp(ocr):
    image = fixture_image(Path(__file__).parent / "fixtures/en_board_dice_unknown.png")
    progress = RunProgress()
    progress.observe(ocr.read(image))
    assert (progress.rolls, progress.total) == (7, 30) and not progress.final_shop
    progress.observe([Text("29/30", 10, 1340, 150, 1400)])
    assert progress.final_shop
    progress.observe([Text("Round 4/30", 600, 100, 840, 180), Text("3/3", 800, 700, 900, 760)])
    assert (progress.rolls, progress.total) == (29, 30)


def test_player_carries_the_board_progress_into_the_shop_budget(tmp_path, monkeypatch):
    import numpy as np
    from roguebot.build import BuildState
    from roguebot.play import Player
    from roguebot.screens import LevelScreen, LevelState
    from roguebot.skills import Catalog
    from test_party import ReplayDevice, ReplayOcr, result
    image = np.zeros((2560, 1440, 3), np.uint8)
    # An automatic dice board with a readable counter, then the final shop and its receipt.
    frames = [(image, [Text("29/30", 10, 1340, 150, 1400)]),
              (image, supply_screen(209, stock="1/3")), (image, supply_screen(209, stock="1/3")),
              (image, supply_screen(190, stock="0/3")),
              (image, result(LevelScreen.VICTORY)), (image, result(LevelScreen.VICTORY))]
    device, progress = ReplayDevice(frames), BuildState()
    from roguebot.play import classify_level_screen as classify
    def classify_board(img, texts):
        return LevelState(LevelScreen.AUTO_PLAY) if texts[0].text == "29/30" else classify(img, texts)
    monkeypatch.setattr("roguebot.play.classify_level_screen", classify_board)
    monkeypatch.setattr("roguebot.play.time.sleep", lambda seconds: None)
    p = Player(device, ReplayOcr(device), catalog=Catalog(tmp_path / "skills.json"), build_state=progress)
    assert p.play_level() is LevelScreen.VICTORY
    assert progress.run_progress.final_shop and STAT_PRICE in device.taps


@pytest.mark.parametrize("rolls,total,final", [(0, 30, False), (19, 30, False), (24, 30, False),
    (25, 30, True), (27, 30, True), (29, 30, True), (34, 40, False), (35, 40, True), (None, None, False)])
def test_only_the_end_of_the_roll_counter_uses_the_final_shop_budget(rolls, total, final):
    assert RunProgress(rolls, total).final_shop is final


@pytest.mark.parametrize("tiles,final", [(150, False), (162, False), (163, True), (190, True)])
def test_195_tile_boards_use_equivalent_progress_instead_of_five_tiles(tiles, final):
    progress = RunProgress(tiles, 195)
    assert progress.unit == "tiles" and progress.remaining_rolls is None
    assert progress.final_shop is final
