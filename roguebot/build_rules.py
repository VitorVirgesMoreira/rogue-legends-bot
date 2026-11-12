"""Semantic compatibility and marginal utility, separate from offer ordering.

Hard pool rules describe future availability. They never pretend an offered
Lv2 card cannot exist: the client has incomplete exclusion links in 0.630.
"""

import re

from roguebot.skill_data import POLICY_VERSION, key, numeric_values, rule_for
from roguebot.skill_value import current_stat, marginal_effects, synergy_value, trigger_rates

_DAMAGE_FEEDERS = {
    "fire": {"fire", "fireball", "firewave", "flamestrike", "meteor", "burn"},
    "ice": {"ice", "icicle", "froststrike", "frostnova"},
    "lightning": {"lightning", "bolt", "bolt_random"},
    "shuriken": {"shuriken_tag"},
    "venom": {"poison"},
    "bleed": {"cleave", "wound"},
}


def sources(state) -> set[str]:
    result = set(state.context.loadout.sources)
    drawbacks = {drawback for skill in state.owned.values() if skill.reference for drawback in skill.reference.drawbacks}
    if "no_weapon" in drawbacks:
        result.difference_update(("weapon", "weapon_crit", "combo", "counter"))
    if "no_ultimate" in drawbacks:
        result.discard("ultimate")
    if state.context.incoming:
        result.update(("incoming", "low_hp"))
    if state.context.mode not in ("dojo", "raid"):
        result.add("kills")
    # Iterate because Fire Weapon -> Firestarter -> Flame Strike is a graph.
    for _ in range(len(state.owned) + 1):
        before = set(result)
        for skill in state.owned.values():
            spec = skill.reference
            if not spec:
                continue
            if "crit_rate" in spec.benefits and "no_weapon" not in drawbacks:
                result.add("weapon_crit")
            if spec.independent or not spec.needs_sources or any(s in result for s in spec.needs_sources):
                result.update(spec.produces)
                result.update(spec.applies)
                result.update(spec.tags)
                if "shield" in spec.benefits:
                    result.update(("shield", "shield_incoming"))
            if "no_wound_from_cleave" in spec.drawbacks:
                if not any(s.reference and "wound" in s.reference.applies and s.reference.id != "cleave"
                           for s in state.owned.values()):
                    result.discard("wound")
        if any(x in result for x in ("shuriken", "shuriken_random", "fuma")):
            result.add("shuriken_tag")
        if any(x in result for x in ("bolt", "bolt_random", "divinebolt")):
            result.add("bolts")
        if result == before:
            break
    return result


def has_damage_source(state, element):
    return bool(_DAMAGE_FEEDERS.get(element, set()).intersection(sources(state)))


def reasons(skill, build, state, primary) -> tuple[str, ...]:
    """Reasons to exclude an optional purchase/pick, also shown in diagnostics."""
    spec = skill.reference
    if not spec:
        return ()
    context, available = state.context, sources(state)
    problems = []
    if spec.mode == "party" and context.mode != "party":
        problems.append("party_only")
    if context.mode == "dojo":
        if spec.role == "support":
            problems.append("dojo_no_incoming_damage")
        if spec.low_hp or "incoming" in spec.needs_sources or "counter" in spec.needs_sources:
            problems.append("dojo_unavailable_trigger")
        if spec.needs_sources == ("kills",):
            problems.append("single_target_no_kills")
        if "counter" in spec.benefits and not any(s.reference and "counter" in s.reference.tags for s in state.owned.values()):
            problems.append("dojo_no_counter")
    if context.mode == "raid" and spec.role == "support":
        # True damage ignores DEF, DR, FDR; shields/heals/immunity still help.
        useful = {"heal", "shield", "survival", "immunity", "max_hp"}
        if not useful.intersection(spec.benefits):
            problems.append("raid_true_damage")
    if context.mode in ("dojo", "raid") and spec.needs_sources == ("kills",):
        problems.append("single_target_no_kills")
    if spec.needs_pets and not context.loadout.pets:
        problems.append("pets_not_configured")
    drawbacks = set(spec.drawbacks)
    magic = primary in ("fire", "ice", "lightning")
    if magic and "less_magic" in drawbacks or primary and not magic and "less_physical" in drawbacks:
        problems.append("opposing_damage_penalty")
    if "no_weapon" in drawbacks and (spec.id == "pettrainer" and build.strategy != "pet" or any(s.reference and
            set(s.reference.needs_sources).intersection(("weapon", "weapon_crit", "combo", "counter"))
            for s in state.owned.values())):
        problems.append("removes_weapon_engine")
    if "no_ultimate" in drawbacks and any(s.reference and "ultimate" in s.reference.needs_sources for s in state.owned.values()):
        problems.append("removes_ultimate_engine")
    if "no_wound_from_cleave" in drawbacks and primary == "bleed" and build.strategy != "cleave":
        problems.append("removes_wound_source")
    if "no_shuriken_effects" in drawbacks and (build.profile == "burn" or any(
            s.reference and s.reference.id in ("elementalstars", "healshuriken", "poisonshuriken", "woundshuriken", "energizingshuriken")
            for s in state.owned.values())):
        problems.append("removes_shuriken_effects")
    if "no_bolt_damage" in drawbacks and any(s.reference and s.reference.id in
            ("highvoltage", "repeatedbolt", "thunderstorm") for s in state.owned.values()):
        problems.append("replaces_bolt_engine")
    if "less_combo_counter" in drawbacks and (build.strategy in ("combo", "counter", "cleave") or
            primary == "fire" and build.profile == "burn"):
        problems.append("reduces_weapon_procs")
    if "hp_drain" in drawbacks and context.mode != "dojo":
        problems.append("recurring_hp_cost")
    if "less_hp" in drawbacks and context.hp is not None and context.hp <= .4 and context.incoming:
        problems.append("low_hp_tradeoff")
    if spec.id == "elementalfocus" and (context.loadout.mixed_elements or len(
            {s.damage_type for s in state.owned.values() if s.damage_type in ("fire", "ice", "lightning")}) > 1):
        problems.append("mixed_elements_reset_focus")
    if spec.needs_sources and not any(s in available for s in spec.needs_sources):
        # An offered amplifier can still be kept as a mandatory fallback; shops
        # should not pay for an engine with no observed feeder.
        problems.append("missing_feeder")
    owned = state.owned.get(spec.id)
    rate_stat = {"criticalhitrateup": "crit_rate", "comborateup": "combo_rate",
                 "counterrateup": "counter_rate", "dodgerateup": "dodge_rate"}.get(spec.id)
    if rate_stat and (rate := current_stat(state, rate_stat)) is not None and rate >= 1.:
        problems.append("rate_already_capped")
    if owned and owned.version is not None and skill.version is not None and skill.version <= owned.version:
        problems.append("no_version_upgrade")
    return tuple(dict.fromkeys(problems))


