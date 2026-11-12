"""Marginal, partial estimates. Unknown arrows never become invented percentages."""

from roguebot.combat_context import additive_gain, effective_reduction, expected_hit
from roguebot.skill_data import numeric_values


_RATES = {"crit_rate": "crit_rate", "crit_damage": "crit_damage",
          "combo_rate": "combo", "counter_rate": "counter"}


def current_stat(state, stat):
    value = state.context.loadout.stat(stat)
    if value is None:
        return None
    for owned in state.owned.values():
        spec = owned.reference
        if spec is None or _RATES.get(stat, stat) not in spec.benefits:
            continue
        bonus = numeric_values(owned, state.context.loadout.game_version).get(stat)
        if bonus is None:
            return None  # the permanent stat is no longer the current run stat
        value += bonus
    return value


def trigger_rates(state):
    """Known rates per opportunity, not a prediction of battle DPS."""
    result = {}
    for source, stat in (("weapon_crit", "crit_rate"), ("combo", "combo_rate"),
                         ("counter", "counter_rate"), ("dodge", "dodge_rate")):
        rate = current_stat(state, stat)
        if rate is not None:
            result[source] = min(1., max(0., rate))
    for owned in state.owned.values():
        spec = owned.reference
        chance = numeric_values(owned, state.context.loadout.game_version).get("proc_chance")
        if spec and chance is not None and spec.needs_sources == ("weapon",):
            for action in spec.produces:
                result[action] = max(result.get(action, 0.), chance)
    return result


def marginal_effects(skill, state):
    spec = skill.reference
    if spec is None:
        return {}
    previous = state.owned.get(spec.id)
    values = numeric_values(skill, state.context.loadout.game_version)
    old = numeric_values(previous, state.context.loadout.game_version) if previous else {}
    gains = {}
    for stat, bonus in values.items():
        if previous and stat not in old:
            continue
        before = old.get(stat, 0.)
        delta = bonus - before
        if delta <= 0:
            continue
        pool = current_stat(state, stat)
        if stat == "proc_chance":
            gains[stat] = delta / before if before else bonus
        elif stat == "proc_count":
            gains[stat] = bonus / max(1., before) - 1.
        elif stat in ("crit_rate", "crit_damage"):
            rate, damage = current_stat(state, "crit_rate"), current_stat(state, "crit_damage")
            if rate is not None and damage is not None:
                baseline = expected_hit(1., 1., crit_rate=rate, crit_damage=damage)
                after = expected_hit(1., 1., crit_rate=rate + (delta if stat == "crit_rate" else 0.),
                                     crit_damage=damage + (delta if stat == "crit_damage" else 0.))
                gains[stat] = after / baseline - 1.
        elif stat == "dr" and pool is not None:
            gains[stat] = ((1. - effective_reduction(pool)) /
                          max(.01, 1. - effective_reduction(pool + delta)) - 1.)
        elif stat in ("vs_burn", "vs_wound", "status_damage", "lightning_damage"):
            gains[stat] = (1. + bonus) / (1. + before) - 1.
        elif pool is not None:
            gains[stat] = additive_gain(pool, delta) - 1.
    return gains


def synergy_value(skill, state, primary):
    spec = skill.reference
    if spec is None:
        return 0.
    value = 0.
    rates = trigger_rates(state)
    # Taking a known rate from 0 to 100% matters; merely having its tag does not.
    known = [rates[s] for s in spec.needs_sources if s in rates]
    if known:
        value -= 1.5 * (1. - max(known))
    if "crit_rate" in spec.benefits:
        crit_procs = any(s.reference and "weapon_crit" in s.reference.needs_sources
                         for s in state.owned.values())
        if crit_procs or primary == "fire" and state.strategy != "dot":
            rate = current_stat(state, "crit_rate")
            value += .8 if rate is None else 1.5 * (1. - min(1., rate))
        rate = current_stat(state, "crit_rate")
        if rate is not None and rate >= 1. and "crit_damage" not in spec.benefits:
            value -= .8
        if spec.id in state.owned:
            value -= 1.  # uncertain repeat bonuses shouldn't crowd out a new synergy
    if "crit_damage" in spec.benefits:
        rate = current_stat(state, "crit_rate")
        if rate is not None:
            value += rate - .5
        elif any(s.reference and "crit_rate" in s.reference.benefits for s in state.owned.values()):
            value += .5
    if {"combo", "counter"}.intersection(spec.benefits):
        if any(s.reference and "weapon" in s.reference.needs_sources for s in state.owned.values()):
            value += .5  # more weapon hits also feed the established spell engine
    if spec.drawbacks:
        value -= .25 * len(spec.drawbacks)
    if "less_noncrit" in spec.drawbacks:
        rate = current_stat(state, "crit_rate")
        if rate is not None:
            value -= 1. - min(1., rate)
    return value
