"""Party Expedition fixtures, role choices, treasure paths and stage-20 progression."""

from pathlib import Path

import numpy as np
import pytest

from conftest import fixture_image
from roguebot import labels
from roguebot.build import Build, BuildState
from roguebot.party import PartyExpedition, PartyError
from roguebot.party_build import ROLE_SKILLS, choose_party_skill
from roguebot.party_routes import Room, best_route, route_vote, visible_rooms, room_graph
from roguebot.party_screens import (TICKET_OCR_REGION, clear_reward, combat_speed, expedition_entry, expedition_result,
                                   home_entry, is_campfire, is_codex, is_combat, is_matching, is_route, parse_team)
from roguebot.report import Report, render
from roguebot.request import build_request
from roguebot.screens import LevelScreen, Mode, parse_skill_cards
from roguebot.skills import Catalog, Skill, infer_tags
from roguebot.vision import Text

FIXTURES = Path(__file__).parent / "fixtures"
V, D = LevelScreen.VICTORY, LevelScreen.DEFEAT


@pytest.fixture(autouse=True)
def language():
    labels.set_language("en")
    yield
    labels.set_language(None)


def load(ocr, name):
    img = fixture_image(FIXTURES / f"en_party_{name}.png")
    return img, ocr.read(img)


def test_lobby_and_castle_entries_do_not_select_the_store_or_another_party(ocr):
    _, lobby = load(ocr, "lobby")
    point = expedition_entry(lobby)
    assert point and point[0] > 1200 and 1400 < point[1] < 1550
    _, home = load(ocr, "home")
    point = home_entry(home)
    assert point and 650 < point[0] < 800 and 2000 < point[1] < 2200
    assert expedition_entry(home) is None
    assert home_entry(lobby) is None


def test_team_reads_stage_and_crops_the_event_counter_when_ocr_misses_it(ocr):
    img, texts = load(ocr, "team")
    team = parse_team(texts + ocr.read(img, TICKET_OCR_REGION))
    assert team and (team.stage, team.total, team.tickets) == (9, 20, 3)
    assert team.match.center[1] > 2400


@pytest.mark.parametrize("name,parse", [("matching", is_matching), ("formed", is_matching),
    ("combat", is_combat), ("campfire", is_campfire), ("route", is_route), ("codex_guardian", is_codex)])
def test_real_online_phases(ocr, name, parse):
    assert parse(load(ocr, name)[1])


@pytest.mark.parametrize("name", ["lobby", "lobby_limited_offer", "home", "team_stage_13", "codex_guardian"])
def test_menu_labels_never_count_as_an_online_fight(ocr, name):
    texts = load(ocr, name)[1]
    assert not is_combat(texts)
    assert not PartyExpedition._in_match(texts)


def test_reported_stage_thirteen_team_is_ready_for_a_new_match(ocr):
    img, texts = load(ocr, "team_stage_13")
    parsed = parse_team(texts + ocr.read(img, TICKET_OCR_REGION))
    assert parsed and parsed.stage == 13 and parsed.tickets is not None
    assert parsed.match.norm == "match"


def test_controller_recognizes_reported_team_through_the_real_ocr_crops(tmp_path, ocr):
    img, texts = load(ocr, "team_stage_13")
    bot = expedition(tmp_path, [(img, texts)])
    bot.ocr = ocr
    parsed = bot._open_team()
    assert parsed and parsed.stage == 13 and parsed.tickets is not None
    assert not bot.device.taps


def skill(name, description=""):
    return Skill(name, "en", "legendary", *infer_tags(name, description), description)


@pytest.mark.parametrize("role,name", [("striker", "Raging Strikes"), ("support", "Blessing"), ("guardian", "Provoke")])
def test_four_card_role_offer_keeps_the_preferred_role(ocr, role, name):
    cards = parse_skill_cards(load(ocr, "role_choice")[1])
    assert len(cards) == 4
    skills = [skill(c.name, c.description) for c in cards]
    chosen = choose_party_skill(skills, role, Build(profile="fire"), BuildState())
    assert skills[chosen].name == name


