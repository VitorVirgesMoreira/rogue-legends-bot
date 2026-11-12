"""Versioned facts from Rogue HQ; policy and OCR observations live elsewhere.

Names are identifiers, not trigger rules. In particular, a Bolt action and the
Bolts tag are different. Unknown numbers stay unknown rather than inferred from
the arrows on a card. See docs/guide-improvements.md for provenance and limits.
"""

from dataclasses import dataclass, replace
import re
import unicodedata
from roguebot.game_locale import PORTUGUESE_SKILLS

VERSION = "0.630"
SOURCE = "https://rogue.desoware.com/guide/skills"
LINK_SOURCE = "https://rogue.desoware.com/guide/skill-links"
TRIGGER_SOURCE = "https://rogue.desoware.com/guide/damage-types"
POLICY_VERSION = "2026-11-12"

# These numeric rows were separately checked in the 0.631 Run Skills guide.
# Other 0.630 values remain disabled for 0.631 rather than assuming compatibility.
VERIFIED_631 = frozenset(("fireweapon", "firestarter", "flamestrike", "pyromania",
                          "criticalhitrateup", "comborateup", "counterrateup", "beefcake"))


def key(name: str) -> str:
    value = unicodedata.normalize("NFKD", name).lower()
    return re.sub("[^a-z]", "", value)


def base_name(name: str) -> str:
    return re.sub(r"\s*(?:(?:lv\.?|nv\.?|level|n[ií]vel)\s*\d+)?\s*[+＋]?\s*$", "", name, flags=re.I).strip()


@dataclass(frozen=True)
class SkillRule:
    name: str
    element: str | None = None
    role: str = "damage"
    tags: tuple[str, ...] = ()
    applies: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    watches_actions: tuple[str, ...] = ()
    watches_tags: tuple[str, ...] = ()
    needs_sources: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    element_count: int = 0
    tree_unlock: bool = False
    level2_tree: bool = False
    needs_pets: bool = False
    excludes: tuple[str, ...] = ()
    drawbacks: tuple[str, ...] = ()
    benefits: tuple[str, ...] = ()
    versions: tuple[int, ...] = (10, 11)
    # (stat, values for Lv1, Lv1+, Lv2, Lv2+); None means not established.
    values: tuple[tuple[str, tuple[float | None, ...]], ...] = ()
    independent: bool = False
    low_hp: float | None = None
    ramping: bool = False
    mode: str = "solo"
    version: str = VERSION

    @property
    def id(self) -> str:
        return key(self.name)

    @property
    def nature(self) -> str:
        return "magic" if self.element in ("fire", "ice", "lightning") or self.id == "wizard" else "physical"


RULES: dict[str, SkillRule] = {}
ALIASES: dict[str, str] = {}


def add(names: str, element=None, **facts):
    for name in names.split("|"):
        rule = SkillRule(name, element, **facts)
        RULES[rule.id] = rule
        ALIASES[rule.id] = rule.id


def amend(names: str, **facts):
    for name in names.split("|"):
        rule_id = ALIASES[key(name)]
        RULES[rule_id] = replace(RULES[rule_id], **facts)


