"""Failed writes preserve user data and remain retryable."""

import json

import pytest

from roguebot import persistence, settings
from roguebot.skills import Catalog


@pytest.mark.parametrize("data", [None, [], "settings", 42, True])
def test_settings_ignore_valid_json_with_the_wrong_root(tmp_path, data):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert settings.load(path) == {}
    settings.save({"lang": "pt"}, path)
    assert settings.load(path) == {"lang": "pt"}


def test_failed_replace_keeps_old_file_and_removes_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    settings.save({"lang": "pt", "unrelated": True}, path)
    original = path.read_bytes()

    def fail(source, destination):
        assert source.parent == destination.parent
        assert json.loads(source.read_text(encoding="utf-8"))["lang"] == "en"
        raise OSError("disk unavailable")

    monkeypatch.setattr(persistence.os, "replace", fail)
    with pytest.raises(OSError, match="disk unavailable"):
        settings.save({"lang": "en"}, path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_serialization_failure_never_changes_the_destination(tmp_path):
    path = tmp_path / "data.json"
    persistence.write_json(path, {"original": True})
    original = path.read_bytes()
    with pytest.raises(TypeError):
        persistence.write_json(path, {"invalid": object()})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_catalog_retries_a_skill_whose_save_failed(tmp_path, monkeypatch):
    path = tmp_path / "skills.json"
    catalog = Catalog(path)
    replace = persistence.os.replace

    def fail(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(persistence.os, "replace", fail)
    with pytest.raises(OSError):
        catalog.lookup("Fire Wave", "Fire damage.", "common", "en")
    assert catalog.skills == {} and not path.exists()
    monkeypatch.setattr(persistence.os, "replace", replace)
    catalog.lookup("Fire Wave", "Fire damage.", "common", "en")
    assert Catalog(path).skills["firewave"].name == "Fire Wave"
