"""Real account screens and read-only navigation boundaries."""

from dataclasses import asdict
from pathlib import Path
import threading

import cv2
import pytest

from conftest import fixture_image
from roguebot import account_screens as S, config
from roguebot.account_scan import AccountReader, AccountScanError
from roguebot.account_state import AccountSnapshot, suggest_strategy
from roguebot.combat_context import Loadout
from roguebot.device import Stopped, ViewportUnavailable
from roguebot.vision import Text

FIXTURES=Path(__file__).parent/"fixtures"


def read(ocr,name):
    img=fixture_image(FIXTURES/(name+".png"))
    return img,ocr.read(img)


@pytest.mark.parametrize("name,item",[("account_weapon","Ember Staff"),("account_armor","Dragon Plate"),
    ("account_ring1","Blazing Band"),("account_ring2","Ring of Thorns"),
    ("account_charm1","Voodoo Doll"),("account_charm2","Angel's Grace")])
def test_only_equipped_item_details_are_imported(ocr,name,item):
    _,texts=read(ocr,name)
    result=S.equipped_item(texts)
    assert result.name==item and result.rarity=="epic" and result.level in (40,50)
    # The same item in inventory uses Equip, not Remove.
    inventory=[Text("Equip",t.x1,t.y1,t.x2,t.y2) if t.norm=="remove" else t for t in texts]
    assert S.equipped_item(inventory) is None


def test_account_stats_pair_labels_to_values_and_keep_displayed_multipliers(ocr):
    _,a=read(ocr,"account_stats")
    _,b=read(ocr,"account_stats2")
    stats={**S.stats_values(a),**S.stats_values(b)}
    assert stats["crit_rate"]==.14 and stats["combo_rate"]==.12 and stats["counter_rate"]==.1
    assert stats["dmg_multiplier"]==1.01 and stats["crit_damage"]==1.46
    assert stats["fire_damage"]==.25 and stats["final_atk"]==557600
    assert "5283" not in stats  # the top gem count never becomes a stat


def test_equipment_context_is_different_from_hero_and_modals(ocr):
    for name,wanted in (("account_equipment",True),("account_heroes",False),("account_weapon",False)):
        _,texts=read(ocr,name)
        assert S.equipment_page(texts) is wanted


def test_hero_level_stars_and_equipped_companion_are_read_from_real_data(ocr):
    img,texts=read(ocr,"account_heroes")
    assert S.hero_values(img,texts)=={"hero":"Lancelot","level":42,"hero_stars":2}
    _,texts=read(ocr,"account_companion1")
    assert S.companions_values(texts)==("Rogue",)


def test_pets_require_checkmarks_and_the_unequip_confirmation(ocr):
    img,texts=read(ocr,"account_pets")
    assert S.equipped_pet_points(img,texts)==((350,1150),(595,1410),(840,1410))
    for name,wanted in (("account_pet1","Pyrehorn"),("account_pet2","Castlepod"),("account_pet3","Emberin")):
        _,texts=read(ocr,name)
        assert S.equipped_pet(texts)==wanted
        assert S.equipped_pet([t for t in texts if t.norm!="unequip"]) is None


def test_mount_and_sentinel_use_the_equipped_power_not_possession_bonus(ocr):
    _,texts=read(ocr,"account_mounts")
    assert S.deployed_power(texts,"mounts")=="Dino"
    _,texts=read(ocr,"account_sentinel_deploy")
    assert S.deployed_power(texts,"sentinels")=="Stone Sentinel"


def test_bag_pairs_owned_quantity_with_its_named_tooltip_and_not_a_cost(ocr):
    _,texts=read(ocr,"account_bag")
    assert len(S.bag_cells(texts))>=15
    _,texts=read(ocr,"account_material2")
    assert S.bag_item(texts)==("Advancement Scrolls",94,None)
    assert S.bag_item([t for t in texts if not t.norm.startswith("you own:")]) is None


def test_version_ocr_accepts_decimal_comma_but_not_a_random_fraction(ocr):
    _,texts=read(ocr,"account_settings")
    assert S.game_version(texts)=="0.631" and S.settings_page(texts)
    assert S.game_version([Text("0,631",0,0,100,30)]) is None