add("Absolute Zero|Affliction Affection|Antidote|Assassinate|Basic Attack Damage Up|Beefcake|Better With Friends|Burnout|Combo Mastery|Combo Rate Up|Counter Mastery|Counter Rate Up|Critical Energy|Critical Hit Damage Up|Critical Hit Rate Up|Critical Mastery|Darkside|Darksoul|Dispel|Divine Intervention|Divine Judgement|Dodge Rate Up|Dualcast|Elemental Focus|Endless Fury|Energetic|Energy Nova|Enhanced Combo|Enhanced Counter|Enraged Dodge|Enraged Durability|Enraged Recovery|Enraged Shield|Enraged Strength|Executioner|Exoplating|Eye for an Eye|Feast|Feral Adaptibility|Feral Lethality|Follow-up Strike|Gigantify|Glass Cannon|Hardened|Heavy Strike|Heroism|Holy Blessing|Ice Wall|Lacerate|Last Stand|Leaping Strike|Lifesteal|Master of War|Opening Strike|Panic Shield|Pet Trainer|Purity|Ramping Defense|Ramping Power|Recovery|Relentless Flurry|Resurrection|Riposte|Shield Bash|Shields Up!|Skilled Fighter|Slow And Steady|Souleater|Special Concoction|Spirit Dodge|Steady Growth|Strike Shield|Super Flash|Transfusion|Ultimate Damage Up|Ultimate Mastery|Ultimate Resistance|Ultimate Shield|Undying|Vampiric|Warrior|Weapon Mastery|Wizard")
add("Adrenaline Rush|Berserk|Bloodlust|Burning Rage|Cleave|Cleave Mastery|Deep Cuts|Desperate Cleave|Lash Out|Licking Wounds|Opportunist|Steel Cyclone|Thrill of Battle|Ultimate Cleave|Wound Mastery|Wound Strike", "bleed")
add("Contagion|Corrosion|Crippling Cloud|Deep Venom|Envenom|Fester|Outbreak|Poison Cloud|Poison Mastery|Poison Strike|Serpent Stance|Sneaky Poison|Special Experiment|Toxic Retaliation|Ultimate Poison|Venom Burst", "venom")
add("A Warm Welcome|Blazing Frenzy|Deadly Fireball|Deadly Flames|Fire Lord|Fire Mastery|Fire Wave|Fire Weapon|Firestarter|Flame Strike|Inferno|Meltdown|Meteor|Pyromania|Ultimate Fireball|Ultimate Flame Strike", "fire")
add("Counter Icicle|Deadly Ice|Enervating Cold|Evercold|Flash Frost|Fragile Cold|Freezing Cold|Frost Nova|Frost Strike|Frostbite|Ice Mastery|Ice Spikes|Ice Weapon|Ultimate Icicle", "ice")
add("Charged Battery|Combo Bolt|Electroparalysis|Energizing Current|Flash Storm|High Voltage|Lightning Mastery|Lightning Weapon|Live Wire|Overload|Repeated Bolt|Round Bolt|Static Discharge|Thunder God|Thunderstorm|Ultimate Bolt", "lightning")
add("Critical Throw|Deadly Stars|Death Lotus|Elemental Stars|Energizing Shuriken|Fuma Shuriken|Heal Shuriken|Ninja Dodge|Poison Shuriken|Quick Throw|Shadow Partner|Shuricoins|Shuriken Mastery|Shuriken Throw|Thousand Cuts|Wound Shuriken", "shuriken")
add("Divine Link|Inspiration|Legacy|Provoke|Resolve|Sacrifice|Thornmail|Unyielding|Ascend|Blessing|Combat Medic|Divine Caress|Essential Dignity|Generosity|Medica|Motivating Ballad|Blood for Blood|Death Mark|Killer Instinct|Lethality|Mercy Strike|Quelling Strikes|Raging Strikes|Ultimate Opportunity", mode="party", versions=(10,))

