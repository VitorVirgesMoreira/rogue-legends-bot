"""Bounded, local combat history. No uploads and no estimated rewards."""

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
from threading import Lock
import uuid
import math

import cv2

from roguebot import labels
from roguebot.mode_screens import parse_power
from roguebot.persistence import write_json
from roguebot.settings import DATA_DIR
from roguebot.skill_data import POLICY_VERSION, VERSION
from roguebot.vision import find

log = logging.getLogger(__name__)
RUNS_PATH = DATA_DIR / "run_history.json"
MAX_RECORDS = 2000
_WRITE_LOCK = Lock()
_GOLD_ICON = cv2.imread(str(Path(__file__).parent / "templates" / "result_gold.png"))


@dataclass
class RunRecord:
    mode: str
    profile: str
    result: str
    seconds: float
    level: int | None = None
    energy: int | None = None
    damage: float | None = None
    rewards: dict[str, float] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    loadout: dict = field(default_factory=dict)
    build_config: dict = field(default_factory=dict)
    rules_version: str = VERSION
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    policy_version: str = POLICY_VERSION
    progress: dict = field(default_factory=dict)
    revives_seen: int = 0


def _nonnegative_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


@dataclass
class RewardSamples:
    total: float = 0.0
    samples: int = 0
    seconds: float = 0.0
    energy_total: float = 0.0
    energy: int = 0
    energy_samples: int = 0

    def add(self, amount: float, seconds: float, energy: int) -> None:
        self.total += amount
        self.samples += 1
        self.seconds += seconds
        if energy > 0:
            self.energy_total += amount
            self.energy += energy
            self.energy_samples += 1


class History:
    def __init__(self, path: Path | None = None):
        self.path = RUNS_PATH if path is None else path

    def read(self) -> list[dict]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            return [r for r in data[-MAX_RECORDS:] if isinstance(r, dict) and
                    isinstance(r.get("id"), str) and _nonnegative_number(r.get("seconds"))]
        except (OSError, ValueError):
            return []

    def record(self, record: RunRecord) -> None:
        try:
            with _WRITE_LOCK:
                values = self.read()
                if all(row["id"] != record.id for row in values):
                    write_json(self.path, (values + [asdict(record)])[-MAX_RECORDS:])
        except OSError as exc:
            # A disk problem after a victory must not cause another energy spend.
            log.warning("Could not save combat history: %s", exc)

    def summary(self) -> list[dict]:
        groups = {}
        for row in self.read():
            if row.get("result") == "abandoned":
                continue
            mode, level, profile = row.get("mode"), row.get("level"), row.get("profile")
            rules_version = row.get("rules_version")
            policy_version = row.get("policy_version", "legacy")
            loadout, build_config = row.get("loadout", {}), row.get("build_config", {})
            if (not isinstance(mode, str) or not isinstance(profile, str)
                    or level is not None and type(level) is not int
                    or rules_version is not None and not isinstance(rules_version, str)
                    or not isinstance(loadout, dict) or not isinstance(build_config, dict)):
                continue
            identity = (mode, level, profile, rules_version, str(policy_version),
                        json.dumps(loadout, sort_keys=True), json.dumps(build_config, sort_keys=True))
            if identity not in groups:
                groups[identity] = {"mode": mode, "level": level, "profile": profile, "rules_version": rules_version,
                                    "policy_version": policy_version,
                                    "loadout": loadout, "build_config": build_config, "runs": 0, "wins": 0,
                                    "seconds": 0., "energy": 0, "energy_known": True, "damage": [],
                                    "samples": defaultdict(RewardSamples)}
            group = groups[identity]
            group["runs"] += 1
            group["wins"] += row.get("result") == "victory"
            group["seconds"] += row["seconds"]
            energy = row.get("energy")
            if type(energy) is not int or energy <= 0:
                energy = 0
                group["energy_known"] = False
            group["energy"] += energy
            if _nonnegative_number(row.get("damage")):
                group["damage"].append(row["damage"])
            rewards = row.get("rewards")
            if isinstance(rewards, dict):
                for currency, amount in rewards.items():
                    if _nonnegative_number(amount):
                        group["samples"][currency].add(amount, row["seconds"], energy)
        rows = []
        for group in groups.values():
            group["win_rate"] = group["wins"] / group["runs"]
            group["seconds_per_run"] = group["seconds"] / group["runs"]
            damage = group.pop("damage")
            group["mean_damage"] = sum(damage) / len(damage) if damage else None
            samples = group.pop("samples")
            group["rewards"] = {key: sample.total for key, sample in samples.items()}
            group["reward_samples"] = {key: sample.samples for key, sample in samples.items()}
            group["reward_energy_samples"] = {key: sample.energy_samples for key, sample in samples.items()
                                              if sample.energy_samples}
            group["rewards_per_energy"] = {key: sample.energy_total / sample.energy
                                           for key, sample in samples.items() if sample.energy}
            group["rewards_per_minute"] = {key: sample.total * 60 / sample.seconds
                                           for key, sample in samples.items() if sample.seconds}
            rows.append(group)
        return rows


