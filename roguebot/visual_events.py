"""Bounded title-image fallback, calibrated from this project's own event captures."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import json

import cv2
import numpy as np

from roguebot import labels
from roguebot.vision import Text

ROOT = Path(__file__).parent / "templates" / "event_titles"
REGION = (160, 1335, 1280, 1470)
MIN_SCORE = 0.94
MIN_MARGIN = 0.05


@dataclass(frozen=True)
class TitleMatch:
    title: str
    language: str
    score: float
    margin: float

    @property
    def text(self) -> Text:
        return Text(self.title, 200, 1360, 1240, 1440)


@lru_cache(maxsize=1)
def _templates():
    entries = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))
    return [(entry, cv2.imread(str(ROOT / entry["file"]), cv2.IMREAD_GRAYSCALE)) for entry in entries]


def match_event_title(img: np.ndarray) -> TitleMatch | None:
    """A visual title supplies identity only. Options/effects must still be readable."""
    if img.shape[:2] != (2560, 1440):
        return None
    x1, y1, x2, y2 = REGION
    crop = cv2.cvtColor(img[y1-8:y2+8, x1-8:x2+8], cv2.COLOR_BGR2GRAY)
    crop = cv2.resize(crop, None, fx=.5, fy=.5, interpolation=cv2.INTER_AREA)
    found = []
    for entry, template in _templates():
        if template is None or labels.active_language() not in (None, entry["language"]):
            continue
        scores = cv2.matchTemplate(crop, template, cv2.TM_CCOEFF_NORMED)
        found.append((float(scores.max()), entry))
    found.sort(key=lambda item: item[0], reverse=True)
    if not found:
        return None
    best, entry = found[0]
    # Two captures of the same title may coexist; only a different identity is a rival.
    rival = next((score for score, other in found[1:] if other["title"] != entry["title"]), 0)
    if best < MIN_SCORE or best - rival < MIN_MARGIN:
        return None
    return TitleMatch(entry["title"], entry["language"], best, best-rival)
