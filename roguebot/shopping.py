"""Choose one shop action at a time and confirm its cost before spending again."""

from dataclasses import asdict, dataclass, field
import logging
from typing import Callable

from roguebot import config
from roguebot import decision_journal
from roguebot.build import Build, BuildState, shop_order, shop_utility_order
from roguebot import build_rules
from roguebot.build import focus
from roguebot.device import Device
from roguebot.observation import Observation, StatusPublisher
from roguebot.screens import Shop, ShopItem, SkillCard, parse_shop
from roguebot.skills import Skill
from roguebot.vision import Ocr, Text

log = logging.getLogger(__name__)
MAX_SHOP_STEPS = 40
MAX_REROLL_COST = 10
CONFIRM_READS = 5


@dataclass(frozen=True)
class SkillPurchase:
    name: str
    price: Text
    cost: int
    skill: Skill


@dataclass(frozen=True)
class Reroll:
    price: Text
    cost: int


ShopAction = SkillPurchase | Reroll | ShopItem


@dataclass
class ShopVisit:
    rolled_prices: set[int] = field(default_factory=set)
    bought: set[str] = field(default_factory=set)
    stock: dict[str, int] = field(default_factory=dict)
    healed: bool = False

    def observe_stock(self, items: tuple[ShopItem, ...]) -> None:
        for item in items:
            if item.kind != "heal" and item.remaining is not None:
                self.stock[item.kind] = min(self.stock.get(item.kind, item.remaining), item.remaining)

    def confirm(self, action: ShopAction) -> None:
        if isinstance(action, Reroll):
            self.rolled_prices.add(action.cost)
            self.bought.clear()
            self.stock.clear()
        elif isinstance(action, SkillPurchase):
            self.bought.add(action.name)
        elif action.kind == "heal":
            self.healed = True
        else:
            self.stock[action.kind] -= 1


def _offer(shop: Shop):
    return tuple((card.offer_key, card.cost, card.sold) for card in shop.cards)


