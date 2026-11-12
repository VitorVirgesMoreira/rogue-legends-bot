"""Bounded account inspection through ADB screenshots and navigation only."""

from dataclasses import asdict
from pathlib import Path
import json
import hashlib
import logging
import re
import time

import cv2

from roguebot import config, labels
from roguebot import account_screens as S
from roguebot.account_state import AccountSnapshot, suggest_strategy, checkpoint, cached_snapshot
from roguebot.device import Device, ViewportUnavailable
from roguebot.emulator import EmulatorError
from roguebot.mode_screens import back_arrow, parse_power
from roguebot.navigation import IN_LEVEL, MAX_LOBBY_ATTEMPTS
from roguebot.polling import wait_for
from roguebot.providers import create_provider
from roguebot.screens import (
    Lobby, Mode, classify_level_screen, close_button, close_button_any_size, footer_visible, is_loading,
    is_star_list, lobby_behind, outside_tap_clear, parse_lobby, popup_close, update_required,
)
from roguebot.setup_guard import check_manual_setup
from roguebot.skill_data import key
from roguebot.vision import Ocr, find, parse_level_number

log = logging.getLogger(__name__)
CAPTURES = Path("debug/account_scan")


class AccountScanError(Exception):
    pass


def _same(a,b):
    if isinstance(a,Lobby) and isinstance(b,Lobby):
        return (a.mode,a.level_title,a.energy,a.has_elite) == (b.mode,b.level_title,b.energy,b.has_elite)
    if isinstance(a,tuple) and isinstance(b,tuple) and len(a)==len(b)==2 and all(type(v) is int for v in (*a,*b)):
        return all(abs(x-y)<15 for x,y in zip(a,b))
    return a == b


def _menu(texts):
    return bool(S.term(texts, "settings", hi=400) and S.term(texts, "bag", hi=800))


def _ready_lobby(img, texts):
    if footer_visible(img) and not _menu(texts):
        return parse_lobby(texts)


def _tree_close(img):
    return S.tree_close(img) or close_button(img)


def _tree_view(img, texts):
    return S.tree_page(texts) and _tree_close(img) is None


def _near_node(a, b):
    return abs(a[0] - b[0]) < 36 and abs(a[1] - b[1]) < 36


def _lobby_step(img, texts):
    """Find a clear lobby or a confirmed way back through the game's menus."""
    if update_required(texts):
        raise EmulatorError("err_game_update")
    if is_loading(texts):
        return None
    behind = lobby_behind(texts)
    if not behind and classify_level_screen(img, texts).kind in IN_LEVEL:
        raise AccountScanError("scan_in_adventure")
    if close := popup_close(texts):
        return close.center
    if close := close_button(img):
        return close
    if S.term(texts, "adventure", lo=2350) and (close := S.tree_close(img)):
        return close
    if S.tree_page(texts):
        return back_arrow(img)
    if _menu(texts):
        return config.MENU_BUTTON
    if footer_visible(img):
        return parse_lobby(texts) or config.AVENTURA_TAB
    if behind:
        if close := close_button_any_size(img):
            return close
        # The limited-offer panel can appear before its dismiss hint. Its purchase
        # buttons are above the dimmed footer where the hint normally appears.
        offer_titles = {"limited offer", "oferta limitada"}
        if any(t.norm.rstrip("!") in offer_titles and 700 < t.center[1] < 1100 for t in texts):
            if outside_tap_clear(texts):
                return config.POPUP_OUTSIDE_TAP
        return None
    if is_star_list(texts):
        return config.LIST_BACK
    return back_arrow(img)