amend("Absolute Zero|Antidote|Beefcake|Dispel|Divine Intervention|Dodge Rate Up|Enraged Dodge|Enraged Durability|Enraged Recovery|Enraged Shield|Exoplating|Feast|Feral Adaptibility|Gigantify|Hardened|Holy Blessing|Ice Wall|Last Stand|Lifesteal|Panic Shield|Purity|Ramping Defense|Recovery|Resurrection|Riposte|Shields Up!|Special Concoction|Steady Growth|Strike Shield|Ultimate Resistance|Ultimate Shield|Undying|Vampiric", role="support")
amend("Divine Link|Inspiration|Legacy|Provoke|Resolve|Sacrifice|Thornmail|Unyielding|Ascend|Blessing|Combat Medic|Divine Caress|Essential Dignity|Generosity|Medica|Motivating Ballad", role="support")
amend("Affliction Affection|Beefcake|Better With Friends|Combo Mastery|Combo Rate Up|Counter Mastery|Counter Rate Up|Critical Hit Rate Up|Darkside|Enraged Strength|Exoplating|Glass Cannon|Hardened|Lifesteal|Recovery|Strike Shield|Warrior|Wizard|Cleave Mastery|Licking Wounds|Opportunist|Wound Strike|Outbreak|Poison Cloud|Poison Strike|Fire Weapon|Firestarter|Pyromania|Fragile Cold|Ice Spikes|Ice Weapon|Energizing Current|High Voltage|Lightning Weapon|Live Wire|Energizing Shuriken|Fuma Shuriken|Shuriken Throw|Slow And Steady", versions=(10, 11, 20, 21))
amend("Flame Strike|Deadly Stars", versions=(10, 20))
amend("Freezing Cold", versions=(10, 20, 21))
amend("Absolute Zero|Antidote|Critical Energy|Elemental Focus|Enhanced Combo|Enhanced Counter|Feast|Follow-up Strike|Gigantify|Panic Shield|Pet Trainer|Purity|Riposte|Shield Bash|Skilled Fighter|Steady Growth|Vampiric|Weapon Mastery|Wizard|Adrenaline Rush|Burning Rage|Deep Cuts|Desperate Cleave|Corrosion|Serpent Stance|Toxic Retaliation|Venom Burst|A Warm Welcome|Blazing Frenzy|Fire Lord|Ultimate Flame Strike|Deadly Ice|Evercold|Flash Frost|Frostbite|Combo Bolt|Electroparalysis|Overload|Static Discharge|Critical Throw|Ninja Dodge|Shuricoins|Thousand Cuts", tree_unlock=True)
amend("Absolute Zero|Wizard", tree_unlock=False)
amend("Enraged Durability", tree_unlock=True)
amend("Affliction Affection|Beefcake|Better With Friends|Combo Mastery|Combo Rate Up|Counter Mastery|Counter Rate Up|Critical Hit Rate Up|Darkside|Enraged Strength|Exoplating|Glass Cannon|Hardened|Lifesteal|Recovery|Slow And Steady|Strike Shield|Warrior|Wizard|Cleave Mastery|Licking Wounds|Opportunist|Wound Strike|Outbreak|Poison Cloud|Poison Strike|Fire Weapon|Firestarter|Flame Strike|Pyromania|Fragile Cold|Freezing Cold|Ice Spikes|Ice Weapon|Energizing Current|High Voltage|Lightning Weapon|Live Wire|Deadly Stars|Energizing Shuriken|Fuma Shuriken|Shuriken Throw", level2_tree=True)
amend("Absolute Zero|Assassinate|Darksoul|Dispel|Divine Intervention|Divine Judgement|Dualcast|Elemental Focus|Endless Fury|Energy Nova|Executioner|Eye for an Eye|Feast|Feral Adaptibility|Feral Lethality|Frost Nova|Gigantify|Heavy Strike|Lacerate|Leaping Strike|Master of War|Panic Shield|Pet Trainer|Purity|Ramping Defense|Ramping Power|Relentless Flurry|Resurrection|Shield Bash|Skilled Fighter|Souleater|Super Flash|Undying|Vampiric|Weapon Mastery|Adrenaline Rush|Berserk|Burning Rage|Thrill of Battle|Contagion|Crippling Cloud|Deep Venom|Envenom|Fester|Serpent Stance|Venom Burst|Blazing Frenzy|Deadly Flames|Fire Lord|Inferno|Meltdown|Meteor|Evercold|Frostbite|Charged Battery|Electroparalysis|Overload|Static Discharge|Thunder God|Thunderstorm|Death Lotus|Elemental Stars|Quick Throw|Shadow Partner|Shuricoins|Thousand Cuts", versions=(10,))
amend("Assassinate|Energy Nova|Heavy Strike|Lacerate|Leaping Strike", versions=(10, 11))
amend("Last Stand", versions=(10, 21))
amend("Better With Friends|Special Experiment", needs_pets=True)
amend("Berserk|Steel Cyclone|Thrill of Battle", requires=("cleave",))
amend("Meteor", requires=("flamestrike",))
for element in ("fire", "ice", "lightning", "venom", "bleed", "shuriken"):
    # Element gates are pool facts; offered cards remain authoritative when the
    # client's Lv2 relationships differ from its documented intent.
    gated = {
        "fire": "Blazing Frenzy|Deadly Flames|Fire Lord|Fire Mastery|Firestarter|Flame Strike|Inferno|Meltdown",
        "ice": "Enervating Cold|Evercold|Freezing Cold|Frost Nova|Frost Strike|Frostbite|Ice Mastery|Ice Spikes",
        "lightning": "Charged Battery|Energizing Current|High Voltage|Lightning Mastery|Overload|Repeated Bolt|Static Discharge|Thunder God|Thunderstorm",
        "venom": "Contagion|Crippling Cloud|Deep Venom|Envenom|Fester|Outbreak|Poison Mastery|Venom Burst",
        "bleed": "Adrenaline Rush|Berserk|Bloodlust|Burning Rage|Cleave Mastery|Licking Wounds|Steel Cyclone|Thrill of Battle|Wound Mastery",
        "shuriken": "Deadly Stars|Death Lotus|Elemental Stars|Fuma Shuriken|Quick Throw|Shadow Partner|Shuricoins|Shuriken Mastery|Thousand Cuts",
    }[element]
    amend(gated, element_count=2)
