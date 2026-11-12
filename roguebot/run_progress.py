"""Read the board's roll counter separately from HP, fight rounds and event attempts."""

from dataclasses import dataclass
from pathlib import Path
import re

import cv2

from roguebot.mode_screens import parse_power
from roguebot.vision import Text


_TEMPLATES = Path(__file__).parent / "templates"
_ELITE_SKULL = cv2.imread(str(_TEMPLATES / "elite_progress_skull.png"))
_FINAL_SKULL = cv2.imread(str(_TEMPLATES / "final_progress_skull.png"))
_SKULL_CONFIDENCE = .88


def _attack(texts: list[Text]) -> int | None:
    return next((power for t in texts if 760 <= t.center[0] <= 1075 and 40 <= t.center[1] <= 130
                 and (power := parse_power(t.norm)) is not None and power > 0), None)


def _second_boss_marker(img) -> int | None:
    strip = img[800:1240, 49:112]
    scores = cv2.matchTemplate(strip, _ELITE_SKULL, cv2.TM_CCOEFF_NORMED)
    markers = []
    for _ in range(2):
        _, score, _, (_, y) = cv2.minMaxLoc(scores)
        if score < _SKULL_CONFIDENCE:
            return None
        markers.append(y + 800 + _ELITE_SKULL.shape[0] // 2)
        scores[max(0, y - 45):y + 46] = 0
    return min(markers)


def _blue_fill(img, top, bottom) -> bool:
    b, g, r = cv2.split(img[top:bottom, 74:85].astype("int16"))
    return ((b > 145) & (g > 120) & (b - r > 45) & (g - r > 35)).mean() > .8


@dataclass
class RunProgress:
    rolls: int | None = None
    total: int | None = None
    starting_attack: int | None = None
    second_boss_marker: int | None = None
    after_second_boss: bool = False

    def observe(self, texts: list[Text]) -> None:
        for text in texts:
            if not (0 <= text.center[0] <= 200 and 1200 <= text.center[1] <= 1450):
                continue
            match = re.fullmatch(r"(\d+)\s*/\s*(\d+)", text.norm)
            if match:
                current, total = map(int, match.groups())
                if 10 <= total <= 999 and 0 <= current <= total:
                    if self.total != total or self.rolls is None or current >= self.rolls:
                        self.rolls, self.total = current, total

    def observe_board(self, img, texts: list[Text]) -> None:
        if self.rolls is None or self.after_second_boss:
            return
        if img is None or img.shape[:2] != (2560, 1440):
            return
        scores = cv2.matchTemplate(img[708:790, 36:124], _FINAL_SKULL, cv2.TM_CCOEFF_NORMED)
        if scores.max() < _SKULL_CONFIDENCE:
            return
        if self.starting_attack is None and self.rolls <= 1:
            self.starting_attack = _attack(texts)
        if self.second_boss_marker is None:
            self.second_boss_marker = _second_boss_marker(img)
        if (y := self.second_boss_marker) is not None:
            # Require fill beyond the whole second marker, on the board between fights.
            self.after_second_boss = _blue_fill(img, y - 38, y - 24) and _blue_fill(img, y + 25, y + 39)

    def ready_for_might(self, texts: list[Text], hp: float | None) -> bool:
        attack = _attack(texts)
        return (self.after_second_boss and hp is not None and hp >= .75 and self.starting_attack is not None
                and attack is not None and attack >= 1.25 * self.starting_attack)

    @property
    def unit(self) -> str:
        return "tiles" if self.total == 195 else "rolls"

    @property
    def remaining_rolls(self) -> int | None:
        if self.unit == "rolls" and self.total is not None and self.rolls is not None:
            return self.total - self.rolls
        return None

    @property
    def final_shop(self) -> bool:
        if self.rolls is None or self.total is None:
            return False
        if self.unit == "tiles":
            # The usual final window is the last sixth of a 30-roll board.
            # Use that share on the linear board, where one roll spans several tiles.
            return self.rolls * 6 >= self.total * 5
        return self.remaining_rolls <= 5
