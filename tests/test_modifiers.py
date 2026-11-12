"""Real elite previews and sequential choices under the user's observed modifiers."""

from pathlib import Path

import pytest

from conftest import fixture_image
from roguebot import labels
from roguebot.build import BURN, Build, BuildState, choose, focus, shop_order
from roguebot.modifiers import Modifier, ModifierRules, parse_modifiers
from roguebot.play import Player
from roguebot.screens import LevelScreen, classify_level_screen
from roguebot.skills import Catalog
from test_build_line import FIRE, WAVE, CRIT, SHURIKEN, sk
from test_party import ReplayDevice, ReplayOcr

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def language():
    labels.set_language("en")
    yield
    labels.set_language(None)


def load(ocr, name):
    image = fixture_image(FIXTURES / name)
    return image, ocr.read(image)


@pytest.mark.parametrize("name,effects", [
    ("en_elite_dialog_x5.png", {"rest_disabled", "reduced_healing", "stronger_enemies"}),
    ("en_level_modifiers.png", {"expensive_shop", "enemy_healing", "stronger_enemies"}),
    ("en_elite_no_training_berserk.png", {"training_disabled", "ramping_attack", "stronger_enemies"}),
    ("en_elite_no_rest_hard_shell.png", {"rest_disabled", "first_round_armor", "stronger_enemies"}),
    ("en_elite_expensive_unkillable.png", {"expensive_shop", "enemy_shields", "stronger_enemies"}),
    ("en_elite_narrow_weakpoints.png", {"fewer_choices", "enemy_critical", "stronger_enemies"}),
    ("en_elite_prison_adaptive.png", {"jail_tiles", "adaptive_armor", "stronger_enemies"}),
])
def test_real_preview_and_intro_read_all_three_cards(ocr, name, effects):
    image, texts = load(ocr, name)
    entries = parse_modifiers(image, texts)
    assert len(entries) == 3 and all(m.description for m in entries)
    rules = ModifierRules.read(entries)
    assert rules.effects == effects and not rules.unknown
    if "enemy_healing" in effects:
        assert entries[-1].description == "All enemy encounters are stronger in various ways."


def state_with(*names):
    state = BuildState()
    state.set_modifiers(tuple(Modifier(name, "") for name in names))
    return state


def established(*names):
    state = state_with(*names)
    for skill in (FIRE, WAVE):
        state.take(skill, Build(profile=BURN))
    return state


DISPEL = sk("Dispel", rarity="legendary", description="Enemy heals and shields are 50% less effective", role="support")
SHIELD = sk("Strike-Shield", description="Weapon Attacks have a chance to grant a Shield", role="support")
RECOVERY = sk("Recovery", description="Chance to restore 5% HP every turn", role="support")


@pytest.mark.parametrize("threat", ["Vampiric Monsters", "Unkillable"])
def test_enemy_healing_and_shields_get_legendary_dispel_immediately(threat):
    build, state = Build(profile=BURN), state_with(threat)
    assert choose([DISPEL, FIRE], build, state, False) == 0
    state.take(FIRE, build)
    state.take(WAVE, build)
    assert choose([WAVE, DISPEL], build, state, False) == 1
    state.take(DISPEL, build)
    state.take(WAVE, build)
    state.take(FIRE, build)
    assert choose([WAVE, DISPEL], build, state, False) == 0
    assert focus(build, state) == "fire"


@pytest.mark.parametrize("threat", ["Vampiric Monsters", "Unkillable"])
@pytest.mark.parametrize("profile", [BURN, "fire", "ice", "shuriken", "custom"])
def test_legendary_dispel_beats_a_mythic_damage_skill_before_the_support_interval(threat, profile):
    state, build = state_with(threat), Build(profile=profile, support_every=3)
    offers = [sk("Meteor", "fire", "mythic"), DISPEL]
    assert choose(offers, build, state, can_reroll=True) == 1
    assert shop_order(offers, build, state, can_reroll=True)[0] == 1


@pytest.mark.parametrize("name", ["Dispel", "Disipar", "Dispel Lv.2"])
def test_known_counter_name_still_works_when_ocr_misses_the_description_or_role(name):
    dispel = sk(name, rarity="legendary")
    assert choose([FIRE, dispel], Build(profile="fire"), state_with("Unkillable"), True) == 1


def test_owned_lower_rarity_counter_does_not_block_acquiring_the_legendary_version():
    state = state_with("Vampiric Monsters")
    state.take(sk("Dispel", rarity="common", role="support"))
    assert choose([FIRE, DISPEL], Build(profile="fire"), state, True) == 1


def test_once_legendary_dispel_is_acquired_the_main_build_resumes_even_after_recovery():
    from copy import deepcopy
    state = state_with("Unkillable")
    state.take(DISPEL)
    recovered = deepcopy(state)
    assert choose([DISPEL, FIRE], Build(profile="fire"), recovered, False) == 1
    assert shop_order([DISPEL, FIRE], Build(profile="fire"), recovered, True) == [1]