class Shopper:
    def __init__(self, device: Device, ocr: Ocr, build: Build, state: BuildState,
                 skill_lookup: Callable[[SkillCard], Skill]):
        self.device, self.ocr = device, ocr
        self.build, self.state, self.skill_lookup = build, state, skill_lookup

    def _confirm(self, before: Shop, action: ShopAction) -> Shop | None:
        """Wait for the expected balance before spending again."""
        assert before.money is not None
        expected = before.money - action.cost
        previous = observed = None
        reroll = isinstance(action, Reroll)
        rounded_price = not reroll and self.state.rules.has("expensive_shop")
        for _ in range(CONFIRM_READS):
            after = parse_shop(self.ocr.read(self.device.screenshot()))
            if after is None or after.money is None:
                previous = None
                continue
            observed = after.money
            confirmed = observed == expected
            if reroll and action.cost == 0:
                confirmed = confirmed and (after.reroll_cost is not None and after.reroll_cost != 0
                                           or _offer(after) != _offer(before))
            elif rounded_price and abs(observed - expected) == 1:
                confirmed = observed == previous and observed < before.money
            if confirmed:
                log.debug("Shop: confirmed spending %d coins (balance %d to %d)",
                          before.money - observed, before.money, observed)
                return after
            previous = observed
        log.warning("Shop: stopping purchases after an unconfirmed action (balance %d, expected %d, observed %s)",
                    before.money, expected, observed)
        return None

    def _reserve(self, shop: Shop, final: bool) -> int:
        if final:
            return 0
        premium = (c.cost for c in shop.cards if not c.sold and c.cost is not None
                   and c.rarity in ("legendary", "mythic") and
                   shop_order([self.skill_lookup(c)], self.build, self.state, can_reroll=True))
        self.state.premium_shop_price = max(self.state.premium_shop_price, max(premium, default=0))
        if self.state.context.survival_pressure:
            return 0  # reserve must not prevent survival before the next shop
        return self.state.shop_reserve

    def _choose(self, shop: Shop, visit: ShopVisit, reserve: int) -> ShopAction | None:
        assert shop.money is not None
        balance = shop.money
        visit.observe_stock(shop.items)
        self.state.context.hp = shop.hp
        if (not visit.healed and shop.hp is not None and
                (shop.hp <= config.HEAL_MAX_FRACTION or self.state.context.survival_pressure)):
            heal = next((item for item in shop.items if item.kind == "heal" and 0 < item.cost <= balance), None)
            if heal:
                return heal

        offers = [SkillPurchase(card.name, card.price, cost, self.skill_lookup(card))
                  for card in shop.cards
                  if not card.sold and card.name not in visit.bought and card.price is not None
                  and (cost := card.cost) is not None and cost > 0]
        affordable = [offer for offer in offers if offer.cost <= balance]
        skills = [offer.skill for offer in affordable]
        prices = [offer.cost for offer in affordable]
        roll_cost = shop.reroll_cost
        base_price = 72 if self.state.rules.has("expensive_shop") else 48
        skill_budget = min((offer.cost for offer in offers), default=base_price)
        can_search = (shop.reroll is not None and roll_cost is not None and 0 <= roll_cost <= MAX_REROLL_COST
                and roll_cost not in visit.rolled_prices and balance > 0
                and (roll_cost == 0 or shop.cards and balance - roll_cost >= min(base_price, skill_budget)))
        wanted = shop_order(skills, self.build, self.state, can_reroll=True, prices=prices)
        if wanted:
            best = skills[wanted[0]]
            if (not can_search or self.state.context.mode != "campaign" or self.state.context.survival_pressure
                    or self.state.priority_enemy_counter(best) or best.reference is None
                    or build_rules.utility(best, self.state, focus(self.build, self.state)) >= .75):
                return affordable[wanted[0]]
        if can_search:
            return Reroll(shop.reroll, roll_cost)

        spare = balance - reserve
        for index in shop_utility_order(skills, self.build, self.state):
            if affordable[index].cost <= spare:
                return affordable[index]
        return next((item for item in sorted(shop.items, key=lambda item: item.kind != "atk")
                     if item.kind != "heal" and visit.stock.get(item.kind, 0) > 0
                     and 0 < item.cost <= spare), None)

    def buy(self, texts: list[Text]) -> None:
        shop = parse_shop(texts)
        if shop is None or shop.money is None:
            return
        progress = self.state.run_progress
        final = progress.final_shop
        log.info("Shop: skills first, progress %s/%s (%s). %s", progress.rolls, progress.total, progress.unit,
                 "Spend useful coins before the final boss" if final else "Save a reserve for later shops")
        visit = ShopVisit()
        status = StatusPublisher()
        for _ in range(MAX_SHOP_STEPS):
            self.state.context.hp = shop.hp
            reserve = self._reserve(shop, final)
            action = self._choose(shop, visit, reserve)
            action_name = "leave" if action is None else "reroll" if isinstance(action, Reroll) else "buy"
            decision_journal.record(self.state, "shop", action_name,
                offers=[{"card": asdict(self.skill_lookup(c)), "cost": c.cost, "sold": c.sold,
                         "evaluation": self.state.explanation(self.skill_lookup(c), self.build)} for c in shop.cards],
                money=shop.money, reserve=reserve, reroll_cost=shop.reroll_cost,
                stock=[asdict(item) for item in shop.items], planned=asdict(action) if action else None)
            if action is None:
                log.info("Shop: leaving with %d coins (reserve %d), no useful purchase within budget",
                         shop.money, reserve)
                return
            if isinstance(action, SkillPurchase):
                name = action.name
                log.info("Shop decision: %s", self.state.explanation(action.skill, self.build))
            elif isinstance(action, Reroll):
                name = action.price.text
            else:
                name = action.kind
            log.info("Shop: %s for %d coins (balance %d)", name, action.cost, shop.money)
            status.publish(Observation("shop", "tap", "decision_shop", name, stable=2, target=action.price.center))
            self.device.tap(*action.price.center)
            after = self._confirm(shop, action)
            if after is None:
                return
            visit.confirm(action)
            if isinstance(action, SkillPurchase):
                self.state.take(action.skill, self.build)
            decision_journal.record(self.state, "shop", "confirmed", money=after.money, completed=asdict(action))
            shop = after
        log.warning("Shop: action limit reached for this visit")
