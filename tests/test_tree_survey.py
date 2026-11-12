"""Tree coverage, zoom and read-only filtering without an attached emulator."""

import cv2
import hashlib
import json
from pathlib import Path
import zipfile
import numpy as np
import pytest

from roguebot import account_screens as S
from roguebot import tree_survey
from roguebot.device import DeviceError, Stopped
from roguebot.tree_survey import TreeSurvey
from roguebot.vision import Text


class World:
    def __init__(self, *, zoomed=True, width=2700, height=4100):
        self.x, self.y = 900, 1900
        self.width, self.height = width, height
        self.zoomed = zoomed
        self.pans, self.pinches = [], []
        self.cached = None

    def read(self):
        identity = self.x, self.y, self.zoomed
        if self.cached is None or self.cached[0] != identity:
            yy, xx = np.mgrid[:224, :144]
            pattern = ((xx + self.x//10)//7 * 29 + (yy + self.y//10)//9 * 37) % 160 + 40
            image = np.full((2560, 1440, 3), 40, np.uint8)
            gray = cv2.resize(pattern.astype(np.uint8), (1340, 2180))
            image[120:2300, 50:1390] = gray[..., None]
            if self.zoomed:
                image[300:700, 400:700] = 250
            height = 44 if self.zoomed else 24
            texts = [Text("1/4", 600, 1300, 680, 1300+height)]
            self.cached = identity, image, texts
        return self.cached[1:]

    def swipe(self, start, end, duration):
        dx, dy = end[0]-start[0], end[1]-start[1]
        self.pans.append((dx, dy))
        self.x = max(0, min(self.width, self.x-dx))
        self.y = max(0, min(self.height, self.y-dy))

    def pinch(self, *points, duration):
        self.pinches.append(points)
        self.zoomed = False


def test_zoom_then_serpentine_covers_both_sides_and_all_vertical_rows():
    world = World()
    survey = TreeSurvey(world, world.read, S.tree_rank_labels)
    positions = []
    for _, _, _ in survey.views():
        positions.append((world.x, world.y))
    assert len(world.pinches) == 1
    assert positions[0] == (0, 4100)
    assert {y for _, y in positions} == {0, 1300, 2700, 4100}
    for y in {y for _, y in positions}:
        assert (0, y) in positions and (2700, y) in positions
    assert any(dx < 0 for dx, _ in world.pans) and any(dx > 0 for dx, _ in world.pans)
    assert any(dy < 0 for _, dy in world.pans) and any(dy > 0 for _, dy in world.pans)
    assert not survey.limit_reached


def test_an_already_open_zoom_is_preserved():
    world = World(zoomed=False)
    TreeSurvey(world, world.read, S.tree_rank_labels).zoom_out()
    assert world.pinches == []


def test_unavailable_zoom_keeps_lateral_coverage_and_stop_is_not_swallowed():
    world = World()
    def fail(*a, **k):
        raise DeviceError("unsupported")
    world.pinch = fail
    survey = TreeSurvey(world, world.read, S.tree_rank_labels)
    assert list(survey.views())
    assert any(dx for dx, _ in world.pans)
    def stop(*a, **k):
        raise Stopped("cancelled")
    world.pinch = stop
    with pytest.raises(Stopped):
        survey.zoom_out()


def test_unbounded_canvas_still_respects_the_scan_limits(monkeypatch):
    monkeypatch.setattr(tree_survey, "MAX_AXIS_PANS", 2)
    monkeypatch.setattr(tree_survey, "MAX_ROWS", 3)
    monkeypatch.setattr(tree_survey, "MAX_COLUMNS", 3)
    world = World(zoomed=False, width=100000, height=100000)
    survey = TreeSurvey(world, world.read, S.tree_rank_labels)
    assert len(list(survey.views())) == 9
    assert survey.limit_reached and len(world.pans) <= 16


def test_stat_squares_are_excluded_and_more_than_six_skill_nodes_are_kept():
    footer = [Text("Adventure", 450, 2400, 750, 2500), Text("Specialization", 800, 2400, 1150, 2500)]
    nodes = [Text("1/4", 300+(i%3)*240, 300+(i//3)*450, 360+(i%3)*240, 330+(i//3)*450) for i in range(9)]
    squares = [Text(rank, 100, 300+i*200, 160, 330+i*200) for i, rank in enumerate(("1/10", "5/10", "10/10", "0/10"))]
    locked = Text("0/4", 1100, 1200, 1160, 1230)
    assert S.researched_nodes(footer+nodes+squares+[locked]) == tuple(t.center for t in nodes)


def test_node_tap_scales_with_rank_text_and_never_uses_the_footer():
    small = Text("3/4", 600, 1200, 650, 1220)
    large = Text("3/4", 600, 1200, 700, 1240)
    assert S.tree_node_tap([small], small.center) == (625, 1180)
    assert S.tree_node_tap([large], large.center) == (650, 1160)
    assert not S.tree_rank_labels([Text("1/4", 600, 2400, 650, 2430)])


def test_small_animation_and_footer_changes_do_not_create_infinite_panning():
    world = World(zoomed=False)
    image, _ = world.read()
    after = image.copy()
    after[2350:] = 250
    after[400:410, 300:310] = 250
    assert tree_survey.same_view(image, after)


def test_bundled_gesture_matches_its_source_and_contains_android_dex():
    root = Path(__file__).parents[1]
    jar = root / "roguebot/assets/tree-gesture.jar"
    metadata = json.loads(jar.with_suffix(".json").read_text(encoding="utf-8"))
    assert hashlib.sha256(jar.read_bytes()).hexdigest() == metadata["jar_sha256"]
    assert hashlib.sha256((root / "tools/android/TreeGesture.java").read_bytes()).hexdigest() == metadata["source_sha256"]
    with zipfile.ZipFile(jar) as archive:
        dex = archive.read("classes.dex")
    assert dex.startswith(b"dex\n035\0") and b"ROGUEBOT_PINCH_OK" in dex
