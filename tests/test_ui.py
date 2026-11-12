"""The tkinter window: info, translations, form behaviour (skipped if Tk is unavailable)."""

import pytest

tk = pytest.importorskip("tkinter")

from roguebot.i18n import TEXTS  # noqa: E402
from roguebot.report import Report  # noqa: E402
from roguebot.request import ROUTINE_CHOICES  # noqa: E402
from roguebot.screens import LevelScreen  # noqa: E402
from roguebot.ui import App  # noqa: E402


@pytest.fixture(scope="module")
def _window(tmp_path_factory):
    # One window for all tests: creating several Tk roots in one process fails randomly on Windows.
    try:
        a = App(run=lambda request: Report([LevelScreen.VICTORY]), settings_path=tmp_path_factory.mktemp("ui") / "settings.json")
    except tk.TclError as e:  # no display available
        pytest.skip(f"Tk cannot open a window: {e}")
    yield a
    a.activity.close()
    a.root.destroy()


@pytest.fixture
def app(_window):
    _window.auto_scan.set(False)  # ordinary run-wiring tests do not connect to a real emulator
    _window.use_scan_strategy.set(False)
    _window.mode.set("normal")
    _window.set_language("en")
    _window.source.set("latest")
    _window._toggle_level()
    _window.level.set("1")
    return _window


def test_first_run_shortcuts_fit_and_open_the_intended_pages(app):
    original_size = app.root.geometry()
    previous_tab = app.workspace.select()
    widgets = {key: widget for widget, key in app._texts}
    try:
        app.root.geometry("790x650")
        app.workspace.select(app.pages["play"])
        for language in ("pt", "es", "en"):
            app.set_language(language)
            app.root.update()
            play = app.pages["play"]
            pets = widgets["open_pets"]
            assert pets.winfo_rooty() + pets.winfo_height() <= play.winfo_rooty() + play.winfo_height()
            keys = [*(f"play_activity_{part}" for part in ROUTINE_CHOICES), "play_loop", "play_ads"]
            for key in keys:
                checkbox = widgets[key]
                assert checkbox.winfo_ismapped()
                assert checkbox.winfo_width() >= checkbox.winfo_reqwidth()
                assert checkbox.winfo_rooty() + checkbox.winfo_height() <= play.winfo_rooty() + play.winfo_height()
            assert app.start.winfo_ismapped()
        widgets["open_connection"].invoke()
        assert app.workspace.select() == str(app.pages["connection"])
        assert not app.manual_connection.winfo_manager()
        widgets["connection_advanced"].invoke()
        assert app.manual_connection.winfo_manager() == "pack"
        widgets["open_pets"].invoke()
        dialog = app.account_dialog
        assert dialog.notebook.select() == str(dialog.tabs["pet_plan"])
        widgets["open_inventory"].invoke()
        assert app.account_dialog is dialog
        assert dialog.notebook.select() == str(dialog.tabs["inventory"])
        app.root.update()
        assert dialog.save_button.winfo_ismapped()
    finally:
        if (dialog := getattr(app, "account_dialog", None)) and dialog.window.winfo_exists():
            dialog.window.destroy()
        app.connection_details.set(False)
        app._show_connection_details()
        app.workspace.select(previous_tab)
        app.root.geometry(original_size)


def test_account_history_renders_party_expedition_records(app):
    from roguebot.metrics import History, RunRecord

    History().record(RunRecord("party", "fire", "victory", 60))
    app._open_account("history")
    dialog = app.account_dialog
    try:
        assert "Party Expedition" in dialog.history.get("1.0", "end")
    finally:
        dialog.window.destroy()


