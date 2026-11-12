"""Event identity, readable refusals and unknown options; no emulator input."""

import pytest

from roguebot import labels
from roguebot.event_rules import choose_event
from roguebot.screens import LevelScreen, classify_level_screen, parse_event_menu
from roguebot.vision import Text
from test_events import event, LEAVE


@pytest.fixture(autouse=True)
def language():
    labels.set_language("en")
    yield
    labels.set_language(None)


@pytest.mark.parametrize("title,exit_label", [("Deal with Devil", "Refuse"), ("Deal with the Devil", "Decline"),
    ("Altar of Greed", "Leave"), ("Test of Might", "Leave"), ("Cursed Fountain", "Walk Away"),
    ("Abandoned Spoils", "Leave"), ("Forbidden Knowledge", "Walk Away")])
def test_known_risky_event_uses_its_readable_exit_even_with_an_attractive_reward(title, exit_label):
    image, texts = event()
    texts[0] = Text(title, 360, 1370, 1080, 1430)
    texts[2] = Text("Accept", 400, 1760, 600, 1820)
    texts[3] = Text(exit_label, 820, 1760, 1020, 1820)
    texts[4] = Text("+50% ATK", 220, 2240, 700, 2310)
    assert classify_level_screen(image, texts).tap == LEAVE


def test_devil_is_not_overridden_by_the_generic_hp_for_legendary_policy():
    from roguebot.events import EventChoices
    image, texts = event(sacrifice=True)
    texts[0] = Text("Deal with Devil", 360, 1370, 1080, 1430)
    texts[3] = Text("Refuse", 820, 1760, 1020, 1820)
    assert EventChoices().choose(image, texts).tap == LEAVE


@pytest.mark.parametrize("description", ["-20% Max HP, +50% ATK", "Lose 20% HP to gain 15% ATK", "Pay 20 Gems"])
def test_cost_text_cannot_be_mistaken_for_a_positive_effect(description):
    image, texts = event()
    texts[0] = Text("Unknown Shrine", 360, 1370, 1080, 1430)
    texts[4] = Text(description, 220, 2240, 700, 2310)
    assert classify_level_screen(image, texts).tap == LEAVE


def test_unknown_buttons_wait_even_if_an_exit_word_appears_in_a_description():
    image, texts = event()
    texts[0] = Text("Unknown Shrine", 360, 1370, 1080, 1430)
    texts[2] = Text("Touch", 400, 1760, 600, 1820)
    texts[3] = Text("Run", 820, 1760, 1020, 1820)
    texts[4] = Text("Leave", 220, 2240, 700, 2310)
    assert parse_event_menu(image, texts)
    state = classify_level_screen(image, texts)
    assert state.kind is LevelScreen.UNKNOWN and state.tap is None


def test_spanish_refusal_is_an_exit():
    labels.set_language("es")
    image, texts = event()
    texts[3] = Text("Rechazar", 820, 1760, 1020, 1820)
    assert classify_level_screen(image, texts).tap == LEAVE


@pytest.mark.parametrize("effect", [
    "drink +20% atk", "drink +20% atk -15% hp", "drink +20% atk -15% max hp pay 10 gems",
    "drink +1% atk -30% max hp",
])
def test_fountain_refuses_when_the_trade_is_unreadable_or_unfavorable(effect):
    title = Text("The Cursed Fountain", 360, 1370, 1080, 1430)
    drink = Text("Drink", 400, 1760, 600, 1820)
    skip = Text("Pass", 820, 1760, 1020, 1820)
    assert choose_event(title, (drink, skip), {drink: effect, skip: "pass"}, 1.).option == skip
