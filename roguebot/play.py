"""In-level loop: roll dice, let fights play, pick skills, until the level ends.

Mode-agnostic: normal and elite levels share the same gameplay.
"""

import logging
from dataclasses import asdict, replace
from datetime import datetime
import json
import time
from pathlib import Path

import cv2

from roguebot import config, labels
from roguebot import decision_journal
from roguebot.build import Build, BuildState, PendingSkill, choose, focus, ranked
from roguebot.device import Device, ViewportUnavailable
from roguebot.decisions import CardFlipError, CardFlips, DecisionGuard, FightSkip, GUARDED
from roguebot.modifiers import parse_modifiers
from roguebot.observation import Observation, StatusPublisher, describe
from roguebot.screens import (LevelScreen, LevelState, SkillCard, classify_level_screen, game_speed,
                              health_fraction, parse_event_menu, parse_fortune_teller, parse_skill_cards, skill_reroll)
from roguebot.shopping import Shopper
from roguebot.skills import Catalog, Skill
from roguebot.vision import Ocr, find, matches

log = logging.getLogger(__name__)

DEBUG_DIR = Path("debug")
EVENT_DEBUG_DIR = DEBUG_DIR / "events"
MAX_EVENT_CAPTURES = 40


class PlayError(Exception):
    pass


def _same_tap(a, b) -> bool:
    """Same screen kind and (nearly) the same point: OCR jitters text centers by a few pixels."""
    return (b is not None and a[0] is b[0]
            and abs(a[1][0] - b[1][0]) <= config.SAME_TAP_TOLERANCE and abs(a[1][1] - b[1][1]) <= config.SAME_TAP_TOLERANCE)


