"""Stability of an offer and confirmation of a card flip, independent of input."""

import logging
import time

from roguebot import config, labels
from roguebot.mode_screens import parse_fight_skip
from roguebot.screens import (LevelScreen, _face_down, close_button, health_fraction, parse_event_menu,
                              parse_money, parse_shop, parse_skill_cards, popup_close)
from roguebot.vision import find

log = logging.getLogger(__name__)

GUARDED = {LevelScreen.SKILL_PICK, LevelScreen.SHOP, LevelScreen.EVENT,
           LevelScreen.VICTORY, LevelScreen.DEFEAT, LevelScreen.DOUBLE_REWARD}
RETRY_AFTER = 3.0


class FightSkip:
    def __init__(self, tap):
        self.tap = tap
        self.reset()

    def reset(self):
        self.attempts = 0
        self.retry_at = 0.
        self.blocked = False

    def dismiss_offer(self, img, texts) -> bool:
        if not self.attempts or not find(texts, labels.VIP_OFFER, exact=True):
            return False
        self.blocked = True
        close = popup_close(texts)
        if close:
            self.tap(close.center)
        elif img is not None and (point := close_button(img)):
            self.tap(point)
        return True

    def use(self, texts) -> bool:
        if self.blocked or self.attempts >= 2 or time.monotonic() < self.retry_at:
            return False
        button = parse_fight_skip(texts)
        if button is None:
            return False
        if self.tap(button.center) is not False:
            log.info("Fight: using Skip")
            self.attempts += 1
            self.retry_at = time.monotonic() + RETRY_AFTER
        return True


def _offer(state, img, texts):
    positions = []
    if state.kind is LevelScreen.EVENT:
        menu = parse_event_menu(img, texts)
        if menu:
            content = (menu.title.norm, tuple((t.norm, menu.descriptions[t]) for t in menu.enabled),
                       health_fraction(texts), parse_money(texts))
            positions = [t.center for t in menu.enabled]
        else:
            content = tuple(t.norm for t in texts)
    elif state.kind in (LevelScreen.SKILL_PICK, LevelScreen.SHOP):
        cards = parse_skill_cards(texts)
        positions = [c.tag.center for c in cards]
        if state.kind is LevelScreen.SHOP:
            stock = tuple((c.offer_key, c.cost, c.sold) for c in cards)
            shop = parse_shop(texts)
            content = (stock, shop.money if shop else None, shop.reroll_cost if shop else None,
                       tuple((i.kind, i.cost, i.remaining) for i in shop.items) if shop else ())
        elif cards:
            content = tuple(c.offer_key for c in cards)
        else:
            content = tuple(t.norm for t in texts)
    else:
        # Ignore changing reward counters/animations, but keep the outcome and action distinct.
        content = tuple(t.norm for t in texts if any(word in t.norm for word in
                        ("victory", "victoria", "defeat", "derrota", "continue", "continuar", "x2 rewards")))
    if state.tap:
        positions.append(state.tap)
    return (state.kind, content), positions


class DecisionGuard:
    def __init__(self):
        self.key = None
        self.positions = []
        self.reads = 0
        self.last_action = None
        self.acted_at = 0.0
        self.reason = "decision_confirming"

    def observe(self, state, img, texts) -> bool:
        if state.kind not in GUARDED:
            self.key, self.positions, self.reads = None, [], 0
            self.last_action = None
            return True
        key, positions = _offer(state, img, texts)
        same = (key == self.key and len(positions) == len(self.positions)
                and all(abs(a[0]-b[0]) <= config.SAME_TAP_TOLERANCE
                        and abs(a[1]-b[1]) <= config.SAME_TAP_TOLERANCE
                        for a, b in zip(positions, self.positions)))
        self.reads = min(2, self.reads+1) if same else 1
        if not same:
            self.last_action = None
        self.key, self.positions = key, positions
        self.reason = "decision_confirming"
        if self.reads < 2:
            return False
        if (state.kind in (LevelScreen.EVENT, LevelScreen.SKILL_PICK, LevelScreen.SHOP)
                and self.last_action == key and time.monotonic()-self.acted_at < RETRY_AFTER):
            self.reason = "decision_wait_change"
            return False
        return True

    def acted(self):
        self.last_action, self.acted_at = self.key, time.monotonic()


class CardFlipError(Exception):
    pass


class CardFlips:
    """Do not advance a queue on dispatch: only the revealed image confirms a flip."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.pending = None
        self.attempts = 0
        self.sent_at = 0.0
        self.waiting_since = None

    def choose(self, img, candidate):
        now = time.monotonic()
        if self.pending is not None:
            if _face_down(img, self.pending):
                if now-self.sent_at < RETRY_AFTER:
                    return None
                if self.attempts >= 3:
                    raise CardFlipError("Card flip was not confirmed after 3 attempts")
                return self.pending
            self.pending, self.attempts = None, 0
        if candidate is None:
            if self.waiting_since is None:
                self.waiting_since = now
            elif now-self.waiting_since > config.UNKNOWN_SCREEN_TIMEOUT:
                raise CardFlipError("Card minigame did not advance after the last flip")
        else:
            self.waiting_since = None
        return candidate

    def tapped(self, point):
        self.attempts = self.attempts+1 if point == self.pending else 1
        self.pending, self.sent_at = point, time.monotonic()