def test_party_mode_shows_roles_and_preserves_normal_preferences(app):
    before = app.options()
    try:
        app.mode.set("party_expedition")
        assert app.party_row.grid_info() and not app.sources_row.grid_info()
        assert not app.run_options.grid_info() and not app.routine_panel.grid_info()
        assert str(app.elite_energy_picker.cget("state")) == "disabled"
        app.set_language("pt")
        assert app.party_role_name.get() == "Atacante" and "20/20" in app.party_help.cget("text")
        app.party_role_name.set("Suporte")
        app._select_party_role()
        app.party_runs.set("12")
        saved = app.options()
        app._restore_options(saved)
        assert app.party_role.get() == "support" and app.party_runs.get() == "12"
        app.mode.set("normal")
        assert app.sources_row.grid_info() and app.run_options.grid_info()
    finally:
        app._restore_options(before)


def test_preview_and_execution_cannot_start_together(app, monkeypatch):
    from roguebot.observation import Observation
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    requests = []
    def watch(request, stop, emit):
        requests.append(request)
        emit(Observation("event", "tap", "decision_damage", "Strength Potion", "visual", .98, 2, (920, 2030)))
    monkeypatch.setattr("roguebot.ui.watch_preview", watch)
    monkeypatch.setattr(app, "run", lambda request: pytest.fail("preview started gameplay"))
    app._preview()
    assert app._preview_active and str(app.start.cget("state")) == "disabled"
    assert str(app.check_button.cget("state")) == "disabled"
    app._start()  # guard also applies to programmatic/double activation
    assert len(requests) == 1
    app._poll_preview()
    assert not app._preview_active and str(app.start.cget("state")) == "normal"
    assert "Strength Potion" in app.activity.next_action.cget("text")
    assert "visual" in app.activity.recognized.cget("text") and "98%" in app.activity.recognized.cget("text")
    app.set_language("pt")
    assert "bônus de dano" in app.activity.decision_reason.cget("text")
    assert app.preview_button.cget("text") == "Testar leitura"


def test_preview_error_and_cancellation_release_controls(app, monkeypatch):
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    def broken(*args):
        raise RuntimeError("capture unavailable")
    monkeypatch.setattr("roguebot.ui.watch_preview", broken)
    app._preview()
    app._poll_preview()
    assert not app._preview_active and "capture unavailable" in app.status.cget("text")
    assert str(app.preview_button.cget("state")) == "normal"
    # A stop while a read is in flight stays pending until the worker reports completion.
    app._preview_active = True
    app._preview_stop.clear()
    app._preview()
    assert app._preview_stop.is_set() and str(app.preview_button.cget("state")) == "disabled"
    app._preview_results.put(None)
    app._poll_preview()
    assert not app._preview_active and str(app.preview_button.cget("state")) == "normal"


@pytest.mark.parametrize("mode", ["normal", "elite", "party_expedition"])
def test_all_mode_buttons_fit_without_clipping(app, mode):
    app.mode.set(mode)
    app.set_language("pt")
    app.root.update()
    for widget, key in app._texts:
        if key in ("normal", "elite", "party_expedition"):
            assert widget.winfo_width() >= widget.winfo_reqwidth(), key


def test_start_passes_party_mode_without_running_the_energy_routine(app, monkeypatch):
    before, requests = app.options(), []
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    monkeypatch.setattr(app, "run", lambda request: requests.append(request) or Report(party_reason="party_complete"))
    try:
        app.mode.set("party_expedition")
        app.party_role.set("guardian")
        app.party_runs.set("20")
        app.routine_options["tower"].set(True)
        app.loop.set(True)
        app._start()
        app.root.update()
        assert requests[0].mode.value == "party_expedition"
        assert requests[0].party_role == "guardian" and requests[0].party_runs == 20
        assert requests[0].routine_parts == () and not requests[0].loop
        assert "Expedition" in app.status.cget("text")
    finally:
        app._restore_options(before)


def test_info_section_lists_requirements(app):
    shown = app.info.cget("text")
    assert shown == TEXTS["en"]["info"]
    for needed in ("MuMu Player 12 with Rogue Legend installed", "Spanish or English", "never spends gems",
                   "skips it and moves on", "options are saved"):
        assert needed in shown


