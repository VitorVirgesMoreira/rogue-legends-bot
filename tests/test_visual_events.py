"""Own captures supply a title only; buttons/effects are never inferred from its image."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from conftest import fixture_image
from roguebot import config, labels
from roguebot.screens import classify_level_screen, parse_event_menu
from roguebot.visual_events import ROOT, match_event_title

FIXTURES = Path(__file__).parent/'fixtures'
ENTRIES = json.loads((ROOT/'index.json').read_text(encoding='utf-8'))


@pytest.fixture(autouse=True)
def language():
    labels.set_language(None)
    yield
    labels.set_language(None)


@pytest.mark.parametrize('entry', ENTRIES, ids=lambda entry: entry['source'])
def test_title_fallback_preserves_the_real_decision_when_title_ocr_is_missing(ocr, entry):
    image = fixture_image(FIXTURES/entry['source'])
    texts = ocr.read(image)
    expected = classify_level_screen(image, texts)
    without_title = [t for t in texts if not config.EVENT_TITLE_Y[0] <= t.center[1] <= config.EVENT_TITLE_Y[1]]
    menu = parse_event_menu(image, without_title)
    assert menu and menu.source == 'visual' and menu.score >= .94
    actual = classify_level_screen(image, without_title)
    assert actual == expected


def test_a_title_image_cannot_authorize_an_unreadable_button(ocr):
    image = fixture_image(FIXTURES/'en_level_potion_makers_hut.png')
    texts = [t for t in ocr.read(image) if t.center[1] < 200]
    assert match_event_title(image)
    assert parse_event_menu(image, texts) is None


def test_wrong_language_and_unsupported_geometry_are_rejected():
    image = fixture_image(FIXTURES/'en_level_potion_makers_hut.png')
    labels.set_language('es')
    assert match_event_title(image) is None
    assert match_event_title(cv2.resize(image, (720, 1280))) is None


def test_non_event_captures_do_not_match_titles():
    # Every existing fixture is a negative except the five observed source captures.
    sources = {entry['source'] for entry in ENTRIES}
    for path in FIXTURES.glob('*.png'):
        if path.name not in sources:
            assert match_event_title(fixture_image(path)) is None, path.name


def test_near_equal_title_matches_are_rejected(monkeypatch):
    from roguebot import visual_events
    image = fixture_image(FIXTURES/'en_level_potion_makers_hut.png')
    entries = visual_events._templates()
    entry, template = next((entry, template) for entry, template in entries if entry['title'] == "Potion Maker's Hut")
    monkeypatch.setattr(visual_events, '_templates', lambda: [(entry, template),
        (dict(entry, title='A different event'), template.copy())])
    assert match_event_title(image) is None
