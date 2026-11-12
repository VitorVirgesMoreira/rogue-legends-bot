"""Cross-guide regressions: source graphs, mode economics and irreversible costs."""

from dataclasses import asdict
import pytest

from roguebot.build import BURN, BURN_DOT, Build, BuildState, choose, family, ranked, shop_order
from roguebot.build_rules import future_unlocks, sources
from roguebot.combat_context import CombatContext, Loadout, additive_gain, effective_reduction, expected_hit
from roguebot.metrics import History, RunRecord
from roguebot.farming import FarmPolicy
from roguebot.skill_data import RULES, rule_for
from roguebot.skills import Catalog, Skill, infer_tags


def skill(name, description="", rarity="common"):
    element, nature, role = infer_tags(name, description)
    return Skill(name, "en", rarity, element, nature, role, description)


def state_for(build, *names, mode="campaign"):
    state = BuildState()
    state.configure(build, mode)
    for name in names:
        state.take(skill(name), build)
    return state


def test_canonical_aliases_and_explicit_versions_do_not_split_a_family():
    assert infer_tags("Cleave", "") == ("bleed", "physical", "damage")
    assert infer_tags("Ultimate Cleave", "")[0] == "bleed"
    assert infer_tags("Enfoque Elemental", "")[0] is None
    assert family(skill("Arma de Fogo Lv. 2+")) == family(skill("Fire Weapon"))
    assert skill("Arma de Fogo Lv. 2+").version == 21
    assert skill("Fire Weapon").version is None


def test_reviewed_observation_overrides_reference_tags(tmp_path):
    catalog = Catalog(tmp_path / "catalog.json")
    card = catalog.lookup("Cleave", "", "common", "en")
    assert card.damage_type == "bleed"
    catalog.skills["cleave"].auto = False
    catalog.skills["cleave"].damage_type = "fire"
    assert catalog.lookup("Cleave", "", "common", "en").damage_type == "fire"


def test_current_card_level_is_not_replaced_by_the_catalogs_first_sighting(tmp_path):
    catalog = Catalog(tmp_path / "catalog.json")
    catalog.lookup("Fire Weapon Lv. 1", "", "common", "en")
    current = catalog.lookup("Fire Weapon Lv. 2+", "", "common", "en")
    assert current.version == 21
    assert catalog.lookup("Fire Weapon Lv. 1", "", "mythic", "en").version == 10


def test_a_counter_is_not_a_source_and_exact_bolt_feeders_matter():
    build = Build(profile="lightning", loadout=Loadout(weapon="Storm Staff"))
    state = state_for(build)
    assert "bolts" in sources(state) and "bolt" not in sources(state)
    assert ranked([skill("High Voltage")], build, state) == []
    assert ranked([skill("Energizing Current")], build, state) == [0]
    state.take(skill("Round Bolt"), build)
    assert ranked([skill("High Voltage")], build, state) == [0]
    state = state_for(Build(profile="shuriken"))
    assert ranked([skill("Fuma Shuriken")], Build(profile="shuriken"), state) == []


def test_source_graph_stops_using_weapon_feeders_when_weapon_is_removed():
    build = Build(profile="lightning")
    state = state_for(build, "Lightning Weapon", "Thunder God")
    assert "weapon" not in sources(state)
    assert "bolt" in sources(state)  # Thunder God is independently a Bolt source.
    state = state_for(Build(strategy="pet", loadout=Loadout(pets=("Flux",))), "Fire Weapon", "Pet Trainer")
    assert "fireball" not in sources(state)


def test_confirmed_zero_crit_blocks_proc_until_a_rate_card_is_taken():
    build = Build(profile="fire", loadout=Loadout(stats=(("crit_rate", 0.),)))
    state = state_for(build)
    deadly = skill("Deadly Fireball")
    assert ranked([deadly], build, state) == []
    state.take(skill("Critical Hit Rate Up"), build)
    assert ranked([deadly], build, state) == [0]
    assert state.explanation(deadly, build)["active_triggers"] == ["weapon_crit"]


@pytest.mark.parametrize("version,active", [("0.630", True), ("0.631", True), ("0.632", False)])
def test_confirmed_ring_burn_can_feed_cards_and_shop_without_a_drafted_source(version, active):
    build = Build(profile="fire", loadout=Loadout(game_version=version, equipment=("Blazing Band:epic",)))
    state = state_for(build)
    pyromania = skill("Pyromania")
    assert ranked([pyromania], build, state) == ([0] if active else [])
    assert shop_order([pyromania], build, state, False) == ([0] if active else [])
    assert state.explanation(pyromania, build)["active_triggers"] == (["burn"] if active else [])


