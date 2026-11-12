"""What a run produced, and how the UI words it in each language."""

from dataclasses import dataclass, field

from roguebot.i18n import tr
from roguebot.screens import LevelScreen

RESULT_KEY = {LevelScreen.VICTORY: "victory", LevelScreen.DEFEAT: "defeat"}


@dataclass
class Report:
    results: list[LevelScreen] = field(default_factory=list)
    repeat: bool = False
    dry_run: bool = False
    parts: list[tuple[str, str]] = field(default_factory=list)  # (part, status), see routine.PARTS
    party_reason: str | None = None
    mode: str | None = None
    mode_reason: str | None = None


def render(report: Report, lang: str) -> str:
    if report.dry_run:
        return tr(lang, "dry_run")
    if report.mode_reason:
        return tr(lang, "mode_summary", mode=tr(lang, report.mode), runs=len(report.results),
                  reason=tr(lang, report.mode_reason))
    if report.party_reason is not None:
        wins = report.results.count(LevelScreen.VICTORY)
        return tr(lang, "party_summary", runs=len(report.results), wins=wins, losses=len(report.results)-wins,
                  reason=tr(lang, report.party_reason))
    if not report.repeat:
        return tr(lang, "level_finished", result=tr(lang, RESULT_KEY[report.results[0]]))
    wins = report.results.count(LevelScreen.VICTORY)
    levels = tr(lang, "out_of_energy", runs=len(report.results), wins=wins, losses=len(report.results) - wins)
    if not report.parts:
        return levels
    parts = ", ".join(f"{tr(lang, 'part_' + part)}: {tr(lang, 'status_' + status)}" for part, status in report.parts)
    return parts + "\n" + levels
