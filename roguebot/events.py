"""Use recognized loot/sacrifice opportunities while bounding attempts and preserving HP."""

from dataclasses import dataclass
import re
import time

from roguebot import config, labels
from roguebot.event_rules import PREMIUM_CURRENCY, choose_event, event_kind
from roguebot.screens import EventMenu, health_fraction, parse_event_menu, parse_money
from roguebot.vision import matches


_NAMED_ACTIONS = {
    "altar": ("offer", ("offer", "oferecer", "ofertar", "ofrecer")),
    "knowledge": ("read", ("read", "ler", "leer")),
    "might": ("fight", ("enter", "entrar")),
    "spoils": ("steal", ("steal", "roubar", "saquear", "robar")),
    "devil": ("sign", ("sign", "assinar", "firmar")),
}
_TOKEN_COST = re.compile(r"\b(?:pay|pague|pagar|paga|costs?|custa)\s+(\d+)\s+(?:tokens?|fichas?|moedas?|monedas?)\b")


@dataclass(frozen=True)
class EventDecision:
    title: str
    action: str
    tap: tuple[int, int] | None
    reason: str
    option: str = ""

    @property
    def status_reason(self) -> str:
        if self.reason.startswith("decision_"):
            return self.reason
        return {"loot": "decision_loot", "sacrifice": "decision_sacrifice",
                "wait": "decision_wait_change", "leave": "decision_safe_exit"}.get(
                    self.action, "decision_event_" + self.action)

    @property
    def detail(self) -> str:
        return f"{self.title} → {self.option}" if self.option else self.title


def _hp_cost(text: str, hp: float) -> float | None:
    percent = r"(\d+(?:[.,]\d+)?)\s*%"
    health = r"(?:of\s+(?:your\s+)?|d[eo]\s+(?:seu\s+)?)?(?:(?:max(?:imum)?|current|atual)\s*)?(?:hp|pv|health|life|vida)"
    patterns = (rf"[-−]\s*{percent}\s*{health}",
                rf"\b(?:sacrific\w*|sacrif\w*|offer|lose|pay|pague|cost\w*|pierde|perd\w*)\s+{percent}\s*{health}",
                rf"\b(?:hp|pv|health|life|vida)\s*[-−]\s*{percent}",
                rf"{percent}\s*{health}\s+(?:cost|loss|lost|perdida)")
    costs = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            value = float(match.group(1).replace(",", "."))/100
            if 0 < value <= 1:
                costs.append(value * hp if re.search(r"\b(?:current|atual)\b", match.group()) else value)
    return max(costs) if costs else None


