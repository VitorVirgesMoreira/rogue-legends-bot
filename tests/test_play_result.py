"""Real Google result: skipping x2 leaves the screen, so record victory before Continue."""

from pathlib import Path

import cv2
import pytest

from roguebot import config, labels
from roguebot.play import Player
from roguebot.screens import LevelScreen
from roguebot.skills import Catalog
from roguebot.vision import Text, find
from test_party import ReplayDevice, ReplayOcr


def test_skip_is_available_in_each_level_fight(tmp_path, monkeypatch):
    fight = [Text("Round: 1/30", 520, 175, 880, 230), Text("Skip", 860, 2400, 980, 2450)]
    victory = [Text("VICTORY!", 560, 560, 880, 635), Text("Continue", 540, 2180, 900, 2260)]
    board = cv2.imread(str(Path(__file__).parent / "fixtures/level_board_auto.png"))
    device = ReplayDevice([fight, fight, (board, []), fight, victory, victory])
    monkeypatch.setattr("roguebot.play.time.sleep", lambda _: None)
    player = Player(device, ReplayOcr(device), catalog=Catalog(tmp_path / "skills.json"))
    assert player.play_level() is LevelScreen.VICTORY
    assert device.taps == [(920, 2425), (920, 2425), (720, 2220)]


@pytest.mark.parametrize("ads", [False, True])
@pytest.mark.parametrize("victory", [True, False])
def test_result_is_returned_before_continue_leaves_the_screen(ocr, tmp_path, ads, victory):
    image = cv2.imread(str(Path(__file__).parent / "fixtures/en_google_level_victory_x2.png"))
    texts = ocr.read(image)
    if not victory:
        texts = [Text("DEFEAT" if "VICTORY" in t.text else t.text, t.x1, t.y1, t.x2, t.y2) for t in texts]
    class Device:
        frames = 0
        taps = []

        def screenshot(self):
            self.frames += 1
            assert self.frames <= (config.DOUBLE_REWARD_TRIES + 2 if ads else 2)
            return image

        def tap(self, x, y):
            self.taps.append((x, y))
    class Ocr:
        def read(self, img):
            return texts
    device = Device()
    try:
        labels.set_language("en")
        player = Player(device, Ocr(), catalog=Catalog(tmp_path / "skills.json"), ads=ads)
        result = player.play_level()
        assert result is (LevelScreen.VICTORY if victory else LevelScreen.DEFEAT)
        assert player.result_values[1] == {"gold": 22_000}
        assert device.taps[-1] == find(texts, labels.CONTINUE, exact=True).center
        double = find(texts, labels.DOUBLE_REWARD).center
        assert device.taps[:-1] == ([double] * config.DOUBLE_REWARD_TRIES if ads else [])
    finally:
        labels.set_language(None)
