"""Read the actual elite modifier cards; retain unknown modifiers instead of guessing effects."""

from dataclasses import dataclass
import re

import cv2

from roguebot import labels
from roguebot.vision import Text, matches, normalize


@dataclass(frozen=True)
class Modifier:
    name: str
    description: str


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", normalize(name))


# These effects come from the game's preview cards, not the chapter number. Later chapters
# reuse names with different combinations; an unknown card must not invent a new strategy.
_EFFECTS = {
    "inflated prices": "expensive_shop",
    "no time to rest": "rest_disabled",
    "no time to study": "training_disabled",
    "prison lockdown": "jail_tiles",
    "narrow minded": "fewer_choices",
    "vampiric monsters": "enemy_healing",
    "anti-heal": "reduced_healing",
    "adaptive armor": "adaptive_armor",
    "weakpoints": "enemy_critical",
    "unkillable": "enemy_shields",
    "hard shell": "first_round_armor",
    "berserk enemies": "ramping_attack",
    "rising omen": "fifth_round_attack",
    "stronger monsters": "stronger_enemies",
    "enemies enraged": "ramping_attack",
    "enraged enemies": "ramping_attack",
    "enemigos enfurecidos": "ramping_attack",
    "everything burns": "burning",
    "todo arde": "burning",
    "precos inflacionados": "expensive_shop", "sem tempo para descansar": "rest_disabled",
    "sem tempo para estudar": "training_disabled", "bloqueio da prisao": "jail_tiles",
    "mente fechada": "fewer_choices", "monstros vampiricos": "enemy_healing",
    "anticura": "reduced_healing", "anti-cura": "reduced_healing", "armadura adaptativa": "adaptive_armor",
    "pontos fracos": "enemy_critical", "imortal": "enemy_shields", "casca dura": "first_round_armor",
    "inimigos enfurecidos": "ramping_attack", "pressagio crescente": "fifth_round_attack",
    "monstros mais fortes": "stronger_enemies", "tudo queima": "burning",
}
_EFFECTS = {_name_key(name): effect for name, effect in _EFFECTS.items()}


@dataclass(frozen=True)
class ModifierRules:
    effects: frozenset[str] = frozenset()
    unknown: tuple[str, ...] = ()

    def has(self, *effects: str) -> bool:
        return bool(self.effects.intersection(effects))

    @classmethod
    def read(cls, entries: tuple[Modifier, ...]):
        effects, unknown = set(), []
        for entry in entries:
            effect = _EFFECTS.get(_name_key(entry.name))
            if effect:
                effects.add(effect)
            else:
                unknown.append(entry.name)
        return cls(frozenset(effects), tuple(unknown))

    def support_priority(self, name: str, description: str) -> int | None:
        """A specific counter, then protection/sustain; unrelated utility stays optional."""
        text = normalize(f"{name} {description}")
        enemy_counter = (bool(re.fullmatch(r"(?:dispel|disipar|dissipar)(?:\s*(?:lv\.?|level|nivel)\s*\d+)?", normalize(name)))
                         or bool(re.search(r"\b(?:enemy|enemig|inimig)", text))
                         and bool(re.search(r"\b(?:heal|shield|cura|escudo)", text))
                         and bool(re.search(r"\b(?:less effective|menos efectiv|menos efetiv)", text)))
        if self.has("enemy_healing", "enemy_shields") and enemy_counter:
            return 0
        protection = bool(re.search(r"\b(?:shield|escudo|def\b|damage reduction|dmg reduction|reduccion de dano|reducao de dano|esquiva|dodge|evasion|max\s*hp|hp\s*max)", text))
        healing = bool(re.search(r"\b(?:heal|recover|restore|lifesteal|cura|recuper|restaura|robo de vida)", text))
        # Dispel affects the enemy's shields and healing; it isn't protection or self healing.
        if not enemy_counter:
            if protection and self.has("reduced_healing", "enemy_critical", "burning", "rest_disabled"):
                return 1
            if healing and self.has("rest_disabled", "burning") and not self.has("reduced_healing"):
                return 1
        return None

    def support_quality(self, name: str, description: str) -> int:
        text = normalize(f"{name} {description}")
        healing = bool(re.search(r"\b(?:heal|recover|restore|lifesteal|cura|recuper|restaura|robo de vida)", text))
        protection = bool(re.search(r"\b(?:shield|escudo|def\b|damage reduction|dmg reduction|max\s*hp|hp\s*max)", text))
        return int(self.has("reduced_healing") and healing and not protection)

    def damage_penalty(self, description: str) -> int:
        text = normalize(description)
        opening = bool(re.search(r"\b(?:at the start of combat|start (?:combat|with a full)|al inicio del combate)", text))
        slow = bool(re.search(r"\b(?:every|cada)\s+(?:[3-9]|[1-9]\d+)\s+(?:turn|round|turno|ronda)|max\s+(?:[5-9]|[1-9]\d+)\s+stacks", text))
        return int((self.has("first_round_armor") and opening)
                   or (self.has("ramping_attack", "fifth_round_attack") and slow))


def parse_modifiers(img, texts: list[Text]) -> tuple[Modifier, ...] | None:
    title = next((t for t in texts if matches(t, labels.LEVEL_MODIFIERS, exact=True)
                  and abs(t.center[0]-720) < 180 and 500 < t.center[1] < 1100), None)
    if title is None:
        return None
    bottom = min((t.center[1] for t in texts if t.center[1] > title.center[1]
                  and abs(t.center[0]-720) < 200 and any(matches(t, label, exact=True)
                  for label in (labels.START_NORMAL, labels.CONTINUE))), default=1900)
    lines = sorted((t for t in texts if 500 <= t.center[0] < 1150
                    and title.center[1]+60 < t.center[1] < bottom-30), key=lambda t: (t.center[1], t.center[0]))
    entries, name, description = [], [], []
    previous_y = None
    for line in lines:
        patch = img[max(0,line.y1):line.y2+1, max(0,line.x1):line.x2+1]
        if not patch.size:
            continue
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        purple = ((hsv[...,0] >= 120) & (hsv[...,0] <= 170) & (hsv[...,1] > 60) & (hsv[...,2] > 140)).mean() > .08
        if purple:
            if name and (description or previous_y is not None and line.center[1]-previous_y > 65):
                entries.append(Modifier(" ".join(name), " ".join(description)))
                name, description = [], []
            name.append(line.text)
        elif name:
            description.append(line.text)
        previous_y = line.center[1]
    if name:
        entries.append(Modifier(" ".join(name), " ".join(description)))
    return tuple(entries)
