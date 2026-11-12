"""Spend run coins on useful pre-boss upgrades without opening a competing build line."""

from pathlib import Path

import pytest

from roguebot import labels
from roguebot.build import Build, BuildState, focus, shop_order
from roguebot.modifiers import Modifier
from roguebot.screens import parse_shop
from roguebot.skills import Skill
from roguebot.vision import Text
from conftest import fixture_image
from test_skill_screens import FIRE_WAVE, RECOVERY, player, price_at, shop_screen


@pytest.fixture(autouse=True)
def reset_language():
    yield
    labels.set_language(None)


@pytest.mark.parametrize("name,kind,cost", [
    ("en_level_shop.png", "max_hp", 19),
    ("en_level_shop_sale.png", "max_hp", 38),
    ("en_level_shop_sold.png", "max_hp", 38),
    ("en_level_shop_rerolled.png", "atk", 57),
    ("level_shop.png", "atk", 19),
    ("level_shop_2.png", "def", 38),
])
def test_real_shop_stat_items_and_healing_are_recognized(ocr, name, kind, cost):
    labels.set_language("en" if name.startswith("en_") else "es")
    texts = ocr.read(fixture_image(Path(__file__).parent / "fixtures" / name))
    shop = parse_shop(texts)
    assert [(item.kind, item.cost, item.remaining) for item in shop.items] == [(kind, cost, 3), ("heal", 95, None)]


def neutral(name, description, role="damage"):
    return Skill(name, "en", "legendary", None, "physical", role, description)


def test_fire_shop_can_buy_weapon_mastery_without_switching_to_ice():
    # The log's final shop was rejected despite Weapon-Mastery boosting existing basic attacks.
    build, state = Build(profile="fire"), BuildState()
    weapon = neutral("Weapon-Mastery", "Basic Attacks, Combo Attacks and Counter Attacks deal +80% more DMG")
    shield = neutral("Enraged Shield", "When HP <40%, gain a Shield.", "support")
    ice = Skill("Ice Weapon", "en", "mythic", "ice", "magic", "damage", "Ice damage")
    assert shop_order([weapon, ice, shield], build, state, True) is None
    assert shop_order([weapon, ice, shield], build, state, False) == [0, 2]
    state.take(weapon, build)
    assert focus(build, state) == "fire"


@pytest.mark.parametrize("skill", [
    neutral("Warrior", "Physical DMG up, Magical DMG down."),
    neutral("Darkside", "ATK up but drain 10% HP every turn."),
    neutral("Mystery", "When"),
])
def test_spare_coins_do_not_justify_a_harmful_or_unknown_fallback(skill):
    assert shop_order([skill], Build(profile="fire"), BuildState(), False) == []


def supply_screen(money, *, stat="ATK", cost=19, stock="3/3", hp=None, heal=False, cards=(), free=False, reroll_cost=20):
    texts = shop_screen(money, cards, free, reroll_cost=reroll_cost)
    if stat is not None:
        texts += [Text(stat, 680, 850, 920, 910), Text(str(cost), 790, 945, 875, 1010)]
        if stock is not None:
            texts.append(Text(stock, 805, 707, 900, 765))
    if heal:
        texts += [Text("Heal 30%", 1020, 850, 1225, 910), Text("95", 1120, 945, 1205, 1010)]
    if hp is not None:
        texts.append(Text(hp, 400, 50, 680, 110))
    return texts


STAT_PRICE = (832, 977)
HEAL_PRICE = (1162, 977)


@pytest.mark.parametrize("stat", ["ATK", "DEF", "Max HP"])
def test_spare_coins_buy_all_three_stat_upgrades(tmp_path, stat):
    screens = [supply_screen(200 - 19 * i, stat=stat, stock=f"{3-i}/3") for i in range(4)]
    p = player(tmp_path, Build(profile="fire"), screens[1:])
    p._shop(screens[0])
    assert p.device.taps == [STAT_PRICE] * 3
    assert not p._state.taken  # stat purchases aren't new skill families


def test_stale_stock_counter_cannot_cause_more_than_three_purchases(tmp_path):
    screens = [supply_screen(200 - 19 * i) for i in range(4)]
    p = player(tmp_path, Build(profile="fire"), screens[1:])
    p._shop(screens[0])
    assert p.device.taps == [STAT_PRICE] * 3


@pytest.mark.parametrize("stock", ["0/3", None, "?/?", "4/3"])
def test_sold_out_or_unreadable_stat_stock_is_not_bought(tmp_path, stock):
    p = player(tmp_path, Build(profile="fire"))
    p._shop(supply_screen(100, stock=stock))
    assert p.device.taps == []


def test_shop_keeps_build_skill_ahead_of_stat_items(tmp_path):
    frames = [supply_screen(5, cards=[(*FIRE_WAVE, True)])]
    p = player(tmp_path, Build(profile="fire"), frames)
    p._shop(supply_screen(100, cards=[(*FIRE_WAVE, False)]))
    assert p.device.taps == [price_at(0)]
    assert p._state.taken == ["Fire Wave"]


