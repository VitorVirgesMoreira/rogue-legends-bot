"""Continuous read-only inspection. This path never creates a Navigator or a Player."""

from dataclasses import replace
import threading
from typing import Callable

from roguebot import config, labels
from roguebot.build import BuildState, choose
from roguebot.decisions import DecisionGuard
from roguebot.device import Device
from roguebot.events import EventChoices
from roguebot.modifiers import parse_modifiers
from roguebot.observation import Observation, describe
from roguebot.providers import create_provider
from roguebot.request import RunRequest
from roguebot.screens import (LevelScreen, LevelState, Mode, classify_level_screen, parse_lobby,
                              parse_skill_cards, skill_reroll)
from roguebot.skills import Catalog
from roguebot.vision import Ocr


class Inspector:
    def __init__(self, request: RunRequest, catalog: Catalog):
        self.request, self.catalog = request, catalog
        self.guard = DecisionGuard()
        self.language = None
        self.event_state = BuildState()

    def inspect(self, img, texts) -> Observation:
        self.language = labels.detect_language(texts) or self.language
        previous = labels.active_language()
        try:
            labels.set_language(self.language)
            return self._inspect(img, texts)
        finally:
            labels.set_language(previous)

    def _inspect(self, img, texts):
        lobby = parse_lobby(texts)
        if lobby:
            self.event_state = BuildState()
            self.guard.observe(LevelState(LevelScreen.UNKNOWN), img, texts)
            return Observation("lobby", reason="decision_preview_lobby", detail=lobby.level_title or "")
        if self.request.mode is Mode.PARTY_EXPEDITION:
            from roguebot.party_screens import (clear_reward, expedition_result, is_campfire, is_codex,
                                               is_combat, is_matching, is_route, parse_team)
            result = expedition_result(texts)
            reward = clear_reward(texts)
            team = parse_team(texts)
            if result or reward:
                button = result[1] if result else reward
                return Observation("party_expedition", "tap", target=button.center, detail=button.text)
            if team:
                return Observation("party_expedition", "wait", "decision_preview_party", f"{team.stage}/{team.total}")
            if any(parse(texts) for parse in (is_matching, is_combat, is_route, is_campfire, is_codex)):
                return Observation("party_expedition", reason="decision_preview_party")
            return Observation("unknown", reason="decision_unknown_screen")
        if self.request.mode in (Mode.CHAOS, Mode.CONQUEST):
            from roguebot.event_modes import season_closed
            return Observation("routine", reason="mode_season_closed" if season_closed(texts) else "mode_fixture_needed",
                               detail=self.request.mode.value)
        state = classify_level_screen(img, texts)
        if state.kind in (LevelScreen.VICTORY, LevelScreen.DEFEAT, LevelScreen.DOUBLE_REWARD):
            self.event_state = BuildState()
        modifiers = parse_modifiers(img, texts)
        if modifiers:
            self.event_state.set_modifiers(modifiers)
        progress = self.event_state.run_progress
        progress.observe(texts)
        if state.kind in (LevelScreen.BOARD_READY, LevelScreen.AUTO_PLAY):
            progress.observe_board(img, texts)
        event = None
        if state.kind in (LevelScreen.EVENT, LevelScreen.UNKNOWN):
            event = EventChoices().choose(img, texts, progress=progress, reserve=self.event_state.shop_reserve)
        if event:
            state = LevelState(LevelScreen.EVENT if event.tap or event.action == "wait" else LevelScreen.UNKNOWN, event.tap)
        ready = self.guard.observe(state, img, texts)
        view = describe(state, img, texts, stable=self.guard.reads)
        if event:
            view = replace(view, reason=event.status_reason, detail=event.detail)
        if state.kind is LevelScreen.SKILL_PICK:
            cards = parse_skill_cards(texts)
            skills = [self.catalog.lookup(c.name, c.description, c.rarity, self.language, persist=False) for c in cards]
            progress = BuildState()
            progress.configure(self.request.build)
            progress.set_modifiers(modifiers or ())
            reroll = skill_reroll(texts)
            if skills:
                index = choose(skills, self.request.build, progress, can_reroll=reroll is not None)
                if index is None:
                    view = replace(view, action="tap", detail=reroll.text, target=reroll.center)
                else:
                    card = cards[index]
                    view = replace(view, detail=card.name, target=(config.SCREEN_SIZE[0]//2,
                                   card.tag.center[1]+config.SKILL_TAP_BELOW_RARITY))
        elif state.kind is LevelScreen.SHOP:
            view = replace(view, target=None)  # purchases require balance/history and post-action confirmation
        elif state.kind is LevelScreen.REVIVE and not self.request.ads:
            view = replace(view, action="wait", target=None, reason="decision_no_ads")
        elif state.kind is LevelScreen.DOUBLE_REWARD and not self.request.ads:
            from roguebot.vision import find
            button = find(texts, labels.CONTINUE, exact=True)
            view = replace(view, target=button.center if button else None, reason="decision_no_ads")
        if not ready:
            view = replace(view, action="wait", reason="decision_confirming", target=None)
        return view


def watch(request: RunRequest, stop: threading.Event, emit: Callable[[Observation], None]):
    """Connect to an already running emulator. Stop/capture errors never trigger recovery."""
    provider = create_provider(request, stop)
    serial = provider.connect()
    device = Device(serial, stop=stop, adb=provider.adb)
    ocr, inspector = Ocr(), Inspector(request, Catalog())
    while not stop.is_set():
        if device.foreground_package() != config.PACKAGE:
            emit(Observation("other_app", reason="decision_foreground"))
        else:
            image = device.peek()
            emit(inspector.inspect(image, ocr.read(image)))
        if stop.wait(.5):
            break
    # The UI treats this as an ordinary preview end rather than a failed run.