def test_language_switch_translates_every_widget(app):
    app.set_language("es")
    assert app.info.cget("text") == TEXTS["es"]["info"]
    assert app.start.cget("text") == "Iniciar"
    assert app.root.title() == "Rogue Legends Bot"
    for widget, key in app._texts:
        assert widget.cget("text") == TEXTS["es"][key]


def test_status_follows_language(app):
    app._finish(("report", {"report": Report([LevelScreen.VICTORY])}, "green"))
    assert app.status.cget("text") == "Level finished: Victory"
    app.set_language("es")
    assert app.status.cget("text") == "Nivel terminado: Victoria"


def test_level_entry_enabled_only_for_star_challenge(app):
    assert str(app.level_entry.cget("state")) == "disabled"
    app.source.set("stars")
    app._toggle_level()
    assert str(app.level_entry.cget("state")) == "normal"


def test_invalid_level_shows_error_status(app):
    app.source.set("stars")
    app.level.set("abc")
    app._start()
    assert app.status.cget("text") == TEXTS["en"]["bad_level"]
    assert str(app.start.cget("state")) != "disabled"


def test_activities_are_individual_and_off_by_default(app):
    assert not hasattr(app, "repeat") and app.loop.get() is False
    assert tuple(app.routine_options) == ROUTINE_CHOICES and app._selected_activities() == ()
    assert not hasattr(app, "full_button")


class InlineThread:
    """Runs the worker right away on the test thread (Tk calls from other threads need a mainloop)."""
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def test_worker_finishes_without_accessing_tk_from_its_thread():
    import queue
    import threading

    worker = App.__new__(App)
    report = Report([LevelScreen.VICTORY])
    worker.run = lambda request: report
    worker._run_results = queue.SimpleQueue()
    # No root exists: a worker must communicate exclusively through its result queue.
    thread = threading.Thread(target=worker._worker, args=(None,))
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert worker._run_results.get_nowait() is report


def test_invalid_saved_option_types_keep_defaults(app):
    original = app.options()
    try:
        app._restore_options({"provider": [], "mode": [], "source": {}, "nature": [],
                              "damage_order": [None, 2], "build_profile": [], "elite_energy": 5.0})
        assert app.options() == original
    finally:
        app._restore_options(original)


def test_log_queue_keeps_recent_messages_without_blocking():
    import logging
    import queue
    from roguebot.activity_ui import _QueueHandler

    messages = queue.Queue(maxsize=2)
    handler = _QueueHandler(messages)
    for i in range(5):
        handler.emit(logging.LogRecord("test", logging.INFO, "", 0, str(i), (), None))
    assert [messages.get_nowait(), messages.get_nowait()] == ["3", "4"]


def test_activity_checkboxes_build_a_request_for_only_the_selected_modes(app, monkeypatch):
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    requests = []
    monkeypatch.setattr(app, "run", lambda request: requests.append(request) or Report([LevelScreen.VICTORY]))
    before = app.options()
    try:
        app.routine_options["vip"].set(True)
        app.routine_options["tower"].set(True)
        app.routine_options["pets"].set(True)
        app._start()
        app.root.update()
    finally:
        app._restore_options(before)
    assert requests[0].routine_parts == ("vip", "tower", "pets")
    assert requests[0].repeat and not requests[0].loop


def test_stop_button(app, monkeypatch):
    from roguebot.device import Stopped
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    assert str(app.stop_button.cget("state")) == "disabled"  # idle
    seen = {}

    def run(request):  # the user presses Stop mid-run; the device then raises Stopped
        seen["stop_enabled"] = str(app.stop_button.cget("state"))
        app.stop_button.invoke()
        seen["status"] = app.status.cget("text")
        raise Stopped("Stopped by the user")
    stops = []
    monkeypatch.setattr(app, "run", run)
    monkeypatch.setattr(app, "stop", lambda: stops.append(1))
    app._start()
    app.root.update()
    assert seen == {"stop_enabled": "normal", "status": TEXTS["en"]["stopping"]}
    assert stops == [1]
    assert app.status.cget("text") == TEXTS["en"]["stopped"]
    assert str(app.start.cget("state")) == "normal"
    assert str(app.stop_button.cget("state")) == "disabled"


