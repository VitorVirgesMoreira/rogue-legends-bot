"""Inspect already running Google emulator; gestures target the last saved OCR.

No coordinate guesses, matches, purchases or application launches. `--tap-text`
requires an exact previously observed label (one match); `--back` sends Back.
"""

import argparse
from dataclasses import asdict
import json
import re
import sys
from pathlib import Path

import cv2

from roguebot.device import Device
from roguebot.providers.google_play_games import GooglePlayGamesProvider
from roguebot.vision import Ocr, Text, normalize


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--tap-text")
    parser.add_argument("--back", action="store_true")
    parser.add_argument("--lobby", action="store_true")
    parser.add_argument("--menu", action="store_true")
    parser.add_argument("--modes-top", action="store_true")
    parser.add_argument("--equip", action="store_true")
    parser.add_argument("--pets", action="store_true")
    parser.add_argument("--account-slot", type=int, choices=range(6))
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--close", action="store_true")
    parser.add_argument("--arrow", action="store_true")
    parser.add_argument("--stats-scroll", action="store_true")
    parser.add_argument("--companion", type=int, choices=range(3))
    parser.add_argument("--pet-index", type=int, choices=range(16))
    parser.add_argument("--tree-node", type=int)
    parser.add_argument("--bag-index", type=int)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.name):
        parser.error("Use a plain capture name")
    provider = GooglePlayGamesProvider()
    device = Device(provider.connect(), adb=provider.adb)
    ocr = Ocr()
    if args.stats_scroll:
        from roguebot import config
        if not any(t.norm == "stats details" for t in ocr.read(device.peek())):
            parser.error("Expected Stats Details")
        device.swipe(*config.ACCOUNT_STATS_SCROLL, duration=.8)
        device.wait(.8)
    elif args.close:
        from roguebot.screens import close_button
        point = close_button(device.peek())
        if point is None:
            parser.error("No recognized close button")
        device.tap(*point)
        device.wait(.6)
    elif args.arrow:
        from roguebot.mode_screens import back_arrow
        point = back_arrow(device.peek())
        if point is None:
            parser.error("No recognized back arrow")
        device.tap(*point)
        device.wait(.6)
    if args.bag_index is not None:
        texts = ocr.read(device.peek())
        if not any(t.norm == "bag" and 400 < t.center[1] < 650 or t.norm.startswith("you own:") for t in texts):
            parser.error("Expected Bag")
        values = sorted((t for t in texts if 650 < t.center[1] < 1800 and 250 < t.center[0] < 1200 and
                        re.fullmatch(r"x?\d+(?:[.,]\d+)?[kmb]?",t.norm)),key=lambda t:(round(t.center[1]/100),t.center[0]))
        if not 0 <= args.bag_index < len(values):
            parser.error("No such bag item")
        x,y = values[args.bag_index].center
        device.tap(x,y-90)
        device.wait(.8)
    elif args.tree_node is not None:
        from roguebot.account_screens import researched_nodes
        points = researched_nodes(ocr.read(device.peek()))
        if not 0 <= args.tree_node < len(points):
            parser.error("No such researched node on this tree page")
        device.tap(*points[args.tree_node])
        device.wait(.8)
    elif args.pet_index is not None:
        from roguebot import config
        if not any(t.norm == "owned pets bonus" for t in ocr.read(device.peek())):
            parser.error("Expected Pets collection")
        device.tap(config.ACCOUNT_PET_COLUMNS[args.pet_index % 4], config.ACCOUNT_PET_ROWS[args.pet_index // 4])
        device.wait(.8)
    elif args.companion is not None:
        from roguebot import config
        texts = ocr.read(device.peek())
        if not any(t.norm == "companions" for t in texts) or not any(t.norm == "heroes" for t in texts):
            parser.error("Expected Heroes")
        device.tap(*config.ACCOUNT_COMPANIONS[args.companion])
        device.wait(.8)
    elif args.account_slot is not None or args.stats:
        from roguebot import config
        current = ocr.read(device.peek())
        if not any(t.norm == "workshop" for t in current) or not any(t.norm == "heroes" for t in current):
            parser.error("Expected the equipped items page")
        point = config.ACCOUNT_STATS_BUTTON if args.stats else config.ACCOUNT_EQUIP_SLOTS[args.account_slot]
        device.tap(*point)
        device.wait(.8)
    elif args.equip or args.pets:
        from roguebot import config
        from roguebot.screens import parse_lobby, footer_visible
        img = device.peek()
        if not parse_lobby(ocr.read(img)):
            parser.error("Equipment tab requires a recognized unobscured lobby")
        device.tap(*(config.PETS_TAB if args.pets else config.EQUIP_TAB))
        device.wait(.8)
    elif args.modes_top:
        from roguebot import config
        from roguebot.mode_screens import is_modes_list
        if not is_modes_list(ocr.read(device.peek())):
            parser.error("Expected the mode list")
        device.swipe(*config.MODES_SCROLL_UP, duration=config.SCROLL_DURATION)
        device.wait(.8)
    elif args.lobby:
        from roguebot.navigation import Navigator
        Navigator(device, ocr).go_to_lobby()
    elif args.menu:
        from roguebot import config
        from roguebot.screens import parse_lobby
        if not parse_lobby(ocr.read(device.peek())):
            parser.error("Menu requires a recognized lobby")
        device.tap(*config.MENU_BUTTON)
        device.wait(.8)
    elif args.tap_text:
        if args.previous is None:
            parser.error("--tap-text requires --previous")
        previous = json.loads(args.previous.read_text(encoding="utf-8"))
        prior = [Text(**item) for item in previous["texts"]]
        # Re-read the current frame; a stale saved screen never authorizes input.
        current = ocr.read(device.peek())
        values = [t for t in current if t.norm == normalize(args.tap_text)]
        old = [t for t in prior if t.norm == normalize(args.tap_text)]
        if len(values) != 1 or len(old) != 1 or abs(values[0].center[0]-old[0].center[0]) > 30 or abs(values[0].center[1]-old[0].center[1]) > 30:
            parser.error("Target is absent, ambiguous or changed")
        device.tap(*values[0].center)
        device.wait(.8)
    elif args.back:
        device.back()
        device.wait(.8)
    image = device.peek()
    texts = ocr.read(image)
    folder = Path("captures/guide_probe")
    folder.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(folder / (args.name + ".png")), image)
    value = {"texts": [asdict(t) for t in texts]}
    (folder / (args.name + ".json")).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(f"{t.text} @ {t.center}" for t in texts))


if __name__ == "__main__":
    main()