class EventChoices:
    """Track one visit, including dispatches and any confirmed reward."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.title = None
        self.attempts = 0
        self.pending = None
        self.sent_at = 0.0

    @staticmethod
    def _leave(menu: EventMenu, reason: str) -> EventDecision:
        leave = next((t for t in menu.enabled if matches(t, labels.LEAVE, exact=True)), None)
        return EventDecision(menu.title.text, "leave", menu.tap(leave) if leave else None, reason,
                             leave.text if leave else "")

    def _visit(self, identity: str) -> None:
        if self.title != identity:
            self.reset()
            self.title = identity

    def _named(self, menu, kind, texts, progress, reserve):
        self._visit(kind)
        if self.attempts:
            if time.monotonic() - self.sent_at < 5:
                return EventDecision(menu.title.text, "wait", None, "Waiting for the attempt to resolve")
            return self._leave(menu, "Already attempted during this visit")
        action, names = _NAMED_ACTIONS[kind]
        option = next((t for t in menu.enabled if t.norm in names), None)
        if option is None:
            return self._leave(menu, "Expected option unavailable")
        description = menu.descriptions[option]
        if PREMIUM_CURRENCY.search(description):
            return self._leave(menu, "The option mentions premium currency")
        reason = {
            "read": "Read the forbidden tome", "steal": "Loot the cart", "sign": "Sign the pact",
            "fight": "Second boss defeated, with sufficient HP and attack",
        }.get(action)
        if action == "offer":
            match = _TOKEN_COST.search(description)
            money = parse_money(texts)
            if match is None or money is None:
                return self._leave(menu, "Token cost or balance unreadable")
            cost = int(match[1])
            if money - cost < reserve + 2 * cost:
                return self._leave(menu, "Insufficient balance after setting aside shop savings and twice the stake")
            reason = f"Offer {cost} tokens, leaving {money - cost} with a shop reserve of {reserve}"
        elif action == "fight" and (progress is None or not progress.ready_for_might(texts, health_fraction(texts))):
            return self._leave(menu, "Requires defeating the second boss, at least 75% HP, and 25% more attack than at the start")
        return EventDecision(menu.title.text, action, menu.tap(option), reason, option.text)

    def _fountain(self, menu: EventMenu, texts) -> EventDecision | None:
        self._visit("cursed_fountain")
        if self.attempts and time.monotonic() - self.sent_at < 5:
            return EventDecision(menu.title.text, "wait", None, "Waiting for the fountain to resolve")
        hp = health_fraction(texts) if not self.attempts else None
        choice = choose_event(menu.title, menu.enabled, menu.descriptions, hp)
        option = choice.option
        if self.attempts:
            return EventDecision(menu.title.text, "leave", menu.tap(option) if option else None,
                                 "One attempt per fountain visit", option.text if option else "")
        if option and choice.reason == "decision_event_drink":
            return EventDecision(menu.title.text, "drink", menu.tap(option),
                                 f"Trade maximum HP for ATK while preserving health (current HP {hp:.1%})", option.text)
        return None  # let the shared screen decision report why we passed

    def choose(self, img, texts, *, progress=None, reserve=190, context=None) -> EventDecision | None:
        menu = parse_event_menu(img, texts)
        if menu is None:
            return None
        kind = event_kind(menu.title.text)
        if kind == "rest" and context is not None:
            choice = choose_event(menu.title, menu.enabled, menu.descriptions, health_fraction(texts), context=context)
            if choice.option is not None:
                return EventDecision(menu.title.text, "rest_choice", menu.tap(choice.option), choice.reason, choice.option.text)
        if kind == "cursed_fountain":
            return self._fountain(menu, texts)
        if kind in _NAMED_ACTIONS:
            return self._named(menu, kind, texts, progress, reserve)
        body = " ".join(t.norm for t in texts if t.center[1] > config.EVENT_TITLE_Y[1])
        loot = next((t for t in menu.enabled if re.fullmatch(
            r"(?:loot|raid|plunder|ransack|steal|rob|invade|saquear|saqueo|robar|invadir)(?: again| otra vez| de novo)?", t.norm)), None)
        goblins = "goblin" in menu.title.norm or "goblin" in body
        if loot is None and goblins:
            loot = next((t for t in menu.enabled if not matches(t, labels.LEAVE, exact=True)
                         and re.search(r"\b(?:coin|gold|token|ficha|moeda|dinheiro)", menu.descriptions[t])
                         and re.search(r"\b(?:battle|fight|batalla|batalha)", menu.descriptions[t])), None)
        sacrifice = next((t for t in menu.enabled if re.fullmatch(
            r"sacrifice|offer|pray|read|sacrificar|ofrecer|ofertar|rezar|ler|leer", t.norm)), None)
        legendary = bool(re.search(r"\b(?:legendary|legendari|lendari)", body)
                         and re.search(r"\b(?:skill|habilidad|habilidade)", body))
        alternatives = [t for t in menu.enabled if not matches(t, labels.LEAVE, exact=True)]
        if legendary and sacrifice is None and len(alternatives) == 1:
            sacrifice = alternatives[0]  # the cost and HP reserve are still validated below
        if loot and goblins:
            option, action, limit = loot, "loot", 3
        elif sacrifice and legendary:
            option, action, limit = sacrifice, "sacrifice", 1
        else:
            return None
        self._visit(menu.title.norm)
        effect = menu.descriptions[option]
        if PREMIUM_CURRENCY.search(effect):
            return self._leave(menu, "The option mentions premium currency")
        hp, money = health_fraction(texts), parse_money(texts)
        if self.pending is not None:
            old_action, old_money, old_hp = self.pending
            confirmed = (money is not None and old_money is not None and money > old_money if old_action == "loot"
                         else hp is not None and old_hp is not None and hp < old_hp)
            if not confirmed:
                if time.monotonic()-self.sent_at < 5:
                    return EventDecision(menu.title.text, "wait", None, "Waiting for the attempt to resolve")
                return self._leave(menu, "Outcome unconfirmed, so the attempt will not be repeated")
            self.pending = None
        if self.attempts >= limit:
            return self._leave(menu, f"Reached the limit of {limit} attempts for this visit")
        if action == "loot":
            if hp is not None and hp <= config.HEAL_MAX_FRACTION:
                return self._leave(menu, "Avoiding another fight at 25% HP or less")
            reason = f"Loot the hut ({self.attempts + 1}/3)"
        else:
            if hp is None:
                return self._leave(menu, "Current HP is unreadable")
            cost = _hp_cost(" ".join((body, effect)), hp)
            if cost is None or hp - cost <= config.HEAL_MAX_FRACTION + 1e-6:
                return self._leave(menu, "The cost is unreadable or the sacrifice would leave 25% HP or less")
            reason = f"Attempt a legendary skill with an estimated {hp - cost:.0%} HP remaining"
        return EventDecision(menu.title.text, action, menu.tap(option), reason, option.text)

    def tapped(self, decision: EventDecision, texts):
        if decision.tap is None or decision.action == "leave":
            return
        self.attempts += 1
        self.sent_at = time.monotonic()
        if decision.action in ("loot", "sacrifice"):
            self.pending = decision.action, parse_money(texts), health_fraction(texts)
