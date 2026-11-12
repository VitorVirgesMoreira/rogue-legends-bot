"""Provider selection and scripted ADB; never require a live emulator."""

import threading

import pytest

from roguebot import config, settings
from roguebot.device import Stopped
from roguebot.emulator import EmulatorError
from roguebot.providers import create_provider
from roguebot.providers.google_play_games import GooglePlayGamesProvider, find_adb
from roguebot.providers.mumu import MuMuProvider
from roguebot.request import RunRequest, build_request
from roguebot.screens import Mode


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    for key in ("GOOGLE_CONNECT_TIMEOUT", "EMULATOR_BOOT_TIMEOUT", "GAME_OPEN_TIMEOUT"):
        monkeypatch.setattr(config, key, 0.001)
    monkeypatch.setattr(config, "EMULATOR_POLL", 0)


@pytest.fixture
def adb(tmp_path):
    exe = tmp_path / "adb.exe"
    exe.touch()
    return str(exe)


class FakeAdb:
    def __init__(self, connected=True, reconnects=True, boot=True, installed=True, front=True, opens=True):
        self.connected, self.reconnects, self.boot = connected, reconnects, boot
        self.installed, self.front, self.opens = installed, front, opens
        self.calls = []

    def __call__(self, args, timeout):
        self.calls.append(args[1:])
        cmd = args[1:]
        if cmd[0] == "connect":
            self.connected = self.reconnects
            return "connected" if self.connected else "connection refused"
        assert cmd[:2] == ["-s", "localhost:6520"] or cmd[:2] == ["-s", "my-device"]
        cmd = cmd[2:]
        if cmd == ["get-state"]:
            return "device\n" if self.connected else "offline\n"
        if not self.connected:
            return ""
        if cmd == ["shell", "getprop", "sys.boot_completed"]:
            return "1\n" if self.boot else "0\n"
        if cmd[:4] == ["shell", "pm", "list", "packages"]:
            return f"package:{config.PACKAGE}\n" if self.installed else ""
        if cmd == ["shell", "dumpsys", "window"]:
            package = config.PACKAGE if self.front else "com.android.launcher"
            return f"mCurrentFocus=Window{{abc u0 {package}/.Activity}}"
        if cmd[:2] == ["shell", "monkey"]:
            self.front = self.opens
        if cmd[:3] == ["shell", "am", "force-stop"]:
            self.front = False
        return ""


def test_default_settings_preserve_mumu(tmp_path):
    folder = tmp_path / "MuMu"
    (folder / "nx_main").mkdir(parents=True)
    for name in ("MuMuManager.exe", "adb.exe"):
        (folder / "nx_main" / name).touch()
    request = RunRequest(Mode.NORMAL, None, mumu_folder=str(folder))
    assert isinstance(create_provider(request), MuMuProvider)
    assert isinstance(create_provider(RunRequest(Mode.NORMAL, None, provider="google_play_games",
                                               adb_path=str(folder / "nx_main" / "adb.exe"))), GooglePlayGamesProvider)


def test_configuration_round_trip(tmp_path, adb):
    request = build_request("normal", "latest", "", provider="google_play_games", adb_path=adb, device_serial="my-device")
    path = tmp_path / "settings.json"
    settings.save({"mumu_folder": "old MuMu", "provider": request.provider,
                   "adb_path": request.adb_path, "device_serial": request.device_serial}, path)
    saved = settings.load(path)
    assert saved["mumu_folder"] == "old MuMu"
    assert create_provider(RunRequest(Mode.NORMAL, None, **saved)).serial == "my-device"


def test_install_discovery(tmp_path, monkeypatch):
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert find_adb() is None
    exe = tmp_path / "Google/Play Games Developer Emulator/current/emulator/adb.exe"
    exe.parent.mkdir(parents=True)
    exe.touch()
    assert find_adb() == exe


def test_missing_install_or_explicit_adb_fails(monkeypatch):
    monkeypatch.setattr("roguebot.providers.google_play_games.find_adb", lambda: None)
    for path in ("", "C:/missing/adb.exe"):
        with pytest.raises(EmulatorError) as err:
            GooglePlayGamesProvider(path)
        assert err.value.key == "err_google_adb"


