"""Bounded local evidence of intended and confirmed decisions, linked to a run."""

from dataclasses import asdict
from datetime import datetime, timezone
import logging
from pathlib import Path

from roguebot.persistence import write_json
from roguebot.skill_data import POLICY_VERSION

log = logging.getLogger(__name__)
DECISION_DIR = Path("debug/decisions")
MAX_RECORDS = 400


def record(state, screen, action, *, offers=(), **details):
    payload = {"run_id": state.run_id, "policy_version": POLICY_VERSION,
               "at": datetime.now(timezone.utc).isoformat(), "screen": screen, "action": action,
               "hp": state.context.hp, "survival_pressure": state.context.survival_pressure,
               "recent_hp_loss": state.context.recent_hp_loss, "revives_seen": state.context.revives_seen,
               "progress": asdict(state.run_progress), "owned": [asdict(s) for s in state.owned.values()],
               "modifiers": [m.name for m in state.modifiers or ()],
               "game_version": state.context.loadout.game_version, "offers": offers, **details}
    log.info("Decision alternatives: %s", payload)
    try:
        DECISION_DIR.mkdir(parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        write_json(DECISION_DIR / f"decision_{name}_{state.run_id}.json", payload)
        for old in sorted(DECISION_DIR.glob("decision_*.json"))[:-MAX_RECORDS]:
            old.unlink(missing_ok=True)
    except (OSError, TypeError, ValueError) as exc:
        log.warning("Could not save decision alternatives: %s", exc)
