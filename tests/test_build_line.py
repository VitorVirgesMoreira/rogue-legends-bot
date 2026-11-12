"""Sequential choices keep a focus, account for upgrades and reject false synergies."""

import pytest

from roguebot.build import BURN, Build, BuildState, choose, family, focus, ranked, selection_order, shop_order
from roguebot.skills import Catalog, Skill


def sk(name, element=None, rarity="common", description="", role="damage"):
    return Skill(name, "en", rarity, element, "magic" if element in ("fire", "ice", "lightning") else "physical",
                 role, description)


FIRE = sk("Fire Weapon", "fire", description="Weapon attacks can cast Fireball.")
WAVE = sk("Fire Wave", "fire", description="Every turn cast Fire Wave.")
ICE = sk("Deadly Icicle", "ice", "mythic", "Whenever you critically hit, cast an Icicle.")
CRIT = sk("Critical Hit Rate Up", description="Critical Hit Rate increased.")
SHURIKEN = sk("Shuriken Throw", "shuriken", description="Every 2 turns throw shurikens.")


def test_custom_build_commits_to_its_first_element_instead_of_chasing_rarity():
    build, state = Build("magic", ("fire", "ice", "lightning", "shuriken", "venom", "bleed")), BuildState()
    state.take(FIRE, build)
    assert choose([ICE, WAVE], build, state, False) == 1
    assert shop_order([ICE], build, state, True) is None
    assert shop_order([ICE], build, state, False) == []
    state.take(ICE, build)  # a mandatory off-line pick cannot change the focus
    assert focus(build, state) == "fire"


@pytest.mark.parametrize("profile", ["fire", "ice", "lightning", "shuriken", "venom", "bleed"])
def test_explicit_line_never_buys_another_element(profile):
    build = Build(profile=profile)
    offers = [sk(element, element, "mythic") for element in ("fire", "ice", "lightning", "shuriken", "venom", "bleed")]
    assert [offers[i].damage_type for i in shop_order(offers, build, BuildState(), False)] == [profile]


def test_burn_build_starts_with_a_source_before_conditional_passives():
    build = Build(profile=BURN)
    passive = sk("Firestarter", "fire", "legendary", "After casting Fireball, cast Fire Wave.")
    assert choose([passive, FIRE], build, BuildState(), False) == 1


def test_existing_fire_skill_is_upgraded_before_opening_another_family():
    build, state = Build(profile="fire"), BuildState()
    state.take(WAVE, build)
    assert choose([sk("Fire Mastery", "fire", "mythic"), WAVE], build, state, False) == 1


def test_critical_proc_from_a_foreign_element_is_not_a_critical_stat_bonus():
    build = Build(profile=BURN)
    assert shop_order([ICE], build, BuildState(), False) == []
    assert choose([ICE, CRIT], build, BuildState(), False) == 1


def test_burn_line_adds_critical_rate_after_establishing_its_fire_sources():
    build, state = Build(profile=BURN), BuildState()
    state.take(FIRE, build)
    state.take(WAVE, build)
    assert choose([sk("Inferno", "fire", "legendary"), CRIT], build, state, False) == 1
    state.take(CRIT, build)
    assert choose([sk("Inferno", "fire", "legendary"), CRIT], build, state, False) == 0


def test_critical_rate_then_critical_damage_form_complementary_synergies():
    build, state = Build(profile=BURN), BuildState()
    damage = sk("Critical Hit Damage Up", rarity="mythic")
    assert choose([damage, CRIT], build, state, False) == 1
    state.take(CRIT, build)
    assert choose([CRIT, damage], build, state, False) == 1


def test_burn_secondary_waits_for_fire_and_is_limited_to_one_family():
    build, state = Build(profile=BURN), BuildState()
    assert shop_order([SHURIKEN], build, state, False) == []
    state.take(FIRE, build)
    state.take(WAVE, build)
    assert shop_order([SHURIKEN], build, state, False) == [0]
    state.take(SHURIKEN, build)
    assert shop_order([SHURIKEN], build, state, False) == []  # secondary cannot overtake the main line
    for _ in range(4):
        state.take(WAVE, build)
    assert shop_order([sk("Poison Shuriken", "shuriken"), SHURIKEN], build, state, False) == [1]