def test_build_section(app):
    from roguebot.build import Build
    assert app.build() == Build()  # defaults: physical, default order, no support
    app.order_list.selection_clear(0, "end")
    app.order_list.selection_set(2)  # fire
    app._move(-1)
    app._move(-1)
    app.nature.set("magic")
    app.support.set(True)
    app.support_every.set("2")
    try:
        assert app.build() == Build("magic", ("fire", "ice", "lightning", "shuriken", "venom", "bleed"), 2)
        assert app.order_list.get(0) == "1. Fire"
        app.set_language("es")
        assert app.order_list.get(0) == "1. Fuego"  # the list follows the UI language
    finally:
        app.damage_order = list(Build().order)
        app._refresh_order()
        app.nature.set("physical")
        app.support.set(False)


def test_loop_checkbox_builds_a_loop_request(app, monkeypatch):
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    assert app.loop.get() is False
    requests = []
    monkeypatch.setattr(app, "run", lambda request: requests.append(request) or Report([LevelScreen.VICTORY]))
    app.loop.set(True)
    try:
        app._start()
        app.root.update()
    finally:
        app.loop.set(False)
    assert requests[0].loop and not requests[0].full and requests[0].repeat


def test_last_beaten_source_builds_a_last_beaten_request(app, monkeypatch):
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    requests = []
    monkeypatch.setattr(app, "run", lambda request: requests.append(request) or Report([LevelScreen.VICTORY]))
    app.source.set("beaten")
    app._toggle_level()
    try:
        assert str(app.level_entry.cget("state")) == "disabled"  # no number needed
        app._start()
        app.root.update()
    finally:
        app.source.set("latest")
        app._toggle_level()
    assert requests[0].last_beaten and requests[0].level is None


def test_mumu_folder_field_marks_valid_folders(app, tmp_path):
    good = tmp_path / "MuMuPlayer"
    (good / "nx_main").mkdir(parents=True)
    for exe in ("MuMuManager.exe", "adb.exe"):
        (good / "nx_main" / exe).write_bytes(b"")
    old = app.mumu_folder.get()
    try:
        app.mumu_folder.set(str(good))
        assert app.mumu_status.cget("text").startswith("✓")
        app.mumu_folder.set(str(tmp_path / "nothing"))
        assert app.mumu_status.cget("text").startswith("✗")
    finally:
        app.mumu_folder.set(old)


def test_start_passes_and_saves_the_mumu_folder(app, monkeypatch, tmp_path):
    from roguebot import settings
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    monkeypatch.setattr(app, "settings_path", tmp_path / "settings.json")
    good = tmp_path / "MuMu"
    (good / "shell").mkdir(parents=True)  # older MuMu 12 layout
    for exe in ("MuMuManager.exe", "adb.exe"):
        (good / "shell" / exe).write_bytes(b"")
    requests = []
    monkeypatch.setattr(app, "run", lambda request: requests.append(request) or Report([LevelScreen.VICTORY]))
    old = app.mumu_folder.get()
    try:
        app.mumu_folder.set(str(good))
        app._start()
        app.root.update()
    finally:
        app.mumu_folder.set(old)
    assert requests[0].mumu_folder == str(good)
    assert settings.load(tmp_path / "settings.json")["mumu_folder"] == str(good)


def test_emulator_errors_are_shown_translated(app, monkeypatch):
    from roguebot.emulator import EmulatorError
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)

    def fail(request):
        raise EmulatorError("err_mumu_boot", seconds=240)
    monkeypatch.setattr(app, "run", fail)
    app._start()
    app.root.update()
    assert app.status.cget("text").endswith(TEXTS["en"]["err_mumu_boot"].format(seconds=240))


def test_missing_stars_source_builds_a_pending_request(app, monkeypatch):
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    requests = []
    monkeypatch.setattr(app, "run", lambda request: requests.append(request) or Report([LevelScreen.VICTORY]))
    app.source.set("pending")
    app._toggle_level()
    try:
        app._start()
        app.root.update()
    finally:
        app.source.set("latest")
        app._toggle_level()
    assert requests[0].pending_stars and requests[0].level is None


