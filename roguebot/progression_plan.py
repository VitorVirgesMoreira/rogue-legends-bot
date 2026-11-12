"""Read-only progression advice backed by the guide snapshot, never auto-spending."""

from dataclasses import dataclass

from roguebot.skill_data import VERSION, RULES, key

GLOBAL_MILESTONES = (30, 60, 90, 140, 180, 200)
FEATURES = {"tower": 3, "pets": 4, "arena": 5, "artifacts": 5, "dive": 6, "guild": 7,
            "heroes": 7, "party": 10, "elite": 11, "hero_synergy": 13, "album": 14,
            "dojo": 18, "runes": 21, "auto_roll": 25, "pet_build": 35, "awakening": 40}
ELITE_FEATURES = {"adventure_tree": 5, "specialization_tree": 11}
AWAKENING = dict(zip(
    ("Plague Blade", "Katana", "Vampiric Edge", "Radiant Hammer", "Ember Staff", "Storm Staff", "Glacial Hammer",
     "Paladin's Plate", "Druid's Coat", "Dragon Plate", "Frost Loop", "Blazing Band", "Ring of Thorns",
     "Charm of Elements", "Angel's Grace", "Voodoo Doll"),
    ("Blightmaker", "Blossom Whisper", "Crimson Hunger", "Holy Justice", "Inferno Spire", "Tempest Wrath", "Unforgiving Frost",
     "Holy Vanguard", "Nature's Embrace", "Primordial Plate", "Arctic Halo", "Molten Halo", "Wicked Briar",
     "Elemental Nexus", "Heaven's Favor", "Malice Effigy")))


@dataclass(frozen=True)
class Recommendation:
    category: str
    target: str
    reason: str
    costs: tuple[tuple[str, int], ...] = ()
    affordable: bool | None = None
    version: str = VERSION
    source: str = "https://rogue.desoware.com/guides"


def affordable(costs, resources):
    if any(currency not in resources for currency, _ in costs):
        return None
    return all(resources[currency] >= amount for currency, amount in costs)


def recommend(build, *, chapter=None, elite=None, world=1, hero_levels=None, resources=None):
    """Known gates plus the account's loadout; missing balances stay unknown."""
    resources, hero_levels = resources or {}, hero_levels or {}
    rows = []
    if chapter is not None:
        next_features = [(gate, feature) for feature, gate in FEATURES.items() if gate > chapter]
        if next_features:
            gate, feature = min(next_features)
            rows.append(Recommendation("unlock", f"{feature} · {gate}", f"Clear chapter {gate}; confirm the feature on screen.",
                                       source="https://rogue.desoware.com/guide/unlocks"))
    if elite is not None:
        for feature, gate in ELITE_FEATURES.items():
            if elite < gate:
                rows.append(Recommendation("unlock", f"{feature} · Elite {gate}", "Permanent tree unlocked by elite progress.",
                                           source="https://rogue.desoware.com/guide/unlocks"))
    for hero, level in hero_levels.items():
        next_level = next((n for n in GLOBAL_MILESTONES if level < n), None)
        if next_level:
            rows.append(Recommendation("hero", f"{hero} Lv.{next_level}", "Next global stat milestone, including benched heroes.",
                                       source="https://rogue.desoware.com/guide/heroes"))
    primary = "fire" if build.profile in ("burn", "burn_dot") else build.profile
    unlocked = {key(name) for name in build.loadout.tree_skills}
    if build.loadout.tree_skills and not build.loadout.tree_skills_partial:
        for rule in RULES.values():
            if rule.tree_unlock and rule.element == primary and rule.id not in unlocked:
                rows.append(Recommendation("skill_tree", rule.name, "Unlock a skill that supports the selected damage line.",
                                           source="https://rogue.desoware.com/guide/skill-links"))
    awakening = next(((source, target) for source, target in AWAKENING.items() if key(source) == key(build.loadout.weapon)), None)
    if awakening and chapter is not None and chapter >= 40 and build.loadout.weapon_rarity in ("legendary", "mythic"):
        costs = (("awakening_crystals", 60), ("iron_bars", 200), ("chromatic_prisms", 1))
        rows.append(Recommendation("awakening", awakening[1], "Fixed awakening pair; verify changed triggers before committing.",
                                   costs, affordable(costs, resources), source="https://rogue.desoware.com/guide/equipment-awakening"))
    if primary in ("fire", "ice", "lightning") and chapter is not None and chapter >= 21:
        rows.append(Recommendation("runes", primary + " damage", "Matching tag multipliers compound; unique runes must remain unique.",
                                   source="https://rogue.desoware.com/guide/runes"))
    if chapter is not None and chapter >= 35:
        costs = (("spirit_bones", 100),)
        rows.append(Recommendation("pet_build", "Build level", "A roll advances the level; lock costs recur on every roll.",
                                   costs, affordable(costs, resources), source="https://rogue.desoware.com/guide/pet-build"))
    loadout = build.loadout
    if loadout.weapon:
        rows.append(Recommendation("gear", loadout.weapon, "Preserve awakening/merge materials; compare the next tier before merging.",
                                   source="https://rogue.desoware.com/guide/gear"))
    if loadout.hero:
        rows.append(Recommendation("companions", loadout.hero, "Up to three companions lend their own documented effects; check hero stars and source tags.",
                                   source="https://rogue.desoware.com/guide/companions"))
    for name in loadout.mounts:
        rows.append(Recommendation("mounts", name, "Enhancement and Mastery use shared resources; prioritize the equipped damage or survival line.",
                                   source="https://rogue.desoware.com/guide/mounts"))
    for name in loadout.sentinels:
        rows.append(Recommendation("sentinels", name, "Check the equipped sentinel's two skill lines before spending the shared enhancement resources.",
                                   source="https://rogue.desoware.com/guide/sentinels"))
    if chapter is not None and chapter >= 5:
        rows.append(Recommendation("artifacts", primary, "Compare set bonuses and damage tags for this build; a boss bonus does not apply in Dojo or raid.",
                                   source="https://rogue.desoware.com/guide/artifacts"))
    if build.loadout.game_version != VERSION:
        rows.insert(0, Recommendation("version", build.loadout.game_version, "The reference snapshot targets 0.630; verify retuned values."))
    return rows


def pet_roll_cost(locked_slots: int):
    if type(locked_slots) is not int or not 0 <= locked_slots <= 5:
        raise ValueError("Invalid locked slots")
    return {"spirit_bones": 100, "memory_stones": locked_slots}


def pet_build_level(rolls: int) -> tuple[int, int]:
    if type(rolls) is not int or rolls < 0:
        raise ValueError("Invalid roll count")
    level = sum(rolls >= threshold for threshold in (0, 10, 30, 100, 200, 350, 650))
    return level, 5 if level >= 6 else 4 if level >= 3 else 3
