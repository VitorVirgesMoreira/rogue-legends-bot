"""Named event policies. Reading a title never authorizes an unreadable option."""

from dataclasses import dataclass
import re

from roguebot import config, labels
from roguebot.vision import Text, matches, normalize


EVENT_NAMES = {
    "rest": ("a moment to rest", "a moment of rest", "un momento de descanso", "un momento para descanso", "um momento de descanso", "um momento para descansar"),
    "potion": ("potion maker's hut", "potion maker", "potion makers hut", "cabana do alquimista", "cabana do fabricante de pocoes"),
    "fairy": ("generous fairy", "fada generosa"),
    "healing_spring": ("healing spring", "fonte de cura"),
    "cursed_fountain": ("the cursed fountain", "cursed fountain", "fonte amaldicoada", "fuente maldita"),
    "altar": ("altar of greed", "altar da ganancia", "altar de la codicia"),
    "spoils": ("abandoned spoils cart", "abandoned spoils", "carro de botin abandonado", "saque abandonado",
               "carro de saque abandonado", "carrinho de saque abandonado"),
    "might": ("test of might", "teste de forca", "prueba de fuerza"),
    "knowledge": ("forbidden knowledge", "conhecimento proibido", "conocimiento prohibido"),
    "devil": ("deal with devil", "deal with the devil", "pacto com o diabo", "acordo com o diabo", "trato con el diablo"),
}
CONSERVATIVE = {"altar", "spoils", "might", "knowledge", "devil"}
PREMIUM_CURRENCY = re.compile(r"\b(?:gems?|diamonds?|gemas?|diamantes?)\b")
_FOUNTAIN_TRADE = re.compile(
    r"(?:drink|beber|tomar)\s+\+\s*(\d+(?:[.,]\d+)?)\s*%\s*(?:atk|atq|attack|ataque)"
    r"\s*[-−]\s*(\d+(?:[.,]\d+)?)\s*%\s*"
    r"(?:max(?:imum)?\s*(?:hp|health)|(?:hp|pv|vida)\s*max(?:im[ao])?)"
)


def event_kind(title: str) -> str | None:
    title = normalize(title)
    return next((kind for kind, names in EVENT_NAMES.items() if title in names), None)


def event_effect(text: str) -> str | None:
    """Only positive effects; a cost mentioning HP/ATK is not a reward."""
    text = normalize(text)
    if re.search(r"\b(?:lose|loss|sacrif\w*|cost\w*|custa\w*|pay|paga\w*|pierde\w*|perde\w*|reduce\w*|reduz\w*)\b|[-−]\s*\d", text):
        return None
    compact = re.sub(r"[^a-z]", "", text)
    if any(word in compact for word in ("maxhp", "hpmax", "maximumhp", "maxhealth", "maximumhealth", "vidamax")):
        return "max_hp"
    if re.search(r"\b(?:upgrad|improv|enhanc|level up|mejor|melhor|aprimor|entren|trein)", text):
        return "upgrade"
    if re.search(r"\b(?:heal|restor|restaur|recover|rest\b|descans|cura|recuper)", text):
        return "heal"
    if (re.search(r"\b(?:strength|fuerza|forca)\b", text)
            or re.search(r"\+\s*\d+(?:[.,]\d+)?\s*%", text)
            and re.search(r"\b(?:atk|atq|attack|ataque|damage|dmg|dano)\b", text)):
        return "damage"
    return None


@dataclass(frozen=True)
class EventOption:
    option: Text | None
    reason: str  # i18n key; raw game text is supplied separately


def _fountain_option(enabled, descriptions, hp, leave) -> EventOption:
    if leave is None:
        leave = next((t for t in enabled if t.norm in ("pass", "passar", "pasar")
                      or descriptions[t] == t.norm + " walk away"), None)
    for option in enabled:
        trade = _FOUNTAIN_TRADE.fullmatch(descriptions[option])
        if trade is None:
            continue
        bonus, cost = (float(percent.replace(",", ".")) / 100 for percent in trade.groups())
        if not 0 < cost < 1 or bonus < cost:
            continue
        # Budget the full Max HP penalty against current HP, measured against the old maximum.
        if hp is not None and hp - cost > config.HEAL_MAX_FRACTION + 1e-6:
            return EventOption(option, "decision_event_drink")
        return EventOption(leave, "decision_fountain_hp")
    return EventOption(leave, "decision_fountain_trade")


def choose_event(title: Text, enabled: tuple[Text, ...], descriptions: dict[Text, str], hp: float | None,
                 *, context=None) -> EventOption:
    leave = next((t for t in enabled if matches(t, labels.LEAVE, exact=True)), None)
    kind = event_kind(title.text)
    if not enabled:
        return EventOption(None, "decision_disabled")
    if kind == "cursed_fountain":
        return _fountain_option(enabled, descriptions, hp, leave)
    if kind in CONSERVATIVE:
        return EventOption(leave, "decision_safe_exit" if leave else "decision_unknown_option")
    # Unknown events can still have an explicitly readable positive effect. Costs invalidate it.
    effects = {t: event_effect(descriptions[t]) for t in enabled
               if not PREMIUM_CURRENCY.search(descriptions[t])}
    healing = next((t for t in enabled if effects.get(t) == "heal"), None)
    if healing and hp is not None and hp <= config.HEAL_MAX_FRACTION:
        return EventOption(healing, "decision_heal")
    for effect in ("damage", "upgrade", "max_hp"):
        option = next((t for t in enabled if effects.get(t) == effect), None)
        if option:
            return EventOption(option, "decision_" + effect)
    if leave:
        return EventOption(leave, "decision_safe_exit")
    if (kind == "rest" and len(enabled) == 1 and healing is not None
            and abs(healing.center[0] - config.SCREEN_SIZE[0] // 2) <= 80):
        return EventOption(healing, "decision_mandatory_rest")
    return EventOption(None, "decision_unknown_option")
