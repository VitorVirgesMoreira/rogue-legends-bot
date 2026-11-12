"""Decisions the level-47 run exposed, plus counterexamples for healthy runs."""

import json
from pathlib import Path

import pytest

from roguebot import decision_journal, labels
from roguebot.build import Build, BuildState, choose, focus
from roguebot.build_rules import future_unlocks
from roguebot.combat_context import CombatContext, Loadout
from roguebot.event_rules import choose_event
from roguebot.metrics import History, RunRecord
from roguebot.screens import health_fraction, parse_shop
from roguebot.shopping import Reroll, Shopper, ShopVisit
from roguebot.skill_data import numeric_values
from roguebot.skill_value import current_stat, marginal_effects, trigger_rates
from roguebot.skills import Skill, infer_tags
from roguebot.vision import Text


def skill(name, rarity="common"):
    element, nature, role = infer_tags(name, "")
    return Skill(name, "en", rarity, element, nature, role)


def configured(*names, stats=(), version="0.631", **loadout):
    build = Build(profile="fire", loadout=Loadout(stats=stats, game_version=version, **loadout))
    state = BuildState()
    state.configure(build)
    for name in names:
        state.take(skill(name), build)
    return build, state


@pytest.mark.parametrize("parts,expected", [
    (["2,5m1", "4,3m"], 2.5/4.3), (["2,5m", "/", "4,3m"], 2.5/4.3),
    (["250k/", "1m"], .25), (["250k", "1m"], None),
    (["5m1", "4m"], None), (["2m1", "0"], None),
])
def test_hp_fragments_require_an_aligned_ratio(parts, expected):
    texts = [Text(value, 400+i*85, 50, 480+i*85, 110) for i, value in enumerate(parts)]
    assert health_fraction(texts) == pytest.approx(expected) if expected is not None else health_fraction(texts) is None
    assert health_fraction([Text("25/100", 400, 300, 650, 360)]) is None


def test_unrelated_rows_are_not_joined_into_hp():
    assert health_fraction([Text("2m/", 400, 40, 490, 70), Text("4m", 500, 90, 590, 130)]) is None


def test_recorded_level_47_rest_has_readable_hp_and_prefers_a_refill():
    data = json.loads((Path(__file__).parent / "fixtures/run47_rest.json").read_text(encoding="utf-8"))
    texts = [Text(**t) for t in data["texts"]]
    hp = health_fraction(texts)
    assert data["hp"] is None  # the old run lost this reading
    assert hp == pytest.approx(2.5/4.3)
    title = next(t for t in texts if t.text == "A Moment To Rest")
    rest, train = (next(t for t in texts if t.text == name) for name in ("Rest", "Train"))
    labels.set_language("en")
    try:
        choice = choose_event(title, (rest, train), {rest: "Restore 45% HP", train: "Improve 1 Existing Skill"}, hp)
        assert choice.option == rest and choice.reason == "decision_heal"
        assert choose_event(title, (rest, train), {rest: "Restore 45% HP", train: "Improve 1 Existing Skill"}, 1.).option == train
    finally:
        labels.set_language(None)


def test_observed_damage_and_revive_influence_risk_without_reusing_stale_hp():
    context = CombatContext()
    context.observe(.95, "fight")
    context.observe(.4, "fight")
    context.observe(.45, "auto_play")
    assert context.recent_hp_loss == pytest.approx(.5) and context.survival_pressure
    context.observe(None, "unknown")
    assert context.hp is None and not context.survival_pressure
    context.observe(None, "revive")
    context.observe(None, "unknown")
    context.observe(None, "revive")
    assert context.revives_seen == 1
    context.observe(.58, "shop")
    assert context.survival_pressure
    context.observe(.95, "shop")
    assert not context.survival_pressure


def test_custom_equipped_weapon_sets_a_coherent_initial_plan():
    build = Build(nature="magic", loadout=Loadout(weapon="Ember Staff", game_version="0.631"))
    state = BuildState()
    assert focus(build, state) == "fire"
    assert choose([skill("Ice Weapon"), skill("Fire Weapon")], build, state, True) == 1
    explicit = Build(profile="ice", loadout=build.loadout)
    assert focus(explicit, state) == "ice"


def test_631_numeric_facts_are_scoped_and_upgrade_gains_replace_old_values():
    build, state = configured("Fire Weapon Lv.2")
    upgrade = skill("Fire Weapon Lv.2+")
    assert numeric_values(upgrade, "0.631") == {"proc_chance": .8}
    assert marginal_effects(upgrade, state)["proc_chance"] == pytest.approx(.8/.6 - 1)
    assert numeric_values(skill("Hardened Lv.2"), "0.631") == {}
    assert numeric_values(upgrade, "0.632") == {}
    assert numeric_values(skill("Fire Weapon"), "0.631") == {}
    assert trigger_rates(state)["fireball"] == .6
    state.take(skill("Firestarter Lv.2"), build)
    effects = marginal_effects(skill("Firestarter Lv.2+"), state)
    assert effects == {"proc_count": .5}  # 2 -> 3 waves; the chance remains 75%


def test_opening_a_chain_can_beat_an_existing_source_upgrade():
    build, state = configured("Fire Weapon Lv.2")
    offers = [skill("Fire Weapon Lv.2+"), skill("Flame Strike", "legendary")]
    assert choose(offers, build, state, False) == 1


