"""Purple elite stars must not make completed late stages hide earlier missing stars."""

from pathlib import Path

import pytest

from conftest import fixture_image
from roguebot import labels
from roguebot.navigation import NavigationError
from roguebot.screens import Mode, card_stars, parse_star_list
from roguebot.vision import Text
from test_logic import _card, _star_nav

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def language():
    labels.set_language("en")
    yield
    labels.set_language(None)


def cards(ocr, name):
    image = fixture_image(FIXTURES / name)
    return image, parse_star_list(image, ocr.read(image), ocr)


def test_real_elite_purple_stars_count_as_earned(ocr):
    _, levels = cards(ocr, "en_stars_elite.png")
    assert levels[0].number == 1 and levels[0].stars == 2
    assert levels[1].button is None
    _, levels = cards(ocr, "en_stars_elite_complete_end.png")
    assert [(c.number, c.stars) for c in levels if c.button] == [(22, 3), (23, 3)]


@pytest.mark.parametrize("name,target", [("en_stars_elite.png", 1), ("en_stars_elite_pending_earlier.png", 21)])
def test_completed_real_elite_end_is_skipped_for_an_earlier_pending_stage(ocr, monkeypatch, name, target):
    _, end = cards(ocr, "en_stars_elite_complete_end.png")
    _, beginning = cards(ocr, name)
    chosen = next(c for c in beginning if c.number == target)
    nav = _star_nav(monkeypatch, [end, beginning])
    nav._scroll_to = lambda number: chosen
    assert nav.start_pending_stars(Mode.ELITE) == target
    assert len(nav.drags) == 1 and nav.drags[0] < 0
    assert nav.started == [chosen.button.center]


def test_unreadable_stars_do_not_become_zero_or_a_complete_scan(monkeypatch, tmp_path):
    nav = _star_nav(monkeypatch, [[_card(23, None, 1080)]] * 3)
    monkeypatch.setattr("roguebot.navigation.DEBUG_DIR", tmp_path)
    with pytest.raises(NavigationError, match="star counts"):
        nav.start_pending_stars(Mode.ELITE)
    assert not nav.started and not nav.drags


def test_ignored_swipes_never_claim_all_earlier_levels_are_complete(monkeypatch, tmp_path):
    nav = _star_nav(monkeypatch, [[_card(23, 3, 1080)]] * 3)
    monkeypatch.setattr("roguebot.navigation.DEBUG_DIR", tmp_path)
    with pytest.raises(NavigationError, match="earlier levels"):
        nav.start_pending_stars(Mode.ELITE)
    assert not nav.started


def test_dark_or_clipped_star_header_is_unreadable():
    import numpy as np
    image = np.zeros((2560, 1440, 3), np.uint8)
    assert card_stars(image, Text("23. Stage", 20, 700, 900, 750)) is None
    assert card_stars(image, Text("23. Stage", 20, 0, 900, 10)) is None