@pytest.mark.parametrize("role,name", [("striker", "ATKUp"), ("support", "ATKUp"), ("guardian", "DEF-Up")])
def test_elite_stat_upgrades_follow_the_party_role(ocr, role, name):
    cards = parse_skill_cards(load(ocr, "stat_choice")[1])
    skills = [skill(c.name, c.description) for c in cards]
    chosen = choose_party_skill(skills, role, Build(profile="fire"), BuildState())
    assert skills[chosen].name == name


def test_codex_has_all_eight_skills_for_each_role():
    assert {role: len(skills) for role, skills in ROLE_SKILLS.items()} == {"guardian": 8, "support": 8, "striker": 8}
    assert choose_party_skill([skill("Generosity"), skill("Combat Medic")], "support", Build(), BuildState()) == 1
    assert choose_party_skill([skill("Raging Strikes"), skill("Lethality")], "striker", Build(), BuildState()) == 1


def test_real_route_votes_for_an_available_chest_not_a_completed_one(ocr):
    img, texts = load(ocr, "route")
    rooms = visible_rooms(img, texts)
    graph = room_graph(img, rooms)
    vote = route_vote(img, texts)
    assert vote and 850 < vote[0] < 950 and 1300 < vote[1] < 1400
    battle = next(i for i, room in enumerate(rooms) if room.available and room.kind == "battle")
    assert {rooms[i].kind for i in graph[battle]} == {"treasure", "elite battle"}


def test_route_looks_ahead_to_a_chest_instead_of_just_choosing_a_room_type():
    rooms = [Room("battle", (350, 1800), True), Room("elite battle", (900, 1800), True),
             Room("treasure", (350, 1300)), Room("battle", (900, 1300))]
    assert best_route(rooms, {0: [2], 1: [3]}) == 0
    # A chest route wins even if it requires an elite, rather than taking a dead-end easy fight.
    assert best_route(rooms, {0: [3], 1: [2]}) == 1


def test_equivalent_chest_routes_prefer_normal_battles():
    rooms = [Room("elite battle", (350, 1800), True), Room("battle", (900, 1800), True),
             Room("treasure", (700, 1300))]
    assert best_route(rooms, {0: [2], 1: [2]}) == 1


def test_user_elite_map_prefers_the_easy_available_path_without_nearby_chests(ocr):
    img, texts = load(ocr, "route_elites")
    rooms = visible_rooms(img, texts)
    vote = route_vote(img, texts)
    assert vote and next(room.kind for room in rooms if room.point == vote) == "battle"
    assert route_vote(img, [t for t in texts if "tap to vote" not in t.norm]) is None


def test_victory_and_first_clear_rewards_are_separate_screens(ocr):
    result = expedition_result(load(ocr, "victory")[1])
    assert result and result[0] is V and result[1].norm == "continue"
    reward = load(ocr, "clear_reward")[1]
    assert clear_reward(reward) and parse_team(reward) is None
    assert expedition_result(reward) is None
    assert combat_speed(load(ocr, "combat")[1])[0] == 4


def test_reported_stage_nineteen_reward_advances_to_twenty(tmp_path, ocr):
    img, texts = load(ocr, "clear_reward_stage_19")
    claim = clear_reward(texts)
    assert claim and parse_team(texts) is None
    bot = expedition(tmp_path, [team(19), result(V), (img, texts), team(20), result(V), team(20)])
    report = bot.run()
    assert report.results == [V, V] and report.party_reason == "party_complete"
    assert claim.center in bot.device.taps
    assert bot.device.taps.count((720, 2445)) == 2


@pytest.mark.parametrize("label", ["Stage19cleared!", "Stage 19cleared!", "Stage19 cleared!", "Stage 19 cleared!"])
def test_reward_with_joined_ocr_words_still_blocks_match_until_claimed(label):
    texts = [*team(20), Text(label, 400, 450, 1040, 530)]
    assert parse_team(texts) is None
    assert clear_reward(texts) is None


def test_party_request_ignores_normal_level_energy_and_loop_options():
    request = build_request("party_expedition", "stars", "invalid", full=True, loop=True, party_role="support")
    assert request.mode is Mode.PARTY_EXPEDITION and request.level is None
    assert not request.full and not request.loop
    assert request.party_role == "support" and request.party_runs == 20


@pytest.mark.parametrize("value", [0, 21, "x", "1.5", True, None])
def test_invalid_match_limits_are_rejected(value):
    with pytest.raises(ValueError, match="bad_party_runs"):
        build_request("party_expedition", "latest", "", party_runs=value)


