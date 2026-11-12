"""Party Expedition: form a team, vote for treasure routes and advance through stage 20."""

import logging
from pathlib import Path
import time

import cv2

from roguebot import config, labels
from roguebot.build import Build, BuildState
from roguebot.decisions import FightSkip
from roguebot.device import ViewportUnavailable
from roguebot.emulator import EmulatorError
from roguebot.mode_screens import back_arrow
from roguebot.observation import Observation, StatusPublisher
from roguebot.party_build import choose_party_skill
from roguebot.party_routes import route_vote
from roguebot.party_screens import (TICKET_OCR_REGION, clear_reward, combat_speed, event_header, expedition_entry, expedition_result,
                                    home_entry, is_campfire, is_codex, is_combat, is_matching, is_route, parse_team,
                                    party_language, expedition_complete, team_status)
from roguebot.report import Report
from roguebot.progress import PartyProgress
from roguebot.screens import LevelScreen, lobby_behind, parse_lobby, parse_skill_cards, popup_close
from roguebot.skills import Catalog
from roguebot.vision import matches
from roguebot.metrics import History, RunRecord, build_signature
from dataclasses import asdict

log = logging.getLogger(__name__)
MATCH_TIMEOUT = 120
MATCH_PLAY_TIMEOUT = 1800
NAV_TIMEOUT = 60
UNKNOWN_TIMEOUT = 30
MENU_SETTLE = 5  # allow an unlabelled return/loading frame to settle before generic initial navigation
TEAM_STAGE_REGION = (460, 150, 990, 350)
TEAM_MATCH_REGION = (450, 2320, 1000, 2530)


class PartyError(EmulatorError):
    """Stop an online run for inspection instead of relaunching it and starting another match."""