class AccountReader:
    def __init__(self, device, ocr, *, progress=None, capture_dir=CAPTURES, budget=600, fresh=False, resume=True,
                 startup=False):
        self.device, self.ocr = device, ocr
        self.progress = progress or (lambda section: None)
        self.folder = Path(capture_dir) if capture_dir is not None else None
        self.deadline = time.monotonic() + budget
        self.snapshot = AccountSnapshot()
        self.last_image, self.last_texts = None, []
        self.section = "lobby"
        self.original_mode = None
        self.fresh, self.resume = fresh, resume
        self.startup = startup

    def _read(self):
        if time.monotonic() > self.deadline:
            raise AccountScanError("scan_timeout")
        if self.device.foreground_package() != config.PACKAGE:
            raise AccountScanError("scan_foreground")
        img = self.device.peek()  # never closes overlays or restarts a game
        texts = self.ocr.read(img)
        if not S.settings_page(texts):
            check_manual_setup(texts)
        if find(texts, labels.RESUME_ADVENTURE):
            raise AccountScanError("scan_in_adventure")
        self.last_image, self.last_texts = img, texts
        return img, texts

    def _stable(self, parse, *, required=True):
        previous = None
        viewport_error = None
        for _ in range(4):
            try:
                img, texts = self._read()
            except ViewportUnavailable as exc:
                # Some menu transitions briefly show a black letterboxed frame.
                viewport_error = exc
                previous = None
                self.device.wait(.4)
                continue
            viewport_error = None
            value = parse(img, texts)
            if value is not None and value is not False and _same(value,previous):
                return value
            previous = value
            self.device.wait(.2)
        if viewport_error is not None:
            raise viewport_error
        if required:
            raise AccountScanError("scan_unreadable")
        return None

    def _evidence(self, name, value):
        if self.folder is not None:
            self.folder.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r"[^a-z0-9_]", "_", name.lower())
            cv2.imwrite(str(self.folder / (safe + ".png")), self.last_image)
            (self.folder / (safe + ".json")).write_text(json.dumps({"texts": [asdict(t) for t in self.last_texts]},
                ensure_ascii=False, indent=2), encoding="utf-8")
        self.snapshot.evidence[name] = value

    def _phase(self, name):
        self.section = name
        self.progress(name)
        log.info("Reading account: %s", name)

    def _checkpoint(self):
        if self.resume:
            checkpoint(self.snapshot)

    def _label(self, names, *, guard=lambda img,texts: True, lo=0, hi=2560, xlo=0, xhi=1440):
        names = tuple(names)
        def parse(img, texts):
            if not guard(img,texts):
                return None
            matches = [t.center for t in texts if t.norm in names and lo <= t.center[1] <= hi
                       and xlo <= t.center[0] <= xhi]
            return matches[0] if len(matches) == 1 else None
        point = self._stable(parse, required=False)
        if point is None:
            return False
        self.device.tap(*point)
        return True

    def _point(self, point, guard):
        self._stable(lambda img,texts: bool(guard(img,texts)) or None)
        self.device.tap(*point)

    def _close(self, find_close=close_button):
        point = self._stable(lambda img,texts: find_close(img), required=False)
        if point:
            self.device.tap(*point)
            return True
        return False

    def _lobby(self):
        deadline = time.monotonic() + config.GAME_LOAD_TIMEOUT
        for _ in range(MAX_LOBBY_ATTEMPTS):
            while True:
                try:
                    step = self._stable(_lobby_step, required=False)
                except ViewportUnavailable:
                    if not self.startup:
                        raise
                    step = None
                if step is not None:
                    break
                if not (self.startup or is_loading(self.last_texts)):
                    raise AccountScanError("scan_start_lobby")
                if time.monotonic() >= deadline:
                    raise EmulatorError("err_game_load", seconds=config.GAME_LOAD_TIMEOUT)
                self.device.wait(config.EMULATOR_POLL)
            if isinstance(step, Lobby):
                self.startup = False
                return step
            self.device.tap(*step)
        raise AccountScanError("scan_start_lobby")

    def _equipment(self):
        self._lobby()
        self._point(config.EQUIP_TAB, _ready_lobby)
        self._stable(lambda i,t: S.equipment_page(t) or None)

    def _read_lobby(self):
        lobby = self._lobby()
        account = self._stable(lambda i,t: _ready_lobby(i,t) and next((x.text for x in t if 100 < x.center[0] < 600
                                               and 40 < x.center[1] < 110 and re.search(r"[a-z]", x.norm)), None))
        if self.snapshot.account and account != self.snapshot.account:
            raise AccountScanError("scan_account_changed")
        self.snapshot.account = account
        latest = parse_level_number(lobby.level_title or "")
        if latest:
            self.snapshot.facts["elite_chapter" if lobby.mode is Mode.ELITE else "chapter"] = max(0, latest-1)
        resources = {}
        for name, bounds in (("gems", (1000,1200)), ("coins", (1230,1440))):
            values = [parse_power(t.norm) for t in self.last_texts if bounds[0] < t.center[0] < bounds[1]
                      and 40 < t.center[1] < 130 and parse_power(t.norm) is not None]
            if len(values) == 1:
                resources[name] = values[0]
        self.snapshot.facts.setdefault("resources", {}).update(resources)
        self._evidence("lobby", {"account": account, "latest": latest, "mode": lobby.mode.value, "resources":resources})
        return lobby

    def _gear(self):
        self._equipment()
        items = []
        for index, point in enumerate(config.ACCOUNT_EQUIP_SLOTS):
            previous = self.snapshot.evidence.get(f"equipment_{index}")
            if previous:
                items.append(S.EquippedItem(**previous))
                continue
            self._point(point, lambda i,t: S.equipment_page(t))
            item = self._stable(lambda i,t: S.equipped_item(t), required=False)
            if item:
                self._evidence(f"equipment_{index}", asdict(item))
                items.append(item)
                if index == 0:
                    self.snapshot.loadout.update(weapon=item.name, weapon_rarity=item.rarity)
            else:
                self.snapshot.warnings.append("scan_item_unreadable")
            if not self._close():
                raise AccountScanError("scan_unreadable")
            self._stable(lambda i,t: S.equipment_page(t) or None)
            self._checkpoint()
        if len(items) == 6:
            self.snapshot.loadout.update(weapon=items[0].name,weapon_rarity=items[0].rarity)
            self.snapshot.loadout["equipment"] = tuple(f"{item.name}:{item.rarity}" for item in items[1:])
        self.snapshot.facts["equipped_items"] = [asdict(item) for item in items]
        if self.snapshot.progress.get("stats_complete"):
            return
        self._point(config.ACCOUNT_STATS_BUTTON, lambda i,t: S.equipment_page(t))
        stats = dict(self.snapshot.loadout.get("stats",{}))
        previous = None
        for index in range(4):
            page = self._stable(lambda i,t: S.stats_values(t) or None)
            stats.update(page)
            self._evidence(f"stats_{index}", page)
            self.snapshot.loadout["stats"] = dict(stats)
            self._checkpoint()
            if page == previous or "final_def" in page:
                break
            previous = page
            self._stable(lambda i,t: bool(S.term(t,"stats")) or None)
            self.device.swipe(*config.ACCOUNT_STATS_SCROLL, duration=.8)
        self.snapshot.loadout["stats"] = stats
        self.snapshot.progress["stats_complete"] = True
        if not self._close():
            raise AccountScanError("scan_unreadable")

    def _hero(self):
        if not self._stable(lambda i,t:S.equipment_page(t) or None,required=False):
            self._equipment()
        if not self._label(S.TERMS["heroes"], guard=lambda i,t:S.equipment_page(t), lo=1150,hi=1300):
            raise AccountScanError("scan_unreadable")
        hero = self._stable(lambda i,t: S.hero_values(i,t) or None)
        self.snapshot.loadout.update({k:v for k,v in hero.items() if k != "level"})
        if "level" in hero:
            self.snapshot.facts["hero_levels"] = {hero["hero"]:hero["level"]}
        self._evidence("hero",hero)
        self._point(config.ACCOUNT_COMPANIONS[0],lambda i,t:S.hero_page(t))
        companions = self._stable(lambda i,t:S.companions_values(t),required=False)
        if companions:
            self.snapshot.loadout["companions"] = companions
            self._evidence("companions",companions)
        else:
            self.snapshot.warnings.append("scan_companions_unknown")
        self._close()

    def _deployment(self, kind):
        self._equipment()
        if not self._label(S.TERMS[kind],guard=lambda i,t:S.equipment_page(t),lo=1050,hi=1200):
            self.snapshot.warnings.append("scan_deployment_unknown")
            return
        name = self._stable(lambda i,t:S.deployed_power(t,kind),required=False)
        if name:
            self.snapshot.loadout[kind] = (name,)
            self._evidence(kind,name)
        else:
            self.snapshot.warnings.append("scan_deployment_unknown")

    def _pets(self):
        self._lobby()
        self._point(config.PETS_TAB, _ready_lobby)
        points = self._stable(lambda i,t:S.equipped_pet_points(i,t) or None,required=False)
        if not points:
            self.snapshot.warnings.append("scan_pets_unknown")
            return
        names = []
        for index,point in enumerate(points):
            previous = self.snapshot.evidence.get(f"pet_{index}")
            if previous:
                names.append(previous)
                continue
            self._point(point,lambda i,t:point in S.equipped_pet_points(i,t))
            name = self._stable(lambda i,t:S.equipped_pet(t),required=False)
            if name:
                names.append(name)
                self._evidence(f"pet_{index}",name)
            arrow = self._stable(lambda i,t:back_arrow(i),required=False)
            if arrow is None:
                raise AccountScanError("scan_unreadable")
            self.device.tap(*arrow)
            self._stable(lambda i,t:S.pets_page(t) or None)
            self._checkpoint()
        if len(names) == len(points):
            self.snapshot.loadout["pets"] = tuple(names)

    def _pet_collection(self):
        self._lobby()
        self._point(config.PETS_TAB, _ready_lobby)
        food = self._stable(lambda i,t:S.pet_collection_food(t), required=False)
        visible = self._stable(lambda i,t:S.pet_collection_cells(t) or None, required=False) or ()
        pets, balances, complete = {}, set(), False
        if food is not None:
            balances.add(food)
        if visible:
            entry = visible[0]
            self._point(entry, lambda i,t:S.pet_collection_start(t) == entry)
            previous = first = None

            def read_pet(img, texts):
                detail = S.pet_detail(texts)
                if detail is None or key(detail[0].name) == previous:
                    return None
                if detail[0].level is None:
                    detail = S.pet_detail(texts, self.ocr.read(img, S.PET_LEVEL_REGION))
                return detail

            for _ in range(64):
                detail = self._stable(read_pet, required=False)
                if detail is None:
                    break
                pet, observed_food = detail
                name = key(pet.name)
                if name in pets:
                    complete = name == first and len(pets) >= len(visible)
                    break
                pets[name] = asdict(pet)
                if observed_food is not None:
                    balances.add(observed_food)
                first, previous = first or name, name

                def arrow(img, texts):
                    current = S.pet_detail(texts)
                    if current and key(current[0].name) == previous:
                        return S.next_pet_arrow(img)

                point = self._stable(arrow, required=False)
                if point is None:
                    break
                self.device.tap(*point)

            back = self._stable(lambda i,t:back_arrow(i), required=False)
            if back:
                self.device.tap(*back)
                self._stable(lambda i,t:S.pets_page(t) or None)
        food = next(iter(balances)) if len(balances) == 1 else None
        self.snapshot.facts["pet_collection"] = {
            "pets": list(pets.values()), "food": food, "complete": complete, "at": self.snapshot.at,
        }
        if food is not None:
            self.snapshot.facts.setdefault("resources", {})["pet_food"] = food
        if complete:
            self.snapshot.loadout["pets"] = tuple(pet["name"] for pet in pets.values() if pet["equipped"])

    def _settings(self):
        self._lobby()
        self._point(config.MENU_BUTTON, _ready_lobby)
        if self._label(S.TERMS["settings"],guard=lambda i,t:_menu(t),hi=400,xhi=650):
            version = self._stable(lambda i,t:S.game_version(t),required=False)
            if version:
                self.snapshot.loadout["game_version"] = version
                self._evidence("game_version",version)
            self._close()

    def _bag(self):
        self._lobby()
        self._point(config.MENU_BUTTON, _ready_lobby)
        if not self._label(S.TERMS["bag"],guard=lambda i,t:_menu(t),lo=450,hi=800,xhi=650):
            return
        cells = self._stable(lambda i,t:S.bag_cells(t) or None,required=False)
        done = self.snapshot.progress.setdefault("resources_done",[])
        for index,point in enumerate((cells or ())[:30]):
            if index in done:
                continue
            self._point(point,lambda i,t:any(abs(x-point[0])<15 and abs(y-point[1])<15 for x,y in S.bag_cells(t)))
            item = self._stable(lambda i,t:S.bag_item(t),required=False)
            if item:
                name,amount,currency = item
                self.snapshot.inventory[name] = amount
                if currency:
                    self.snapshot.facts.setdefault("resources",{})[currency] = amount
                self._evidence(f"material_{index}",{"name":name,"amount":amount})
            else:
                self.snapshot.warnings.append("scan_resources_partial")
            done.append(index)
            self._checkpoint()
        self.snapshot.facts["bag_items"] = sorted(self.snapshot.inventory.items())
        self._close()

    def _tree_nodes(self, img, texts, expected=None):
        if not _tree_view(img, texts):
            return () if expected is None else None
        points = list(S.researched_nodes(texts))
        if expected is not None and (match := next((p for p in points if _near_node(p, expected)), None)):
            return match
        # The dense tree sometimes loses white rank labels in full-screen OCR.
        footer = [t for t in texts if t.center[1] >= 2360]
        for top, bottom in ((0, 1400), (1000, 2130), (1100, 2360)):
            if expected is not None and not top < expected[1] < bottom:
                continue
            crop = self.ocr.read(img, (0, top, 1440, bottom))
            for point in S.researched_nodes(crop + footer):
                if expected is not None and _near_node(point, expected):
                    return point
                if not any(_near_node(point, p) for p in points):
                    points.append(point)
        return sorted(points, key=lambda p: (p[1], p[0])) if expected is None else None

    def _tree_target(self, img, texts, point, observed_image):
        x, y = point
        patch = (slice(y - 80, min(2360, y + 15)), slice(max(0, x - 42), min(1440, x + 42)))
        if _tree_view(img, texts) and cv2.absdiff(img[patch], observed_image[patch]).mean() < 10:
            return point
        return self._tree_nodes(img, texts, point)

    def _tree(self):
        if "scan_tree_partial" not in self.snapshot.warnings:
            self.snapshot.warnings.append("scan_tree_partial")
        self._equipment()
        if not self._label(S.TERMS["tree"], guard=lambda i,t:S.equipment_page(t), lo=1050, hi=1200):
            return
        if not self._stable(_tree_view, required=False):
            self._close(_tree_close)  # a finished research may show an announcement
        skills = set(self.snapshot.loadout.get("tree_skills", ()))
        self.snapshot.loadout["tree_skills_partial"] = True
        self.snapshot.progress["tree_scan_version"] = 2
        visited = self.snapshot.progress.setdefault("tree_nodes_v2", [])

        def read_view():
            self._stable(_tree_view)
            return self.last_image, self.last_texts

        for (row, column), observed_image, observed_texts in [((0, 0), *read_view())]:
            self.snapshot.progress["tree_position"] = [row, column]
            # Checkpoint coordinates belong to this actual view, never to the old
            # four-page route or a different zoom/pan position on resume.
            thumbnail = cv2.resize(observed_image[100:2330], (72, 112))
            view_id = hashlib.sha256(thumbnail.tobytes()).hexdigest()[:16]
            points = self._tree_nodes(observed_image, observed_texts)
            log.info("Tree row %d, column %d: %d learned skill nodes (attribute squares skipped)", row, column, len(points))
            for index, point in enumerate(points):
                signature = f"{view_id}:{round(point[0]/20)}:{round(point[1]/20)}"
                if signature in visited:
                    continue
                target = self._stable(lambda i,t: self._tree_target(i,t,point,observed_image), required=False)
                if target is None:
                    continue
                self.device.tap(*S.tree_node_tap(observed_texts, target))
                close = self._stable(lambda i,t: _tree_close(i), required=False)
                if close is None:
                    if self._stable(_tree_view, required=False):
                        continue
                    return
                rank = S.tree_rank(self.last_texts) or S.tree_rank(
                    self.ocr.read(self.last_image, (510, 400, 930, 1050)))
                found = S.unlocked_skills(self.last_texts, rank)
                if found:
                    skills.update(found)
                    self._evidence(f"tree_{row}_{column}_{index}", found)
                    self.snapshot.loadout["tree_skills"] = tuple(sorted(skills))
                    self.snapshot.loadout["tree_skills_partial"] = True
                self.device.tap(*close)
                visited.append(signature)
                self._checkpoint()
        self.snapshot.progress["tree_coverage"] = "visible_view"
        self._checkpoint()

    def scan(self, *, pets_only=False):
        before = labels.active_language()
        labels.set_language(None)
        try:
            self._phase("prepare")
            self.original_mode = self._read_lobby().mode
            if pets_only:
                self._phase("pet_collection")
                self._pet_collection()
                self._phase("lobby")
                self._read_lobby()
                self.snapshot.status = "complete"
                return self.snapshot
            current = self.snapshot
            cached = cached_snapshot(current.account,fresh=self.fresh) if self.resume else None
            if cached:
                self.snapshot = cached
                self.snapshot.facts.update({k:v for k,v in current.facts.items() if k != "resources"})
                self.snapshot.facts.setdefault("resources",{}).update(current.facts.get("resources",{}))
                if ("tree" in cached.completed and cached.progress.get("tree_scan_version") != 2):
                    cached.completed.remove("tree")
                    cached.status = "in_progress"
                if cached.status == "complete":
                    return cached
            for name,step in (("equipment",self._gear),("heroes",self._hero),("mounts",lambda:self._deployment("mounts")),
                              ("sentinels",lambda:self._deployment("sentinels")),("pets",self._pets),
                              ("resources",self._bag),("version",self._settings),("tree",self._tree)):
                if name in self.snapshot.completed:
                    continue
                self._phase(name)
                step()
                self.snapshot.completed.append(name)
                self._checkpoint()
            self._phase("lobby")
            lobby = self._read_lobby()  # account identity must still match before applying anything
            if lobby.has_elite:
                def in_mode(img, texts, mode):
                    current = _ready_lobby(img, texts)
                    return current if current and current.mode is mode else None

                other_mode = Mode.ELITE if lobby.mode is Mode.NORMAL else Mode.NORMAL
                self._point(config.ELITE_TOGGLE, lambda i,t: in_mode(i,t,lobby.mode))
                self._stable(lambda i,t: in_mode(i,t,other_mode))
                self._read_lobby()
                self._point(config.ELITE_TOGGLE, lambda i,t: in_mode(i,t,other_mode))
                self._stable(lambda i,t: in_mode(i,t,self.original_mode))
            suggest_strategy(self.snapshot)
            self.snapshot.status = "complete"
            if self.resume:
                checkpoint(self.snapshot)
            return self.snapshot
        finally:
            labels.set_language(before)


def scan_account(request, stop=None, progress=None, *, fresh=False, launch=False, pets_only=False):
    provider = create_provider(request,stop)
    if launch:
        serial,adb,launched = provider.start()
    else:
        serial,adb,launched = provider.connect(),provider.adb,False
    device = Device(serial,stop=stop,adb=adb)
    if not launch and device.foreground_package() != config.PACKAGE:
        if not device.installed():
            raise EmulatorError("err_game_missing")
        device.launch(config.PACKAGE)
        if not wait_for(lambda: device.foreground_package() == config.PACKAGE, config.GAME_OPEN_TIMEOUT, stop):
            raise EmulatorError("err_game_open")
        launched = True
    reader = AccountReader(device,Ocr(),progress=progress,fresh=fresh,startup=launched)
    return reader.scan(pets_only=True) if pets_only else reader.scan()