def team(stage, tickets=3):
    return [Text("Party Expedition", 60, 50, 600, 110), Text(f"Stage {stage}/20", 600, 190, 840, 250),
            Text("Match", 630, 2410, 810, 2480), Text(str(tickets), 1080, 55, 1130, 110)]


def result(outcome):
    return [Text("Party Expedition", 400, 950, 1000, 1050),
            Text("VICTORY!" if outcome is V else "DEFEAT!", 500, 700, 940, 850),
            Text("Continue", 600, 2280, 840, 2350)]


class ReplayDevice:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.taps = []
        self.img = np.zeros((2560, 1440, 3), dtype=np.uint8)

    def screenshot(self):
        frame = next(self.frames)
        if isinstance(frame, tuple):
            self.img, self.texts = frame
        else:
            self.texts = frame
        return self.img

    def tap(self, x, y):
        self.taps.append((x, y))

    def wait(self, seconds):
        pass


class ReplayOcr:
    def __init__(self, device):
        self.device = device

    def read(self, img, region=None):
        return list(self.device.texts)


class NoLobbyActions:
    def go_to_lobby(self):
        raise AssertionError("Known event phases must not enter ordinary lobby navigation")


def expedition(tmp_path, frames):
    device = ReplayDevice(frames)
    return PartyExpedition(device, ReplayOcr(device), NoLobbyActions(), Build(profile="fire"),
                           Catalog(tmp_path / "skills.json"))


def test_party_uses_skip_during_combat(tmp_path, ocr):
    img, texts = load(ocr, "combat")
    fight = img, [*texts, Text("Skip", 860, 2400, 980, 2450)]
    bot = expedition(tmp_path, [fight, result(V)])
    assert bot._play_match() is V
    assert bot.device.taps == [(920, 2425), (720, 2315)]


def test_progresses_from_nineteen_and_stops_after_winning_stage_twenty(tmp_path):
    bot = expedition(tmp_path, [team(19), result(V), team(20), result(V), team(20)])
    report = bot.run()
    assert report.results == [V, V] and report.party_reason == "party_complete"
    assert bot.device.taps.count((720, 2445)) == 2
    assert bot.progress.stage == 20


def test_default_goal_runs_from_ten_through_twenty_without_a_twenty_first_match(tmp_path):
    frames = [frame for stage in range(10, 21) for frame in (team(stage), result(V))] + [team(20)]
    bot = expedition(tmp_path, frames)
    report = bot.run()
    assert report.party_reason == "party_complete" and report.results == [V] * 11
    assert bot.device.taps.count((720, 2445)) == 11


def test_stale_victory_and_stale_team_do_not_duplicate_a_win_or_replay_a_stage(tmp_path):
    reward = [*team(20), Text("Stage20 cleared!", 500, 1100, 940, 1160),
              Text("Tap anywhere to claim", 400, 2290, 1040, 2350)]
    bot = expedition(tmp_path, [team(19), result(V), result(V), team(19), team(20), result(V), reward])
    report = bot.run()
    assert report.results == [V, V] and report.party_reason == "party_complete"
    assert bot.device.taps.count((720, 2445)) == 2
    assert clear_reward(reward).center in bot.device.taps


def test_stage_ten_is_not_reset_and_a_defeat_retries_the_same_stage(tmp_path):
    bot = expedition(tmp_path, [team(10), result(D), team(10, 2), result(V), team(11, 3)])
    report = bot.run(max_matches=2)
    assert report.results == [D, V] and report.party_reason == "party_limit"
    assert bot.progress.started == 2
    assert bot.device.taps.count((720, 2445)) == 2


def test_without_attempts_it_never_taps_match_or_buys_a_key(tmp_path):
    bot = expedition(tmp_path, [team(10, 0)])
    report = bot.run()
    assert report.party_reason == "party_no_tickets" and not bot.device.taps
    assert "energia" not in render(report, "pt").lower()


def test_dry_run_never_starts_a_match(tmp_path):
    bot = expedition(tmp_path, [team(10)])
    assert bot.run(dry_run=True).dry_run and not bot.device.taps


