"""Account loadout and damage layers used by every combat policy.

Loadouts are user supplied or screen observed, never equipped by this module.
Unknown stats are omitted. Multipliers are estimates only when all inputs exist.
"""

from dataclasses import dataclass, field
import math

from roguebot.skill_data import VERSION, key

MODES = ("campaign", "dojo", "raid", "party", "chaos", "conquest")


@dataclass(frozen=True)
class Loadout:
    hero: str = ""
    hero_stars: int = 0
    weapon: str = ""
    weapon_rarity: str = ""
    companions: tuple[str, ...] = ()
    pets: tuple[str, ...] = ()
    mounts: tuple[str, ...] = ()
    sentinels: tuple[str, ...] = ()
    # Exact permanent skills the account has unlocked; empty means unknown.
    tree_skills: tuple[str, ...] = ()
    # Other equipped items, for example Volt Band. Rarity must be supplied
    # explicitly as "Volt Band:epic" before a rarity-gated proc is assumed.
    equipment: tuple[str, ...] = ()
    stats: tuple[tuple[str, float], ...] = ()
    game_version: str = VERSION
    tree_skills_partial: bool = False

    def __post_init__(self):
        if type(self.tree_skills_partial) is not bool:
            raise ValueError("bad_loadout")
        if type(self.hero_stars) is not int or not 0 <= self.hero_stars <= 10:
            raise ValueError("bad_loadout")
        if any(not isinstance(v, str) for v in (self.hero, self.weapon, self.weapon_rarity, self.game_version)):
            raise ValueError("bad_loadout")
        if self.weapon_rarity not in ("", "common", "rare", "epic", "legendary", "mythic"):
            raise ValueError("bad_loadout")
        for values in (self.companions, self.pets, self.mounts, self.sentinels, self.tree_skills, self.equipment):
            if not isinstance(values, tuple) or any(not isinstance(v, str) for v in values):
                raise ValueError("bad_loadout")
        if any(":" in entry and entry.partition(":")[2] not in ("", "common", "rare", "epic", "legendary", "mythic")
               for entry in self.equipment):
            raise ValueError("bad_loadout")
        for name, value in self.stats:
            if not isinstance(name, str) or type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError("bad_loadout")

    @classmethod
    def from_dict(cls, values: dict):
        if not isinstance(values, dict):
            raise ValueError("bad_loadout")
        fields = cls.__dataclass_fields__
        args = {k: v for k, v in values.items() if k in fields}
        for name in ("companions", "pets", "mounts", "sentinels", "tree_skills", "equipment"):
            if name in args:
                if not isinstance(args[name], (list, tuple)):
                    raise ValueError("bad_loadout")
                args[name] = tuple(args[name])
        if "stats" in args:
            raw = args["stats"]
            if isinstance(raw, dict):
                raw = raw.items()
            try:
                args["stats"] = tuple((str(k), float(v)) for k, v in raw)
            except (TypeError, ValueError):
                raise ValueError("bad_loadout") from None
        return cls(**args)

    def stat(self, name: str) -> float | None:
        return dict(self.stats).get(name)

    @property
    def sources(self) -> frozenset[str]:
        result = {"weapon", "ultimate"}
        # Presence is distinct from frequency. A zero rate disables its feeder.
        for name, stat in (("combo", "combo_rate"), ("counter", "counter_rate"),
                           ("dodge", "dodge_rate"), ("weapon_crit", "crit_rate")):
            value = self.stat(stat)
            if value is None and name == "weapon_crit":
                value = self.stat("weapon_crit_rate")  # old manual loadouts
            if value is None or value > 0:
                result.add(name)
        if self.pets:
            result.add("pet")
        weapon = key(self.weapon)
        # These effects are confirmed on the account's 0.631 weapon/ring screens
        # as well as the earlier reference. Do not opt other rules into 0.631.
        if self.game_version in (VERSION, "0.631"):
            if weapon in ("emberstaff", "infernospire"):
                result.update(("burn", "fire"))
            for entry in self.equipment:
                name, _, rarity = entry.partition(":")
                if key(name) == "blazingband" and rarity in ("rare", "epic", "legendary", "mythic"):
                    result.update(("burn", "fire"))
        if self.game_version == VERSION:
            if weapon in ("katana", "blossomwhisper") and self.weapon_rarity in ("rare", "epic", "legendary", "mythic"):
                result.update(("shuriken", "shuriken_tag", "skill"))
            if weapon in ("stormstaff", "tempestwrath"):
                # Their Ultimate summons targeting variants. A shared Bolt
                # feeder must come from a drafted skill or an explicit source.
                result.update(("bolts", "bolt_random", "lightning", "skill"))
            if weapon in ("glacialhammer", "unforgivingfrost"):
                result.update(("chill", "ice"))
            if weapon in ("plagueblade", "blightmaker"):
                result.add("poison")
            for entry in self.equipment:
                name, _, rarity = entry.partition(":")
                if rarity not in ("epic", "legendary", "mythic"):
                    continue
                item = key(name)
                if item == "ninjaring":
                    result.update(("shuriken_random", "shuriken_tag", "skill"))
                elif item in ("voltband", "paladinsplate"):
                    # Their lightning proc is not the shared Bolt action.
                    result.update(("lightning", "skill"))
                elif item == "ringofthorns":
                    result.update(("cleave", "wound", "skill"))
            if key(self.hero) == "corvus":
                result.add("miasma")
                if self.hero_stars >= 4:
                    result.update(("poison", "wound"))
            if key(self.hero) == "draco":
                result.add("fire")
                if self.hero_stars >= 2:
                    result.add("burn")
        return frozenset(result)

    @property
    def mixed_elements(self) -> bool:
        return any(key(name) == "ultimaniacodex" for name in self.mounts)


