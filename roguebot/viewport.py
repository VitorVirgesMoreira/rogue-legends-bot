"""One screenshot/input transform. Landscape crops require visible evidence of 9:16 borders."""

from dataclasses import dataclass
import math

import cv2
import numpy as np

from roguebot import config


class ViewportError(Exception):
    """No trustworthy game rectangle; no input may use the previous mapping."""


@dataclass(frozen=True)
class Viewport:
    left: int
    top: int
    width: int
    height: int
    display_width: int
    display_height: int
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if (min(self.width, self.height, self.display_width, self.display_height) <= 0
                or min(self.left, self.top) < 0
                or self.left + self.width > self.display_width
                or self.top + self.height > self.display_height
                or not 0.9 <= self.confidence <= 1
                or abs(self.width / self.height / (9 / 16) - 1) > config.ASPECT_TOLERANCE):
            raise ViewportError(f"Invalid viewport: {self}")

    def to_device(self, x: float, y: float) -> tuple[int, int]:
        rw, rh = config.SCREEN_SIZE
        if not (math.isfinite(x) and math.isfinite(y) and 0 <= x <= rw and 0 <= y <= rh):
            raise ViewportError(f"Reference point outside {rw}x{rh}: ({x}, {y})")
        # The mathematical far edge is outside the last pixel; clamp only that rounding overflow.
        return (min(self.left + self.width - 1, round(self.left + x * self.width / rw)),
                min(self.top + self.height - 1, round(self.top + y * self.height / rh)))

    def to_reference(self, x: float, y: float) -> tuple[float, float]:
        if not (self.left <= x < self.left + self.width and self.top <= y < self.top + self.height):
            raise ViewportError(f"Device point outside viewport: ({x}, {y})")
        rw, rh = config.SCREEN_SIZE
        return (x - self.left) * rw / self.width, (y - self.top) * rh / self.height

    def normalize(self, image: np.ndarray) -> np.ndarray:
        if image.shape[:2] != (self.display_height, self.display_width):
            raise ViewportError("Screenshot resolution changed; detect the viewport again")
        crop = image[self.top:self.top + self.height, self.left:self.left + self.width]
        return cv2.resize(crop, config.SCREEN_SIZE, interpolation=cv2.INTER_CUBIC) if (
            self.width, self.height) != config.SCREEN_SIZE else crop


def detect_viewport(image: np.ndarray) -> Viewport:
    """Accept portrait, or full-height centered 9:16 content with almost entirely black sides.

    Never crop to the bounding box of bright game pixels: a dark scene must not shrink the game.
    Both measured border transitions must agree with the aspect-derived rectangle (within 2 px).
    An entirely black/ambiguous landscape frame is rejected, including during loading.
    """
    if image is None or image.ndim != 3 or image.shape[2] != 3 or image.size == 0:
        raise ViewportError("Invalid screenshot; expected a nonempty BGR image")
    height, width = image.shape[:2]
    if abs(width / height / (9 / 16) - 1) <= config.ASPECT_TOLERANCE:
        return Viewport(0, 0, width, height, width, height)
    expected = height * 9 / 16
    if width <= height or expected >= width:
        raise ViewportError(f"Unsupported display {width}x{height}; expected portrait 9:16 or black sidebars")
    # Sample roughly 256 rows. This makes the per-frame cache validation cheap.
    pixels = image[::max(1, height // 256)].max(axis=2)
    expected_left = (width - expected) / 2
    # Dark dialogs can leave both game edges nearly black. Against black bars, their faint
    # pixels still show where the game ends. Apply the same geometry checks at either threshold.
    for threshold in (8, 0):
        columns = np.flatnonzero((pixels > threshold).mean(axis=0) > 0.01)
        if not columns.size:
            raise ViewportError(f"Ambiguous black frame on {width}x{height}; wait for visible game content")
        left, right = int(columns[0]), int(columns[-1]) + 1
        if (abs(left - expected_left) <= 2 and abs(right - (expected_left + expected)) <= 2
                and abs((right - left) - expected) <= 2):
            return Viewport(left, 0, right - left, height, width, height, 0.99)
    raise ViewportError(f"Uncertain viewport on {width}x{height}: measured x={left}:{right}; "
                        f"expected centered width {expected:.1f}. No input sent.")


class ViewportTracker:
    """Reuse a stable rectangle, checking its borders on every new screenshot."""

    def __init__(self) -> None:
        self.current: Viewport | None = None

    def update(self, image: np.ndarray) -> Viewport:
        previous = self.current
        self.current = None  # a failed detection must invalidate old input coordinates
        height, width = image.shape[:2]
        if previous and (previous.display_width, previous.display_height) == (width, height):
            if previous.left == 0 and previous.width == width:
                self.current = previous
                return previous
            # Validate just narrow strips on both sides of each boundary, across the full height.
            p = image[::max(1, height // 256)]
            left, right = previous.left, previous.left + previous.width
            outside = np.concatenate((p[:, :left:8], p[:, right::8]), axis=1)
            edges = p[:, [left, right - 1]].max(axis=2)
            if ((outside.max(axis=2) > 8).mean() < 0.001 and ((edges > 8).mean(axis=0) > 0.01).all()):
                self.current = previous
                return previous
        self.current = detect_viewport(image)
        return self.current