def test_window_has_the_game_icon(app):
    from roguebot.ui import ICON
    assert ICON.exists()
    assert (app.icon.width(), app.icon.height()) == (192, 192)
    assert app.header_icon.width() == 64


@pytest.mark.parametrize("language", ("pt", "es", "en"))
def test_window_and_header_show_the_same_title_without_version(app, language):
    app.set_language(language)
    assert app.root.title() == app.header_title.cget("text") == "Rogue Legends Bot"


def test_changelog_is_hidden_until_toggled(app):
    from roguebot import __version__
    assert not app.activity.changelog.winfo_ismapped() and not app.activity.changelog_shown
    assert app.changelog_toggle.cget("text") == "▸ Changelog"
    app._toggle_changelog()
    assert app.activity.changelog_shown and app.activity.changelog.grid_info()
    assert f"## {__version__}" in app.activity.changelog.get("1.0", "end")
    app.set_language("es")
    assert app.changelog_toggle.cget("text") == "▾ Novedades"
    app._toggle_changelog()
    assert not app.activity.changelog_shown and not app.activity.changelog.grid_info()


def test_watch_ads_option_explains_it_needs_ad_skip(app):
    assert app.ads.get() is False  # off by default
    assert "(only if the account has bought the skip ads option)" in TEXTS["en"]["ads"]
    assert "(solo si" in TEXTS["es"]["ads"]


def test_portuguese_run_options_explain_waiting_and_the_ad_pass(app):
    app.set_language("pt")
    widgets = {key: widget for widget, key in app._texts}
    assert widgets["play_loop"].cget("text") == "Esperar energia e voltar a jogar"
    assert widgets["play_ads"].cget("text") == "Ver anúncios (exige passe para pular)"


def test_every_option_is_saved_and_restored(app, tmp_path, monkeypatch):
    from roguebot import settings
    monkeypatch.setattr(app, "settings_path", tmp_path / "settings.json")
    chosen = {"mode": "elite", "source": "stars", "level": "7", "loop": True,
              "ads": True, "nature": "magic", "support": True, "support_every": "4"}
    defaults = {k: getattr(app, k).get() for k in chosen}
    order = list(reversed(app.damage_order))
    try:
        for key, value in chosen.items():
            getattr(app, key).set(value)
        app.routine_options["arena"].set(True)
        app.routine_options["mines"].set(True)
        app.damage_order = list(order)
        app._save_options()
        saved = settings.load(tmp_path / "settings.json")
        assert {k: saved[k] for k in chosen} == chosen and saved["damage_order"] == order and saved["lang"] == "en"
        assert saved["routine_parts"] == ["arena", "mines"]
        for key, value in defaults.items():  # a fresh window, then last session's choices
            getattr(app, key).set(value)
        app.damage_order = sorted(order)
        app._restore_options({"routine_parts": []})
        app._restore_options(saved)
        assert {k: getattr(app, k).get() for k in chosen} == chosen and app.damage_order == order
        assert app._selected_activities() == ("arena", "mines")
        assert str(app.level_entry.cget("state")) == "normal"  # "stars" enables the level box
    finally:
        for key, value in defaults.items():
            getattr(app, key).set(value)
        app._restore_options({"routine_parts": []})
        app.damage_order = sorted(order, key=list(reversed(order)).index)
        app._toggle_level()


def test_invalid_saved_options_keep_the_defaults(app):
    before = app.options()
    app._restore_options({"mode": "hard", "source": 3, "level": "-1", "full": "yes", "damage_order": ["fire"]})
    assert app.options() == before