amend("Elemental Stars|Frostbite|Overload|Shuricoins", element_count=1)

for left, right in (("Adrenaline Rush", "Burning Rage"), ("Beefcake", "Glass Cannon"),
                    ("Charged Battery", "High Voltage"), ("Cleave Mastery", "Wound Mastery"),
                    ("Deadly Stars", "Heal Shuriken"), ("Deadly Stars", "Poison Shuriken"),
                    ("Deadly Stars", "Wound Shuriken"), ("Warrior", "Wizard")):
    for name, other in ((left, right), (right, left)):
        rule = RULES[key(name)]
        amend(name, excludes=rule.excludes + (key(other),))

# What a card supplies versus what has to supply it. A counter of attacks is not
# a self-sufficient source just because its description begins with "Every N".
for name, action, trigger in (
    ("Fire Weapon", "fireball", "weapon"), ("Ice Weapon", "icicle", "weapon"),
    ("Lightning Weapon", "bolt", "weapon"), ("Cleave", "cleave", "weapon"),
    ("Deadly Fireball", "fireball", "weapon_crit"), ("Critical Throw", "shuriken", "weapon_crit"),
    ("Counter Icicle", "icicle", "counter"), ("Combo Bolt", "bolt", "combo"),
    ("Ultimate Fireball", "fireball", "ultimate"), ("Ultimate Icicle", "icicle", "ultimate"),
    ("Ultimate Bolt", "bolt", "ultimate"), ("Ultimate Cleave", "cleave", "ultimate"),
    ("Ultimate Flame Strike", "flamestrike", "ultimate"), ("Death Lotus", "shuriken_random", "ultimate"),
    ("Live Wire", "bolt", "incoming"), ("Ice Spikes", "icicle", "shield_incoming"),
    ("Ninja Dodge", "shuriken", "dodge"), ("Desperate Cleave", "cleave", "low_hp"),
    ("Lash Out", "cleave", "low_hp"),
):
    amend(name, produces=(action,), watches_tags=(trigger,), needs_sources=(trigger,), tags=("skill",))
for name, action in (("Fire Wave", "firewave"), ("Round Bolt", "bolt"), ("Flash Frost", "icicle"),
                     ("Shuriken Throw", "shuriken"), ("Heal Shuriken", "shuriken"),
                     ("Poison Shuriken", "shuriken"), ("Wound Shuriken", "shuriken"),
                     ("Energizing Shuriken", "shuriken")):
    amend(name, produces=(action,), independent=True, tags=("skill",))
