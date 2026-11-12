"""Read-only inspection must not launch/recover a game, change a catalog or send input."""

import threading
from types import SimpleNamespace

import pytest

from roguebot import config, labels, preview
from roguebot.build import Build
from roguebot.observation import Observation
from roguebot.request import RunRequest
from roguebot.screens import Mode
from roguebot.skills import Catalog
from test_events import event
from test_skill_screens import PROMPT, card


def test_preview_skill_choice_does_not_learn_or_write_anything(tmp_path):
    catalog = Catalog(tmp_path/'skills.json')
    request = RunRequest(Mode.NORMAL, None, build=Build(profile='fire'))
    inspector = preview.Inspector(request, catalog)
    image, _ = event()
    texts = [PROMPT, *card('Common', 'Ice Weapon', 'Deal ice damage', 928),
             *card('Common', 'Fire Weapon', 'Deal fire damage', 1260)]
    first = inspector.inspect(image, texts)
    second = inspector.inspect(image, texts)
    assert first.action == 'wait' and first.stable == 1
    assert second.action == 'skill' and second.detail == 'Fire Weapon' and second.stable == 2
    assert catalog.skills == {} and not catalog.path.exists()


def test_inspector_restores_the_execution_language(tmp_path):
    labels.set_language('es')
    inspector = preview.Inspector(RunRequest(Mode.NORMAL, None), Catalog(tmp_path/'skills.json'))
    inspector.inspect(*event())
    assert labels.active_language() == 'es'
    labels.set_language(None)


@pytest.mark.parametrize('foreground', [config.PACKAGE, 'another.app'])
def test_watch_uses_only_connect_foreground_and_read_only_capture(monkeypatch, tmp_path, foreground):
    calls, updates, stop = [], [], threading.Event()
    provider = SimpleNamespace(adb='selected-adb', connect=lambda: calls.append('connect') or 'device')
    monkeypatch.setattr(preview, 'create_provider', lambda request, event: provider)
    image, texts = event()
    class Device:
        def __init__(self, serial, stop, adb):
            assert serial == 'device' and adb == 'selected-adb'
        def foreground_package(self):
            calls.append('foreground')
            return foreground
        def peek(self):
            calls.append('peek')
            return image
    monkeypatch.setattr(preview, 'Device', Device)
    monkeypatch.setattr(preview, 'Ocr', lambda: SimpleNamespace(read=lambda image: texts))
    monkeypatch.setattr(preview, 'Catalog', lambda: Catalog(tmp_path/'skills.json'))
    def emit(update):
        updates.append(update)
        stop.set()
    preview.watch(RunRequest(Mode.NORMAL, None), stop, emit)
    assert calls == (['connect', 'foreground', 'peek'] if foreground == config.PACKAGE else ['connect', 'foreground'])
    assert len(updates) == 1 and isinstance(updates[0], Observation)
    assert not (tmp_path/'skills.json').exists()


def test_capture_error_does_not_trigger_recovery(monkeypatch):
    provider = SimpleNamespace(adb='adb', connect=lambda: 'device')
    monkeypatch.setattr(preview, 'create_provider', lambda request, stop: provider)
    class Device:
        def __init__(self, *args, **kwargs):
            pass
        def foreground_package(self):
            return config.PACKAGE
        def peek(self):
            raise RuntimeError('capture unavailable')
    monkeypatch.setattr(preview, 'Device', Device)
    monkeypatch.setattr(preview, 'Ocr', lambda: None)
    with pytest.raises(RuntimeError, match='capture unavailable'):
        preview.watch(RunRequest(Mode.NORMAL, None), threading.Event(), lambda view: None)


def test_device_peek_does_not_close_overlays_or_run_the_watchdog(monkeypatch):
    from roguebot.device import Device
    calls = []
    device = object.__new__(Device)
    device._stop = None
    device.viewport = SimpleNamespace(normalize=lambda img: calls.append('normalize') or img)
    device.capture_raw = lambda: calls.append('capture') or 'image'
    device.close_overlays = lambda: pytest.fail('read-only preview closed an overlay')
    device._watch = lambda img: pytest.fail('read-only preview ran recovery checks')
    assert device.peek() == 'image' and calls == ['capture', 'normalize']