def test_old_routine_setting_migrates_and_explicit_selection_takes_precedence(app):
    before = app.options()
    try:
        app._restore_options({"full": True})
        assert app._selected_activities() == ROUTINE_CHOICES
        app._restore_options({"full": True, "routine_parts": ["dojo", "daily", "unknown"]})
        assert app._selected_activities() == ("dojo",)
        app._restore_options({"full": True, "routine_parts": []})
        assert app._selected_activities() == ()
    finally:
        app._restore_options(before)


def test_log_view_keeps_only_the_last_lines(app, monkeypatch):
    monkeypatch.setattr("roguebot.activity_ui.LOG_VIEW_LINES", 5)
    app.activity.append([f"line {i}" for i in range(20)])
    lines = app.activity.log_view.get("1.0", "end-1c").splitlines()
    assert len(lines) <= 5 and lines[-1] == "line 19"


def test_google_selection_saves_separate_connections_and_keeps_mumu_folder(app, monkeypatch, tmp_path):
    from roguebot import settings
    from roguebot.providers import PROVIDERS
    monkeypatch.setattr(app, "settings_path", tmp_path / "settings.json")
    old = app.options()
    folder = app.mumu_folder.get()
    try:
        app.adb_path.set("mumu-adb.exe")
        app.device_serial.set("127.0.0.1:16416")
        app.provider_name.set(PROVIDERS["google_play_games"])
        app._change_provider()
        assert not app.adb_path.get() and not app.device_serial.get()
        assert not app.folder_row.winfo_manager()
        app.adb_path.set("google-adb.exe")
        app.device_serial.set("localhost:6520")
        app._save_options()
        saved = settings.load(app.settings_path)
        assert saved["provider"] == "google_play_games"
        assert saved["provider_connections"]["mumu"]["adb_path"] == "mumu-adb.exe"
        assert app.mumu_folder.get() == folder
        app.provider_name.set(PROVIDERS["mumu"])
        app._change_provider()
        assert app.adb_path.get() == "mumu-adb.exe"
        app._restore_options(saved)
        assert app.provider.get() == "google_play_games" and app.adb_path.get() == "google-adb.exe"
    finally:
        app._restore_options(old)


def test_connection_check_is_read_only_and_displays_geometry(app, monkeypatch):
    from roguebot.diagnostics import ConnectionStatus
    from roguebot.viewport import Viewport
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    seen = []
    result = ConnectionStatus("localhost:6520", True, Viewport(656, 0, 608, 1080, 1920, 1080, .99))
    monkeypatch.setattr("roguebot.ui.inspect_emulator", lambda request: seen.append(request) or result)
    app._check_connection()
    app._poll_connection()
    assert len(seen) == 1 and seen[0].provider == app.provider.get()
    shown = app.connection_status.cget("text")
    assert "1920×1080" in shown and "608×1080" in shown and "installed" in shown
    app.set_language("es")
    assert "instalado" in app.connection_status.cget("text")


def test_start_passes_google_options(app, monkeypatch):
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    previous = app.options()
    requests = []
    monkeypatch.setattr(app, "run", lambda request: requests.append(request) or Report([LevelScreen.VICTORY]))
    try:
        app.provider.set("google_play_games")
        app.adb_path.set("adb-google.exe")
        app.device_serial.set("localhost:6520")
        app._start()
        app.root.update()
        assert requests[0].provider == "google_play_games"
        assert requests[0].adb_path == "adb-google.exe" and requests[0].device_serial == "localhost:6520"
    finally:
        app._restore_options(previous)


def test_invalid_saved_connection_profile_does_not_break_provider_switch(app, monkeypatch, tmp_path):
    from roguebot.providers import PROVIDERS
    monkeypatch.setattr(app, "settings_path", tmp_path / "settings.json")
    previous = app.options()
    try:
        app._connections["google_play_games"] = "invalid profile"
        app.provider_name.set(PROVIDERS["google_play_games"])
        app._change_provider()
        assert app.adb_path.get() == "" and app.device_serial.get() == ""
    finally:
        app._restore_options(previous)