for names, source in (("Firestarter|Flame Strike", "fireball"), ("Meteor", "flamestrike"),
                      ("Frost Nova|Frost Strike|Enervating Cold|Deadly Ice", "icicle"),
                      ("High Voltage|Repeated Bolt|Thunderstorm", "bolt"),
                      ("Steel Cyclone", "cleave"), ("Fuma Shuriken", "shuriken")):
    amend(names, watches_actions=(source,), needs_sources=(source,))
amend("Firestarter", produces=("firewave",), tags=("skill",))
amend("Flame Strike", produces=("flamestrike",), tags=("skill",))
amend("Meteor", produces=("meteor",), tags=("skill",), versions=(10,))
amend("Repeated Bolt", produces=("bolt",))
amend("Frost Strike|Deadly Ice", produces=("froststrike",), tags=("skill",))
amend("Frost Nova", produces=("frostnova",), applies=("freeze",), tags=("skill",), versions=(10,))
amend("Steel Cyclone", produces=("steelcyclone",), tags=("skill",))
amend("Fuma Shuriken", produces=("fuma",), tags=("skill",))
amend("Energizing Current|Overload|Static Discharge", watches_tags=("bolts",), needs_sources=("bolts",))
amend("Shadow Partner|Quick Throw|Shuricoins|Thousand Cuts|Elemental Stars", watches_tags=("shuriken",), needs_sources=("shuriken_tag",))
amend("Elemental Stars", benefits=("elemental_weapon",))
amend("Inferno|Meltdown|Blazing Frenzy|Pyromania", needs_sources=("burn",))
amend("Wound Mastery|Bloodlust|Opportunist|Licking Wounds|Adrenaline Rush", needs_sources=("wound",))
amend("Poison Mastery|Deep Venom|Fester|Contagion|Corrosion|Venom Burst", needs_sources=("poison",))
amend("Fragile Cold|Freezing Cold|Frostbite", needs_sources=("chill",))
amend("Wound Strike|Deep Cuts|Cleave", applies=("wound",))
amend("Poison Strike|Poison Cloud|Special Experiment|Sneaky Poison|Toxic Retaliation|Ultimate Poison|Outbreak|Envenom|Serpent Stance", applies=("poison",))
amend("Fire Weapon|Fire Wave|Deadly Fireball|Ultimate Fireball|Ultimate Flame Strike|A Warm Welcome", applies=("burn",))
amend("Ice Weapon|Flash Frost|Counter Icicle|Ultimate Icicle|Ice Spikes", applies=("chill",))
amend("Poison Cloud", independent=True)
amend("Special Experiment", needs_sources=("pet",))
amend("Wound Strike|Poison Strike|Deep Cuts", needs_sources=("weapon",))
amend("Eye for an Eye", needs_sources=("incoming",), versions=(10,))
amend("Ultimate Poison", needs_sources=("ultimate",))
amend("Toxic Retaliation", needs_sources=("incoming",))
amend("Sneaky Poison", needs_sources=("dodge",))
amend("Slow And Steady", benefits=("dot",))
amend("Critical Hit Rate Up|Critical Mastery|Master of War", benefits=("crit_rate",))
amend("Critical Hit Damage Up", benefits=("crit_damage",))
amend("Critical Mastery", benefits=("crit_rate", "crit_damage"), drawbacks=("less_noncrit",))
amend("Divine Judgement", element="lightning", produces=("bolt_random",), tags=("skill",), versions=(10,))
amend("Thunder God", produces=("bolt",), independent=True, drawbacks=("no_weapon",), versions=(10,))
amend("Pet Trainer", drawbacks=("no_weapon",), benefits=("pet",), versions=(10,))
amend("Skilled Fighter", drawbacks=("less_combo_counter",), benefits=("skill",), versions=(10,))
amend("Vampiric", drawbacks=("less_magic",), benefits=("lifesteal",), versions=(10,))
amend("Warrior", drawbacks=("less_magic",), benefits=("weapon",))
amend("Wizard", drawbacks=("less_physical",), benefits=("skill",))
amend("Cleave Mastery", drawbacks=("no_wound_from_cleave",), benefits=("cleave",))
amend("Deadly Stars", drawbacks=("no_shuriken_effects",), benefits=("shuriken",))
amend("Burning Rage", drawbacks=("no_ultimate",), benefits=("cleave",), versions=(10,))
amend("Charged Battery", drawbacks=("no_bolt_damage",), needs_sources=("bolts",), benefits=("ultimate",), versions=(10,))
amend("Darkside", drawbacks=("hp_drain",))
amend("Glass Cannon", drawbacks=("less_hp",))
amend("Beefcake", drawbacks=("less_atk",))
amend("Exoplating", drawbacks=("less_hp",), benefits=("shield",))
amend("Elemental Focus", benefits=("single_element",), versions=(10,))
amend("Better With Friends", benefits=("pet",))
amend("Shield Bash", needs_sources=("shield",), benefits=("shield",), versions=(10,))
amend("Weapon Mastery|Basic Attack Damage Up", benefits=("weapon",))
amend("Ultimate Damage Up|Dualcast|Energetic|Ultimate Mastery|Critical Energy", benefits=("ultimate",))
amend("Combo Rate Up|Combo Mastery|Enhanced Combo|Follow-up Strike|Relentless Flurry", benefits=("combo",))
amend("Counter Rate Up|Counter Mastery|Enhanced Counter", benefits=("counter",))
amend("Enraged Strength|Enraged Dodge|Enraged Durability|Enraged Recovery|Enraged Shield|Burnout|Desperate Cleave|Lash Out", low_hp=.4)
amend("Darksoul|Berserk|Thrill of Battle|Undying", low_hp=.5)
amend("Absolute Zero", low_hp=.3, benefits=("immunity", "heal"), versions=(10,))
amend("Divine Intervention", low_hp=.35, benefits=("shield", "ultimate"), versions=(10,))
amend("Enraged Shield|Strike Shield|Ultimate Shield|Panic Shield|Holy Blessing", benefits=("shield",))
amend("Recovery|Enraged Recovery|Lifesteal|Undying|Special Concoction|Transfusion|Licking Wounds|Thrill of Battle|Fire Lord", benefits=("heal",))
amend("Hardened|Enraged Durability|Enhanced Counter|Shields Up!", benefits=("dr",))
amend("Antidote", benefits=("status_resistance",))
amend("Ice Wall|Riposte", benefits=("weapon_skill_resistance",))
amend("Dispel", benefits=("anti_heal", "anti_shield"), versions=(10,))
amend("Beefcake|Steady Growth|Endless Fury|Feast|Souleater|Gigantify", benefits=("max_hp",))
amend("Dodge Rate Up|Enraged Dodge", benefits=("dodge",))
amend("Purity", benefits=("cleanse",), versions=(10,))
amend("Resurrection", benefits=("survival",), versions=(10,))
amend("Last Stand", benefits=("survival",), versions=(10, 21))
amend("Ramping Power|Ramping Defense|Combo Mastery|Counter Mastery|Spirit Dodge|Evercold|Blazing Frenzy|Steady Growth|Endless Fury|Enhanced Combo|Enhanced Counter", ramping=True)
amend("Feast|Souleater|Feral Adaptibility|Feral Lethality", needs_sources=("kills",), ramping=True, versions=(10,))

