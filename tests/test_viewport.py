"""Geometry independent of gameplay: synthetic boundaries and a real landscape screenshot."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from roguebot import config
from roguebot.viewport import Viewport, ViewportError, ViewportTracker, detect_viewport


def letterbox(width=1920, height=1080, value=80):
    image = np.zeros((height, width, 3), np.uint8)
    left = round((width - height * 9 / 16) / 2)
    image[:, left:width - left] = value
    return image


@pytest.mark.parametrize("width,height", [(1440, 2560), (1080, 1920), (720, 1280)])
def test_portrait_keeps_entire_frame_including_dark_game_edges(width, height):
    image = np.zeros((height, width, 3), np.uint8)
    image[height // 2, width // 2] = 255
    v = detect_viewport(image)
    assert (v.left, v.top, v.width, v.height) == (0, 0, width, height)
    assert v.normalize(image).shape == (2560, 1440, 3)


@pytest.mark.parametrize("width,height", [(1920, 1080), (2560, 1440), (1280, 720), (1600, 900)])
def test_landscape_crop_and_normalization(width, height):
    image = letterbox(width, height)
    v = detect_viewport(image)
    assert abs(v.width - height * 9 / 16) <= 1
    assert v.left == width - v.left - v.width
    assert np.all(v.normalize(image) == 80)


def test_dark_scene_is_not_cropped_to_its_bright_interior():
    image = letterbox(value=9)
    image[300:600, 800:1000] = 255
    assert detect_viewport(image).width == 608


@pytest.mark.parametrize("name", ["en_mines_ticket.png", "en_mines_no_tickets.png", "en_tower_defeat.png"])
def test_faint_scene_borders_are_visible_against_black_google_bars(name):
    portrait = cv2.imread(str(Path(__file__).parent / "fixtures" / name))
    game = cv2.resize(portrait, (608, 1080), interpolation=cv2.INTER_AREA)
    image = cv2.copyMakeBorder(game, 0, 0, 656, 656, cv2.BORDER_CONSTANT)
    tracker = ViewportTracker()
    lobby = tracker.update(letterbox())

    assert detect_viewport(image) == lobby
    assert tracker.update(image) == lobby


def test_faint_borders_cannot_validate_a_narrower_frame():
    image = letterbox(value=4)
    image[:, 656:680] = 0
    image[:, 1240:1264] = 0
    image[300:600, 800:1000] = 255
    tracker = ViewportTracker()
    tracker.update(letterbox())
    with pytest.raises(ViewportError, match="Uncertain"):
        tracker.update(image)
    assert tracker.current is None


@pytest.mark.parametrize("image", [np.zeros((1080, 1920, 3), np.uint8),
                                  np.full((1080, 1920, 3), 80, np.uint8),
                                  np.zeros((2400, 1080, 3), np.uint8),
                                  np.zeros((0, 0, 3), np.uint8), None])
def test_uncertain_or_invalid_images_fail_closed(image):
    with pytest.raises(ViewportError):
        detect_viewport(image)


def test_asymmetric_and_wrong_aspect_bars_are_rejected():
    image = letterbox()
    image[:, 600:700] = 80
    with pytest.raises(ViewportError, match="Uncertain"):
        detect_viewport(image)
    image = np.zeros_like(image)
    image[:, 710:1210] = 80
    with pytest.raises(ViewportError):
        detect_viewport(image)


def test_near_black_sidebars_allow_minor_noise():
    image = letterbox()
    image[:, :656] = 4
    image[:, 1264:] = 4
    assert detect_viewport(image).left == 656


def test_round_trips_and_edges_use_one_transform():
    v = detect_viewport(letterbox())
    for x, y in [(0, 0), (720, 1280), (100, 200), (1430, 2550)]:
        dx, dy = v.to_device(x, y)
        rx, ry = v.to_reference(dx, dy)
        assert abs(x - rx) <= config.SCREEN_SIZE[0] / v.width / 2
        assert abs(y - ry) <= config.SCREEN_SIZE[1] / v.height / 2
    assert v.to_device(0, 0) == (656, 0)
    assert v.to_device(720, 1280) == (960, 540)
    assert v.to_device(1440, 2560) == (1263, 1079)
    for point in [(-1, 0), (0, 2561), (1441, 0), (float("nan"), 0)]:
        with pytest.raises(ViewportError):
            v.to_device(*point)


def test_invalid_bounds_and_mismatched_capture():
    with pytest.raises(ViewportError):
        Viewport(-1, 0, 608, 1080, 1920, 1080)
    with pytest.raises(ViewportError):
        Viewport(0, 0, 608, 1080, 1920, 1080, 0.2)
    with pytest.raises(ViewportError):
        detect_viewport(letterbox()).normalize(letterbox(2560, 1440))


def test_cached_mapping_rechecks_borders_and_recalculates_resolution(monkeypatch):
    import roguebot.viewport as module
    tracker = ViewportTracker()
    first = tracker.update(letterbox())
    original = module.detect_viewport
    calls = []
    monkeypatch.setattr(module, "detect_viewport", lambda img: calls.append(img.shape) or original(img))
    assert tracker.update(letterbox()) is first and not calls
    assert tracker.update(letterbox(2560, 1440)).width == 810
    assert len(calls) == 1
    with pytest.raises(ViewportError):
        tracker.update(np.full((1440, 2560, 3), 80, np.uint8))
    assert tracker.current is None


def test_real_google_screenshot():
    image = cv2.imread(str(Path(__file__).parent / "fixtures" / "google_lobby_landscape.png"))
    v = detect_viewport(image)
    assert (v.left, v.top, v.width, v.height) == (656, 0, 608, 1080)
    assert v.normalize(image).shape == (2560, 1440, 3)


def test_existing_recognition_reads_real_normalized_google_lobby(ocr):
    from roguebot import labels
    from roguebot.screens import parse_lobby, footer_visible
    image = cv2.imread(str(Path(__file__).parent / "fixtures" / "google_lobby_landscape.png"))
    normalized = detect_viewport(image).normalize(image)
    try:
        labels.set_language("en")
        lobby = parse_lobby(ocr.read(normalized))
        assert lobby is not None and lobby.level_title == "38. Runelight Caverns VI"
        assert lobby.energy == 81 and footer_visible(normalized)
    finally:
        labels.set_language(None)