def test_burn_build_and_ad_skip_preferences_are_saved_and_restored(app, monkeypatch, tmp_path):
    from roguebot import settings
    from roguebot.build import BURN
    monkeypatch.setattr(app, "settings_path", tmp_path / "settings.json")
    previous = app.options()
    try:
        app.burn_build.set(True)
        app.ads.set(True)
        assert app.build().profile == BURN
        app._save_options()
        saved = settings.load(app.settings_path)
        app.burn_build.set(False)
        app.ads.set(False)
        app._restore_options(saved)
        assert app.build().profile == BURN and app.ads.get()
    finally:
        app._restore_options(previous)


def test_portuguese_controls_status_errors_and_language_persistence(app, monkeypatch, tmp_path):
    from roguebot import settings
    from roguebot.i18n import UI_LANGUAGES
    monkeypatch.setattr(app, "settings_path", tmp_path / "settings.json")
    app.set_language("pt")
    assert app.ui_lang.get() == UI_LANGUAGES["pt"] == "Português"
    assert app.root.title() == "Rogue Legends Bot"
    assert app.start.cget("text") == "Iniciar" and app.stop_button.cget("text") == "Parar"
    for widget, key in app._texts:
        assert widget.cget("text") == TEXTS["pt"][key]
    app._finish(("report", {"report": Report([LevelScreen.VICTORY])}, "green"))
    assert app.status.cget("text") == "Fase concluída: Vitória"
    app._set_status("error", "red", msg=TEXTS["pt"]["err_game_missing"])
    assert app.status.cget("text") == "Erro: Rogue Legend não está instalado no emulador."
    app._save_options()
    assert settings.load(app.settings_path)["lang"] == "pt"


def test_elite_cost_is_available_only_in_elite_and_is_saved(app, monkeypatch, tmp_path):
    from roguebot import settings
    monkeypatch.setattr(app, "settings_path", tmp_path / "settings.json")
    previous = app.options()
    try:
        app.mode.set("normal")
        assert str(app.elite_energy_picker.cget("state")) == "disabled"
        app.mode.set("elite")
        assert str(app.elite_energy_picker.cget("state")) == "readonly"
        app.elite_energy_name.set("10")
        app._select_elite_energy()
        app._save_options()
        assert settings.load(app.settings_path)["elite_energy"] == 10
        app.elite_energy.set("auto")
        app._restore_options(settings.load(app.settings_path))
        assert app.elite_energy.get() == "10"
        app.set_language("pt")
        assert app.elite_energy_name.get() == "10"
    finally:
        app._restore_options(previous)


def test_profile_selection_is_translated_persistent_and_reaches_the_request(app, monkeypatch, tmp_path):
    from roguebot import settings
    from roguebot.i18n import tr
    monkeypatch.setattr(app, "settings_path", tmp_path / "settings.json")
    monkeypatch.setattr("roguebot.ui.threading.Thread", InlineThread)
    previous, requests = app.options(), []
    monkeypatch.setattr(app, "run", lambda request: requests.append(request) or Report([LevelScreen.VICTORY]))
    try:
        app.profile_name.set(tr(app.lang, "profile_fire"))
        app._select_profile()
        app.elite_energy.set("5")
        app._start()
        app.root.update()
        assert requests[0].build.profile == "fire" and requests[0].elite_energy == 5
        assert settings.load(app.settings_path)["build_profile"] == "fire"
        app.set_language("pt")
        assert app.profile_name.get() == "Fogo puro / queimadura"
    finally:
        app._restore_options(previous)