for name, stat, values in (
    ("Critical Hit Rate Up", "crit_rate", (None, None, .15, .25)),
    ("Combo Rate Up", "combo_rate", (None, None, .15, .30)),
    ("Counter Rate Up", "counter_rate", (None, None, .15, .30)),
    ("Hardened", "dr", (None, None, .15, .30)),
    ("Slow And Steady", "status_damage", (None, None, .40, .60)),
    ("Pyromania", "vs_burn", (None, None, .25, .40)),
    ("Opportunist", "vs_wound", (None, None, .25, .50)),
    ("Beefcake", "max_hp", (None, None, .55, .75)),
    ("Glass Cannon", "atk", (None, None, .55, .75)),
    ("Fire Weapon", "proc_chance", (None, None, .60, .80)),
    ("Ice Weapon", "proc_chance", (None, None, .75, 1.0)),
    ("Recovery", "proc_chance", (None, None, .50, .80)),
    ("Firestarter", "proc_chance", (None, None, .75, .75)),
    ("Flame Strike", "proc_chance", (None, None, .70, None)),
    ("High Voltage", "lightning_damage", (.08, .12, .12, .15)),
    ("Antidote", "status_resistance", (1.0, 3.0, None, None)),
    ("Dispel", "enemy_heal_shield_cut", (.5, None, None, None)),
):
    amend(name, values=((stat, values),))