def test_research_preview_does_not_claim_a_locked_skill(ocr):
    _,texts=read(ocr,"account_tree_detail")
    assert S.unlocked_skills(texts)==()  # this is DEF, not a run-skill unlock
    locked=[Text("Research",600,1750,850,1780),Text("0/4",600,1000,850,1030),
            Text("Ultimate Flame Strike: new effect",400,1200,1100,1240)]
    assert S.unlocked_skills(locked)==()


def test_research_detail_imports_only_rewards_at_the_confirmed_rank(ocr):
    img, texts = read(ocr, "account_tree_fire_detail")
    rank = S.tree_rank(ocr.read(img, (510, 400, 930, 1050)))
    assert rank == (1, 4)
    assert S.unlocked_skills(texts, rank) == ("Ultimate Flame Strike",)
    assert S.unlocked_skills(texts, (4, 4)) == ("Ultimate Flame Strike", "Blazing Frenzy")
    assert S.unlocked_skills(texts, (0, 4)) == ()
    assert S.tree_close(img) == (720, 2311)


def test_partial_tree_merge_keeps_other_confirmed_unlocks():
    previous = Loadout(tree_skills=("Fire Lord",))
    observed = AccountSnapshot(loadout={"tree_skills": ["Ultimate Flame Strike"], "tree_skills_partial": True})
    updated, _ = observed.merge(previous, {})
    assert updated.tree_skills == ("Fire Lord", "Ultimate Flame Strike")
    assert updated.tree_skills_partial


def test_partial_reads_preserve_manual_fields_and_account_switch_drops_stale_facts():
    snapshot=AccountSnapshot(account="new",loadout={"weapon":"Ember Staff","stats":{"crit_rate":.14}})
    old=Loadout(weapon="Katana",pets=("Flux",),stats=(("combo_rate",.3),))
    current,facts=snapshot.merge(old,{"resources":{"iron_bars":200}},previous_account="new")
    assert current.pets==("Flux",) and current.stat("combo_rate")==.3
    current,facts=snapshot.merge(old,{"resources":{"iron_bars":200}},previous_account="old")
    assert current.pets==() and current.stat("combo_rate") is None and facts=={}


def test_strategy_is_based_on_identified_equipment_and_never_fabricates_matches():
    snapshot=AccountSnapshot(loadout={"weapon":"Ember Staff"})
    suggest_strategy(snapshot)
    assert (snapshot.profile,snapshot.strategy)==("burn","skill")
    assert "results" not in asdict(snapshot)


def test_unknown_screen_gets_no_input_and_is_not_restarted(ocr):
    img=fixture_image(FIXTURES/"en_party_combat.png")
    class Device:
        taps=[]
        def foreground_package(self): return config.PACKAGE
        def peek(self): return img
        def wait(self,seconds): pass
        def tap(self,*point): self.taps.append(point)
    device=Device()
    with pytest.raises(AccountScanError,match="scan_start_lobby|scan_in_adventure"):
        AccountReader(device,ocr,capture_dir=None).scan()
    assert device.taps==[]


class LobbyReplay:
    def __init__(self, steps, final):
        self.steps = list(steps)
        self.final = final
        self.taps = []

    def foreground_package(self):
        return config.PACKAGE

    def peek(self):
        return self.steps[0][0] if self.steps else self.final

    def wait(self, seconds):
        pass

    def tap(self, *point):
        _, expected = self.steps.pop(0)
        assert point == expected
        self.taps.append(point)


def test_scan_dismisses_chained_offers_and_login_notice_before_opening_equipment(ocr):
    offer, _ = read(ocr, "en_party_lobby_limited_offer")
    promo, _ = read(ocr, "lobby_promo_popup")
    autumn, _ = read(ocr, "lobby_autumn_event_popup")
    login, _ = read(ocr, "pt_daily_login")
    lobby, _ = read(ocr, "account_current")
    gear, _ = read(ocr, "account_equipment")
    steps = [(offer, config.POPUP_OUTSIDE_TAP), (promo, (719, 2455)),
             (autumn, (720, 2453)), (login, (720, 2072)), (lobby, config.EQUIP_TAB)]
    device = LobbyReplay(steps, gear)
    AccountReader(device, ocr, capture_dir=None)._equipment()
    assert device.taps == [point for _, point in steps]


