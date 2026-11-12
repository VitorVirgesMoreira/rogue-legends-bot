"""Boundaries between guide advice, observations and resource-spending decisions."""

from dataclasses import asdict
from pathlib import Path
import pytest

from conftest import fixture_image
from roguebot.build import Build
from roguebot.combat_context import CombatContext, Loadout
from roguebot.event_modes import ChaosPath, ConquestTarget, EventMode, choose_chaos_path, choose_conquest_target
from roguebot.farming import FarmPolicy
from roguebot.metrics import History, RunRecord, build_signature, result_values
from roguebot.party_routes import Room, best_route
from roguebot.party_screens import team_status
from roguebot.progression_plan import recommend, pet_roll_cost, pet_build_level
from roguebot.request import build_request, RunRequest
from roguebot.rewards import parse_claim
from roguebot.schedule import RoutineSchedule, refresh_seconds
from roguebot.screens import Mode
from roguebot.skill_data import rule_for, card_version
from roguebot.vision import Text


def text(value, x=720, y=500):
    return Text(value, x-40, y-15, x+40, y+15)


def test_conquest_uses_current_crowns_and_never_guesses_a_power():
    targets = [ConquestTarget("decayed", 30, 1), ConquestTarget("fresh", 40, 10),
               ConquestTarget("whale", 301, 100), ConquestTarget("too strong", 101, 10)]
    assert choose_conquest_target(100, targets) == 1
    assert choose_conquest_target(None, targets) is None
    assert choose_conquest_target(1, targets) is None


def test_chaos_path_avoids_a_75_percent_penalty_to_its_damage_line():
    paths = [ChaosPath("rich", "chaotic", ("Fire Down, Poison Up",), 999),
             ChaosPath("safe", "normal", ("Evasive",), 10)]
    assert choose_chaos_path(paths, Build(profile="burn")) == 1
    assert choose_chaos_path([], Build()) is None


@pytest.mark.parametrize("mode", [Mode.CHAOS, Mode.CONQUEST])
def test_unvalidated_modes_are_inspection_only_and_ignore_campaign_controls(mode):
    request = build_request(mode.value, "stars", "25", full=True, loop=True)
    assert request.mode is mode and request.level is None
    assert not request.full and not request.loop and not request.repeat


def test_closed_conquest_entry_spends_no_attempts(ocr):
    fixture = Path(__file__).parent / "fixtures" / "pt_conquest_closed.png"
    image = fixture_image(fixture)
    class Device:
        taps = []
        def screenshot(self): return image
        def tap(self, *point): self.taps.append(point)
        def wait(self, seconds): pass
    class Nav:
        def go_to_lobby(self): pass
        def detect_language(self): return "pt"
    device = Device()
    controller = EventMode(device, ocr, Nav(), "conquest")
    controller._enter = lambda values: True  # navigation already reached the captured Wars page
    report = controller.run()
    assert report.mode_reason == "mode_season_closed" and device.taps == []


def test_history_separates_specializations_before_farm_comparison(tmp_path):
    history = History(tmp_path / "runs.json")
    for strategy in ("crit", "dot"):
        build = Build(profile="fire", strategy=strategy)
        for _ in range(3):
            history.record(RunRecord("normal", "fire", "victory", 60, level=7 if strategy == "crit" else 6,
                energy=5, loadout=asdict(build.loadout), build_config=build_signature(build)))
    rows = history.summary()
    build = Build(profile="fire", strategy="dot")
    assert FarmPolicy().choose(rows, "normal", "fire", 10, loadout=asdict(build.loadout),
                               build_config=build_signature(build)) == 6
    assert len(rows) == 2


def test_retreat_is_not_undone_by_a_different_old_successful_stage():
    policy = FarmPolicy(target=8)
    policy.observe(False)
    policy.observe(False)
    row = dict(mode="normal", profile="fire", level=9, runs=10, win_rate=1., seconds_per_run=30)
    assert policy.choose([row], "normal", "fire", 10) == 7


