"""Keep a coherent build and compare each compatible choice's marginal value."""

from copy import deepcopy
from dataclasses import dataclass, field
import re
import uuid

from roguebot.skills import DAMAGE, DAMAGE_TYPES, MAGIC, MAGIC_TYPES, PHYSICAL, RARITY_NAMES, SUPPORT, Skill, skill_key
from roguebot.modifiers import Modifier, ModifierRules
from roguebot.run_progress import RunProgress
from roguebot.events import EventChoices
from roguebot.vision import normalize
from roguebot.combat_context import CombatContext, Loadout
from roguebot import build_rules
from roguebot.skill_data import base_name, rule_for

CUSTOM, BURN, BURN_DOT = "custom", "burn", "burn_dot"
PROFILES = (CUSTOM, BURN, BURN_DOT, *DAMAGE_TYPES)
STRATEGIES = ("balanced", "dot", "crit", "combo", "counter", "cleave", "pet", "ultimate", "skill")


@dataclass(frozen=True)
class Build:
    nature: str = PHYSICAL
    order: tuple[str, ...] = DAMAGE_TYPES
    support_every: int | None = None
    profile: str = CUSTOM
    strategy: str = "balanced"
    loadout: Loadout = Loadout()

    def __post_init__(self) -> None:
        if self.profile not in PROFILES:
            raise ValueError("bad_build_profile")
        if self.strategy not in STRATEGIES or not isinstance(self.loadout, Loadout):
            raise ValueError("bad_loadout")


def family(skill: Skill) -> str:
    """Upgrades such as 'Shuriken Throw Lv.2' stay in the same family."""
    reference = rule_for(skill.name)
    return reference.id if reference else skill_key(base_name(skill.name))


@dataclass
class PendingSkill:
    skill: Skill
    offer: tuple[tuple[str, str], ...]
    index: int


@dataclass
class BuildState:
    damage_since_support: int = 0
    taken: list[str] = field(default_factory=list)
    focus: str | None = None
    owned: dict[str, Skill] = field(default_factory=dict)
    type_picks: dict[str, int] = field(default_factory=dict)
    pending_skill: PendingSkill | None = None  # dispatch is confirmed by leaving the offer, even after recovery
    modifiers: tuple[Modifier, ...] | None = None
    rules: ModifierRules = field(default_factory=ModifierRules)
    run_progress: RunProgress = field(default_factory=RunProgress)
    event_choices: EventChoices = field(default_factory=EventChoices)
    premium_shop_price: int = 0  # remember the price to save for across earlier shops/recovery
    context: CombatContext = field(default_factory=CombatContext)
    strategy: str = "balanced"
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def configure(self, build: Build, mode: str | None = None) -> None:
        self.context.loadout = build.loadout
        self.strategy = "dot" if build.profile == BURN_DOT else build.strategy
        if mode is not None:
            self.context.mode = mode

    def explanation(self, skill: Skill, build: Build) -> dict:
        self.configure(build)
        result = build_rules.explain(skill, build, self, focus(build, self))
        result["rank_score"] = _score(skill, build, self)
        return result

    def set_modifiers(self, entries: tuple[Modifier, ...]) -> None:
        self.modifiers = entries
        self.rules = ModifierRules.read(entries)

    @property
    def shop_reserve(self) -> int:
        return max(285 if self.rules.has("expensive_shop") else 190, self.premium_shop_price)

    def take(self, skill: Skill, build: Build | None = None) -> None:
        if build:
            self.configure(build)
        self.taken.append(skill.name)
        self.owned[family(skill)] = skill
        if skill.role == DAMAGE and skill.damage_type:
            self.type_picks[skill.damage_type] = self.type_picks.get(skill.damage_type, 0) + 1
            if self.focus is None and (build is None or skill.nature == build.nature):
                self.focus = (focus(build, self) if build else None) or skill.damage_type
        self.damage_since_support = 0 if skill.role == SUPPORT else self.damage_since_support + 1

    def wants_support(self, build: Build) -> bool:
        return build.support_every is not None and self.damage_since_support >= build.support_every

    def priority_enemy_counter(self, skill: Skill) -> bool:
        """Acquire the legendary heal/shield counter immediately, once per level."""
        def counter(candidate: Skill) -> bool:
            return (candidate.damage_type is None and candidate.rarity in ("legendary", "mythic")
                    and self.rules.support_priority(candidate.name, candidate.description) == 0)
        return counter(skill) and not any(counter(owned) for owned in self.owned.values())