def test_scan_from_another_tab_returns_to_adventure(ocr):
    pets, _ = read(ocr, "account_pets")
    lobby, _ = read(ocr, "pt_lobby")
    device = LobbyReplay([(pets, config.AVENTURA_TAB)], lobby)
    assert AccountReader(device, ocr, capture_dir=None)._lobby()
    assert device.taps == [config.AVENTURA_TAB]


def test_resume_from_tree_closes_detail_then_uses_back_arrow(ocr):
    tree, _ = read(ocr, "account_tree_recovery")
    detail, _ = read(ocr, "account_tree_fire_detail")
    lobby, _ = read(ocr, "account_current")
    device = LobbyReplay([(detail, (720, 2310)), (tree, (120, 2447))], lobby)
    assert AccountReader(device, ocr, capture_dir=None)._lobby()
    assert len(device.taps) == 2


def test_tree_skips_a_node_that_does_not_open_and_keeps_the_unlock(ocr, monkeypatch):
    tree, _ = read(ocr, "account_tree_recovery")
    detail, _ = read(ocr, "account_tree_fire_detail")

    class TreeReplay(LobbyReplay):
        def swipe(self, start, end, duration):
            assert 0 < start[0] < 1440 and 0 < end[0] < 1440
            assert 100 < start[1] < 2330 and 100 < end[1] < 2330

        def tap(self, *point):
            if len(self.steps) == 3:
                assert 620 < point[0] < 820 and 1200 < point[1] < 1390
            elif len(self.steps) == 1:
                assert point[0] < 160 and 1800 < point[1] < 2050
            else:
                assert point == (720, 2311)
            self.steps.pop(0)
            self.taps.append(point)

    steps = [(tree, None), (detail, None), (tree, None)]
    device = TreeReplay(steps, tree)
    reader = AccountReader(device, ocr, capture_dir=None, resume=False)
    monkeypatch.setattr(reader, "_equipment", lambda: None)
    monkeypatch.setattr(reader, "_label", lambda *args, **kwargs: True)
    reader.snapshot.progress["tree_nodes"] = ["0:4:100", "0:20:116", "0:4:116"]
    reader._tree()
    assert len(device.taps) == 3 and not device.steps
    # The old failed click at (402, 1611) was a 1/10 DEF attribute square.
    assert not any(300 < x < 500 and 1500 < y < 1750 for x, y in device.taps)
    assert reader.snapshot.loadout["tree_skills"] == ("Ultimate Flame Strike",)
    assert reader.snapshot.warnings == ["scan_tree_partial"]


def test_scan_leaves_a_pending_adventure_untouched(ocr):
    prompt, _ = read(ocr, "en_lobby_resume_adventure")
    device = LobbyReplay([], prompt)
    with pytest.raises(AccountScanError, match="scan_in_adventure"):
        AccountReader(device, ocr, capture_dir=None).scan()
    assert device.taps == []


def test_offer_without_close_hint_never_taps_text_in_the_footer(ocr):
    offer, _ = read(ocr, "en_party_lobby_limited_offer")
    class BlockedOfferOcr:
        def read(self, image):
            return ocr.read(image) + [Text("$19.99", 660, 2410, 780, 2480)]

    device = LobbyReplay([], offer)
    with pytest.raises(AccountScanError, match="scan_start_lobby"):
        AccountReader(device, BlockedOfferOcr(), capture_dir=None).scan()
    assert device.taps == []


def test_manual_scan_opens_background_game_and_waits_through_loading(ocr, monkeypatch):
    from types import SimpleNamespace
    from roguebot import account_scan

    lobby, _ = read(ocr, "account_current")
    cached = AccountSnapshot(account="VitaoPistola", status="complete")
    monkeypatch.setattr(account_scan, "cached_snapshot", lambda account, **kw: cached)

    class StartingDevice(LobbyReplay):
        package = "com.android.launcher"
        loading = True

        def foreground_package(self):
            return self.package

        def installed(self):
            return True

        def launch(self, package):
            self.package = package

        def peek(self):
            if self.loading:
                self.loading = False
                raise ViewportUnavailable("black loading frame")
            return super().peek()

    device = StartingDevice([], lobby)
    monkeypatch.setattr(account_scan, "create_provider", lambda *args: SimpleNamespace(adb="adb", connect=lambda: "serial"))
    monkeypatch.setattr(account_scan, "Device", lambda *args, **kwargs: device)
    monkeypatch.setattr(account_scan, "Ocr", lambda: ocr)
    assert account_scan.scan_account(None) is cached
    assert device.package == config.PACKAGE and not device.taps