def test_account_rarity_strategy_and_farm_preferences_are_saved_canonically(app, monkeypatch, tmp_path):
    from roguebot.account_ui import AccountDialog
    from roguebot.i18n import tr
    from roguebot import settings
    previous = app.options()
    monkeypatch.setattr(app, "settings_path", tmp_path / "account.json")
    dialog = None
    try:
        app.set_language("pt")
        dialog = AccountDialog(app)
        dialog.values["weapon"].set("Katana")
        dialog.rarity[0].set(tr("pt", "rarity_legendary"))
        dialog.strategy[0].set(tr("pt", "strategy_crit"))
        dialog.values["hero_levels"].set("Draco=90")
        dialog.values["chapter"].set("40")
        dialog._plan()
        assert "Custo:" in dialog.plan.get("1.0", "end")
        assert "saldo" in dialog.plan.get("1.0", "end").lower()
        dialog._save()
        assert app.build().strategy == "crit"
        assert app.loadout.weapon_rarity == "legendary" and "shuriken" in app.loadout.sources
        saved = settings.load(app.settings_path)
        assert saved["loadout"]["weapon_rarity"] == "legendary" and saved["planner_facts"]["hero_levels"] == {"Draco": 90}
        app._restore_options(saved)
        assert app.build().strategy == "crit"
    finally:
        if dialog and dialog.window.winfo_exists():
            dialog.window.destroy()
        app._restore_options(previous)


def test_event_modes_show_the_inspection_limit_and_hide_campaign_controls(app):
    previous = app.options()
    try:
        app.mode.set("conquest")
        assert not app.sources_row.grid_info() and not app.routine_panel.grid_info()
        assert app.build_box.grid_info()
        assert "spends no attempts" in app.party_help.cget("text")
    finally:
        app._restore_options(previous)


def test_pet_optimizer_button_persists_the_observed_collection_and_renders_a_plan(app, monkeypatch, tmp_path):
    from dataclasses import asdict
    from roguebot import account_scan_ui, settings
    from roguebot.account_state import AccountSnapshot
    from roguebot.account_ui import AccountDialog
    from roguebot.pet_upgrades import Pet

    previous = app.options()
    monkeypatch.setattr(app, "settings_path", tmp_path / "pets.json")
    monkeypatch.setattr(account_scan_ui.threading, "Thread", InlineThread)
    snapshot = AccountSnapshot(account="A", status="complete")
    snapshot.facts["pet_collection"] = {"pets": [asdict(Pet("Sly", "common", 1, 20, False))],
                                       "food": 100, "complete": True, "at": snapshot.at}

    def scan(*args, **options):
        assert options["pets_only"]
        return snapshot

    monkeypatch.setattr(account_scan_ui, "scan_account", scan)
    app.set_language("pt")
    dialog = AccountDialog(app)
    try:
        dialog.pet_button.invoke()
        app.account_reader.poll()
        text = dialog.pet_plan.get("1.0", "end")
        assert "Sly · Nv. 1 → 5" in text and "sobra 0" in text
        assert settings.load(app.settings_path)["planner_facts"]["pet_collection"]["food"] == 100
    finally:
        dialog.window.destroy()
        app._restore_options(previous)


def test_account_scan_populates_preferences_and_the_pending_run_before_start(app,monkeypatch,tmp_path):
    from roguebot.account_state import AccountSnapshot
    from roguebot import account_scan_ui,settings
    previous=app.options()
    monkeypatch.setattr(app,"settings_path",tmp_path/"scanned.json")
    monkeypatch.setattr(account_scan_ui.threading,"Thread",InlineThread)
    monkeypatch.setattr(account_scan_ui,"save_snapshot",lambda snapshot:None)
    snapshot=AccountSnapshot(account="A",loadout={"hero":"Lancelot","weapon":"Ember Staff","weapon_rarity":"epic"},
        profile="burn",strategy="skill",reason="scan_strategy_weapon",status="complete")
    monkeypatch.setattr(account_scan_ui,"scan_account",lambda *args,**kwargs:snapshot)
    requests=[]
    monkeypatch.setattr(app,"run",lambda request:requests.append(request) or Report([LevelScreen.VICTORY]))
    try:
        app.auto_scan.set(True)
        app.use_scan_strategy.set(True)
        app._start()
        assert app.account_reader.active and not requests
        app.account_reader.poll()
        app.root.update()
        assert requests[0].build.loadout.weapon=="Ember Staff"
        assert requests[0].build.strategy=="skill" and requests[0].build.profile=="burn"
        assert settings.load(app.settings_path)["scanned_account"]=="A"
    finally:
        app._restore_options(previous)