def utility(skill, state, primary) -> float:
    """Comparable utility within a compatibility tier, not a DPS prediction."""
    spec = skill.reference
    if spec is None:
        return 0.
    available = sources(state)
    value = 1.
    if spec.produces and (spec.independent or set(spec.needs_sources).intersection(available)):
        value += 1.
    if spec.needs_sources:
        value += .5 if set(spec.needs_sources).intersection(available) else -2.
    if spec.id == "elementalstars" and "elemental_weapon" not in available:
        value -= 2.
    if spec.id == "shuricoins":
        progress = state.run_progress
        remaining = progress.remaining_rolls
        value += -2. if progress.final_shop else 2. if remaining is not None and remaining >= 10 else 0.
    if spec.id in ("flamestrike", "cleave"):
        value += .25  # opens another documented branch; never outranks a missing source
    if primary in ("venom", "bleed") or state.strategy == "dot":
        if "dot" in spec.benefits:
            value += 2.
        if "crit_rate" in spec.benefits or "crit_damage" in spec.benefits:
            if not any(s.reference and "weapon_crit" in s.reference.needs_sources for s in state.owned.values()):
                value -= 1.
    if spec.ramping and state.context.expected_rounds is not None:
        value += .5 if state.context.expected_rounds >= 8 else -.5
    if state.context.hp is not None and state.context.hp <= .4:
        value += float(bool({"shield", "immunity", "survival"}.intersection(spec.benefits)))
    gains = marginal_effects(skill, state)
    if spec.id in state.owned and gains:
        value *= .5  # compare the upgrade's increment, not its full absolute effect
    value += 3. * sum(gains.values()) + synergy_value(skill, state, primary)
    if state.strategy not in ("balanced", "dot") and state.strategy in spec.benefits + spec.tags:
        value += .6
    if state.strategy == "crit" and {"crit_rate", "crit_damage"}.intersection(spec.benefits):
        value += .6
    if not state.run_progress.final_shop:
        after_sources = available | set(spec.produces + spec.applies)
        useful = [rule_for(name) for name in future_unlocks(skill, state)]
        value += min(.6, .15 * sum(bool(rule and (not rule.needs_sources or
                     after_sources.intersection(rule.needs_sources))) for rule in useful))
    return value


def future_unlocks(skill, state) -> tuple[str, ...]:
    from roguebot.skill_data import RULES
    spec = skill.reference
    if not spec:
        return ()
    owned = set(state.owned)
    owned.add(spec.id)
    # Count distinct learned families; an upgrade replaces its family.
    def counts_for(ids):
        counts = {}
        for skill_id in ids:
            reference = rule_for(skill_id)
            if reference and reference.element:
                counts[reference.element] = counts.get(reference.element, 0) + 1
        return counts
    counts, previous_counts = counts_for(owned), counts_for(state.owned)
    loadout = state.context.loadout
    known_tree = {key(name) for name in loadout.tree_skills} if not loadout.tree_skills_partial else set()
    unlocked = []
    for candidate in RULES.values():
        if candidate.mode != "solo" or candidate.id in owned:
            continue
        if candidate.tree_unlock and known_tree and candidate.id not in known_tree:
            continue
        if candidate.element_count and counts.get(candidate.element, 0) < candidate.element_count:
            continue
        if not set(candidate.requires).issubset(owned) or set(candidate.excludes).intersection(owned):
            continue
        opens_element = (candidate.element == spec.element and candidate.element_count
                         and previous_counts.get(candidate.element, 0) < candidate.element_count)
        if spec.id in candidate.requires and spec.id not in state.owned or opens_element:
            unlocked.append(candidate.name)
    return tuple(unlocked)


def explain(skill, build, state, primary) -> dict:
    spec = skill.reference
    available = sources(state)
    return {"skill": skill.name, "family": spec.id if spec else key(skill.name),
            "policy_version": POLICY_VERSION,
            "version": skill.version, "rules_version": spec.version if spec else None,
            "mode": state.context.mode, "game_version": state.context.loadout.game_version,
            "blocked": reasons(skill, build, state, primary),
            "active_triggers": sorted(available.intersection(spec.needs_sources)) if spec else [],
            "new_sources": sorted(set(spec.produces + spec.applies) - available) if spec else [],
            "sources": sorted(available), "utility": round(utility(skill, state, primary), 3),
            "marginal_effects": marginal_effects(skill, state), "trigger_rates": trigger_rates(state),
            "numeric_values": numeric_values(skill, state.context.loadout.game_version),
            "unlocks": future_unlocks(skill, state)}