def test_stop_propagates_before_any_navigation(ocr):
    class Device:
        def foreground_package(self): raise Stopped("stop")
        def tap(self,*point): raise AssertionError("input after stop")
    with pytest.raises(Stopped):
        AccountReader(Device(),ocr,capture_dir=None).scan()


def test_transient_viewport_loss_during_menu_transition_is_retried(ocr):
    lobby, _ = read(ocr, "account_current")

    class TransitionReplay(LobbyReplay):
        loading = True

        def peek(self):
            if self.loading:
                self.loading = False
                raise ViewportUnavailable("black transition frame")
            return super().peek()

    device = TransitionReplay([], lobby)
    assert AccountReader(device, ocr, capture_dir=None)._lobby()
    assert device.taps == []


def test_recent_completed_scan_checks_only_lobby_without_revisiting_menus(ocr,monkeypatch):
    from roguebot import account_scan
    image,_=read(ocr,"account_current")
    cached=AccountSnapshot(account="VitaoPistola",loadout={"weapon":"Ember Staff"},status="complete")
    monkeypatch.setattr(account_scan,"cached_snapshot",lambda account,**kwargs:cached if account==cached.account else None)
    class Device:
        def foreground_package(self): return config.PACKAGE
        def peek(self): return image
        def wait(self,seconds): pass
        def tap(self,*point): raise AssertionError("repeat navigation for a fresh cache")
    result=AccountReader(Device(),ocr,capture_dir=None).scan()
    assert result is cached


@pytest.mark.parametrize("version,rescan", [(None, True), (2, False)])
def test_old_vertical_tree_cache_is_rescanned_without_repeating_other_sections(monkeypatch, version, rescan):
    from roguebot import account_scan
    from roguebot.screens import Lobby, Mode
    sections = ["equipment", "heroes", "mounts", "sentinels", "pets", "resources", "version", "tree"]
    cached = AccountSnapshot(account="A", completed=list(sections), status="complete",
                             loadout={"tree_skills": ["Fire Lord"]})
    if version is not None:
        cached.progress["tree_scan_version"] = version
    monkeypatch.setattr(account_scan, "cached_snapshot", lambda *a, **k: cached)
    reader = AccountReader(None, None, capture_dir=None, resume=False)
    reader.resume = True
    def lobby():
        reader.snapshot.account = "A"
        return Lobby(Mode.NORMAL, "47. Sands", Text("Start", 500, 2000, 900, 2100), None, 10, False)
    reader._read_lobby = lobby
    calls = []
    def tree():
        calls.append("tree")
        reader.snapshot.progress["tree_scan_version"] = 2
    reader._tree = tree
    result = reader.scan()
    assert calls == (["tree"] if rescan else [])
    assert result.completed == sections and result.loadout["tree_skills"] == ["Fire Lord"]


def test_interrupted_scan_resumes_only_unfinished_sections(monkeypatch):
    from roguebot import account_scan
    from roguebot.screens import Lobby,Mode
    cached=AccountSnapshot(account="A",completed=["equipment","heroes"],status="in_progress")
    monkeypatch.setattr(account_scan,"cached_snapshot",lambda *args,**kwargs:cached)
    checkpoints=[]
    monkeypatch.setattr(account_scan,"checkpoint",lambda snapshot:checkpoints.append(list(snapshot.completed)))
    reader=AccountReader(None,None,capture_dir=None)
    def lobby():
        reader.snapshot.account="A"
        return Lobby(Mode.NORMAL,"4. Woods",Text("Start",500,2000,900,2100),None,10,False)
    reader._read_lobby=lobby
    calls=[]
    reader._gear=lambda:calls.append("gear")
    reader._hero=lambda:calls.append("hero")
    reader._deployment=lambda kind:calls.append(kind)
    for method in ("_pets","_bag","_settings","_tree"):
        setattr(reader,method,lambda name=method:calls.append(name))
    reader.scan()
    assert "gear" not in calls and "hero" not in calls
    assert calls==["mounts","sentinels","_pets","_bag","_settings","_tree"]
    assert checkpoints[-1]==["equipment","heroes","mounts","sentinels","pets","resources","version","tree"]


