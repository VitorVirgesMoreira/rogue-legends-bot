"""Structured decisions shared by the live window and the read-only inspector."""

from dataclasses import dataclass
import logging

from roguebot.event_rules import choose_event
from roguebot.screens import LevelScreen, health_fraction, parse_event_menu

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Observation:
    screen: str
    action: str = "wait"
    reason: str = "decision_next"
    detail: str = ""
    source: str = "ocr"
    score: float | None = None
    stable: int = 0
    target: tuple[int, int] | None = None


def describe(state, img, texts, *, stable=0, reason=None, target=None) -> Observation:
    point = state.tap if target is None else target
    action = "tap" if point else "wait"
    source, score, detail = "ocr", None, ""
    inferred = "decision_next"
    if state.kind in (LevelScreen.EVENT, LevelScreen.UNKNOWN):
        menu = parse_event_menu(img, texts)
        if menu:
            choice = choose_event(menu.title, menu.enabled, menu.descriptions, health_fraction(texts))
            inferred, detail, source, score = choice.reason, menu.title.text, menu.source, menu.score
            if choice.option:
                detail += " → " + choice.option.text
        else:
            inferred = "decision_unknown_screen"
    elif state.kind is LevelScreen.AUTO_PLAY:
        source, inferred = "pixels", "decision_auto"
    elif state.kind is LevelScreen.BOARD_READY:
        source, action = "pixels", "hold"
    elif state.kind is LevelScreen.FIGHT:
        inferred = "decision_battle"
    elif state.kind is LevelScreen.SHOP:
        action, inferred = "shop", "decision_shop"
    elif state.kind is LevelScreen.SKILL_PICK:
        action, inferred = "skill", "decision_build"
    elif state.kind is LevelScreen.FLIP_CARDS:
        source = "pixels"
    return Observation(state.kind.value, action, reason or inferred, detail, source, score, stable, point)


class StatusPublisher:
    def __init__(self):
        self.last = None

    def publish(self, observation: Observation):
        if observation != self.last:
            log.info("%s: %s (%s)%s", observation.screen, observation.action, observation.reason,
                     f" — {observation.detail}" if observation.detail else "", extra={"observation": observation})
            self.last = observation
