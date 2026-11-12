"""Plan new spending from observed levels, using the Theorycraft cost curves."""

from dataclasses import dataclass


# Food per current level in each of the four level brackets, copies per
# ten-level tier, and the three recurring hero bonuses in milestone order.
CURVES = {
    "common": ((10, 13, 15, 18), 5, 3, ("atk", "hp", "def")),
    "great": ((15, 18, 21, 24), 5, 3, ("atk", "def", "hp")),
    "rare": ((30, 30, 30, 30), 4, 4, ("hp", "atk", "def")),
    "epic": ((50, 50, 50, 50), 3, 4, ("hp", "def", "atk")),
    "legendary": ((75, 75, 75, 75), 2, 5, ("def", "atk", "hp")),
    "mythic": ((100, 100, 100, 100), 1, 5, ("def", "hp", "atk")),
}
SKILL_LEVELS = (10, 30, 50, 70, 90)


@dataclass(frozen=True)
class Pet:
    name: str
    rarity: str
    level: int | None
    copies: int | None
    equipped: bool
    food_cost: int | None = None
    copies_cost: int | None = None


@dataclass(frozen=True)
class PetUpgrade:
    name: str
    start: int
    target: int
    food: int
    copies: int
    hp: int
    atk: int
    defense: int
    skills: int

    @property
    def score(self) -> int:
        # Percent bonuses are the main goal. Give equipped skill milestones
        # a small weight since their combat value depends on the pet and mode.
        return self.hp + self.atk + self.defense + self.skills


def level_cost(rarity: str, level: int) -> tuple[int, int]:
    food, copies, _, _ = CURVES[rarity]
    bracket = sum(level > limit for limit in (30, 50, 80))
    return level * food[bracket], copies * ((level - 1) // 10 + 1)


def supported(pet: Pet) -> bool:
    if pet.rarity not in CURVES or type(pet.level) is not int or not 1 <= pet.level <= 100:
        return False
    if type(pet.copies) is not int or pet.copies < 0:
        return False
    if pet.level == 100:
        return True
    food, copies = level_cost(pet.rarity, pet.level)
    return ((pet.food_cost is None or pet.food_cost == food)
            and (pet.copies_cost is None or pet.copies_cost == copies))


def milestones(pet: Pet, budget: int):
    if not supported(pet):
        return
    _, _, bonus, order = CURVES[pet.rarity]
    food = copies = skills = 0
    stats = dict.fromkeys(("hp", "atk", "def"), 0)
    for target in range(pet.level + 1, 101):
        step_food, step_copies = level_cost(pet.rarity, target - 1)
        food += step_food
        copies += step_copies
        if food > budget or copies > pet.copies:
            break
        if target in SKILL_LEVELS:
            if not pet.equipped:
                continue
            skills += 1
        elif target % 5 == 0:
            stats[order[(5, 15, 0).index(target % 20)]] += bonus
        else:
            continue
        yield PetUpgrade(pet.name, pet.level, target, food, copies, stats["hp"],
                         stats["atk"], stats["def"], skills)


def optimize(pets: list[Pet], budget: int) -> tuple[PetUpgrade, ...]:
    """Keep the cheapest path for each score, choosing at most one target per pet."""
    states = {0: (0, ())}
    seen = set()
    for pet in pets:
        if pet.name.casefold() in seen:
            continue
        seen.add(pet.name.casefold())
        options = tuple(milestones(pet, budget))
        next_states = states.copy()
        for score, (food, path) in states.items():
            for option in options:
                cost, gain = food + option.food, score + option.score
                old = next_states.get(gain)
                if cost <= budget and (old is None or cost < old[0]):
                    next_states[gain] = (cost, (*path, option))
        states = next_states
    _, plan = states[max(states)]
    return tuple(sorted(plan, key=lambda step: (-step.score / step.food, step.food, step.name)))