def build_signature(build):
    return {"nature": build.nature, "order": list(build.order), "support_every": build.support_every,
            "strategy": build.strategy}


def _result_gold(img, texts, ocr):
    if img is None or img.shape[:2] != (2560, 1440):
        return None
    outcome = find(texts, labels.VICTORY) or find(texts, labels.DEFEAT)
    button = find(texts, labels.CONTINUE, exact=True) or find(texts, labels.CONFIRM, exact=True)
    if outcome is None or button is None:
        return None
    top, bottom = max(1000, outcome.y2 + 350), min(2110, button.y1 - 120)
    if bottom - top < _GOLD_ICON.shape[0]:
        return None
    scores = cv2.matchTemplate(img[top:bottom, 100:1340], _GOLD_ICON, cv2.TM_CCOEFF_NORMED)
    _, confidence, _, (x, y) = cv2.minMaxLoc(scores)
    if confidence < .88:
        return None
    center_x = 100 + x + _GOLD_ICON.shape[1] // 2
    icon_bottom = top + y + _GOLD_ICON.shape[0]
    region = (center_x - 72, icon_bottom - 6, center_x + 72, icon_bottom + 73)
    quantities = _gold_quantities(texts, region)
    if not quantities and ocr is not None:
        quantities = _gold_quantities(ocr.read(img, region), region)
    return next(iter(quantities)) if len(quantities) == 1 else None


def _gold_quantities(texts, region):
    x1, y1, x2, y2 = region
    return {parse_power(match[1]) for t in texts if x1 <= t.center[0] <= x2 and y1 <= t.center[1] <= y2
            and (match := re.fullmatch(r"[x×]?\s*(\d+(?:[.,]\d+)?\s*[kmb]?)", t.norm))}


def result_values(texts, img=None, *, ocr=None) -> tuple[float | None, dict[str, float]]:
    """Only explicitly labelled result values, never HP, power or a shop price."""
    damage, rewards = None, {}
    labels = {"adventure journals": "adventure_journals", "specialization journals": "specialization_journals",
              "diarios de aventura": "adventure_journals", "diarios de especializacion": "specialization_journals",
              "diarios de especializacao": "specialization_journals"}
    for text in texts:
        match = re.fullmatch(r"(total damage|damage dealt|dano infligido)\s*[:：]?\s*(\d+(?:[.,]\d+)?)\s*([kmb]?)", text.norm)
        if match:
            damage = float(match[2].replace(",", ".")) * {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[match[3]]
        for label, currency in labels.items():
            match = re.fullmatch(re.escape(label) + r"\s*[:：x×]?\s*(\d+)", text.norm)
            if match:
                rewards[currency] = float(match[1])
    gold = _result_gold(img, texts, ocr)
    if gold is not None:
        rewards["gold"] = gold
    return damage, rewards