def test_explicit_stage_cannot_be_combined_with_automatic_farm():
    with pytest.raises(ValueError):
        RunRequest(Mode.NORMAL, 9, farm=True)


def test_earned_gem_reward_is_allowed_but_premium_lane_is_not(ocr):
    img = fixture_image(Path(__file__).parent / "fixtures" / "pt_daily_login.png")
    texts = ocr.read(img)
    assert parse_claim(img, texts)
    texts.append(text("Premium", x=415, y=600))
    assert parse_claim(img, texts) is None


def test_observed_deadline_and_unavailable_mode_backoff():
    schedule = RoutineSchedule()
    delay = refresh_seconds([text("Renova em 1h 2m")])
    assert delay == 3720
    schedule.observe("dojo", 100, count=0, refresh=delay)
    assert schedule.due(3819) == () and schedule.due(3820) == ("dojo",)
    schedule.observe("arena", 100, available=False)
    assert "arena" not in schedule.due(1000)


def test_rewards_only_accept_explicit_results_and_preserve_unknowns():
    assert result_values([text("Dano Infligido: 1,2m"), text("Diários de Especialização x15"), text("500")]) == (
        1_200_000, {"specialization_journals": 15.})


@pytest.mark.parametrize("capture,gold", [
    ("level_victory", 350), ("level_defeat", 2383), ("en_level_victory_x2", 350),
    ("en_google_level_victory_x2", 22000), ("level_board_ready", None),
])
def test_gold_comes_from_the_result_card_even_on_a_loss(ocr, capture, gold):
    img = fixture_image(Path(__file__).parent / "fixtures" / (capture + ".png"))
    assert result_values(ocr.read(img), img)[1].get("gold") == gold


def test_gold_is_read_again_at_the_icon_when_the_full_screen_ocr_misses_it(ocr):
    img = fixture_image(Path(__file__).parent / "fixtures" / "en_google_level_victory_x2.png")
    texts = [t for t in ocr.read(img) if t.norm != "x22k"]
    assert result_values(texts, img, ocr=ocr)[1] == {"gold": 22_000}


def test_gold_can_appear_lower_in_the_result_panel(ocr):
    img = fixture_image(Path(__file__).parent / "fixtures" / "en_google_level_victory_x2.png")
    texts = [t for t in ocr.read(img) if t.norm != "x22k"]
    reward = img[1450:1675, 600:840].copy()
    img[1450:1675, 600:840] = 0
    img[1700:1925, 600:840] = reward
    assert result_values(texts, img, ocr=ocr)[1] == {"gold": 22_000}


def test_reward_rates_use_matching_samples_and_keep_unread_results_in_win_rate(tmp_path):
    history = History(tmp_path / "runs.json")
    history.record(RunRecord("elite", "fire", "victory", 80, level=26, energy=5))
    history.record(RunRecord("elite", "fire", "victory", 60, level=26, energy=5, rewards={"gold": 400}))
    history.record(RunRecord("elite", "fire", "defeat", 60, level=26, rewards={"gold": 200}))
    history.record(RunRecord("elite", "fire", "abandoned", 10, level=26, energy=5))
    row, = history.summary()
    assert row["win_rate"] == 2/3
    assert row["reward_samples"] == {"gold": 2}
    assert row["reward_energy_samples"] == {"gold": 1}
    assert row["rewards_per_energy"] == {"gold": 80}
    assert row["rewards_per_minute"] == {"gold": 300}


