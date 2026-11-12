"""Replay in-level actions for dice, ads and the Fortune Teller."""

import pytest

from roguebot import config, labels
from roguebot.vision import Text


def _play(monkeypatch, kinds, texts=()):
    """Run Player.play_level over a list of screen states (OCR reads `texts`); returns the device's (action, point) log."""
    import numpy as np
    from roguebot import play
    from roguebot.screens import LevelState
    monkeypatch.setattr(play.time, "sleep", lambda s: None)
    from roguebot.decisions import GUARDED
    states = iter(LevelState(k, t) for k, t in kinds for _ in range(2 if k in GUARDED else 1))
    monkeypatch.setattr(play, "classify_level_screen", lambda img, texts: next(states))

    class Dev:
        actions = []

        def screenshot(self):
            return np.zeros((10, 10, 3), np.uint8)

        def tap(self, x, y, settle=0):
            Dev.actions.append(("tap", (x, y)))

        def hold(self, x, y, seconds, settle=0):
            Dev.actions.append(("hold", (x, y)))

    class NoOcr:
        def read(self, img):
            return list(texts)
    play.Player(Dev(), NoOcr()).play_level()
    return Dev.actions


def test_red_dice_is_held_for_auto_play_then_left_alone(monkeypatch):
    from roguebot.screens import LevelScreen as S
    dice = config.DICE_BUTTON
    actions = _play(monkeypatch, [(S.BOARD_READY, dice), (S.AUTO_PLAY, None), (S.AUTO_PLAY, None),
                                  (S.SKILL_PICK, (720, 1052)), (S.AUTO_PLAY, None), (S.VICTORY, (720, 2220))])
    assert actions == [("hold", dice), ("tap", (720, 1052)), ("tap", (720, 2220))]


def test_auto_play_stopping_mid_level_is_turned_on_again(monkeypatch):
    from roguebot.screens import LevelScreen as S
    dice = config.DICE_BUTTON
    actions = _play(monkeypatch, [(S.BOARD_READY, dice), (S.AUTO_PLAY, None), (S.BOARD_READY, dice),
                                  (S.AUTO_PLAY, None), (S.VICTORY, (720, 2220))])
    assert actions == [("hold", dice), ("hold", dice), ("tap", (720, 2220))]


def test_without_auto_play_the_dice_is_tapped(monkeypatch):
    """Holding brought the red dice back (no auto-play on this game version): roll by taps from then on."""
    from roguebot.screens import LevelScreen as S
    dice = config.DICE_BUTTON
    actions = _play(monkeypatch, [(S.BOARD_READY, dice), (S.BOARD_READY, dice), (S.FIGHT, None),
                                  (S.BOARD_READY, dice), (S.VICTORY, (720, 2220))])
    assert actions == [("hold", dice), ("tap", dice), ("tap", dice), ("tap", (720, 2220))]


def test_a_missed_hold_is_retried_once_auto_play_worked_in_the_level(monkeypatch):
    """Seen live 2026-10-16: auto-play stopped after a shop, one hold brought the red dice back and the bot
    tapped for the rest of the level. Auto-play exists there: hold again, up to AUTO_PLAY_RETRIES misses."""
    from roguebot.screens import LevelScreen as S
    dice = config.DICE_BUTTON
    misses = [(S.BOARD_READY, dice)] * config.AUTO_PLAY_RETRIES
    actions = _play(monkeypatch, [(S.BOARD_READY, dice), (S.AUTO_PLAY, None), (S.BOARD_READY, dice),
                                  (S.AUTO_PLAY, None), *misses, (S.BOARD_READY, dice), (S.VICTORY, (720, 2220))])
    holds = 2 + config.AUTO_PLAY_RETRIES  # the misses reset when auto-play shows again
    assert actions == [("hold", dice)] * holds + [("tap", dice), ("tap", (720, 2220))]


def test_without_ads_x2_rewards_is_skipped_and_revive_waits(monkeypatch):
    from roguebot.screens import LevelScreen as S
    actions = _play(monkeypatch, [(S.REVIVE, (990, 1455)), (S.REVIVE, (990, 1455)), (S.DOUBLE_REWARD, (1150, 2220)),
                                  (S.VICTORY, (720, 2220))])
    assert actions == [("tap", (720, 2220))]  # no revive video, no x2 video: just Continue