def test_inflated_prices_never_put_cheap_stats_ahead_of_a_useful_skill(tmp_path):
    from test_build_line import FIRE
    p = player(tmp_path, Build(profile="fire"), [supply_screen(5, cards=[(*FIRE_WAVE, True)])])
    p._state.set_modifiers((Modifier("Inflated Prices", "Shop prices are higher."),))
    p._state.take(FIRE, p.build)
    p._state.take(FIRE, p.build)
    p._shop(supply_screen(100, stock="1/3", cards=[(*FIRE_WAVE, False)]))
    assert p.device.taps == [price_at(0)]
    assert p._state.taken == ["Fire Weapon", "Fire Weapon", "Fire Wave"]


@pytest.mark.parametrize("counter", [False, True])
def test_inflated_prices_keep_owned_upgrades_and_needed_dispel_ahead_of_stats(tmp_path, counter):
    from test_build_line import FIRE, WAVE
    offer = (("Common", "Dispel", "Enemy heals and shields are 50% less effective", 95)
             if counter else FIRE_WAVE)
    p = player(tmp_path, Build(profile="fire"), [supply_screen(5, cards=[(*offer, True)])])
    p._state.set_modifiers((Modifier("Inflated Prices", ""), Modifier("Unkillable", "")))
    p._state.take(FIRE, p.build)
    p._state.take(WAVE, p.build)
    p._shop(supply_screen(100, cards=[(*offer, False)]))
    assert p.device.taps == [price_at(0)]
    assert p._state.taken[-1] == offer[1]


def test_unaffordable_build_skill_does_not_block_free_reroll_and_stats(tmp_path):
    expensive = (*FIRE_WAVE[:3], 190, False)
    frames = [supply_screen(100, stock="1/3", cards=[expensive]),
              supply_screen(81, stock="0/3", cards=[expensive])]
    p = player(tmp_path, Build(profile="fire"), frames)
    p._shop(supply_screen(100, stock="1/3", cards=[expensive], free=True))
    assert p.device.taps == [(855, 2385), STAT_PRICE]
    assert not p._state.taken


def test_health_draining_skill_does_not_block_a_safe_stat_purchase(tmp_path):
    darkside = ("Legendary", "Darkside", "ATK up but drain 10% HP every turn.", 95, False)
    frames = [supply_screen(81, stock="0/3", cards=[darkside])]
    p = player(tmp_path, Build(profile="fire"), frames)
    p._shop(supply_screen(100, stock="1/3", cards=[darkside]))
    assert p.device.taps == [STAT_PRICE]
    assert not p._state.taken


@pytest.mark.parametrize("hp,buy", [("25/100", True), ("24/100", True), ("26/100", True), ("41/100", False),
                                    ("100/100", False), (None, False)])
def test_shop_heals_at_risk_and_preserves_healthy_or_unknown_hp(tmp_path, hp, buy):
    screen = supply_screen(200, stat=None, hp=hp, heal=True)
    after = supply_screen(105, stat=None, hp="55/100", heal=True)
    p = player(tmp_path, Build(profile="fire"), [after] if buy else [])
    p._shop(screen)
    assert p.device.taps == ([HEAL_PRICE] if buy else [])


def test_emergency_healing_precedes_a_build_skill(tmp_path):
    cards = [(*FIRE_WAVE, False)]
    after = supply_screen(5, stat=None, hp="55/100", heal=True, cards=cards)
    p = player(tmp_path, Build(profile="fire"), [after])
    p._shop(supply_screen(100, stat=None, hp="25/100", heal=True, cards=cards))
    assert p.device.taps == [HEAL_PRICE]


def test_shop_regeneration_is_useful_even_at_full_health(tmp_path):
    recovery = (*RECOVERY[:2], "Chance to restore 5% HP every turn.", 48)
    screen = supply_screen(100, stat=None, hp="100/100", cards=[(*recovery, False)])
    after = supply_screen(52, stat=None, hp="100/100", cards=[(*recovery, True)])
    p = player(tmp_path, Build(profile="fire"), [after])
    p._shop(screen)
    assert p.device.taps == [price_at(0)]
    assert p._state.taken == ["Recovery"]


def test_unconfirmed_purchase_does_not_count_as_a_learned_skill(tmp_path):
    screen = shop_screen(100, [(*FIRE_WAVE, False)], free=False)
    p = player(tmp_path, Build(profile="fire"), [screen])
    p._shop(screen)
    assert p.device.taps == [price_at(0)]
    assert p._state.taken == []


def test_reroll_above_ten_and_foreign_element_are_left_alone(tmp_path):
    ice = ("Mythic", "Ice Weapon", "Your attacks deal ice damage.", 95, False)
    p = player(tmp_path, Build(profile="fire"))
    p._shop(shop_screen(1000, [ice], free=False))
    assert p.device.taps == []
