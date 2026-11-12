"""Vote along visible room connections toward the nearest treasure, then prefer easier fights."""

from dataclasses import dataclass
from functools import lru_cache
import math

import cv2
import numpy as np

from roguebot.vision import Text
from roguebot.game_locale import contains_term

ROOMS = {"treasure", "campfire", "battle", "elite battle", "boss battle"}
ROOM_TRANSLATIONS = {"tesouro": "treasure", "tesoro": "treasure", "fogueira": "campfire", "hoguera": "campfire",
    "batalha": "battle", "batalla": "battle", "batalha elite": "elite battle", "batalla elite": "elite battle",
    "batalha de chefe": "boss battle", "batalla de jefe": "boss battle"}


@dataclass(frozen=True)
class Room:
    kind: str
    point: tuple[int, int]  # the room's label; the hexagon center is 150 px above it
    available: bool = False


def _available(hsv, point) -> bool:
    x, y = point
    patch = hsv[max(0, y-270):max(0, y-60), max(0, x-105):x+105]
    if not patch.size:
        return False
    purple = (patch[..., 0] >= 120) & (patch[..., 0] <= 165) & (patch[..., 1] >= 55) & (patch[..., 2] >= 140)
    return bool(purple.mean() >= .12)  # selectable hexagons are bright purple; completed/current ones aren't


def visible_rooms(img, texts: list[Text]) -> list[Room]:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return [Room(ROOM_TRANSLATIONS.get(t.norm, t.norm), t.center, _available(hsv, t.center)) for t in texts
            if ROOM_TRANSLATIONS.get(t.norm, t.norm) in ROOMS and 250 < t.center[1] < 2350]


def _connected(hsv, lower: Room, upper: Room, spacing: float) -> bool:
    if abs(lower.point[0] - upper.point[0]) > .9 * spacing:
        return False
    # Sample the middle of the dashed purple path, excluding both room icons.
    patches = []
    for t in np.linspace(.32, .68, 40):
        x = round(lower.point[0] + t * (upper.point[0] - lower.point[0]))
        y = round(lower.point[1] - 150 + t * (upper.point[1] - lower.point[1]))
        patches.append(hsv[max(0, y-3):y+4, max(0, x-3):x+4].reshape(-1, 3))
    pixels = np.concatenate(patches)
    path = (pixels[:, 0] >= 110) & (pixels[:, 0] <= 170) & (pixels[:, 2] < 130)
    return bool(path.mean() >= .07)


def room_graph(img, rooms: list[Room]) -> dict[int, list[int]]:
    rows: list[list[int]] = []
    for i in sorted(range(len(rooms)), key=lambda i: rooms[i].point[1]):
        if not rows or rooms[i].point[1] - rooms[rows[-1][0]].point[1] > 100:
            rows.append([])
        rows[-1].append(i)
    gaps = [b-a for row in rows for a, b in zip(sorted(rooms[i].point[0] for i in row),
                                               sorted(rooms[i].point[0] for i in row)[1:]) if b-a > 100]
    spacing = float(np.median(gaps)) if gaps else 500
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    return {lower: [upper for upper in rows[row-1] if _connected(hsv, rooms[lower], rooms[upper], spacing)]
            for row in range(1, len(rows)) for lower in rows[row]}


def best_route(rooms: list[Room], graph: dict[int, list[int]], context=None) -> int | None:
    """Nearest reachable chest first, more subsequent chests next, fewer elite fights on ties."""
    candidates = [i for i, room in enumerate(rooms) if room.available]
    reachable = set()
    def visit(i):
        if i in reachable:
            return
        reachable.add(i)
        for j in graph.get(i, []):
            visit(j)
    for i in candidates:
        visit(i)
    low_health = context is not None and context.team_hp and min(context.team_hp) <= .35
    goal = "campfire" if low_health and any(rooms[i].kind == "campfire" for i in reachable) else "treasure"
    @lru_cache(None)
    def score(i):
        room = rooms[i]
        following = min((score(j) for j in graph.get(i, [])), default=(math.inf, 0, 0, 0))
        distance = 0 if room.kind == goal else following[0] + 1
        return (distance, following[1] - (room.kind == "treasure"),
                following[2] + (room.kind == "elite battle"), following[3] + (room.kind == "battle"))
    return min(candidates, key=lambda i: (score(i), rooms[i].point[0])) if candidates else None


def route_vote(img, texts: list[Text], context=None) -> tuple[int, int] | None:
    if not any(contains_term(t.norm, "route") and any(word in t.norm for word in ("vote", "votar")) for t in texts):
        return None  # no votes while the party is already moving
    rooms = visible_rooms(img, texts)
    choice = best_route(rooms, room_graph(img, rooms), context)
    return rooms[choice].point if choice is not None else None
