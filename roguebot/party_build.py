"""Party Expedition roles, kept separate from the elemental combat build."""

import re

from roguebot.build import Build, BuildState, choose
from roguebot.skills import Skill, skill_key
from roguebot.vision import normalize

ROLES = ("striker", "support", "guardian")

# Names and effects transcribed from the event's Skill Codex supplied by the user.
# Damage favors critical scaling / lower aggro; support establishes recurring healing first.
ROLE_SKILLS = {
    "striker": ("Lethality", "Quelling Strikes", "Ultimate Opportunity", "Death Mark", "Mercy Strike",
                "Killer Instinct", "Raging Strikes", "Blood for Blood"),
    "support": ("Combat Medic", "Medica", "Divine Caress", "Blessing", "Motivating Ballad", "Essential Dignity", "Generosity", "Ascend"),
    "guardian": ("Unyielding", "Provoke", "Inspiration", "Resolve", "Thornmail", "Divine Link", "Legacy", "Sacrifice"),
}
_KNOWN = {skill_key(name): (role, rank) for role, names in ROLE_SKILLS.items() for rank, name in enumerate(names)}


def _identity(skill):
    return skill.reference.id if skill.reference else skill_key(skill.name)


def skill_role(skill: Skill) -> str | None:
    entry = _KNOWN.get(_identity(skill))
    return entry[0] if entry else None


def role_order(skills: list[Skill], role: str, state: BuildState | None = None) -> list[int]:
    """Known role skills first; avoid a tank's aggro or a striker's healing penalty on support."""
    if role not in ROLES:
        raise ValueError("bad_party_role")
    def score(i):
        identity = _identity(skills[i])
        rank = _KNOWN[identity][1]
        if state is not None:
            owned = set(state.owned)
            if identity in owned:
                rank += 100  # Party cards have one level; avoid a duplicate draft.
            sustain = {"combatmedic", "medica", "divinecaress", "essentialdignity"}
            if identity == "generosity" and owned.intersection(sustain):
                rank = -1
            if identity == "combatmedic" and any(s.reference and "no_weapon" in s.reference.drawbacks for s in state.owned.values()):
                rank += 50
            if state.context.team_hp and min(state.context.team_hp) <= .35 and identity in sustain:
                rank -= 3
            if identity == "ascend" and ("illumina" in {skill_key(h) for h in state.context.team_heroes} or "ascend" in owned):
                rank += 10
        return rank, i
    return sorted((i for i, skill in enumerate(skills) if skill_role(skill) == role), key=score)


def choose_party_skill(skills: list[Skill], role: str, build: Build, state: BuildState) -> int | None:
    state.configure(build, "party")
    order = role_order(skills, role, state)
    if order:
        return order[0]
    # Elite rooms offer three flat-stat upgrades rather than a new class skill.
    stats = {}
    for i, skill in enumerate(skills):
        text = normalize(skill.name + " " + skill.description)
        if re.search(r"\b(?:atk|atq)(?:up)?\b", text):
            stats[i] = "atk"
        elif re.search(r"\bdef(?:up)?\b", text):
            stats[i] = "def"
        elif re.search(r"\bmax\s*hp", text):
            stats[i] = "hp"
    if len(stats) == len(skills) and stats:
        priority = ("def", "hp", "atk") if role == "guardian" else ("atk", "hp", "def")
        return min(stats, key=lambda i: priority.index(stats[i]))
    if any(skill_role(skill) is not None for skill in skills):
        # Mandatory off-role offer: avoid additional aggro and healing penalties where possible.
        penalties = {"killerinstinct": 3, "bloodforblood": 2, "sacrifice": 3, "ragingstrikes": 2,
                     "divinelink": 2, "provoke": 2, "legacy": 1}
        return min(range(len(skills)), key=lambda i: (penalties.get(_identity(skills[i]), 0),
                   _KNOWN.get(_identity(skills[i]), ("", 99))[1], i))
    return choose(skills, build, state, can_reroll=False)