def test_resumes_an_online_match_without_pressing_match_again(tmp_path):
    combat = [Text("Expedition", 600, 170, 840, 250)]
    bot = expedition(tmp_path, [combat, result(V), team(10)])
    report = bot.run(max_matches=1)
    assert report.results == [V] and report.party_reason == "party_limit"
    assert (720, 2445) not in bot.device.taps


def test_first_clear_reward_is_claimed_before_reading_the_next_team(tmp_path, ocr):
    reward = load(ocr, "clear_reward")[1]
    bot = expedition(tmp_path, [reward, team(10)])
    assert bot.run(dry_run=True).dry_run
    assert bot.device.taps == [clear_reward(reward).center]


def test_complete_online_flow_replays_the_real_test_match_without_requeueing(tmp_path, ocr):
    frames = [team(9)] + [load(ocr, name) for name in (
        "matching", "formed", "role_choice", "combat", "route", "stat_choice", "campfire", "victory", "clear_reward")]
    bot = expedition(tmp_path, frames + [team(10)])
    report = bot.run(max_matches=1)
    assert report.results == [V] and report.party_reason == "party_limit"
    assert bot.state.taken == ["Raging Strikes", "ATKUp"]
    assert bot.device.taps.count((720, 2445)) == 1
    img, texts = load(ocr, "route")
    assert route_vote(img, texts) in bot.device.taps


def test_a_dark_transition_before_match_does_not_count_or_spend_an_extra_attempt(tmp_path):
    from roguebot.device import ViewportUnavailable
    bot = expedition(tmp_path, [team(19), team(19), result(V), team(20), result(V), team(20)])
    tap = bot.device.tap
    first = True
    def transient(x, y):
        nonlocal first
        if first:
            first = False
            raise ViewportUnavailable("Loading")
        tap(x, y)
    bot.device.tap = transient
    assert bot.run().party_reason == "party_complete"
    assert bot.progress.started == 2


@pytest.mark.parametrize("transition", [[], [t for t in team(13) if t.norm != "match"]])
def test_post_victory_transition_waits_then_starts_the_next_stage(tmp_path, transition):
    bot = expedition(tmp_path, [team(12), result(V), transition, team(13), result(V), team(14)])
    report = bot.run(max_matches=2)
    assert report.results == [V, V] and report.party_reason == "party_limit"
    assert bot.device.taps.count((720, 2445)) == 2
    assert bot.progress.stage == 13


def test_partial_initial_team_does_not_back_out_of_the_event(tmp_path):
    partial = [t for t in team(13) if t.norm != "match"]
    bot = expedition(tmp_path, [partial, team(13)])
    assert bot.run(dry_run=True).dry_run
    assert not bot.device.taps


def test_team_match_is_recovered_by_regional_ocr(tmp_path):
    from roguebot.party import TEAM_MATCH_REGION
    partial = [t for t in team(13) if t.norm != "match"]
    bot = expedition(tmp_path, [partial])
    read = bot.ocr.read
    bot.ocr.read = lambda img, region=None: [team(13)[2]] if region == TEAM_MATCH_REGION else read(img, region)
    assert bot.run(dry_run=True).dry_run
    assert not bot.device.taps


def test_reward_without_a_readable_claim_prompt_is_not_a_ready_team(tmp_path):
    partial = [*team(13), Text("Stage12 cleared!", 500, 1100, 940, 1160)]
    claim = Text("Tap anywhere to claim", 400, 2290, 1040, 2350)
    assert parse_team(partial) is None
    bot = expedition(tmp_path, [team(12), result(V), partial, [*partial, claim], team(13)])
    report = bot.run(max_matches=1)
    assert report.results == [V]
    assert bot.device.taps == [(720, 2445), result(V)[-1].center, claim.center]


def test_unknown_return_transition_times_out_without_leaving_the_event(tmp_path, monkeypatch):
    import itertools
    from roguebot import party
    clock = [100.0]
    monkeypatch.setattr(party.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(party, "NAV_TIMEOUT", 3)
    bot = expedition(tmp_path, itertools.chain([team(12), result(V)], itertools.repeat([])))
    bot.device.wait = lambda seconds: clock.__setitem__(0, clock[0]+1)
    def fail(key="party_unknown"):
        raise PartyError(key)
    bot._fail = fail
    with pytest.raises(PartyError, match="party_unknown"):
        bot.run(max_matches=2)
    assert bot.device.taps.count((720, 2445)) == 1