def test_unknown_provider_is_not_silently_mumu():
    with pytest.raises(EmulatorError, match="err_provider"):
        create_provider(RunRequest(Mode.NORMAL, None, provider="unknown"))


def test_connected_game_does_not_require_or_launch_mumu(adb):
    fake = FakeAdb()
    assert GooglePlayGamesProvider(adb, run=fake).start() == ("localhost:6520", adb, False)
    assert not any("monkey" in c or "MuMuManager.exe" in c for c in fake.calls)


def test_reconnect_then_launch(adb):
    fake = FakeAdb(connected=False, front=False)
    assert GooglePlayGamesProvider(adb, run=fake).start()[2]
    assert ["connect", "localhost:6520"] in fake.calls
    assert any("monkey" in c for c in fake.calls)


def test_slow_transport_handshake_is_not_reset_by_repeated_connect(adb, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CONNECT_TIMEOUT", 1)
    class Slow(FakeAdb):
        pending = 0
        def __call__(self, args, timeout):
            if args[1:3] == ["connect", "localhost:6520"]:
                self.calls.append(args[1:])
                self.pending = 3
                return "connected to localhost:6520"
            if args[-1] == "get-state" and self.pending:
                self.pending -= 1
                self.connected = self.pending == 0
            return super().__call__(args, timeout)
    fake = Slow(connected=False)
    assert GooglePlayGamesProvider(adb, run=fake).connect() == "localhost:6520"
    assert fake.calls.count(["connect", "localhost:6520"]) == 1


@pytest.mark.parametrize("options,key", [({"connected": False, "reconnects": False}, "err_google_connection"),
    ({"boot": False}, "err_google_boot"), ({"installed": False}, "err_game_missing"),
    ({"front": False, "opens": False}, "err_game_open")])
def test_actionable_errors(adb, options, key):
    with pytest.raises(EmulatorError) as err:
        GooglePlayGamesProvider(adb, run=FakeAdb(**options)).start()
    assert err.value.key == key


def test_multiple_devices_always_use_explicit_serial(adb):
    fake = FakeAdb()
    assert GooglePlayGamesProvider(adb, "my-device", run=fake).start()[0] == "my-device"
    assert all(c[:2] == ["-s", "my-device"] for c in fake.calls)


def test_recovery_reconnects_before_foregrounding_then_escalates_only_game(adb):
    fake = FakeAdb(connected=False, front=False)
    provider = GooglePlayGamesProvider(adb, run=fake)
    provider.recover()
    assert provider.start()[2]
    assert fake.connected and fake.front
    assert not any("force-stop" in c for c in fake.calls)
    provider.recover(restart_game=True)
    assert provider.start()[2]
    assert any(c[-3:] == ["am", "force-stop", config.PACKAGE] for c in fake.calls)
    assert not any("taskkill" in c or "kill-server" in c or "shutdown" in c for c in fake.calls)
    assert fake.front


def test_shutdown_never_terminates_google_or_other_processes(adb):
    fake = FakeAdb()
    GooglePlayGamesProvider(adb, run=fake).shutdown()
    assert not fake.calls


def test_stop_interrupts_reconnection(adb, monkeypatch):
    monkeypatch.setattr(config, "GOOGLE_CONNECT_TIMEOUT", 60)
    stop = threading.Event()
    stop.set()
    with pytest.raises(Stopped):
        GooglePlayGamesProvider(adb, stop=stop, run=FakeAdb(connected=False, reconnects=False)).start()


def test_mumu_connection_check_does_not_start_or_stop_anything(tmp_path):
    from test_emulator import FakeMuMu, install
    fake = FakeMuMu()
    assert MuMuProvider(install(tmp_path), run=fake).connect() == "127.0.0.1:16416"
    assert not any("launch" in c or "shutdown" in c or "taskkill" in c for c in fake.calls)


def test_mumu_connection_check_requests_manual_start_if_off(tmp_path):
    from test_emulator import FakeMuMu, install
    with pytest.raises(EmulatorError, match="err_mumu_not_running"):
        MuMuProvider(install(tmp_path), run=FakeMuMu(started=False)).connect()
