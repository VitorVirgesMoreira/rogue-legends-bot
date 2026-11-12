"""An opt-in farm objective. Explicit stage and star requests are never changed."""

from dataclasses import dataclass, field
import json
from roguebot.skill_data import VERSION

OBJECTIVES = ("reliable", "gold_per_energy", "gold_per_minute", "adventure_journals", "specialization_journals")


@dataclass
class FarmPolicy:
    target: int | None = None
    losses: int = 0
    tried: set[int] = field(default_factory=set)
    evidence: dict | None = field(default=None, init=False)

    def choose(self, history: list[dict], mode: str, profile: str, latest: int,
               *, objective="reliable", loadout=None, build_config=None) -> int:
        if objective not in OBJECTIVES:
            raise ValueError("bad_farm_objective")
        self.evidence = None
        if self.target is not None and self.target >= latest:
            self.target, self.losses = None, 0
            self.tried.clear()
        candidates = []
        for row in history:
            level = row.get("level")
            if row.get("mode") != mode or row.get("profile") != profile or type(level) is not int or not 1 <= level < latest:
                continue
            if row.get("rules_version", VERSION) != VERSION or loadout is not None and json.dumps(
                    row.get("loadout"), sort_keys=True) != json.dumps(loadout, sort_keys=True):
                continue
            if build_config is not None and row.get("build_config") != build_config:
                continue
            if self.tried and self.target is not None and level > self.target:
                continue
            if row.get("runs", 0) < 3 or row.get("win_rate", 0) < .8 or level in self.tried:
                continue
            energy = row.get("rewards_per_energy", {})
            minute = row.get("rewards_per_minute", {})
            if objective.startswith("gold_"):
                first, second = (energy, minute) if objective == "gold_per_energy" else (minute, energy)
                sample_key = "reward_energy_samples" if objective == "gold_per_energy" else "reward_samples"
                if "gold" not in first or row.get(sample_key, {}).get("gold", row["runs"]) < 3:
                    continue
                reward = (first["gold"], second.get("gold", -1.))
            elif objective == "reliable":
                reward = (row["win_rate"],)
            elif objective in energy and row.get("reward_energy_samples", {}).get(objective, row["runs"]) >= 3:
                reward = (energy[objective], minute.get(objective, -1.))
            else:
                continue
            candidates.append(((*reward, row["win_rate"], -row.get("seconds_per_run", float("inf")), level), row))
        if candidates:
            self.evidence = max(candidates, key=lambda item: item[0])[1]
            level = self.evidence["level"]
            if level != self.target:
                self.target, self.losses = level, 0
        elif self.target is None:
            self.target = max(1, latest - 1)
        return self.target

    def observe(self, victory: bool) -> bool:
        self.losses = 0 if victory else self.losses + 1
        if self.losses < 2 or self.target is None:
            return False
        self.tried.add(self.target)
        self.losses = 0
        if self.target <= 1:
            return True  # stop instead of burning all energy on an unwinnable stage
        self.target -= 1
        return False