def test_upgrade_does_not_claim_to_open_a_second_element_family():
    build, state = configured("Fire Weapon Lv.2")
    assert "Flame Strike" not in future_unlocks(skill("Fire Weapon Lv.2+"), state)
    assert "Flame Strike" in future_unlocks(skill("Fire Wave"), state)
    state.take(skill("Fire Wave"), build)
    assert "Meteor" in future_unlocks(skill("Flame Strike"), state)


def test_crit_rate_cap_and_upgrade_replacement_make_a_weak_offer_rerollable():
    build, state = configured("Fire Weapon Lv.2", "Critical Hit Rate Up Lv.2",
                              stats=(("crit_rate", .95), ("crit_damage", 1.5)))
    upgrade = skill("Critical Hit Rate Up Lv.2+")
    assert current_stat(state, "crit_rate") == pytest.approx(1.1)
    assert marginal_effects(upgrade, state)["crit_rate"] == 0.
    assert choose([upgrade], build, state, True) is None
    assert choose([upgrade], build, state, False) == 0
    state.take(upgrade, build)
    assert current_stat(state, "crit_rate") == pytest.approx(1.2)  # not 1.35


def test_protection_can_precede_damage_after_a_revive_before_support_interval():
    build, state = configured("Fire Weapon Lv.2")
    state.context.hp, state.context.revives_seen = .58, 1
    assert choose([skill("Fire Weapon Lv.2+"), skill("Resurrection", "mythic")], build, state, True) == 1
    state.context.hp = 1.
    assert choose([skill("Fire Weapon Lv.2+"), skill("Resurrection", "mythic")], build, state, True) == 0


def test_shop_does_not_reserve_for_an_unrelated_expensive_card(tmp_path):
    from test_shop_strategy import supply_screen
    from test_skill_screens import player
    p = player(tmp_path, Build(profile="fire"), final_shop=False)
    shop = parse_shop(supply_screen(200, stat=None, cards=[("Mythic", "Ice Weapon", "Ice damage", 380, False)]))
    buyer = Shopper(p.device, p.ocr, p.build, p._state, p._skill)
    assert buyer._reserve(shop, False) == 190 and p._state.premium_shop_price == 0
    p._state.context.hp, p._state.context.revives_seen = .58, 1
    assert buyer._reserve(shop, False) == 0


def test_shop_can_search_instead_of_buying_a_capped_rate(tmp_path):
    from test_shop_strategy import supply_screen
    from test_skill_screens import player
    build, state = configured("Fire Weapon Lv.2", "Critical Hit Rate Up Lv.2",
                              stats=(("crit_rate", .95), ("crit_damage", 1.5)))
    p = player(tmp_path, build)
    shop = parse_shop(supply_screen(300, stat=None, cards=[("Common", "Critical Hit Rate Up Lv.2+", "Critical Hit Rate", 48, False)], free=True))
    buyer = Shopper(p.device, p.ocr, build, state, p._skill)
    assert isinstance(buyer._choose(shop, ShopVisit(), 190), Reroll)
    no_search = parse_shop(supply_screen(300, stat=None, cards=[("Common", "Critical Hit Rate Up Lv.2+", "Critical Hit Rate", 48, False)]))
    assert buyer._choose(no_search, ShopVisit(), 0) is None


def test_journal_has_alternatives_and_keeps_confirmation_separate(tmp_path):
    from test_skill_screens import PROMPT, card, player
    from roguebot.screens import LevelScreen
    p = player(tmp_path, Build(profile="fire"))
    p._pick_skill([PROMPT, *card("Common", "Fire Weapon", "Weapon Attacks cast Fireball", 928),
                   *card("Common", "Ice Weapon", "Weapon attacks cast Icicle", 1250)])
    records = [json.loads(f.read_text(encoding="utf-8")) for f in decision_journal.DECISION_DIR.glob("*.json")]
    assert len(records) == 1 and len(records[0]["offers"]) == 2
    assert records[0]["run_id"] == p._state.run_id and records[0]["owned"] == []
    p._state.pending_skill = p._planned_skill
    p._confirm_skill(LevelScreen.BOARD_READY, [])
    records = [json.loads(f.read_text(encoding="utf-8")) for f in sorted(decision_journal.DECISION_DIR.glob("*.json"))]
    assert records[-1]["action"] == "confirmed" and len(records[-1]["owned"]) == 1


def test_journal_is_bounded_and_failure_cannot_repeat_a_game_action(monkeypatch):
    monkeypatch.setattr(decision_journal, "MAX_RECORDS", 2)
    state = BuildState()
    for _ in range(3):
        decision_journal.record(state, "skill_pick", "pick")
    assert len(list(decision_journal.DECISION_DIR.glob("*.json"))) == 2
    monkeypatch.setattr(decision_journal, "write_json", lambda *a: (_ for _ in ()).throw(OSError("disk full")))
    decision_journal.record(state, "skill_pick", "confirmed")


def test_history_separates_policy_versions(tmp_path):
    history = History(tmp_path / "history.json")
    for policy in ("legacy", "2026-11-12"):
        history.record(RunRecord("normal", "fire", "defeat", 60., level=47, policy_version=policy))
    assert len(history.summary()) == 2
