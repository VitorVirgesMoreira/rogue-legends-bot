"""Gated Chaos/Conquest entry and pure guide policies.

Active screens have not been available on the validation account. Navigation
can inspect them, but spending an attack/Chaos Energy stays disabled until real
fixtures establish their counters and confirmation screens.
"""

from dataclasses import dataclass
import re

from roguebot import config, labels
from roguebot.game_locale import is_term
from roguebot.report import Report
from roguebot.screens import parse_lobby
from roguebot.vision import find

CHAOS_COST, CHAOS_CAP, CHAOS_REGEN_SECONDS = 10, 30, 1200


@dataclass(frozen=True)
class ChaosPath:
    name: str
    intensity: str
    modifiers: tuple[str, ...] = ()
    reward_value: float | None = None  # supplied objective value, not a guessed drop


def chaos_risk(path, build):
    primary = "fire" if build.profile in ("burn", "burn_dot") else build.profile
    risks = {"cursed fate": 2, "price of knowledge": 3, "bloodletting": 3, "sudden death": 3,
             "cleansing fury": 2 if build.strategy == "dot" or build.profile == "burn_dot" else 1,
             "crit resistant": 3 if build.strategy == "crit" or build.profile == "burn" else 0,
             "companion guard": 3 if build.strategy == "pet" else 0,
             "skill guard": 3 if build.strategy == "skill" else 1,
             "weapon guard": 3 if build.strategy in ("combo", "counter", "cleave") else 1,
             "draining effort": 3 if build.strategy == "ultimate" else 1,
             "hardened": 3, "regeneration": 2, "bloodpact legion": 2, "cursed campfire": 2}
    down = {"fire": "fire down, poison up", "ice": "ice down, wound up", "lightning": "lightning down, ice up",
            "venom": "poison down, shuriken up", "shuriken": "shuriken down, fire up", "bleed": "wound down, lightning up"}
    risk = 0.
    for modifier in path.modifiers:
        name = modifier.strip().lower()
        risk += 8 if name == down.get(primary) else risks.get(name, 1)
    return risk


def choose_chaos_path(paths, build):
    """Compatibility first, known reward objective on ties; no paid rerolls."""
    return min(range(len(paths)), key=lambda i: (chaos_risk(paths[i], build),
        -(paths[i].reward_value or 0), i)) if paths else None


@dataclass(frozen=True)
class ConquestTarget:
    name: str
    power: int
    crowns: int  # current displayed value, already decayed by previous defeats


def choose_conquest_target(own_power, targets):
    """Conservative affordable fight, highest current crowns, weakest on ties.

    Power is not a measured win probability. Targets stronger than the player
    are excluded; the game's >3x zero-crown rule is an additional hard limit.
    """
    if own_power is None or own_power <= 0:
        return None
    eligible = [i for i, target in enumerate(targets) if 0 < target.power <= own_power
                and target.power <= 3 * own_power and target.crowns > 0]
    return max(eligible, key=lambda i: (targets[i].crowns, -targets[i].power, -i)) if eligible else None


def season_closed(texts):
    return any(re.search(r"season (?:is )?over|until next season|isn't active|temporada encerrada|"
                         r"proxima temporada|temporada terminada|no esta activ", t.norm) for t in texts)


class EventMode:
    def __init__(self, device, ocr, nav, mode):
        self.device, self.ocr, self.nav, self.mode = device, ocr, nav, mode

    def _read(self):
        return self.ocr.read(self.device.screenshot())

    def _enter(self, values):
        # Text positions must agree in consecutive fresh frames.
        first = self._read()
        candidates = [t for t in first if re.sub(r"[^a-z]", "", t.norm) in values]
        second = self._read()
        for target in candidates:
            current = next((t for t in second if t.norm == target.norm and
                           abs(t.center[0]-target.center[0]) < 20 and abs(t.center[1]-target.center[1]) < 20), None)
            if current:
                self.device.tap(*current.center)
                self.device.wait(config.UI_SETTLE)
                return True
        return False

    def run(self, *, dry_run=False):
        self.nav.go_to_lobby()
        self.nav.detect_language()
        if self.mode == "conquest":
            if not self._enter({"guild", "guiid", "gremio", "guilda"}):
                return self._report("mode_unavailable")
            if not self._enter({"wars", "guerras"}):
                return self._report("mode_unavailable")
            if season_closed(self._read()):
                return self._report("mode_season_closed")
            if not self._enter({"guildconquest", "conquistadeguilda", "conquistadaguilda", "conquistadelgremio"}):
                return self._report("mode_unavailable")
            if season_closed(self._read()):
                return self._report("mode_season_closed")
        else:
            texts = self._read()
            lobby = parse_lobby(texts)
            if lobby is None:
                return self._report("mode_unavailable")
            button = find(texts, labels.MODES_BUTTON, exact=True)
            if button is None:
                return self._report("mode_unavailable")
            self.device.tap(*button.center)
            self.device.wait(config.UI_SETTLE)
            names = {"chaosrealm", "reinodocaos", "reinodelcaos"}
            if not self._enter(names):
                return self._report("mode_unavailable")
        return Report(dry_run=True) if dry_run else self._report("mode_fixture_needed")

    def _report(self, reason):
        self.nav.go_to_lobby()
        return Report(mode=self.mode, mode_reason=reason)
