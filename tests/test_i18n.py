"""UI translations and run summaries."""

import pytest

from roguebot.i18n import TEXTS, UI_LANGUAGES, tr
from roguebot.report import Report, render
from roguebot.screens import LevelScreen

V, D = LevelScreen.VICTORY, LevelScreen.DEFEAT


def test_all_languages_have_the_same_keys():
    assert TEXTS.keys() == UI_LANGUAGES.keys()
    for lang in TEXTS:
        assert TEXTS[lang].keys() == TEXTS["en"].keys(), lang


def test_placeholders_match_between_languages():
    import string
    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}  # noqa: E731
    for lang in TEXTS:
        for key in TEXTS[lang]:
            assert fields(TEXTS[lang][key]) == fields(TEXTS["en"][key]), (lang, key)


@pytest.mark.parametrize("report, es, en", [
    (Report([V]), "Nivel terminado: Victoria", "Level finished: Victory"),
    (Report([D]), "Nivel terminado: Derrota", "Level finished: Defeat"),
    (Report([V, D, V], repeat=True), "Sin energía tras 3 partidas: 2 victorias, 1 derrotas",
     "Out of energy after 3 runs: 2 victories, 1 defeats"),
    (Report(dry_run=True), "Simulación terminada", "Dry run done"),
    (Report([V], repeat=True, parts=[("arena", "done"), ("tower", "failed"), ("raid", "skipped")]),
     "Arena: hecho, Torre: FALLÓ, Jefe de incursión: omitido\nSin energía tras 1 partidas: 1 victorias, 0 derrotas",
     "Arena: done, Tower: FAILED, Guild raid: skipped\nOut of energy after 1 runs: 1 victories, 0 defeats"),
])
def test_render(report, es, en):
    assert render(report, "es") == es
    assert render(report, "en") == en


def test_error_text():
    assert tr("es", "error", msg="boom") == "Error: boom"


def test_every_routine_part_and_status_is_translated():
    from roguebot.routine import DONE, FAILED, PARTS, SKIPPED
    for lang in TEXTS:
        for part in PARTS:
            assert tr(lang, "part_" + part)
        for status in (DONE, SKIPPED, FAILED):
            assert tr(lang, "status_" + status)


@pytest.mark.parametrize("report,expected", [
    (Report([V]), "Fase concluída: Vitória"),
    (Report([D]), "Fase concluída: Derrota"),
    (Report(dry_run=True), "Simulação concluída"),
    (Report([V, D, V], repeat=True), "Sem energia — partidas: 3, vitórias: 2, derrotas: 1"),
    (Report([V], repeat=True, parts=[("arena", "done"), ("tower", "failed"), ("raid", "skipped")]),
     "Arena: concluído, Torre: FALHOU, Chefe da guilda: ignorado\nSem energia — partidas: 1, vitórias: 1, derrotas: 0"),
])
def test_portuguese_run_summaries(report, expected):
    assert render(report, "pt") == expected