def test_scan_cache_expires_and_does_not_cross_accounts(tmp_path,monkeypatch):
    from datetime import datetime,timedelta,timezone
    from roguebot import account_state
    from roguebot.persistence import write_json
    monkeypatch.setattr(account_state,"CHECKPOINT_PATH",tmp_path/"checkpoint.json")
    monkeypatch.setattr(account_state,"SCAN_PATH",tmp_path/"scan.json")
    now=datetime.now(timezone.utc)
    snap=AccountSnapshot(account="A",at=now.isoformat(),status="complete")
    write_json(account_state.SCAN_PATH,asdict(snap))
    assert account_state.cached_snapshot("A",now=now)
    assert account_state.cached_snapshot("B",now=now) is None
    assert account_state.cached_snapshot("A",now=now+timedelta(minutes=11)) is None
    assert account_state.cached_snapshot("A",fresh=True,now=now) is None


def test_tree_only_checkpoint_can_resume_after_normal_cache_expiry(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from roguebot import account_state
    from roguebot.persistence import write_json

    monkeypatch.setattr(account_state, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    now = datetime.now(timezone.utc)
    snapshot = AccountSnapshot(account="A", at=now.isoformat(),
                               completed=["equipment", "heroes", "mounts", "sentinels", "pets", "resources", "version"])
    write_json(account_state.CHECKPOINT_PATH, asdict(snapshot))
    assert account_state.cached_snapshot("A", fresh=True, now=now + timedelta(minutes=15))
    assert account_state.cached_snapshot("A", fresh=True, now=now + timedelta(days=2)) is None
    assert account_state.cached_snapshot("B", fresh=True, now=now + timedelta(minutes=15)) is None


def test_newer_complete_scan_wins_over_an_older_checkpoint(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from roguebot import account_state
    from roguebot.persistence import write_json

    monkeypatch.setattr(account_state, "CHECKPOINT_PATH", tmp_path / "checkpoint.json")
    monkeypatch.setattr(account_state, "SCAN_PATH", tmp_path / "scan.json")
    now = datetime.now(timezone.utc)
    old = AccountSnapshot(account="A", at=(now - timedelta(minutes=3)).isoformat())
    complete = AccountSnapshot(account="A", at=now.isoformat(), status="complete")
    write_json(account_state.CHECKPOINT_PATH, asdict(old))
    write_json(account_state.SCAN_PATH, asdict(complete))
    assert account_state.cached_snapshot("A", now=now) == complete
    assert account_state.cached_snapshot("A", fresh=True, now=now) == old


def test_equipment_resume_does_not_reopen_already_confirmed_slots():
    reader=AccountReader(None,None,capture_dir=None,resume=False)
    reader.snapshot.progress["stats_complete"]=True
    for index in range(5):
        reader.snapshot.evidence[f"equipment_{index}"]={"name":"Ember Staff" if index==0 else f"Item {index}",
                                                       "rarity":"epic","level":50}
    reader._equipment=lambda:None
    taps=[]
    reader._point=lambda point,guard:taps.append(point)
    values=iter((S.EquippedItem("Angel's Grace","epic",50),True))
    reader._stable=lambda *args,**kwargs:next(values)
    reader._close=lambda:True
    reader._gear()
    assert taps==[config.ACCOUNT_EQUIP_SLOTS[5]]
    assert len(reader.snapshot.loadout["equipment"])==5


def test_material_resume_skips_already_read_tooltips():
    reader=AccountReader(None,None,capture_dir=None,resume=False)
    reader.snapshot.progress["resources_done"]=[0]
    reader._lobby=lambda:None
    reader._label=lambda *args,**kwargs:True
    taps=[]
    reader._point=lambda point,guard:taps.append(point)
    cells=((300,700),(500,700))
    values=iter((cells,("Iron Bars",200,"iron_bars")))
    reader._stable=lambda *args,**kwargs:next(values)
    reader._close=lambda:True
    reader._bag()
    assert taps==[config.MENU_BUTTON,cells[1]]
    assert reader.snapshot.facts["resources"]["iron_bars"]==200
    assert reader.snapshot.progress["resources_done"]==[0,1]