class PartyExpedition:
    def __init__(self, device, ocr, nav, build: Build = Build(), catalog: Catalog | None = None,
                 role: str = "striker", progress: PartyProgress | None = None):
        self.device, self.ocr, self.nav = device, ocr, nav
        self.build, self.role = build, role
        self.catalog = catalog if catalog is not None else Catalog()
        self.progress = progress if progress is not None else PartyProgress()
        self.results = self.progress.results
        self.state = BuildState()
        self.state.configure(build, "party")
        self._last_image = None
        self._status = StatusPublisher()

    def _capture(self):
        deadline = time.monotonic() + UNKNOWN_TIMEOUT
        while True:
            try:
                img = self.device.screenshot()
                break
            except ViewportUnavailable:
                if time.monotonic() >= deadline:
                    raise
                self.device.wait(config.POLL_INTERVAL)
        self._last_image = img
        texts = self.ocr.read(img)
        hp, roles, heroes = team_status(texts)
        if hp:
            self.state.context.team_hp = hp
        if roles:
            self.state.context.team_roles = roles
        if heroes:
            self.state.context.team_heroes = heroes
        if is_combat(texts):
            self._status.publish(Observation("fight", reason="decision_battle"))
        elif is_matching(texts):
            self._status.publish(Observation("party_expedition", reason="decision_matching"))
        elif is_route(texts):
            self._status.publish(Observation("party_expedition", reason="decision_route"))
        elif any(matches(t, labels.SKILL_PROMPT) for t in texts):
            self._status.publish(Observation("skill_pick", "skill", "decision_build"))
        else:
            self._status.publish(Observation("party_expedition", reason="decision_next"))
        return img, texts

    def _fail(self, key="party_unknown"):
        if self._last_image is not None:
            folder = Path("debug")
            folder.mkdir(exist_ok=True)
            path = folder / f"party_{time.strftime('%Y%m%d_%H%M%S')}.png"
            cv2.imwrite(str(path), self._last_image)
            log.error("Party Expedition: %s (screenshot: %s)", key, path)
        raise PartyError(key)

    def _tap(self, point):
        try:
            self.device.tap(*point)
            return True
        except ViewportUnavailable:
            # Unity can begin a dark transition between OCR and the gesture's fresh capture.
            # No input was sent; read the next frame instead of restarting an online game.
            self.device.wait(config.POLL_INTERVAL)
            return False

    @staticmethod
    def _in_match(texts):
        return (is_combat(texts) or is_matching(texts) or is_route(texts) or is_campfire(texts)
                or expedition_result(texts) is not None
                or any(matches(t, labels.SKILL_PROMPT) for t in texts))

    def _open_team(self, *, after_result=False, finishing=False, expected_stage=None):
        deadline = time.monotonic() + NAV_TIMEOUT
        returned_to_lobby = False
        result_retaps = 0
        opened_at = time.monotonic()
        seen_event = after_result
        while time.monotonic() < deadline:
            img, texts = self._capture()
            in_event_menu = event_header(texts) or is_codex(texts)
            seen_event = seen_event or in_event_menu
            if lang := party_language(texts):
                labels.set_language(lang)
            if expedition_complete(texts):
                raise PartyError("party_complete")
            reward = clear_reward(texts)
            if reward:
                accepted = self._tap(reward.center)
                if finishing and accepted:
                    return None
                continue
            previous_result = expedition_result(texts) if after_result else None
            if previous_result:
                if result_retaps >= 2:
                    self._fail()
                if self._tap(previous_result[1].center):
                    result_retaps += 1
                continue
            team = parse_team(texts)
            if team is None and event_header(texts) and not self._in_match(texts):
                # The team can appear before the full-frame OCR has picked up its stage/button.
                # Re-read those regions; never back out of the event for a missed label.
                texts += self.ocr.read(img, TEAM_STAGE_REGION)
                texts += self.ocr.read(img, TEAM_MATCH_REGION)
                team = parse_team(texts)
            if team:
                if expected_stage is not None and team.stage < expected_stage:
                    self.device.wait(config.POLL_INTERVAL)
                    continue  # server has not advanced the stage yet; never replay the old one
                if team.tickets is None:
                    texts += self.ocr.read(img, TICKET_OCR_REGION)
                    team = parse_team(texts)
                if team.tickets is None:
                    self._fail("party_ticket_unknown")
                return team
            if self._in_match(texts):
                return None  # resume an online party already running; never tap Match twice
            if is_codex(texts):
                point = back_arrow(img)
                if point:
                    self._tap(point)
                    continue
            entry = expedition_entry(texts) or home_entry(texts)
            if entry:
                self._tap(entry)
                continue
            close = popup_close(texts)
            if close:
                self._tap(close.center)
                continue
            if parse_lobby(texts):
                raise PartyError("party_unavailable")
            # A completed online match returns through partly drawn frames. Generic lobby
            # navigation presses Back through the event and can open unrelated promotions.
            # Use it only for a proven lobby popup or an initial unrelated menu after settling.
            lobby_popup = not in_event_menu and lobby_behind(texts)
            initial_menu = not seen_event and time.monotonic()-opened_at >= MENU_SETTLE
            if (not returned_to_lobby and (lobby_popup or initial_menu)
                    and not any(any(word in t.norm for word in ("loading", "carregando", "cargando")) for t in texts)):
                self.nav.go_to_lobby()
                returned_to_lobby = True
            self.device.wait(config.POLL_INTERVAL)
        self._fail()

    def run(self, max_matches: int = 20, *, dry_run: bool = False) -> Report:
        if type(max_matches) is not int or not 1 <= max_matches <= 20:
            raise ValueError("bad_party_runs")
        labels.set_language(None)
        try:
            team = self._open_team()
        except PartyError as exc:
            if exc.key in ("party_unavailable", "party_complete"):
                return self._report(exc.key)
            raise
        if dry_run:
            return Report(dry_run=True)
        while self.progress.started < max_matches or self.progress.pending:
            if team is not None:
                self.progress.stage = team.stage
                if team.tickets < 1:
                    return self._report("party_no_tickets")
                self.state = BuildState()
                self.state.configure(self.build, "party")
                log.info("Party Expedition: stage %d/%d, %d attempts; matchmaking (%d/%d)",
                         team.stage, team.total, team.tickets, self.progress.started+1, max_matches)
                if not self._tap(team.match.center):
                    team = self._open_team()
                    continue
                self.progress.pending = True
                self.progress.started += 1
            elif not self.progress.pending:
                self.progress.pending = True
                self.progress.started += 1
                log.info("Party Expedition: resuming an online party already in progress")
            result = self._play_match()
            self.progress.pending = False
            if result is None:
                return self._report("party_match_timeout")
            self.results.append(result)
            if result is LevelScreen.VICTORY and self.progress.stage is not None and self.progress.stage >= 20:
                try:
                    self._open_team(after_result=True, finishing=True)
                except PartyError as exc:
                    if exc.key != "party_complete":
                        raise
                return self._report("party_complete")
            expected = self.progress.stage + 1 if result is LevelScreen.VICTORY and self.progress.stage is not None else None
            team = self._open_team(after_result=True, expected_stage=expected)
        return self._report("party_limit")

    def _report(self, reason):
        return Report(list(self.results), repeat=True, party_reason=reason)

    def _play_match(self):
        deadline = time.monotonic() + MATCH_PLAY_TIMEOUT
        started = time.monotonic()
        last_known = time.monotonic()
        matching_since = None
        last_offer, choice_at, choice_tries = None, 0, 0
        last_vote = None
        speed_from, speed_target, speed_tries = None, 4, 0
        skip = FightSkip(self._tap)
        while time.monotonic() < deadline:
            img, texts = self._capture()
            if skip.dismiss_offer(img, texts):
                if time.monotonic() - last_known >= UNKNOWN_TIMEOUT:
                    self._fail()
                self.device.wait(config.POLL_INTERVAL)
                continue
            result = expedition_result(texts)
            if result:
                log.info("Party Expedition finished: %s", result[0].value)
                if self._tap(result[1].center):
                    History().record(RunRecord("party", self.build.profile, result[0].value,
                        max(0., time.monotonic()-started), level=self.progress.stage,
                        skills=list(self.state.taken), loadout=asdict(self.build.loadout), build_config=build_signature(self.build)))
                    return result[0]
                continue
            if parse_team(texts):
                return None  # matchmaking ended without a game; never immediately requeue
            cards = parse_skill_cards(texts) if any(matches(t, labels.SKILL_PROMPT) for t in texts) else []
            combat = is_combat(texts)
            route = is_route(texts)
            campfire = is_campfire(texts)
            known = bool(cards) or is_matching(texts) or combat or route or campfire
            if known:
                last_known = time.monotonic()
            elif time.monotonic() - last_known >= UNKNOWN_TIMEOUT:
                self._fail()
            if cards:
                offer = tuple(card.name for card in cards)
                if offer != last_offer:
                    choice_tries = 0
                if choice_tries < 2 and (offer != last_offer or time.monotonic() - choice_at >= 3):
                    skills = [self.catalog.lookup(c.name, c.description, c.rarity, labels.active_language()) for c in cards]
                    choice = choose_party_skill(skills, self.role, self.build, self.state)
                    if choice is not None:
                        card = cards[choice]
                        log.info("Party Expedition: %s skill: %s", self.role, card.name)
                        if not self._tap((config.SCREEN_SIZE[0]//2, card.tag.center[1] + config.SKILL_TAP_BELOW_RARITY)):
                            continue
                        if offer != last_offer:
                            self.state.take(skills[choice], self.build)
                        last_offer, choice_at, choice_tries = offer, time.monotonic(), choice_tries+1
            else:
                last_offer = None
            if route or campfire:
                skip.reset()
            elif combat and not cards and skip.use(texts):
                continue
            if is_matching(texts):
                if matching_since is None:
                    matching_since = time.monotonic()
                if time.monotonic() - matching_since >= MATCH_TIMEOUT:
                    cancel = next((t for t in texts if t.norm in ("cancel", "cancelar") and t.center[1] > 2200), None)
                    if cancel:
                        self._tap(cancel.center)
                    return None
            else:
                matching_since = None
            vote = route_vote(img, texts, self.state.context)
            if vote and (last_vote is None or abs(vote[0]-last_vote[0]) > 25 or abs(vote[1]-last_vote[1]) > 25):
                log.info("Party Expedition: voting for the route toward treasure at %s", vote)
                if self._tap(vote):
                    last_vote = vote
            elif not route:
                last_vote = None
            speed = combat_speed(texts) if combat else None
            if speed and speed[0] < speed_target and speed_tries < 3:
                if speed_from is not None and speed[0] < speed_from:
                    speed_target = speed_from
                if speed[0] < speed_target:
                    if self._tap(speed[1]):
                        speed_from, speed_tries = speed[0], speed_tries+1
            self.device.wait(config.POLL_INTERVAL)
        self._fail()
