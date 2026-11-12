"""Observed account facts, provenance and conservative strategy suggestions."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json

from roguebot.combat_context import Loadout
from roguebot.persistence import write_json
from roguebot.settings import DATA_DIR, load
from roguebot.skill_data import key

SCAN_PATH = DATA_DIR / "account_scan.json"
SCAN_HISTORY_PATH = DATA_DIR / "account_scan_history.json"
CHECKPOINT_PATH = DATA_DIR / "account_scan_checkpoint.json"


@dataclass
class AccountSnapshot:
    account: str = ""
    loadout: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    inventory: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    profile: str = "custom"
    strategy: str = "balanced"
    reason: str = "scan_strategy_unknown"
    completed: list[str] = field(default_factory=list)
    status: str = "in_progress"
    progress: dict = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def merge(self, current: Loadout, facts: dict, *, previous_account=""):
        same = not previous_account or previous_account == self.account
        values = asdict(current if same else Loadout(game_version=""))
        for name, value in self.loadout.items():
            if name == "stats":
                values[name] = {**dict(values.get(name, ())), **dict(value)}
            elif name == "tree_skills" and self.loadout.get("tree_skills_partial"):
                values[name] = tuple(dict.fromkeys((*values.get(name, ()), *value)))
            else:
                values[name] = value
        result = dict(facts) if same else {}
        for name, value in self.facts.items():
            if isinstance(value, dict):
                result[name] = {**result.get(name, {}), **value}
            else:
                result[name] = value
        return Loadout.from_dict(values), result


def suggest_strategy(snapshot):
    weapon = key(snapshot.loadout.get("weapon", ""))
    line = {"emberstaff": ("burn", "skill"), "infernospire": ("burn", "skill"),
            "stormstaff": ("lightning", "skill"), "tempestwrath": ("lightning", "skill"),
            "glacialhammer": ("ice", "skill"), "unforgivingfrost": ("ice", "skill"),
            "plagueblade": ("venom", "dot"), "blightmaker": ("venom", "dot"),
            "katana": ("shuriken", "crit"), "blossomwhisper": ("shuriken", "crit"),
            "vampiricedge": ("custom", "combo"), "crimsonhunger": ("bleed", "combo")}.get(weapon)
    if line:
        snapshot.profile, snapshot.strategy = line
        snapshot.reason = "scan_strategy_weapon"


def save_snapshot(snapshot):
    data = asdict(snapshot)
    write_json(SCAN_PATH, data)
    rows = [row for row in scan_history()
            if (row.get("account"), row.get("at")) != (snapshot.account, snapshot.at)]
    write_json(SCAN_HISTORY_PATH, (rows + [data])[-30:])


def load_snapshot():
    return load(SCAN_PATH)


def scan_history():
    try:
        rows = json.loads(SCAN_HISTORY_PATH.read_text(encoding="utf-8"))
        return [row for row in rows[-30:] if isinstance(row, dict)] if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def checkpoint(snapshot):
    snapshot.at = datetime.now(timezone.utc).isoformat()
    write_json(CHECKPOINT_PATH, asdict(snapshot))


def cached_snapshot(account, *, fresh=False, now=None):
    now = now or datetime.now(timezone.utc)
    best = None
    best_age = float("inf")
    for path in (SCAN_PATH, CHECKPOINT_PATH):
        try:
            candidate = AccountSnapshot(**load(path))
            if candidate.account != account or not account:
                continue
            if any(not isinstance(value, dict) for value in (
                    candidate.loadout, candidate.facts, candidate.evidence, candidate.inventory, candidate.progress)):
                continue
            if any(not isinstance(values, list) or any(not isinstance(value, str) for value in values)
                   for values in (candidate.completed, candidate.warnings)):
                continue
            age = (now - datetime.fromisoformat(candidate.at)).total_seconds()
            # A scan stopped at the tree can resume the pending section the same day.
            # Completed scans still expire after ten minutes.
            sections = {"equipment", "heroes", "mounts", "sentinels", "pets", "resources", "version"}
            tree_pending = candidate.status == "in_progress" and set(candidate.completed) == sections
            max_age = 86400 if tree_pending else 600
            if fresh and candidate.status == "complete":
                continue
            if 0 <= age <= max_age and age < best_age:
                best, best_age = candidate, age
        except (ValueError, TypeError):
            continue
    return best
