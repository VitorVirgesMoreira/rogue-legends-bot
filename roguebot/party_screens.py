"""Recognize the Party Expedition event without treating its store or spin as gameplay."""

from dataclasses import dataclass
import re

from roguebot.screens import LevelScreen, parse_lobby
from roguebot.vision import Text
from roguebot import labels
from roguebot.vision import matches
from roguebot.game_locale import TERMS, contains_term, is_term, language

TICKET_REGION = (1050, 40, 1175, 125)
TICKET_OCR_REGION = (960, 20, 1200, 155)  # include enough surrounding pixels for OCR to detect a single digit


def _exact(texts: list[Text], value: str) -> Text | None:
    concept = next((name for name, values in TERMS.items() if value in values.get("en", ())), None)
    if concept:
        return next((t for t in texts if is_term(t.norm, concept)), None)
    return next((t for t in texts if t.norm == value), None)


def event_header(texts: list[Text]) -> bool:
    return any(is_term(t.norm, "party") and t.center[1] < 180 and t.center[0] < 950 for t in texts)


def expedition_entry(texts: list[Text]) -> tuple[int, int] | None:
    """Lobby right-hand event icon; disambiguate the unrelated Gear Up Party promotion."""
    if parse_lobby(texts) is None:
        return None
    words = [t for t in texts if t.center[0] > 1100 and 300 < t.center[1] < 2000]
    full = _exact(words, "party expedition")
    if full:
        return full.center
    party = _exact(words, "party")
    expedition = _exact(words, "expedition")
    if party and expedition and abs(party.center[0] - expedition.center[0]) < 100 and 0 < abs(expedition.center[1] - party.center[1]) < 100:
        return party.center
    return None


@dataclass(frozen=True)
class ExpeditionTeam:
    stage: int
    total: int
    match: Text
    tickets: int | None


def event_tickets(texts: list[Text]) -> int | None:
    x1, y1, x2, y2 = TICKET_REGION
    return next((int(t.norm) for t in texts if t.norm.isdigit()
                 and x1 <= t.center[0] <= x2 and y1 <= t.center[1] <= y2), None)


def parse_team(texts: list[Text]) -> ExpeditionTeam | None:
    if _exact(texts, "party expedition") is None or is_clear_reward(texts):
        return None
    match = next((t for t in texts if is_term(t.norm, "match") and t.center[1] > 2200), None)
    stage = next((m for t in texts if t.center[1] < 400 and (m := re.fullmatch(r"(?:stage|fase|etapa|estagio)\s*(\d+)\s*/\s*(\d+)", t.norm))), None)
    if not match or not stage or not 1 <= int(stage.group(1)) <= int(stage.group(2)):
        return None
    return ExpeditionTeam(int(stage.group(1)), int(stage.group(2)), match, event_tickets(texts))


def home_entry(texts: list[Text]) -> tuple[int, int] | None:
    if _exact(texts, "party expedition") is None or parse_team(texts):
        return None
    # The center-bottom castle icon, not the large banner or the Exchange Shop to its right.
    words = [t for t in texts if 570 < t.center[0] < 850 and 1900 < t.center[1] < 2200]
    full = _exact(words, "party expedition")
    if full:
        return full.center
    party, expedition = _exact(words, "party"), _exact(words, "expedition")
    if party and expedition and 0 < abs(expedition.center[1] - party.center[1]) < 100:
        return party.center
    return None


def is_codex(texts: list[Text]) -> bool:
    return _exact(texts, "skill codex") is not None


def expedition_complete(texts: list[Text]) -> bool:
    return event_header(texts) and any(t.norm in ("all stages cleared!", "all stages completed!",
        "todas as fases concluidas!", "todas las etapas completadas!") for t in texts)


def team_status(texts):
    """Only explicitly labelled team facts; an unlabeled fraction may be tickets."""
    hp, roles, heroes = [], [], []
    role_names = {"guardian": "guardian", "guardiao": "guardian", "guardiao(a)": "guardian",
                  "support": "support", "apoio": "support", "suporte": "support",
                  "striker": "striker", "atacante": "striker"}
    for t in texts:
        if not 350 < t.center[1] < 2200:
            continue
        m = re.fullmatch(r"(?:hp|pv)\s*[:：]?\s*(\d+)\s*/\s*(\d+)", t.norm)
        if m and 0 <= int(m[1]) <= int(m[2]) and int(m[2]) > 0:
            hp.append(int(m[1])/int(m[2]))
        if t.norm in role_names:
            roles.append(role_names[t.norm])
        if t.norm in ("illumina", "kitsura", "corvus", "draco", "rowan", "hilda", "kael"):
            heroes.append(t.norm)
    return tuple(hp), tuple(roles), tuple(heroes)


def party_language(texts: list[Text]) -> str | None:
    return language(texts, "party") or language(texts, "codex") or ("en" if expedition_entry(texts) else None)


def is_clear_reward(texts: list[Text]) -> bool:
    return bool(_exact(texts, "party expedition")
                and any(re.fullmatch(r"(?:stage|fase|etapa|estagio)\s*\d+\s*(?:cleared|concluid[ao]|completad[ao])[!.]?", t.norm) for t in texts))


def clear_reward(texts: list[Text]) -> Text | None:
    return _exact(texts, "tap anywhere to claim") if is_clear_reward(texts) else None


def expedition_result(texts: list[Text]) -> tuple[LevelScreen, Text] | None:
    if _exact(texts, "party expedition") is None:
        return None
    result = next((LevelScreen.VICTORY if matches(t, labels.VICTORY) else LevelScreen.DEFEAT
                   for t in texts if matches(t, labels.VICTORY) or matches(t, labels.DEFEAT)), None)
    button = next((t for t in texts if matches(t, labels.CONTINUE, exact=True) and t.center[1] > 2100), None)
    return (result, button) if result is not None and button else None


def is_matching(texts: list[Text]) -> bool:
    return any(contains_term(t.norm, "matching") for t in texts)


def is_route(texts: list[Text]) -> bool:
    return any(contains_term(t.norm, "route") for t in texts)


def is_combat(texts: list[Text]) -> bool:
    # The lobby icon and castle menu also contain "Expedition". Only the actual fight
    # title is centered near the top of the display.
    return any(is_term(t.norm, "expedition") and abs(t.center[0]-720) <= 200 and 100 <= t.center[1] <= 400 for t in texts)


def is_campfire(texts: list[Text]) -> bool:
    return _exact(texts, "taking a break") is not None


def combat_speed(texts: list[Text]) -> tuple[int, tuple[int, int]] | None:
    return next(( (int(m.group(1)), t.center) for t in texts if t.center[0] > 1000 and t.center[1] > 2300
                 and (m := re.fullmatch(r"x\s*([124])", t.norm))), None)