def test_proc_blockers_and_opposing_damage_tradeoffs_are_avoided():
    build, state = Build(profile=BURN), BuildState()
    bad = [sk("Deadly Stars", "shuriken", "mythic", "Shurikens no longer trigger other effects."),
           sk("Warrior", description="Physical DMG up, Magical DMG down.")]
    assert ranked(bad, build, state) == []
    shield = sk("Shield", role="support")
    assert choose([*bad, shield], build, state, False) == 2


def test_mandatory_multi_pick_uses_a_neutral_boost_instead_of_branching():
    build, state = Build("magic", ("fire", "ice", "lightning", "shuriken", "venom", "bleed")), BuildState()
    atk = sk("Attack Up", description="ATK increased.")
    order = selection_order([FIRE, ICE, atk], build, state)
    assert order[:2] == [0, 2]
    assert not state.taken  # planning does not count unconfirmed choices


def test_forced_pick_does_not_lock_custom_magic_to_a_physical_element():
    state, build = BuildState(), Build("magic")
    state.take(sk("Poison Strike", "venom"), build)
    assert state.focus is None
    state.take(FIRE, build)
    assert state.focus == "fire"


def test_upgraded_skill_names_share_one_family():
    assert family(sk("Shuriken Throw Lv.2")) == family(sk("Shuriken Throw Lv.3")) == family(sk("Shuriken Throw"))


def test_catalog_keeps_fire_and_ice_mastery_separate_despite_similar_names(tmp_path):
    catalog = Catalog(tmp_path / "skills.json")
    catalog.lookup("Fire Mastery", "Fire DMG increased.", "common", "en")
    ice = catalog.lookup("Ice Mastery", "Ice DMG increased.", "legendary", "en")
    assert ice.damage_type == "ice" and ice.name == "Ice Mastery" and len(catalog.skills) == 2


def test_catalog_uses_the_current_offers_rarity_and_preserves_reviewed_tags(tmp_path):
    catalog = Catalog(tmp_path / "skills.json")
    catalog.lookup("Fire Wave", "Fire damage.", "common", "en")
    upgraded = catalog.lookup("Fire Wave", "Fire damage increased.", "mythic", "en")
    assert upgraded.rarity == "mythic"
    catalog.skills["firewave"].auto = False
    catalog.skills["firewave"].damage_type = "shuriken"
    assert catalog.lookup("Fire Wave", "Fire damage.", "legendary", "en").damage_type == "shuriken"


def test_player_recovery_keeps_focus_and_does_not_double_count_a_pending_skill(tmp_path):
    from roguebot import labels
    from roguebot.play import Player
    from test_skill_screens import PROMPT, card, TapLog
    build, progress = Build(profile="fire"), BuildState()
    catalog = Catalog(tmp_path / "skills.json")
    screen = [PROMPT, *card("Common", "Fire Weapon", "Weapon Attacks deal fire damage.", 928)]
    try:
        labels.set_language("en")
        first = Player(TapLog(), None, build, catalog, build_state=progress)
        first._pick_skill(screen)
        progress.pending_skill = first._planned_skill
        recovered = Player(TapLog(), None, build, catalog, build_state=progress)
        recovered._pick_skill(screen)
        assert progress.taken == []
        from roguebot.screens import LevelScreen
        recovered._confirm_skill(LevelScreen.UNKNOWN, [])
        assert progress.taken == []
        recovered._confirm_skill(LevelScreen.BOARD_READY, [])
        recovered._confirm_skill(LevelScreen.BOARD_READY, [])
        assert focus(build, recovered._state) == "fire"
        assert progress.type_picks == {"fire": 1} and len(progress.taken) == 1
    finally:
        labels.set_language(None)