class Player:
    def __init__(self, device: Device, ocr: Ocr, build: Build = Build(), catalog: Catalog | None = None,
                 ads: bool = False, *, build_state: BuildState | None = None, inspect_modifiers: bool = False):
        self.device = device
        self.ads = ads  # watch ads (x2 rewards, free revive); only with an account that skips them
        self.ocr = ocr
        self.build = build
        self.catalog = catalog if catalog is not None else Catalog()
        self._saved_build_state = build_state
        self._state = build_state if build_state is not None else BuildState()
        self._state.configure(build)
        self._rerolled = False       # the skill pick on screen is already the rerolled one
        self._doubles = 0            # x2 rewards taps at this level end
        self._planned_skill: PendingSkill | None = None
        self._speed_from: int | None = None
        self._speed_tries = 0
        self._speed_tapped_at = 0.0
        self._speed_target = config.TARGET_GAME_SPEED
        self._speed_locked = False
        self._auto_held = False     # held the dice for auto-play and not seen it on yet
        self._auto_missing = False  # a hold brought the red dice back: no auto-play here, tap instead
        self._auto_seen = False     # auto-play worked in this level: a hold that brings the red dice back was missed
        self._auto_misses = 0       # such missed holds in a row
        self._fortune_bought = []   # Fortune Teller balls bought this visit (chances)
        self._fortune_tap = None    # (chance, orbs before, time) of the last ball tap, until the orbs drop
        self._inspect_modifiers = inspect_modifiers
        self._modifier_reads = 0
        self._modifier_tapped_at = 0.0
        self._events = self._state.event_choices
        self._last_event_trace = None
        self._guard = DecisionGuard()
        self._cards = CardFlips()
        self._status = StatusPublisher()

    def play_level(self) -> LevelScreen:
        """Play until the level ends; returns LevelScreen.VICTORY or LevelScreen.DEFEAT."""
        last_known = time.monotonic()
        self.result_values = (None, {})
        last_tap, repeats, first_repeat = None, 0, time.monotonic()
        self._state = self._saved_build_state if self._saved_build_state is not None else BuildState()
        self._state.configure(self.build)
        self._events = self._state.event_choices
        self._rerolled, self._doubles, self._planned_skill = False, 0, None
        self._fortune_bought, self._fortune_tap = [], None
        skip = FightSkip(lambda point: self.device.tap(*point))
        viewport_missing_since = None
        if self._state.modifiers:
            self._log_modifiers()
        while True:
            try:
                img = self.device.screenshot()
            except ViewportUnavailable:
                now = time.monotonic()
                if viewport_missing_since is None:
                    viewport_missing_since = now
                    log.info("Game viewport temporarily unavailable; waiting up to %s s without input",
                             config.VIEWPORT_TRANSITION_TIMEOUT)
                    self._status.publish(Observation("unknown", reason="decision_unknown_screen", source="pixels"))
                remaining = config.VIEWPORT_TRANSITION_TIMEOUT - (now - viewport_missing_since)
                if remaining <= 0:
                    raise
                self.device.wait(min(config.POLL_INTERVAL, remaining))
                continue
            if viewport_missing_since is not None:
                waited = time.monotonic() - viewport_missing_since
                log.info("Game viewport restored after %.1f s; continuing the same run", waited)
                # Loading does not count as an unknown offer or an ignored tap. Keep pending
                # actions/build/autoplay, but require fresh visual stability after the gap.
                last_known += waited
                first_repeat += waited
                self._guard.reads = 0
                viewport_missing_since = None
            texts = self.ocr.read(img)
            if skip.dismiss_offer(img, texts):
                if time.monotonic() - last_known > config.UNKNOWN_SCREEN_TIMEOUT:
                    self._fail("Could not close the VIP offer", img)
                time.sleep(config.POLL_INTERVAL)
                continue
            state = classify_level_screen(img, texts)
            hp = health_fraction(texts)
            if (hp is None and isinstance(self.ocr, Ocr)
                    and state.kind in (LevelScreen.EVENT, LevelScreen.SHOP, LevelScreen.SKILL_PICK)):
                retry = self.ocr.read(img, config.HEALTH_REGION)
                hp = health_fraction(retry)
                if hp is not None:
                    x1, y1, x2, y2 = config.HEALTH_REGION
                    texts = [t for t in texts if not (x1 <= t.center[0] <= x2 and y1 <= t.center[1] <= y2)] + retry
                    state = classify_level_screen(img, texts)
            self._state.context.observe(hp, state.kind.value)
            if state.kind in (LevelScreen.BOARD_READY, LevelScreen.AUTO_PLAY):
                skip.reset()
                self._state.run_progress.observe(texts)
                self._state.run_progress.observe_board(img, texts)
            event_decision = None
            entries = parse_modifiers(img, texts)
            if entries:
                observed = {m.name: m for m in self._state.modifiers or ()}
                observed.update((m.name, m) for m in entries)
                combined = tuple(observed.values())
                if combined != self._state.modifiers:
                    self._state.set_modifiers(combined)
                    self._log_modifiers()
            if self._read_modifier_panel(texts, state.kind):
                continue
            if state.kind in (LevelScreen.EVENT, LevelScreen.UNKNOWN):
                event_decision = self._events.choose(img, texts, progress=self._state.run_progress,
                                                     reserve=self._state.shop_reserve, context=self._state.context)
                if event_decision:
                    kind = LevelScreen.UNKNOWN if event_decision.action == "leave" and event_decision.tap is None else LevelScreen.EVENT
                    state = LevelState(kind, event_decision.tap)
            if not self._guard.observe(state, img, texts):
                view = describe(state, img, texts, stable=self._guard.reads, reason=self._guard.reason)
                if event_decision:
                    view = replace(view, detail=event_decision.detail)
                self._status.publish(replace(view, action="wait", target=None))
                if time.monotonic() - last_known > config.UNKNOWN_SCREEN_TIMEOUT:
                    self._fail("The offer did not stabilize or confirm its last action", img)
                time.sleep(config.POLL_INTERVAL)
                continue
            log.debug("screen: %s", state.kind.value)
            self._confirm_skill(state.kind, texts)

            if state.kind is LevelScreen.SKILL_PICK:
                state = LevelState(state.kind, self._pick_skill(texts) or state.tap)
            elif state.kind is LevelScreen.SHOP:
                self._status.publish(describe(state, img, texts, stable=self._guard.reads))
                self._shop(texts)  # buys what the build wants and the coins allow; then state.tap exits
            elif state.kind is LevelScreen.FORTUNE_TELLER:
                state = LevelState(state.kind, self._fortune(texts))
            elif state.kind is LevelScreen.FLIP_CARDS:
                try:
                    state = LevelState(state.kind, self._cards.choose(img, state.tap))
                except CardFlipError as exc:
                    self._fail(str(exc), img)
            elif state.kind in (LevelScreen.BOARD_READY, LevelScreen.AUTO_PLAY):
                self._fortune_bought = []  # back on the board: a later Fortune Teller is a new visit
                self._events.reset()
                self._cards.reset()

            if state.kind is LevelScreen.DOUBLE_REWARD:
                self._doubles += 1
                proceed = find(texts, labels.CONTINUE, exact=True)
                # No ads, or the x2 button stays after the tries: just continue
                if (not self.ads or self._doubles > config.DOUBLE_REWARD_TRIES) and proceed:
                    # Continue leaves the result screen immediately. Preserve its outcome now;
                    # waiting for another VICTORY frame after the tap gets stuck in the star list.
                    kind = (LevelScreen.VICTORY if find(texts, labels.VICTORY) else
                            LevelScreen.DEFEAT if find(texts, labels.DEFEAT) else LevelScreen.CONTINUE)
                    state = LevelState(kind, proceed.center)
                elif not self.ads:  # Continue not read yet: never the ad button. Unknown, so the stuck guard applies
                    state = LevelState(LevelScreen.UNKNOWN)
            elif state.kind is LevelScreen.REVIVE and not self.ads:
                state = LevelState(LevelScreen.UNKNOWN)  # the free revive is a video: let the 10 s countdown run out
            elif state.kind is LevelScreen.FIGHT and skip.use(texts):
                last_known = time.monotonic()
                continue

            view = describe(state, img, texts, stable=self._guard.reads)
            if event_decision:
                view = replace(view, reason=event_decision.status_reason, detail=event_decision.detail)
            elif state.kind is LevelScreen.SKILL_PICK and self._planned_skill:
                view = replace(view, detail=self._planned_skill.skill.name)
            elif state.kind is LevelScreen.FLIP_CARDS and state.tap is None:
                view = replace(view, reason="decision_wait_flip")
            elif state.kind is LevelScreen.BOARD_READY and self._auto_missing:
                view = replace(view, action="tap")
            self._status.publish(view)
            if state.kind is LevelScreen.UNKNOWN and parse_event_menu(img, texts):
                self._trace_event(img, texts, None, view.reason)

            if state.kind in (LevelScreen.BOARD_READY, LevelScreen.AUTO_PLAY) and self._ensure_speed(texts):
                continue
            if state.kind is LevelScreen.AUTO_PLAY and self._auto_held:
                log.info("Auto-play on")
                self._auto_held, self._auto_seen, self._auto_misses = False, True, 0
            elif state.kind is LevelScreen.BOARD_READY and self._auto_held:
                self._auto_held, self._auto_misses = False, self._auto_misses + 1
                if self._auto_seen and self._auto_misses < config.AUTO_PLAY_RETRIES:
                    log.info("Holding the dice did not start auto-play this time; holding again")
                else:
                    log.info("Holding the dice did not start auto-play; rolling by taps")
                    self._auto_missing = True

            if state.kind in (LevelScreen.VICTORY, LevelScreen.DEFEAT):
                from roguebot.metrics import result_values
                self.result_values = result_values(texts, img, ocr=self.ocr)
                log.debug("Level result detected: %s", state.kind.value)
                self.device.tap(*state.tap)
                return state.kind

            if state.kind is LevelScreen.UNKNOWN:
                if time.monotonic() - last_known > config.UNKNOWN_SCREEN_TIMEOUT:
                    self._fail("Stuck on an unknown screen", img)
            else:
                last_known = time.monotonic()

            if state.tap:
                if _same_tap((state.kind, state.tap), last_tap):
                    repeats += 1
                else:
                    repeats, first_repeat = 1, time.monotonic()
                last_tap = (state.kind, state.tap)
                if repeats > config.MAX_REPEATED_TAPS and time.monotonic() - first_repeat > config.STUCK_TAP_SECONDS:
                    self._fail(f"Tapping {state.tap} on {state.kind.value} has no effect", img)
                if state.kind is LevelScreen.BOARD_READY and not self._auto_missing:
                    log.info("board_ready -> hold %s for auto-play", state.tap)
                    self.device.hold(*state.tap, config.AUTO_PLAY_HOLD)
                    self._auto_held = True
                else:
                    if state.kind is LevelScreen.EVENT:
                        self._trace_event(img, texts, state.tap, event_decision.reason if event_decision else view.reason)
                    log.info("%s -> tap %s", state.kind.value, state.tap)
                    self.device.tap(*state.tap)
                    if state.kind is LevelScreen.SKILL_PICK and self._planned_skill:
                        self._state.pending_skill = self._planned_skill
                    if state.kind in GUARDED:
                        self._guard.acted()
                    if state.kind is LevelScreen.FLIP_CARDS:
                        self._cards.tapped(state.tap)
                    if event_decision:
                        self._events.tapped(event_decision, texts)
            else:
                last_tap, repeats = None, 0  # screen changed on its own: the last tap worked
                time.sleep(config.POLL_INTERVAL)

    def _trace_event(self, img, texts, point, reason):
        menu = parse_event_menu(img, texts)
        if menu is None:
            return
        signature = (tuple(t.norm for t in texts), point, reason)
        if signature == self._last_event_trace:
            return
        self._last_event_trace = signature
        decision_journal.record(self._state, "event", "tap" if point else "wait", title=menu.title.text,
            offers=[{"option": t.text, "description": menu.descriptions[t]} for t in menu.enabled],
            point=point, reason=reason)
        try:
            folder = EVENT_DEBUG_DIR
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"event_{datetime.now():%Y%m%d_%H%M%S_%f}.png"
            if not cv2.imwrite(str(path), img):
                raise OSError("Could not save event capture")
            path.with_suffix(".json").write_text(json.dumps({"title": menu.title.text, "tap": point,
                "reason": reason, "hp": health_fraction(texts), "source": menu.source,
                "similarity": menu.score, "texts": [asdict(t) for t in texts]},
                ensure_ascii=False, indent=2), encoding="utf-8")
            for old in sorted(folder.glob("event_*.png"))[:-MAX_EVENT_CAPTURES]:
                old.unlink(missing_ok=True)
                old.with_suffix(".json").unlink(missing_ok=True)
            log.info("Event '%s': %s (capture: %s)", menu.title.text, reason, path)
        except OSError as exc:
            log.warning("Could not save the event capture: %s", exc)

    def _log_modifiers(self):
        log.info("Stage modifiers: %s", "; ".join(m.name for m in self._state.modifiers))
        log.info("Build rules: %s", ", ".join(sorted(self._state.rules.effects)))
        if self._state.rules.unknown:
            log.warning("Modifiers without a known rule: %s", ", ".join(self._state.rules.unknown))

    def _read_modifier_panel(self, texts, kind):
        """A resumed elite run missed its preview; read the labelled board icon once."""
        if (not self._inspect_modifiers or self._state.modifiers is not None or self._modifier_reads >= 2
                or kind not in (LevelScreen.BOARD_READY, LevelScreen.AUTO_PLAY, LevelScreen.EVENT)):
            return False
        if self._modifier_reads and time.monotonic() - self._modifier_tapped_at < 4:
            return False
        words = [t for t in texts if t.center[0] > 1100]
        icon = next((t for t in words if matches(t, labels.LEVEL_MODIFIERS, exact=True)), None)
        if icon is None:
            level = next((t for t in words if t.norm == "level"), None)
            modifier = next((t for t in words if t.norm == "modifiers"), None)
            if level and modifier and abs(level.center[0]-modifier.center[0]) < 100 and 0 < modifier.center[1]-level.center[1] < 100:
                icon = level
        if icon is None:
            return False
        self.device.tap(*icon.center)
        self._modifier_reads += 1
        self._modifier_tapped_at = time.monotonic()
        return True

    def _skill(self, card: SkillCard) -> Skill:
        return self.catalog.lookup(card.name, card.description, card.rarity, labels.active_language())

    @staticmethod
    def _skill_offer(cards: list[SkillCard]) -> tuple[tuple[str, str], ...]:
        return tuple(card.offer_key for card in cards)

    def _confirm_skill(self, kind: LevelScreen, texts) -> None:
        pending = self._state.pending_skill
        if pending is None or kind is LevelScreen.UNKNOWN:
            return
        if kind is LevelScreen.SKILL_PICK:
            cards = parse_skill_cards(texts)
            if not cards or self._skill_offer(cards) == pending.offer:
                return
        self._state.take(pending.skill, self.build)
        decision_journal.record(self._state, "skill_pick", "confirmed", selected=pending.skill.name)
        self._state.pending_skill = None

    def _pick_skill(self, texts) -> tuple[int, int] | None:
        """Tap point of the card the build wants, or of the reroll button. None if no card was read."""
        self._planned_skill = None
        cards = parse_skill_cards(texts)
        if not cards:
            return None
        skills = [self._skill(c) for c in cards]
        reroll = skill_reroll(texts)
        offer = self._skill_offer(cards)
        pending = self._state.pending_skill
        if pending is not None and pending.offer == offer:
            i = pending.index
        else:
            i = choose(skills, self.build, self._state, can_reroll=reroll is not None and not self._rerolled)
        decision_journal.record(self._state, "skill_pick", "reroll" if i is None else "pick",
            offers=[{"card": asdict(s), "evaluation": self._state.explanation(s, self.build)} for s in skills],
            selected=i, ranking=ranked(skills, self.build, self._state),
            can_reroll=reroll is not None and not self._rerolled, retry=pending is not None and pending.offer == offer)
        if i is None:
            log.info("No wanted skill in %s: rerolling", [s.name for s in skills])
            self._rerolled = True
            return reroll.center
        self._rerolled = False
        if self._state.priority_enemy_counter(skills[i]):
            log.info("Stage priority: %s to counter enemy healing and shields", skills[i].name)
        if i not in ranked(skills, self.build, self._state):
            log.warning("Mandatory fallback: %s; build focus remains %s", skills[i].name, focus(self.build, self._state))
        self._planned_skill = pending if pending is not None and pending.offer == offer else PendingSkill(skills[i], offer, i)
        log.info("Skill: %s (%s, %s, %s)", skills[i].name, skills[i].rarity, skills[i].damage_type or "-",
                 skills[i].role)
        log.info("Skill decision: %s", self._state.explanation(skills[i], self.build))
        log.info("Build focus: %s; learned families: %d", focus(self.build, self._state), len(self._state.owned))
        return config.SCREEN_SIZE[0] // 2, cards[i].tag.center[1] + config.SKILL_TAP_BELOW_RARITY

    def _shop(self, texts) -> None:
        """Use current run progress to reserve coins or finish shopping before the last boss."""
        Shopper(self.device, self.ocr, self.build, self._state, self._skill).buy(texts)

    def _fortune(self, texts) -> tuple[int, int] | None:
        """Fortune Teller: buy the balls in FORTUNE_BUYS order while the orbs allow, then the back arrow.
        A buy counts once the orb counter drops (a missed tap is tapped again); None = wait for it."""
        teller = parse_fortune_teller(texts)
        if self._fortune_tap:
            chance, orbs, tapped = self._fortune_tap
            if teller.orbs is not None and teller.orbs < orbs:
                self._fortune_bought.append(chance)
            elif time.monotonic() - tapped < config.FORTUNE_RETAP_AFTER:
                return None
            self._fortune_tap = None
        if teller.orbs is not None:
            for chance, times in config.FORTUNE_BUYS:
                if (self._fortune_bought.count(chance) < times and chance in teller.balls
                        and teller.orbs >= config.FORTUNE_COST[chance]):
                    log.info("Fortune Teller: %d%% ball (orbs %d)", chance, teller.orbs)
                    self._fortune_tap = chance, teller.orbs, time.monotonic()
                    return teller.balls[chance]
        return config.FORTUNE_TELLER_BACK

    def _ensure_speed(self, texts) -> bool:
        """Reach x4 without cycling past it. If x4 is locked, restore the highest observed speed."""
        speed = game_speed(texts)
        if speed is None or self._speed_locked:
            return False
        if speed >= self._speed_target:
            self._speed_from, self._speed_tries = None, 0
            return False
        if self._speed_from is not None:
            if speed < self._speed_from:
                self._speed_target = self._speed_from
                self._speed_from, self._speed_tries = None, 0
                log.info("x4 unavailable; restoring the highest observed speed x%d", self._speed_target)
            elif speed == self._speed_from:
                if time.monotonic() - self._speed_tapped_at < config.SPEED_RETRY_AFTER:
                    return False
                if self._speed_tries >= config.SPEED_RETRIES:
                    log.info("Speed did not change after %d taps; keeping x%d", self._speed_tries, speed)
                    self._speed_locked = True
                    return False
            else:
                self._speed_tries = 0
        log.info("Changing speed x%d toward x%d", speed, self._speed_target)
        self.device.tap(*config.SPEED_BUTTON)
        self._speed_from = speed
        self._speed_tries += 1
        self._speed_tapped_at = time.monotonic()
        return True

    def _fail(self, msg: str, img) -> None:
        DEBUG_DIR.mkdir(exist_ok=True)
        path = DEBUG_DIR / f"play_{time.strftime('%Y%m%d_%H%M%S')}.png"
        cv2.imwrite(str(path), img)
        raise PlayError(f"{msg} (screenshot: {path})")