def focus(build: Build, state: BuildState) -> str | None:
    if build.profile in (BURN, BURN_DOT):
        return "fire"
    if build.profile in DAMAGE_TYPES:
        return build.profile
    if state.focus is not None:
        return state.focus
    return None


def _rarity(skill: Skill) -> int:
    return RARITY_NAMES.index(skill.rarity) if skill.rarity in RARITY_NAMES else len(RARITY_NAMES)


def _text(skill: Skill) -> str:
    return normalize(f"{skill.name} {skill.description}")


def _critical(skill: Skill) -> bool:
    # Casting an icicle on a critical hit remains an ICE skill, not a universal critical bonus.
    text = re.sub(r"\b(?:non[ -]*|sin\s+)crit\w*", "", _text(skill))
    return skill.damage_type is None and bool(re.search(r"\bcrit", text))


def _critical_traits(skill: Skill) -> tuple[bool, bool]:
    text = _text(skill)
    return bool(re.search(r"\b(?:rate|tasa|taxa|chance|probab)", text)), bool(re.search(r"\b(?:damage|dmg|dano)", text))


def _source(skill: Skill) -> bool:
    reference = skill.reference
    if reference:
        return reference.independent or bool(reference.produces and
                    set(reference.needs_sources).intersection(("weapon", "weapon_crit", "ultimate")))
    return bool(re.search(r"\b(?:weapon|arma|shuriken throw)", normalize(skill.name))
                or re.search(r"\b(?:every\s+(?:turn|\d+)|cada\s+(?:turno|\d+))", normalize(skill.description)))


def _conflict(skill: Skill, primary: str | None) -> bool:
    text, name = _text(skill), normalize(skill.name)
    if primary in MAGIC_TYPES and re.search(r"\b(?:warrior|guerrero|guerreiro)\b", name):
        return True  # known tradeoff: magical damage goes down
    if primary and primary not in MAGIC_TYPES and re.search(r"\b(?:wizard|mago)\b", name):
        return True
    return bool(primary == "fire" and skill.damage_type == "shuriken"
                and re.search(r"no longer trigger|cannot trigger|ya no activ|no activan", text))


