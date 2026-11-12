from dataclasses import replace

import pytest

from roguebot import account_screens as screens, config
from roguebot.account_scan import AccountReader
from roguebot.mode_screens import back_arrow
from roguebot.pet_upgrades import Pet, optimize, supported
from test_account_scan import LobbyReplay, read


def test_plan_uses_only_new_food_and_spare_copies():
    sly = Pet("Sly", "common", 1, 20, False)
    assert not optimize([sly], 99)
    assert not optimize([replace(sly, copies=19)], 100)
    step, = optimize([sly], 100)
    assert (step.target, step.food, step.copies, step.atk) == (5, 100, 20, 3)

    castle = Pet("Castlepod", "legendary", 5, 10, True, 375, 2)
    assert not optimize([replace(castle, copies=5)], 1680)
    step, = optimize([castle], 2625)
    assert (step.start, step.target, step.food, step.copies, step.skills) == (5, 10, 2625, 10, 1)
    assert not optimize([replace(castle, equipped=False)], 2625)


def test_plan_combines_pets_and_excludes_a_mismatching_observed_cost():
    pets = [Pet("Sly", "common", 1, 20, False), Pet("Zorg", "common", 1, 20, False),
            Pet("Castlepod", "legendary", 4, 2, True)]
    assert [p.name for p in optimize(pets, 300)] == ["Sly", "Zorg"]
    assert not supported(replace(pets[0], food_cost=20))
    assert not supported(replace(pets[0], copies=None))


@pytest.mark.parametrize("capture,name,level,copies,cost", [
    ("account_pet1", "Pyrehorn", 8, 0, 600),
    ("account_pet2", "Castlepod", 5, 5, 375),
    ("account_pet3", "Emberin", 10, 0, 500),
])
def test_reads_real_pet_level_available_copies_and_step_cost(ocr, capture, name, level, copies, cost):
    img, texts = read(ocr, capture)
    pet, food = screens.pet_detail(texts, ocr.read(img, screens.PET_LEVEL_REGION))
    assert (pet.name, pet.level, pet.copies, pet.food_cost, food) == (name, level, copies, cost, 1680)
    assert pet.equipped and supported(pet)
    assert screens.next_pet_arrow(img)


def test_collection_selects_a_visible_owned_card_and_reads_food(ocr):
    _, texts = read(ocr, "account_pets")
    assert screens.pet_collection_start(texts) == (350, 1150)
    assert screens.pet_collection_food(texts) == 1680
    assert screens.pet_detail(texts) is None


def test_pet_only_scan_walks_the_collection_without_tapping_upgrade(ocr):
    lobby, _ = read(ocr, "account_current")
    collection, _ = read(ocr, "account_pets")
    pyrehorn, _ = read(ocr, "account_pet1")
    castle, _ = read(ocr, "account_pet2")
    emberin, _ = read(ocr, "account_pet3")
    steps = [(lobby, config.PETS_TAB), (collection, (350, 1150)),
             (pyrehorn, screens.next_pet_arrow(pyrehorn)), (castle, screens.next_pet_arrow(castle)),
             (emberin, screens.next_pet_arrow(emberin)), (pyrehorn, back_arrow(pyrehorn)),
             (collection, config.AVENTURA_TAB)]
    device = LobbyReplay(steps, lobby)
    reader = AccountReader(device, ocr, capture_dir=None, resume=False)
    result = reader.scan(pets_only=True)
    assert not result.facts["pet_collection"]["complete"]  # the collection shows more than these three
    assert result.facts["resources"]["pet_food"] == 1680
    assert [p["name"] for p in result.facts["pet_collection"]["pets"]] == ["Pyrehorn", "Castlepod", "Emberin"]
    assert not device.steps
