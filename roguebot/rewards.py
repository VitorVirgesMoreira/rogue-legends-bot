"""Claim only named, already-earned rewards; prices and paid tracks are excluded."""

from dataclasses import dataclass
import re
import time

import cv2

from roguebot import labels
from roguebot.event_rules import PREMIUM_CURRENCY
from roguebot.screens import parse_lobby
from roguebot.vision import Text, matches

EVENT_TITLES = {
    "quests", "misiones", "missoes", "carnival", "carnaval", "7-day carnival", "carnaval de 7 dias",
    "sticker album", "album de pegatinas", "album de figurinhas", "album de adesivos",
    "celestial fortunes", "fortunas celestiais", "fortunas celestiales", "frozen riches", "riquezas congeladas",
    "gifts of nature", "presentes da natureza", "regalos de la naturaleza", "chest rush", "corrida dos baus",
    "egg rush", "corrida dos ovos", "wish challenge", "desafio de desejos", "party expedition",
    "expedicao em grupo", "expedicion en grupo", "hero event", "evento de heroi", "evento de heroe",
    "daily login", "login diario", "inicio de sesion diario",
}
CLAIMS = {"claim", "claim all", "reclamar", "reclamar todo", "resgatar", "resgatar tudo", "coletar", "coletar tudo", "reivindicar", "reivindicar tudo"}
PAID = re.compile(r"\b(?:buy|purchase|price|comprar|preco|precio|premium|luxury|advanced|vip|unlock|desbloquear|oferta|offer|top up|recarga)\b|[$€£]|\b\d+[.,]\d{2}\b")


@dataclass(frozen=True)
class RewardClaim:
    title: str
    button: Text

    def matches(self, other: "RewardClaim | None") -> bool:
        return (other is not None and self.title == other.title and self.button.norm == other.button.norm
                and all(abs(a - b) <= 15 for a, b in zip(self.button.center, other.button.center)))


def parse_claim(img, texts) -> RewardClaim | None:
    # A lobby has Quests/Carnival labels too; those are entries, not claim pages.
    if parse_lobby(texts) is not None:
        return None
    title = next((t for t in texts if t.norm in EVENT_TITLES and t.center[1] < 650), None)
    if title is None:
        return None
    for button in texts:
        if button.norm not in CLAIMS or not 250 < button.center[0] < 1200 or button.center[1] <= title.center[1] + 80:
            continue
        # Associate the same row/lane only, so an unrelated shop price cannot
        # authorize or conceal a claim. Premium headers apply down their lane.
        lane = [t for t in texts if abs(t.center[0]-button.center[0]) < 160 and
                title.center[1] < t.center[1] <= button.y2 + 75]
        if any(PAID.search(t.norm) for t in lane):
            continue
        near = [t for t in texts if abs(t.center[1]-button.center[1]) < 100 and abs(t.center[0]-button.center[0]) < 240]
        if any(PREMIUM_CURRENCY.search(t.norm)
               or re.search(r"\b(?:cost|custo|costa|preco|precio)\b.*\d", t.norm) for t in near):
            continue
        x1, y1, x2, y2 = button.x1-35, button.y1-25, button.x2+35, button.y2+25
        patch = img[max(0,y1):min(img.shape[0],y2), max(0,x1):min(img.shape[1],x2)]
        if not patch.size:
            continue
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        # Grey disabled claims do not count. At least a colored button exists.
        if ((hsv[...,1] > 80) & (hsv[...,2] > 100)).mean() < .15:
            continue
        return RewardClaim(title.norm, button)
    return None


class RewardCollector:
    def __init__(self):
        self.previous = None
        self.last_tap = None
        self.sent_at = 0.
        self.count = 0
        self.tries = 0

    def choose(self, img, texts, now=None) -> tuple[int, int] | None:
        now = time.monotonic() if now is None else now
        claim = parse_claim(img, texts)
        if claim is None or self.count >= 40:
            self.previous = None
            return None
        same = claim.matches(self.previous)
        self.previous = claim
        pending_same = claim.matches(self.last_tap)
        if not pending_same:
            self.tries = 0
        if not same or pending_same and (now-self.sent_at < 4 or self.tries >= 2):
            return None
        return claim.button.center

    def tapped(self, point, now=None):
        self.last_tap = self.previous
        self.sent_at = time.monotonic() if now is None else now
        self.count += 1
        self.tries += 1


def collect_events(device, ocr, nav):
    """Visit known free-reward pages. Unknown layouts stay untouched."""
    entries = (("quests", "misiones", "missoes"), ("carnival", "carnaval"),
               ("sticker album", "album", "album de figurinhas", "album de adesivos"))
    count = 0
    nav.go_to_lobby()
    for names in entries:
        texts = ocr.read(device.screenshot())
        if parse_lobby(texts) is None:
            break
        entry = next((t for t in texts if t.norm in names and (t.center[0] < 180 or t.center[0] > 1250)), None)
        if entry is None:
            continue
        device.tap(*entry.center)
        collector, empty = RewardCollector(), 0
        for _ in range(90):
            img = device.screenshot()
            texts = ocr.read(img)
            banner = next((t for t in texts if matches(t, labels.TAP_TO_CLAIM)), None)
            if banner:
                device.tap(*banner.center)
                empty = 0
            elif point := collector.choose(img, texts):
                device.tap(*point)
                collector.tapped(point)
                count += 1
                empty = 0
            else:
                empty += 1
                if empty >= 5:
                    break
            device.wait(.6)
        nav.go_to_lobby()
    return count
