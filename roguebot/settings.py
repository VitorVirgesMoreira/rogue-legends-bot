"""UI settings kept between sessions in data/settings.json; old keys remain compatible."""

import json
import shutil
import sys
from pathlib import Path

from roguebot.persistence import write_json


def data_dir() -> Path:
    """The writable data folder: next to the exe when frozen (PyInstaller unpacks the package into a
    temp folder deleted on exit), else the repo's data/."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "data"
    return Path(__file__).parent.parent / "data"


def seed_data(target: Path, bundled: Path) -> None:
    """First run of the exe: copy the bundled skill database next to it (never overwrites user edits)."""
    if bundled.exists() and not (target / "skills.json").exists():
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bundled, target / "skills.json")


DATA_DIR = data_dir()
SETTINGS_PATH = DATA_DIR / "settings.json"


def load(path: Path = SETTINGS_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(values: dict, path: Path = SETTINGS_PATH) -> None:
    write_json(path, {**load(path), **values})