def test_without_enemy_healing_or_shields_dispel_does_not_displace_the_main_build():
    assert choose([DISPEL, FIRE], Build(profile="fire"), state_with("Berserk Enemies"), True) == 1


@pytest.mark.parametrize("names", [("Anti-Heal", "No Time To Rest"), ("Weakpoints",)])
def test_protection_beats_reduced_healing_without_scattering_the_build(names):
    build, state = Build(profile=BURN), established(*names)
    assert choose([RECOVERY, WAVE, SHIELD], build, state, False) == 2
    state.take(SHIELD, build)
    assert choose([RECOVERY, WAVE, SHIELD], build, state, False) == 1


def test_no_rest_adds_passive_sustain_instead_of_relying_on_campfires():
    state, build = established("No Time To Rest"), Build(profile=BURN)
    assert choose([WAVE, RECOVERY], build, state, False) == 1
    assert choose([WAVE, DISPEL], build, state, False) == 0  # Dispel isn't self healing


def test_anti_heal_prefers_protection_for_configured_support_and_shop_utility():
    state, build = established("Anti-Heal"), Build(profile=BURN, support_every=2)
    assert choose([RECOVERY, SHIELD], build, state, False) == 1
    state = state_with("Anti-Heal")
    assert shop_order([RECOVERY, SHIELD], Build(profile=BURN), state, False) == [1, 0]


def test_adaptive_armor_favors_critical_hits_and_does_not_add_shuriken_procs():
    state, build = established("Adaptive Armor"), Build(profile=BURN)
    assert choose([WAVE, CRIT], build, state, False) == 1
    assert shop_order([SHURIKEN], build, state, False) == []
    state.take(CRIT, build)
    # Once its critical family is acquired, continue strengthening the fire line.
    assert choose([WAVE, CRIT], build, state, False) == 0
    assert focus(build, state) == "fire"


@pytest.mark.parametrize("modifier", ["Berserk Enemies", "Rising Omen"])
def test_rising_enemy_attack_prefers_immediate_damage_over_slow_ramping(modifier):
    slow = sk("Fire Ramp", "fire", "mythic", "Every turn gain ATK (max 10 stacks)")
    state = established(modifier)
    assert choose([slow, WAVE], Build(profile=BURN), state, False) == 1


def test_hard_shell_favors_recurring_damage_over_opening_only_burst():
    burst = sk("Opening Fire", "fire", "mythic", "At the start of combat deal fire damage.")
    state = established("Hard Shell")
    assert choose([burst, WAVE], Build(profile=BURN), state, False) == 1


def test_unknown_modifier_retains_its_text_and_does_not_change_the_build():
    state = established("Unknown Flame", "Prison Lockdown", "Narrow Minded")
    assert state.rules.unknown == ("Unknown Flame",)
    assert choose([SHURIKEN, WAVE], Build(profile=BURN), state, False) == 1
    assert state.modifiers[0].name == "Unknown Flame"


@pytest.mark.parametrize("name", ["Anti-Heal", "Anti Heal", "AntiHeal"])
def test_modifier_names_tolerate_ocr_joined_words_and_hyphens(name):
    assert state_with(name).rules.effects == {"reduced_healing"}


def test_elite_navigation_carries_the_actual_preview_modifiers_without_starting(ocr):
    from roguebot.navigation import Navigator
    image, texts = load(ocr, "en_elite_no_training_berserk.png")
    device = ReplayDevice([])
    nav = Navigator(device, None, elite_energy=5)
    nav._capture = lambda: (image, texts)
    assert nav._set_elite_cost().norm == "start"
    assert {"training_disabled", "ramping_attack"} <= ModifierRules.read(nav.level_modifiers).effects
    assert not device.taps


def test_resumed_elite_reads_the_modifier_panel_before_making_an_event_choice(ocr, tmp_path):
    rest = load(ocr, "en_level_rest_only.png")
    panel = load(ocr, "en_level_modifiers.png")
    victory = load(ocr, "level_victory.png")
    device = ReplayDevice([rest, panel, rest, rest, victory, victory])
    state = BuildState()
    player = Player(device, ReplayOcr(device), Build(profile=BURN), Catalog(tmp_path / "skills.json"),
                    build_state=state, inspect_modifiers=True)
    # The final fixture is Spanish; permit both label sets in this replay.
    labels.set_language(None)
    assert player.play_level() is LevelScreen.VICTORY
    assert {"enemy_healing", "expensive_shop"} <= state.rules.effects
    assert len(device.taps) == 4  # labelled modifier icon, Continue, sole Rest, victory
    assert device.taps[0][0] > 1100
    assert device.taps[1] == classify_level_screen(*panel).tap


def test_normal_level_never_opens_the_elite_modifier_icon(ocr):
    image, texts = load(ocr, "en_level_rest_only.png")
    device = ReplayDevice([])
    assert not Player(device, None)._read_modifier_panel(texts, LevelScreen.EVENT)
    assert not device.taps