@dataclass
class CombatContext:
    mode: str = "campaign"
    hp: float | None = None
    loadout: Loadout = field(default_factory=Loadout)
    # Known enemy properties. Empty means not observed, not proof of absence.
    enemy_tags: frozenset[str] = frozenset()
    expected_rounds: int | None = None
    team_hp: tuple[float, ...] = ()
    team_roles: tuple[str, ...] = ()
    team_heroes: tuple[str, ...] = ()
    recent_hp_loss: float = 0.
    revives_seen: int = 0
    _fight_hp: float | None = None
    _revive_visible: bool = False

    def observe(self, hp: float | None, screen: str) -> None:
        """Use fresh HP only; summarize losses once each fight actually ends."""
        self.hp = hp
        if screen == "revive" and not self._revive_visible:
            self.revives_seen += 1
        if screen != "unknown":
            self._revive_visible = screen == "revive"
        if screen == "fight":
            if self._fight_hp is None and hp is not None:
                self._fight_hp = hp
        elif screen not in ("unknown", "revive") and hp is not None and self._fight_hp is not None:
            self.recent_hp_loss = max(0., self._fight_hp - hp)
            self._fight_hp = None

    @property
    def survival_pressure(self) -> bool:
        if not self.incoming or self.hp is None:
            return False
        return (self.hp <= .4 or self.hp <= .65 and
                (self.revives_seen > 0 or self.recent_hp_loss >= .25
                 or self.recent_hp_loss >= self.hp * .75))

    @property
    def incoming(self) -> bool:
        return self.mode != "dojo"

    @property
    def enemy_is_boss(self) -> bool | None:
        if self.mode in ("dojo", "raid", "conquest"):
            return False
        return True if "boss" in self.enemy_tags else None


def effective_reduction(raw: float) -> float:
    """Raw DR/FDR percentages as fractions, curved once after addition."""
    raw = max(0., raw)
    return min(1., raw, raw / (raw + 1.) + .1)


def resistance_multiplier(resistance: float) -> float:
    return 1. / max(.01, 1. + resistance)


def additive_gain(pool: float, bonus: float) -> float:
    return (1. + pool + bonus) / max(.01, 1. + pool)


def expected_hit(base: float, coefficient: float, *, tags=(), tag_bonuses=None,
                 resistances=None, crit_rate=0., crit_damage=1.5, enemy_def=0.,
                 raw_dr=0., final_dr=0., true_damage=False, enemy_dot=False,
                 damage_boost=0., final_boost=0.) -> float:
    """Known layers only. Lists of tag sources multiply; DoT cannot crit.

    `enemy_dot` means an enemy's tick on the player; player ticks still pay DEF.
    Shields and per-hit procs require a battle simulation and are not fabricated.
    """
    tag_bonuses, resistances = tag_bonuses or {}, resistances or {}
    hit = max(0., base * coefficient)
    for tag in set(tags):
        hit *= math.prod(1. + v for v in tag_bonuses.get(tag, ()))
        hit *= resistance_multiplier(resistances.get(tag, 0.))
    if "status" not in tags:
        hit *= 1. + min(1., max(0., crit_rate)) * max(0., crit_damage - 1.)
    if not true_damage and not enemy_dot:
        hit = max(hit * .1, hit - max(0., enemy_def)) * (1. - effective_reduction(raw_dr))
    if not true_damage:
        hit *= (1. + damage_boost) * (1. + final_boost) * (1. - effective_reduction(final_dr))
    return max(0., hit)