def _secondary_allowed(skill: Skill, build: Build, state: BuildState) -> bool:
    if build.profile != BURN or skill.damage_type != "shuriken":
        return False
    primary = state.type_picks.get("fire", 0)
    secondary = state.type_picks.get("shuriken", 0)
    families = {key for key, owned in state.owned.items() if owned.damage_type == "shuriken"}
    return (primary >= 2 and secondary < max(1, primary // 3)
            and (not families or family(skill) in families))


def _line_score(skill: Skill, build: Build, state: BuildState) -> tuple | None:
    primary = focus(build, state)
    if _conflict(skill, primary):
        return None
    owned = family(skill) in state.owned
    if skill.role == SUPPORT:
        if state.wants_support(build) and skill.damage_type in (None, primary):
            return (-1, not owned, _rarity(skill))
        return None
    if skill.role != DAMAGE:
        return None
    reference = skill.reference
    if reference and build.strategy in ("combo", "counter", "cleave", "pet", "ultimate", "skill"):
        if build.strategy in reference.benefits or build.strategy in reference.tags:
            return (0, 0, _rarity(skill))
    if reference and ("single_element" in reference.benefits and primary in MAGIC_TYPES
                      or "dot" in reference.benefits and (primary in ("venom", "bleed") or state.strategy == "dot")):
        return (0, 1, _rarity(skill))
    critical = [s for s in state.owned.values() if _critical(s)]
    needs_critical = build.profile == BURN and state.type_picks.get("fire", 0) >= 2 and not critical
    if primary is None:  # custom: the first chosen compatible element establishes the line
        if skill.nature == build.nature:
            rank = build.order.index(skill.damage_type) if skill.damage_type in build.order else len(build.order)
            return (0, rank, _rarity(skill))
        return None
    if skill.damage_type == primary:
        has_source = build_rules.has_damage_source(state, primary) or any(
            s.reference is None and s.damage_type == primary and _source(s) for s in state.owned.values())
        stage = (0 if _source(skill) else 2) if not has_source else (0 if owned else 1)
        return (1 if needs_critical else 0, stage, _rarity(skill))
    if _critical(skill):
        rate, damage = _critical_traits(skill)
        has_rate = any(_critical_traits(s)[0] for s in critical)
        has_damage = any(_critical_traits(s)[1] for s in critical)
        stage = 0 if rate and not has_rate else 1 if damage and not has_damage else 2
        return (3 if state.strategy == "dot" else 0 if needs_critical else 1, stage, _rarity(skill))
    if _secondary_allowed(skill, build, state):
        return (3, not owned, _rarity(skill))
    nature = MAGIC if primary in MAGIC_TYPES else PHYSICAL
    if skill.damage_type is None and (skill.nature == nature or re.search(r"\b(?:atk|atq)\b", _text(skill))):
        return (2, not owned, _rarity(skill))
    return None


def _score(skill: Skill, build: Build, state: BuildState) -> tuple | None:
    """Keep the elemental line, adding a bounded counter to the actual stage's threats."""
    if state.priority_enemy_counter(skill):
        return (-3, _rarity(skill))  # no damage foundation or support interval required
    primary = focus(build, state)
    if build_rules.reasons(skill, build, state, primary):
        return None
    if _conflict(skill, primary):
        return None
    established = state.type_picks.get(primary, 0) >= 2
    owned = family(skill) in state.owned
    if skill.role == SUPPORT and skill.damage_type in (None, primary):
        priority = state.rules.support_priority(skill.name, skill.description)
        # Establish damage first; one counter family is enough for each threat. Normal
        # configured support still works. Never turn every offer into a new utility pick.
        protected = any(state.rules.support_priority(s.name, s.description) == priority
                        for s in state.owned.values() if s.role == SUPPORT) if priority is not None else False
        if (priority is not None and established and state.damage_since_support >= 2
                and not protected):
            return (-2, priority, not owned, _rarity(skill))
    base = _line_score(skill, build, state)
    if base is None:
        return None
    if skill.role == SUPPORT:
        return (0, base[0], state.rules.support_quality(skill.name, skill.description), *base[1:])
    adjustment = state.rules.damage_penalty(skill.description)
    if established and state.rules.has("adaptive_armor"):
        if skill.damage_type == "shuriken" and primary != "shuriken" and not owned:
            return None  # avoid adding more small hits that strengthen the enemy's armor
        if not owned and (_critical(skill) or skill.damage_type is None and re.search(r"\b(?:atk|atq)\b", _text(skill))):
            adjustment -= 1
    value = build_rules.utility(skill, state, primary)
    return (adjustment, *base[:-1], -value, base[-1])


def needs_critical_pick(state, primary):
    return (primary == "fire" and state.type_picks.get("fire", 0) >= 2
            and not any(_critical(skill) for skill in state.owned.values()))


def ranked(skills: list[Skill], build: Build, state: BuildState) -> list[int]:
    state.configure(build)
    scores = [(score, i) for i, skill in enumerate(skills) if (score := _score(skill, build, state)) is not None]
    return [i for _, i in sorted(scores)]


def fallback(skills: list[Skill], build: Build | None = None, state: BuildState | None = None) -> list[int]:
    """A mandatory pick keeps neutral utility ahead of unrelated elements and harmful tradeoffs."""
    if build is None or state is None:
        return sorted(range(len(skills)), key=lambda i: (_rarity(skills[i]), i))
    primary = focus(build, state)
    def score(i: int) -> tuple:
        skill = skills[i]
        blocked = build_rules.reasons(skill, build, state, primary)
        if _conflict(skill, primary) or blocked:
            group = 5
        elif skill.damage_type == primary and primary is not None:
            group = 0
        elif skill.damage_type is None:
            group = (3 if state.context.mode == "dojo" else 1) if skill.role == SUPPORT else 2
        elif build.profile == BURN and skill.damage_type == "shuriken":
            group = 3
        else:
            group = 4
        quality = state.rules.support_quality(skill.name, skill.description) if skill.role == SUPPORT else 0
        return group, len(blocked), quality, family(skill) not in state.owned, _rarity(skill), i
    return sorted(range(len(skills)), key=score)


def choose(skills: list[Skill], build: Build, state: BuildState, can_reroll: bool) -> int | None:
    wanted = ranked(skills, build, state)
    if wanted:
        return wanted[0]
    if can_reroll or not skills:
        return None
    return fallback(skills, build, state)[0]


def selection_order(skills: list[Skill], build: Build, state: BuildState) -> list[int]:
    """All cards for mandatory multi-picks; simulate each choice to maintain a single focus."""
    remaining, selected, progress = list(range(len(skills))), [], deepcopy(state)
    while remaining:
        choice = choose([skills[i] for i in remaining], build, progress, can_reroll=False)
        assert choice is not None, "A nonempty mandatory offer must produce a choice"
        index = remaining.pop(choice)
        selected.append(index)
        progress.take(skills[index], build)
    return selected


def shop_order(skills: list[Skill], build: Build, state: BuildState, can_reroll: bool,
               prices: list[int] | None = None) -> list[int] | None:
    if prices is not None and (len(prices) != len(skills) or any(type(p) is not int or p <= 0 for p in prices)):
        raise ValueError("Invalid skill prices")
    state.configure(build)
    primary = focus(build, state)
    scores = []
    for i, skill in enumerate(skills):
        if re.search(
                r"\b(?:drain|lose|pierde|drena)\w*(?:\s+(?:\d+(?:[.,]\d+)?%?|of|your|tu|de))*\s+(?:hp|health|vida)\b",
                _text(skill)):
            continue
        score = _score(skill, build, state)
        if score is None:
            continue
        if prices is not None:
            # Compare value per coin within the same tactical priority.
            value = max(.1, build_rules.utility(skill, state, primary)) / prices[i]
            score = (score[:2], -value, score)
        scores.append((score, i))
    wanted = [i for _, i in sorted(scores)]
    if can_reroll:
        return wanted or None
    return wanted + shop_utility_order(skills, build, state, excluded=frozenset(wanted))


def shop_utility_order(skills: list[Skill], build: Build, state: BuildState, *,
                       excluded: frozenset[int] = frozenset()) -> list[int]:
    """Neutral purchases eligible for spare coins after the search for core skills."""
    primary = focus(build, state)
    utility = []
    for i, skill in enumerate(skills):
        if (i in excluded or skill.damage_type is not None
                or _conflict(skill, primary) or build_rules.reasons(skill, build, state, primary)):
            continue
        text = _text(skill)
        if re.search(r"[↓⇩]|\b(?:drain|sacrific|lose|pierde|drena)\w*", text):
            continue  # don't introduce a new sacrifice merely to empty the purse
        if skill.role == DAMAGE and re.search(
                r"\b(?:atk|atq|attack|ataque|damage|dmg|dano|crit|execut|ejecut|ultimate|definitiva)\w*", text):
            group = 0
        elif skill.role == SUPPORT and re.search(
                r"\b(?:hp|vida|def|shield|escudo|heal|cura|recover|recuper|lifesteal|robo|reviv|resur|dodge|evas|resist)\w*", text):
            group = 1
        else:
            continue  # incomplete OCR or an unknown effect isn't a reason to spend
        quality = state.rules.support_quality(skill.name, skill.description) if skill.role == SUPPORT else 0
        utility.append(((group, quality, family(skill) not in state.owned, _rarity(skill), i), i))
    return [i for _, i in sorted(utility)]