def test_build_plan_reports_the_meteor_chain_and_declared_lockouts():
    build = Build(profile="fire")
    state = state_for(build, "Fire Weapon")
    assert "Flame Strike" in future_unlocks(skill("Fire Wave"), state)
    state.take(skill("Fire Wave"), build)
    assert "Meteor" in future_unlocks(skill("Flame Strike"), state)
    assert "glasscannon" in rule_for("Beefcake").excludes
    assert all(rule.version and rule.name for rule in RULES.values())


@pytest.mark.parametrize("name", ["Pet Trainer", "Vampiric", "Darkside"])
def test_magic_campaign_refuses_engine_breakers_and_health_drain(name):
    build = Build(profile=BURN)
    state = state_for(build, "Fire Weapon", "Fire Wave")
    assert choose([skill(name, rarity="mythic"), skill("Fire Wave")], build, state, False) == 1
    assert shop_order([skill(name)], build, state, False) == []


def test_dojo_skips_defense_hit_and_kill_triggers():
    build = Build("physical", support_every=1)
    state = state_for(build, "Wound Strike", mode="dojo")
    offers = [skill("Recovery"), skill("Eye for an Eye"), skill("Souleater"), skill("Weapon Mastery")]
    # Eye for an Eye has no useful incoming attack in Dojo either.
    assert choose(offers, build, state, False) == 3


def test_raid_rejects_dr_but_keeps_shield_support():
    build = Build(profile="fire", support_every=1)
    state = state_for(build, "Fire Weapon", mode="raid")
    assert choose([skill("Hardened"), skill("Strike Shield")], build, state, False) == 1


def test_burn_dot_does_not_force_a_critical_pick():
    build = Build(profile=BURN_DOT)
    state = state_for(build, "Fire Weapon", "Fire Wave")
    assert choose([skill("Critical Hit Rate Up"), skill("Inferno")], build, state, False) == 1


def test_only_a_real_explicit_upgrade_can_be_bought_again():
    build = Build(profile="fire")
    state = state_for(build, "Fire Weapon Lv.2+")
    assert shop_order([skill("Fire Weapon Lv.2")], build, state, False) == []
    assert shop_order([skill("Fire Weapon Lv.2+")], build, state, False) == []


def test_mixed_equipment_prevents_elemental_focus_reset_trap():
    build = Build(profile="ice", loadout=Loadout(mounts=("Ultimania Codex",)))
    assert ranked([skill("Elemental Focus")], build, state_for(build)) == []


def test_damage_pools_tags_and_dots_follow_different_layers():
    assert additive_gain(3., .25) == 1.0625
    assert effective_reduction(.9) == pytest.approx(.573684, abs=1e-6)
    assert expected_hit(100., 1., tags=("fire",), tag_bonuses={"fire": (.3, .3)}) == pytest.approx(169.)
    assert expected_hit(100., 1., tags=("status",), crit_rate=1., crit_damage=5.) == 100.
    assert expected_hit(100., 1., enemy_def=200., raw_dr=0.) == 10.
    assert expected_hit(100., 1., true_damage=True, enemy_def=200., raw_dr=9., final_dr=9.) == 100.
    assert expected_hit(100., 1., tags=("status",), enemy_dot=True, enemy_def=200., raw_dr=9.) == 100.


def test_history_is_local_bounded_deduplicated_and_separates_equipment(tmp_path):
    history = History(tmp_path / "history.json")
    record = RunRecord("elite", "fire", "victory", 60., level=10, energy=15,
                       rewards={"adventure_journals": 300.}, loadout={"hero": "Draco"})
    history.record(record)
    history.record(record)
    assert len(history.read()) == 1
    summary = history.summary()[0]
    assert summary["rewards_per_energy"] == {"adventure_journals": 20.}
    assert summary["rewards_per_minute"] == {"adventure_journals": 300.}
    history.record(RunRecord("elite", "fire", "victory", 30., level=10, loadout={"hero": "Rogue"}))
    assert len(history.summary()) == 2


def test_farm_retreats_and_stops_after_repeated_stage_one_defeats():
    farm = FarmPolicy()
    assert farm.choose([], "elite", "fire", 4) == 3
    assert not farm.observe(False) and not farm.observe(False) and farm.target == 2
    farm.observe(False)
    farm.observe(False)
    farm.observe(False)
    assert farm.observe(False) and farm.target == 1


def test_invalid_loadout_values_never_become_trusted_stats():
    with pytest.raises(ValueError):
        Loadout.from_dict({"hero_stars": True})
    with pytest.raises(ValueError):
        Loadout.from_dict({"stats": {"crit_rate": float("nan")}})