def test_without_ads_a_revive_popup_that_stays_still_times_out(monkeypatch, tmp_path):
    """Review: waiting out the revive (no ads) must not wait forever if the popup never goes away."""
    from roguebot import play
    from roguebot.screens import LevelScreen as S
    clock = iter(range(1000))
    monkeypatch.setattr(play.time, "monotonic", lambda: next(clock) * 5.0)
    monkeypatch.setattr(play, "DEBUG_DIR", tmp_path)
    with pytest.raises(play.PlayError, match="unknown screen"):
        _play(monkeypatch, [(S.REVIVE, (990, 1455))] * 50)


def test_without_ads_the_level_end_continues_instead_of_doubling(monkeypatch):
    from roguebot.screens import LevelScreen as S
    labels.set_language("es")
    try:
        actions = _play(monkeypatch, [(S.DOUBLE_REWARD, (1150, 2220)), (S.VICTORY, (720, 2220))],
                        [Text("Continuar", 600, 2360, 840, 2400), Text("x2 Recompensas", 1000, 2200, 1300, 2240)])
    finally:
        labels.set_language(None)
    assert actions == [("tap", (720, 2380)), ("tap", (720, 2220))]  # Continuar, never the x2 ad button


_BALLS = {100: (421, 1626), 70: (775, 1626), 40: (1129, 1626)}


def _fortune_visit(monkeypatch, orbs_per_frame, clock_step=1.0):
    """Fortune Teller frames with these orb counts (None = a won skill popup in between), then the board and VICTORY.
    Returns the taps."""
    from roguebot import play
    from roguebot.screens import FortuneTeller, LevelScreen as S
    frames = [(S.CONTINUE, (717, 2349)) if o is None else (S.FORTUNE_TELLER, config.FORTUNE_TELLER_BACK)
              for o in orbs_per_frame]
    tellers = iter(FortuneTeller(o, _BALLS) for o in orbs_per_frame if o is not None)
    monkeypatch.setattr(play, "parse_fortune_teller", lambda texts: next(tellers))
    clock = iter(range(1000))
    monkeypatch.setattr(play.time, "monotonic", lambda: next(clock) * clock_step)
    actions = _play(monkeypatch, [*frames, (S.AUTO_PLAY, None), (S.VICTORY, (720, 2220))])
    return [p for a, p in actions if a == "tap"][:-1]  # without the VICTORY tap


def test_fortune_teller_buys_the_40_ball_once_then_the_70_one_three_times(monkeypatch):
    """Seen live 2026-10-21: 5 orbs = 40% (x2) + 3 x 70% (x1). A won skill shows a "tap to claim" popup."""
    taps = _fortune_visit(monkeypatch, [5, 3, None, 2, 1, None, 0])
    assert taps == [_BALLS[40], _BALLS[70], (717, 2349), _BALLS[70], _BALLS[70], (717, 2349),
                    config.FORTUNE_TELLER_BACK]


def test_fortune_teller_leaves_when_the_orbs_run_out(monkeypatch):
    taps = _fortune_visit(monkeypatch, [3, 1, 0])
    assert taps == [_BALLS[40], _BALLS[70], config.FORTUNE_TELLER_BACK]


def test_fortune_teller_skips_the_40_ball_without_orbs_for_it(monkeypatch):
    taps = _fortune_visit(monkeypatch, [1, 0])
    assert taps == [_BALLS[70], config.FORTUNE_TELLER_BACK]


def test_fortune_teller_stops_after_three_70_balls_with_orbs_left(monkeypatch):
    taps = _fortune_visit(monkeypatch, [9, 7, 6, 5, 4, 4])
    assert taps == [_BALLS[40], _BALLS[70], _BALLS[70], _BALLS[70], config.FORTUNE_TELLER_BACK,
                    config.FORTUNE_TELLER_BACK]  # a missed back tap never buys again


def test_fortune_teller_waits_for_the_orbs_then_taps_a_missed_ball_again(monkeypatch):
    """A frame right after the tap can still show the old count: wait, never buy twice; still the same count
    after FORTUNE_RETAP_AFTER: the tap did not land, tap again."""
    taps = _fortune_visit(monkeypatch, [2, 2, 2, 2, 2, 2, 0], clock_step=0.5)
    assert taps == [_BALLS[40], _BALLS[40], config.FORTUNE_TELLER_BACK]


def test_fortune_teller_with_unreadable_orbs_leaves(monkeypatch):
    from roguebot import play
    from roguebot.screens import FortuneTeller, LevelScreen as S
    monkeypatch.setattr(play, "parse_fortune_teller", lambda texts: FortuneTeller(None, _BALLS))
    actions = _play(monkeypatch, [(S.FORTUNE_TELLER, config.FORTUNE_TELLER_BACK), (S.VICTORY, (720, 2220))])
    assert actions[0] == ("tap", config.FORTUNE_TELLER_BACK)