# 0.631's Firestarter upgrades its number of waves, not its proc probability.
amend("Firestarter", values=RULES[key("Firestarter")].values +
      (("proc_count", (None, None, 2., 3.)),))

# Curated translations observed in this project's captures. Fuzzy matching is
# limited to these identifiers; it never rewrites a user's manually reviewed tag.
TRANSLATIONS = {
    "Arma de Fuego": "Fire Weapon", "Arma de Hielo": "Ice Weapon", "Arma de Rayo": "Lightning Weapon",
    "Enfoque Elemental": "Elemental Focus", "Estrellas Elementales": "Elemental Stars",
    "Shuriken Fuma": "Fuma Shuriken", "Shuriken Curativo": "Heal Shuriken",
    "Carámbano de Contraataque": "Counter Icicle", "Descarga Definitiva": "Ultimate Bolt",
    "Golpe Venenoso": "Poison Strike", "Lento y Seguro": "Slow And Steady",
    "Macizo": "Beefcake", "Mago": "Wizard", "Guerrero": "Warrior", "Vampírico": "Vampiric",
    "Disipar": "Dispel", "Dissipar": "Dispel", "Fuerza Enfurecida": "Enraged Strength",
    "Evasión Enfurecida": "Enraged Dodge", "Escudo Enfurecido": "Enraged Shield",
    "Defensa Creciente": "Ramping Defense", "Lanzamiento Doble": "Dualcast",
    "Feral Adaptability": "Feral Adaptibility", "Crit Up": "Critical Hit Rate Up",
}
ALIASES.update({key(alias): key(name) for alias, name in TRANSLATIONS.items()})
ALIASES.update({key(alias): key(name) for alias, name in PORTUGUESE_SKILLS.items()})
for name in ("Assassinate", "Energy Nova", "Heavy Strike", "Lacerate", "Leaping Strike"):
    for suffix in (" 2", " 3"):
        ALIASES[key(name + suffix)] = key(name)


def rule_for(name: str) -> SkillRule | None:
    rule_id = ALIASES.get(key(base_name(name)))
    return RULES.get(rule_id) if rule_id else None


def card_version(name: str, description: str = "") -> int | None:
    """Only explicit level/+ evidence; rarity does not tell us the skill level."""
    match = re.search(r"\b(?:lv\.?|nv\.?|level|n[ií]vel)\s*([12])\s*([+＋]?)", name, re.I)
    if match:
        return int(match[1]) * 10 + bool(match[2] or re.search(r"[+＋]\s*$", name))
    return 11 if re.search(r"[+＋]\s*$", name) else None


def numeric_values(skill, game_version: str) -> dict[str, float]:
    """Absolute card values, never an upgrade delta or guessed arrow strength."""
    spec = skill.reference
    if (spec is None or skill.version not in (10, 11, 20, 21)
            or game_version != VERSION and not (game_version == "0.631" and spec.id in VERIFIED_631)):
        return {}
    index = (10, 11, 20, 21).index(skill.version)
    return {stat: values[index] for stat, values in spec.values if values[index] is not None
            and (stat != "proc_count" or game_version == "0.631")}
