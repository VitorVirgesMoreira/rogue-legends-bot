"""Bounded two-dimensional tree traversal, independent of skill-detail reading."""

import logging
from statistics import median

import cv2

from roguebot.device import DeviceError

log = logging.getLogger(__name__)
MAX_AXIS_PANS = 12
MAX_ROWS, MAX_COLUMNS = 16, 8
ZOOM_TARGET_TEXT_HEIGHT = 28


def same_view(first, second):
    """Ignore footer badges and minor icon animation when detecting a pan limit."""
    def thumbnail(image):
        gray = cv2.cvtColor(image[120:2300, 50:1390], cv2.COLOR_BGR2GRAY)
        return cv2.GaussianBlur(cv2.resize(gray, (144, 224)), (3, 3), 0)
    return float(cv2.absdiff(thumbnail(first), thumbnail(second)).mean()) < 1.3


class TreeSurvey:
    def __init__(self, device, read_view, rank_labels):
        self.device, self.read_view, self.rank_labels = device, read_view, rank_labels
        self.limit_reached = False

    def zoom_out(self):
        pinch = getattr(self.device, "pinch", None)
        if pinch is None:
            log.info("Tree: two-finger zoom unavailable; covering the tree by panning")
            return
        for _ in range(3):
            image, texts = self.read_view()
            heights = [t.y2 - t.y1 for t in self.rank_labels(texts)]
            if heights and median(heights) <= ZOOM_TARGET_TEXT_HEIGHT:
                return
            try:
                pinch((270, 1200), (1170, 1200), (490, 1200), (950, 1200), duration=.6)
            except DeviceError as exc:
                log.warning("Tree zoom unavailable: %s; continuing lateral coverage", exc)
                return
            after, _ = self.read_view()
            if same_view(image, after):
                return

    def pan(self, dx, dy):
        before, _ = self.read_view()
        start = (720 - dx // 2, 1200 - dy // 2)
        end = (720 + dx // 2, 1200 + dy // 2)
        self.device.swipe(start, end, duration=.8)
        after, _ = self.read_view()
        return not same_view(before, after)

    def anchor(self):
        # Finger right -> leftmost branch. Finger up -> bottom/root of the tree.
        for delta in ((960, 0), (0, -1400)):
            for _ in range(MAX_AXIS_PANS):
                if not self.pan(*delta):
                    break
            else:
                self.limit_reached = True

    def views(self):
        self.zoom_out()
        self.anchor()
        direction = -1
        for row in range(MAX_ROWS):
            for column in range(MAX_COLUMNS):
                image, texts = self.read_view()
                yield (row, column), image, texts
                if not self.pan(direction * 960, 0):
                    break
            else:
                self.limit_reached = True
            # Serpentine rows retain overlap and visit both lateral branches.
            if not self.pan(0, 1400):
                return
            direction *= -1
        self.limit_reached = True