def test_farm_can_optimize_gold_by_energy_or_time_and_explain_sample(tmp_path):
    history = History(tmp_path / "runs.json")
    for stage, gold, energy, seconds in ((6, 500, 5, 120), (7, 800, 10, 60)):
        for _ in range(3):
            history.record(RunRecord("elite", "fire", "victory", seconds, level=stage,
                                     energy=energy, rewards={"gold": gold}))
    farm = FarmPolicy()
    rows = history.summary()
    assert farm.choose(rows, "elite", "fire", 10, objective="gold_per_energy") == 6
    assert farm.evidence["runs"] == 3 and farm.evidence["win_rate"] == 1.
    assert farm.choose(rows, "elite", "fire", 10, objective="gold_per_minute") == 7
    assert farm.evidence["rewards_per_minute"]["gold"] == 800


def test_farm_does_not_mix_game_versions_even_on_the_same_stage(tmp_path):
    history = History(tmp_path / "runs.json")
    for version, stage, gold in (("0.630", 6, 900), ("0.631", 7, 500)):
        for _ in range(3):
            history.record(RunRecord("normal", "fire", "victory", 60, level=stage, energy=5,
                                     rewards={"gold": gold}, loadout=asdict(Loadout(game_version=version))))
    assert FarmPolicy().choose(history.summary(), "normal", "fire", 10, objective="gold_per_energy",
                               loadout=asdict(Loadout(game_version="0.631"))) == 7


def test_farm_loss_streak_belongs_to_the_selected_stage():
    farm = FarmPolicy()
    assert farm.choose([], "normal", "fire", 10) == 9
    farm.observe(False)
    row = {"mode": "normal", "profile": "fire", "level": 6, "runs": 3, "win_rate": 1.0}
    assert farm.choose([row], "normal", "fire", 10) == 6
    assert not farm.observe(False)
    assert farm.target == 6
    assert not farm.observe(False)
    assert farm.target == 5


def test_history_ignores_malformed_rewards_and_group_fields(tmp_path):
    from roguebot.persistence import write_json

    history = History(tmp_path / "runs.json")
    first = asdict(RunRecord("normal", "fire", "victory", 60, energy=5, rewards={"gold": 300}))
    damaged = asdict(RunRecord("normal", "fire", "defeat", 60, energy=5))
    damaged["rewards"] = None
    invalid = {**damaged, "id": "invalid", "profile": ["fire"]}
    write_json(history.path, [first, damaged, invalid])
    row, = history.summary()
    assert row["runs"] == 2
    assert row["rewards_per_energy"] == {"gold": 60}


def test_progression_advice_has_real_costs_and_no_assumed_balances():
    build = Build(profile="fire", loadout=Loadout(weapon="Ember Staff", weapon_rarity="legendary"))
    awakening = next(r for r in recommend(build, chapter=40) if r.category == "awakening")
    assert awakening.target == "Inferno Spire" and awakening.affordable is None
    assert dict(awakening.costs) == dict(awakening_crystals=60, iron_bars=200, chromatic_prisms=1)
    assert pet_roll_cost(3) == dict(spirit_bones=100, memory_stones=3)
    assert pet_build_level(350) == (6, 5)


def test_low_hp_route_uses_only_reachable_campfires_and_explicit_hp():
    rooms = [Room("battle", (0, 0), True), Room("treasure", (0, -100)), Room("campfire", (900, -100))]
    context = CombatContext(team_hp=(.2,))
    assert best_route(rooms, {0: [1]}, context) == 0
    hp, roles, heroes = team_status([text("PV: 20/100"), text("1/3"), text("Apoio"), text("Illumina")])
    assert hp == (.2,) and roles == ("support",) and heroes == ("illumina",)


def test_portuguese_level_suffix_and_all_tree_metadata_are_distinct():
    assert rule_for("Arma de Fogo Nível 2+").id == "fireweapon"
    assert card_version("Arma de Fogo Nv. 2+") == 21
    assert rule_for("Wizard").level2_tree and not rule_for("Wizard").tree_unlock
    assert rule_for("Enraged Durability").tree_unlock
    assert rule_for("Last Stand").versions == (10, 21)
    with pytest.raises(ValueError):
        Loadout(weapon_rarity="Lendário")
