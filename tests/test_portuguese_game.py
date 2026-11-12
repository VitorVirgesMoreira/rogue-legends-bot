"""Real Brazilian Portuguese captures from the user's emulator."""

from pathlib import Path
import pytest

from conftest import fixture_image
from roguebot import labels
from roguebot.build import BuildState, Build, focus
from roguebot.game_locale import PORTUGUESE_SKILLS
from roguebot.mode_screens import is_modes_list, mode_entry
from roguebot.party_build import skill_role
from roguebot.party_screens import expedition_entry, home_entry, event_header, expedition_complete, is_codex
from roguebot.rewards import parse_claim, RewardCollector
from roguebot.screens import Mode, parse_lobby, is_star_list, parse_star_list
from roguebot.skill_data import rule_for
from roguebot.skills import Skill, infer_tags
from roguebot.event_modes import season_closed
from roguebot.vision import Text

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def portuguese_labels():
    before = labels.active_language()
    labels.set_language("pt")
    yield
    labels.set_language(before)


def read(ocr, name):
    img = fixture_image(FIXTURES / (name + ".png"))
    return img, ocr.read(img)


def test_portuguese_lobby_and_split_star_entry(ocr):
    _, texts = read(ocr, "pt_lobby")
    assert labels.detect_language(texts) == "pt"
    lobby = parse_lobby(texts)
    assert lobby.mode is Mode.ELITE and lobby.energy == 71
    assert lobby.stars_button and lobby.stars_button.norm == "estelar"
    assert expedition_entry(texts) is not None


def test_portuguese_star_header_wrap_and_real_completed_stars(ocr):
    img, texts = read(ocr, "pt_star_list")
    assert is_star_list(texts) and parse_lobby(texts) is None
    cards = {c.number: c for c in parse_star_list(img, texts, ocr)}
    assert cards[22].stars == cards[23].stars == 3
    assert cards[22].button and cards[23].button
    assert cards[24].button is None


def test_portuguese_modes_include_real_tower_translation(ocr):
    _, texts = read(ocr, "pt_modes")
    assert is_modes_list(texts)
    for label in (labels.ARENA, labels.DOJO, labels.TOWER, labels.DIVE, labels.MINES, labels.PETS):
        assert mode_entry(texts, label)


def test_portuguese_expedition_menus_and_completed_account(ocr):
    _, texts = read(ocr, "pt_party_home")
    assert event_header(texts) and home_entry(texts)
    _, texts = read(ocr, "pt_party_complete")
    assert expedition_complete(texts)


@pytest.mark.parametrize("name,role,expected", [
    ("pt_codex_guardian", "guardian", ("Cota-de-Espinhos", "Determinação", "Elo-Divino", "Inflexível", "Inspiração", "Legado", "Provocar")),
    ("pt_codex_support", "support", ("Avançar", "Balada-Motivadora", "Bênção", "Caricia-Divina", "DignidadeEssencial", "Generosidade", "Medica")),
    ("pt_codex_striker", "striker", ("Golpe da Piedade", "Golpes-Apaziguadores", "Golpes-Furiosos", "Instinto-Assassino", "Letalidade", "Marca da Morte", "Oportunidade-Suprema")),
])
def test_real_codex_names_have_canonical_roles(ocr, name, role, expected):
    from roguebot.skill_data import key
    _, texts = read(ocr, name)
    assert is_codex(texts)
    read_names = {key(t.text) for t in texts}
    for name in expected:
        assert key(name) in read_names
        tags = infer_tags(name, "")
        assert skill_role(Skill(name, "pt", "legendary", *tags)) == role


def test_login_reward_requires_two_reads_and_never_repeats_indefinitely(ocr):
    img, texts = read(ocr, "pt_daily_login")
    claim = parse_claim(img, texts)
    assert claim and claim.button.norm == "resgatar"
    collector = RewardCollector()
    assert collector.choose(img, texts, now=0) is None
    assert collector.choose(img, texts, now=1) == claim.button.center
    collector.tapped(claim.button.center, now=1)
    assert collector.choose(img, texts, now=2) is None
    assert collector.choose(img, texts, now=6) == claim.button.center
    collector.tapped(claim.button.center, now=6)
    assert collector.choose(img, texts, now=100) is None


def test_reward_claim_is_blocked_by_a_nearby_premium_price(ocr):
    img, texts = read(ocr, "pt_daily_login")
    claim = parse_claim(img, texts)
    x, y = claim.button.center
    price = Text("10 Gemas", x - 40, y - 60, x + 40, y - 30)
    assert parse_claim(img, [*texts, price]) is None


def test_portuguese_closed_conquest_is_not_an_attack_screen(ocr):
    _, texts = read(ocr, "pt_conquest_closed")
    assert season_closed(texts)


def test_all_curated_portuguese_names_resolve_and_keep_focus():
    assert all(rule_for(name) is not None for name in PORTUGUESE_SKILLS)
    state = BuildState()
    build = Build(profile="burn")
    for name in ("Arma de Fogo", "Arma de Fogo Lv. 2+"):
        state.take(Skill(name, "pt", "common", *infer_tags(name, "")), build)
    assert len(state.owned) == 1 and focus(build, state) == "fire"
