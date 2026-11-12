"""Pure recognition for the account reader; equipment and ownership are distinct."""

from dataclasses import dataclass
from pathlib import Path
import re

import cv2

from roguebot import config
from roguebot.mode_screens import parse_power
from roguebot.pet_upgrades import Pet
from roguebot.screens import rarity_name
from roguebot.skill_data import key, rule_for
from roguebot.vision import match_template, normalize

TERMS = {
    "workshop": ("workshop", "oficina", "taller"),
    "heroes": ("heroes", "herois", "heróis", "héroes"),
    "equipment": ("equipment", "equipamento", "equipo"),
    "stats": ("stats details", "detalhes de atributos", "detalhes dos atributos", "detalhes de estatisticas", "detalles de estadisticas"),
    "companions": ("companions", "companheiros", "companeros"),
    "power_skill": ("choose power skill", "escolha a pericia de poder", "escolher habilidade de poder", "elige habilidad de poder"),
    "remove": ("remove", "remover", "quitar"),
    "unequip": ("unequip", "desequipar", "desequipar pet"),
    "pets": ("owned pets bonus", "bonus de pets possuidos", "bonus dos pets possuidos", "bonificacion de mascotas"),
    "pet_skill": ("pet equip skill", "pericia de pet equipado", "habilidade de pet equipado", "habilidade de equipamento do pet", "habilidad de mascota equipada"),
    "mounts": ("mounts", "montarias", "monturas"),
    "sentinels": ("sentinels", "sentinelas", "centinelas"),
    "tree": ("skill tree", "arvore de pericias", "arvore de habilidades", "arbol de habilidades"),
    "adventure": ("adventure", "aventura"),
    "specialization": ("specialization", "especializacao", "especializacion"),
    "settings": ("settings", "configuracoes", "ajustes", "configuracion"),
    "bag": ("bag", "bolsa", "mochila"),
}
TERMS = {k: tuple(normalize(s) for s in v) for k,v in TERMS.items()}


def term(texts, name, *, lo=0, hi=2560):
    return next((t for t in texts if t.norm in TERMS[name] and lo <= t.center[1] <= hi), None)


def equipment_page(texts):
    return bool(term(texts, "workshop", lo=1200, hi=1450) and term(texts, "heroes", lo=1150, hi=1300)
                and sum(bool(re.fullmatch(r"[l1][vyv]\.?\s*\d+", t.norm)) for t in texts if t.center[1] < 900) >= 3)


@dataclass(frozen=True)
class EquippedItem:
    name: str
    rarity: str
    level: int | None = None


def equipped_item(texts):
    if not term(texts, "remove", lo=1600, hi=2000):
        return None  # inventory details use Equip; owning an item is insufficient
    tag = next((t for t in texts if 350 < t.center[1] < 700 and abs(t.center[0]-720) < 120 and rarity_name(t)), None)
    if tag is None:
        return None
    names = [t for t in texts if abs(t.center[0]-720) < 160 and 200 < t.center[1] < tag.center[1]-50
             and re.search(r"[a-z]{3}", t.norm)]
    if len(names) != 1:
        return None
    level = next((int(m[1]) for t in texts if 600 < t.center[1] < 950 and
                  (m := re.fullmatch(r"(?:level|nivel|lv\.?)\s*(\d+)\s*/\s*\d+", t.norm))), None)
    return EquippedItem(names[0].text, rarity_name(tag), level)


STAT_NAMES = {
    "base_atk": ("base atk", "atk base", "atq base"), "base_hp": ("base hp", "hp base", "pv base"),
    "base_def": ("base def", "def base"), "final_atk": ("final atk", "atk final", "atq final"),
    "final_hp": ("final hp", "hp final", "pv final"), "final_def": ("final def", "def final"),
    "global_atk": ("global atk%", "atk global%", "atq global%"),
    "global_hp": ("global hp%", "hp global%", "pv global%"), "global_def": ("global def%", "def global%"),
    "crit_rate": ("crit rate", "taxa crit", "taxa crit.", "taxa critico", "tasa critica"),
    "crit_damage": ("crit damage %", "dano crit %", "dano critico %", "dano crit", "dano critico", "dano crit.", "dano crit.%"),
    "combo_rate": ("combo rate", "taxa de combo", "taxa combo", "tasa de combo"),
    "counter_rate": ("counter rate", "taxa de contra-ataque", "taxa contra-ataque", "taxa de contra ataque", "tasa de contraataque"),
    "dodge_rate": ("dodge rate", "taxa de esquiva", "taxa esquiva", "tasa de evasion"),
    "speed": ("speed", "velocidade", "velocidad"), "dr": ("damage reduction", "reducao de dano", "reduccion de dano"),
    # Displayed DMG Boost is a whole multiplier, unlike additive tag bonuses.
    "dmg_multiplier": ("dmg boost", "aumento de dmg", "aumento de dano"),
    "combo_damage": ("combo attack dmg", "dano de ataque combo", "dano de combo"),
    "counter_damage": ("counter attack dmg", "dano de contra-ataque", "dano de contra ataque"),
    "physical_damage": ("physical dmg", "dano fisico"), "magic_damage": ("magical dmg", "dano magico"),
    "fire_damage": ("fire dmg", "dano de fogo", "dano fogo"), "ice_damage": ("ice dmg", "dano de gelo", "dano gelo"),
    "lightning_damage": ("lightning dmg", "dano de raio", "dano raio"),
    "poison_damage": ("poison dmg", "dano de veneno", "dano veneno"),
    "wound_damage": ("wound dmg", "dano de ferida", "dano ferida"),
    "shuriken_damage": ("shuriken dmg", "dano de shuriken", "dano shuriken"),
    "lifesteal_rate": ("lifesteal", "roubo de vida"), "pet_damage": ("pet dmg", "dano de pet", "dano dos pets"),
}
STAT_KEYS = {key(label): name for name, labels in STAT_NAMES.items() for label in labels}


def stats_values(texts):
    if not term(texts, "stats"):
        return {}
    result = {}
    for label in texts:
        name = STAT_KEYS.get(key(label.text))
        if name is None or not 600 < label.center[1] < 1950 or not 200 < label.center[0] < 850:
            continue
        values = [t for t in texts if 1000 < t.center[0] < 1230 and abs(t.center[1]-label.center[1]) < 14
                  and re.fullmatch(r"[+]?\d+(?:[.,]\d+)?\s*[kmb%]?", t.norm)]
        if len(values) != 1:
            continue
        raw = values[0].norm.lstrip("+")
        value = float(raw[:-1].replace(",", "."))/100 if raw.endswith("%") else parse_power(raw)
        if value is not None:
            result[name] = float(value)
    return result


HEROES = ("Rogue", "Lancelot", "Dracula", "Illumina", "Kitsura", "Corvus", "Draco")


def hero_page(texts):
    return bool(term(texts, "heroes", lo=1150, hi=1300) and term(texts, "companions", lo=700, hi=1100)
                and not term(texts, "power_skill"))


def hero_values(img, texts):
    if not hero_page(texts):
        return {}
    name = next((t.text for t in texts if 150 < t.center[1] < 330 and t.center[0] < 600 and
                 key(t.text) in {key(h) for h in HEROES}), None)
    if name is None:
        return {}
    result = {"hero": name}
    level = next((int(m[1]) for t in texts if 700 < t.center[0] < 1050 and 350 < t.center[1] < 550
                  and (m := re.fullmatch(r"lv\.?\s*(\d+)", t.norm))), None)
    if level is not None:
        result["level"] = level
    rarity = next((t for t in texts if rarity_name(t) and 850 < t.center[1] < 1050 and 300 < t.center[0] < 700), None)
    if rarity:
        y = rarity.center[1]+75
        patch = img[y-30:y+30, 320:660]
        hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
        yellow = cv2.inRange(hsv, (18, 120, 170), (40, 255, 255))
        n, _, components, _ = cv2.connectedComponentsWithStats(yellow)
        stars = [s for s in components[1:] if 20 <= s[2] <= 65 and 20 <= s[3] <= 65 and s[4] > 250]
        # Full yellow stars are verified. Other star colors remain unknown.
        if 1 <= len(stars) <= 5:
            result["hero_stars"] = len(stars)
    return result


def companions_values(texts):
    if not term(texts, "power_skill"):
        return None
    result = []
    for button in texts:
        if button.norm not in TERMS["remove"] or not 800 < button.center[1] < 2100:
            continue
        body = " ".join(t.text for t in texts if 450 < t.center[0] < 950 and abs(t.center[1]-button.center[1]) < 100)
        names = [name for name in HEROES if re.search(r"\b"+re.escape(name)+r"\b", body, re.I)]
        if len(names) == 1:
            result.append(names[0])
    return tuple(dict.fromkeys(result)) if result else None


_PET_CHECK = cv2.imread(str(Path(__file__).parent / "templates" / "account" / "pet_equipped.png"), cv2.IMREAD_GRAYSCALE)


def pets_page(texts):
    return bool(term(texts, "pets") and any(t.norm in ("collection", "colecao", "coleccion") and
                2100 < t.center[1] < 2300 for t in texts))


def equipped_pet_points(img, texts):
    if not pets_page(texts):
        return ()
    mask = cv2.inRange(cv2.cvtColor(img, cv2.COLOR_BGR2HSV), (35, 100, 150), (75, 255, 255))
    points = []
    for y in config.ACCOUNT_PET_ROWS:
        for x in config.ACCOUNT_PET_COLUMNS:
            patch = mask[y-130:y-50, x+45:x+135]
            if patch.shape[0] >= _PET_CHECK.shape[0] and patch.shape[1] >= _PET_CHECK.shape[1]:
                scores = [float(cv2.matchTemplate(patch, cv2.resize(_PET_CHECK, None, fx=s, fy=s,
                          interpolation=cv2.INTER_NEAREST), cv2.TM_CCOEFF_NORMED).max()) for s in (.96, 1., 1.04)]
                if max(scores) >= .88:
                    points.append((x,y))
    return tuple(points) if 0 < len(points) <= 3 else ()


def equipped_pet(texts):
    if not term(texts, "unequip", lo=1900, hi=2250) or not term(texts, "pet_skill", lo=750, hi=1050):
        return None
    return _pet_name(texts)


def _pet_name(texts):
    names = [t.text for t in texts if 110 < t.center[1] < 200 and t.center[0] < 650 and re.search(r"[a-z]{3}", t.norm)]
    return names[0] if len(names) == 1 else None


def pet_collection_food(texts):
    if pets_page(texts):
        return _pet_number(texts, (775, 45, 930, 130))


def pet_collection_start(texts):
    return next(iter(pet_collection_cells(texts)), None)


def pet_collection_cells(texts):
    if not pets_page(texts):
        return ()
    levels = [t.center for t in texts if re.fullmatch(r"(?:lv|nv)\.?\s*\d{1,3}", t.norm)]
    return tuple((x, y) for y in config.ACCOUNT_PET_ROWS for x in config.ACCOUNT_PET_COLUMNS
                 if any(x-90 < lx < x+30 and y+15 < ly < y+100 for lx, ly in levels))


_PET_RARITY = {
    "common": ("common", "comum", "comun"),
    "great": ("great", "otimo", "excelente", "incomum", "pouco comum", "genial"),
    "rare": ("rare", "raro", "rara"),
    "epic": ("epic", "epico", "epica"),
    "legendary": ("legendary", "lendario", "legendario", "lendaria", "legendaria"),
    "mythic": ("mythic", "mitico", "mitica"),
}
PET_LEVEL_REGION = (104, 1715, 230, 1815)


def _pet_number(texts, region):
    x1, y1, x2, y2 = region
    numbers = [int(re.sub(r"[.,\s]", "", t.norm)) for t in texts
               if x1 <= t.center[0] <= x2 and y1 <= t.center[1] <= y2
               and re.fullmatch(r"\d+(?:[., ]\d{3})*", t.norm)]
    return numbers[0] if len(numbers) == 1 else None


def _pet_counter(texts, region):
    x1, y1, x2, y2 = region
    counters = [tuple(int(re.sub(r"[.,\s]", "", value)) for value in match.groups())
                for t in texts if x1 <= t.center[0] <= x2 and y1 <= t.center[1] <= y2
                and (match := re.fullmatch(r"(\d+(?:[., ]\d{3})*)\s*/\s*(\d+(?:[., ]\d{3})*)", t.norm))]
    return counters[0] if len(counters) == 1 else (None, None)


def pet_detail(texts, level_texts=()):
    if not term(texts, "pet_skill", lo=750, hi=1050):
        return None
    equipped = bool(term(texts, "unequip", lo=1900, hi=2250))
    if not equipped and not any(t.norm in ("equip", "equipar") and 1900 < t.center[1] < 2250 for t in texts):
        return None
    name = _pet_name(texts)
    if not name:
        return None
    rarity = next((rarity for rarity, labels in _PET_RARITY.items()
                   if any(t.norm in labels and t.center[0] < 450 and 190 < t.center[1] < 275 for t in texts)), "")
    if any("+" in t.text and t.norm.rstrip("+ ") in _PET_RARITY["mythic"]
           for t in texts if t.center[0] < 450 and 190 < t.center[1] < 275):
        rarity = "mythic_plus"
    level = _pet_number(texts, PET_LEVEL_REGION) or _pet_number(level_texts, PET_LEVEL_REGION)
    copies, copies_cost = _pet_counter(texts, (380, 1700, 1270, 1810))
    food, food_cost = _pet_counter(texts, (785, 2050, 1185, 2205))
    return Pet(name, rarity, level, copies, equipped, food_cost, copies_cost), food


def next_pet_arrow(img):
    # The navigation chevron has a solid white triangular centre. Limit this
    # check to its own strip, away from the gear and upgrade controls.
    left, top = 1280, 435
    mask = cv2.inRange(img[top:540, left:1385], (232, 232, 232), (255, 255, 255))
    _, _, components, _ = cv2.connectedComponentsWithStats(mask)
    arrows = [(left + x + w // 2, top + y + h // 2) for x, y, w, h, area in components[1:]
              if 34 <= w <= 65 and 42 <= h <= 82 and .48 <= area / (w * h) <= .84]
    return arrows[0] if len(arrows) == 1 else None


def deployed_power(texts, kind):
    title_words = ("equipped mount power", "poder de montaria equipado", "poder da montaria equipada") if kind == "mounts" else (
        "equipped sentinel power", "poder de sentinela equipado", "poder da sentinela equipada")
    title = next((t for t in texts if t.norm in title_words and 1200 < t.center[1] < 1450), None)
    if title is None:
        return None
    power = next((t for t in texts if 40 < t.center[1]-title.center[1] < 110 and 350 < t.center[0] < 850), None)
    if power is None:
        return None
    # Observed pairs. Other powers remain raw evidence until identified.
    return {"dinoblessing": "Dino", "colossalstrength": "Stone Sentinel"}.get(key(power.text))


def tree_page(texts):
    return bool(term(texts, "adventure", lo=2350) and term(texts, "specialization", lo=2350))


def researched_nodes(texts):
    if not tree_page(texts):
        return ()
    return tuple(t.center for t in tree_rank_labels(texts)
                 if (rank := _learned_rank(t.norm)) and rank[1] <= 4)


def tree_rank_labels(texts):
    """Only canvas ranks: ten-level attribute squares are not skill unlock nodes."""
    return tuple(t for t in texts if 100 < t.center[1] < 2330
                 and (m := re.fullmatch(r"(\d+)\s*/\s*(\d+)", t.norm))
                 and 0 <= int(m[1]) <= int(m[2]) <= 20)


def tree_node_tap(texts, point):
    label = next((t for t in tree_rank_labels(texts) if abs(t.center[0] - point[0]) < 25
                  and abs(t.center[1] - point[1]) < 25), None)
    # Rank text scales with zoom too. Aim within the icon at either scale.
    offset = max(18, round((label.y2 - label.y1) * 1.5)) if label else 60
    return point[0], max(40, point[1] - offset)


_TREE_CLOSE = cv2.imread(str(Path(__file__).parent / "templates" / "account" / "tree_close.png"))
_TREE_RANK = re.compile(r"(\d+)\s*/\s*(\d+)")
_NEW_SKILL = re.compile(r"(?:new skill|nova habilidade|nova pericia|nueva habilidad)\s*[-:–]\s*(.+)")
_REQUIRED_RANK = re.compile(r"(?:lv|nv|nivel)\.?\s*(\d+)\s*/\s*(\d+)")


def tree_close(img):
    """The square close button used on the larger research details."""
    left, top = 580, 2160
    point = match_template(img[top:2370, left:860], _TREE_CLOSE, config.CLOSE_X_MIN_SCORE)
    if point:
        return point[0] + left, point[1] + top


def _learned_rank(text):
    m = _TREE_RANK.fullmatch(text)
    if m and 0 < int(m[1]) <= int(m[2]) <= 20:
        return int(m[1]), int(m[2])


def tree_rank(texts):
    return next((_learned_rank(t.norm) for t in texts if 400 < t.center[1] < 1050
                 and abs(t.center[0]-720) < 105 and _learned_rank(t.norm)), None)


def unlocked_skills(texts, rank=None):
    rank = rank or tree_rank(texts)
    if rank is None:
        return ()
    learned, maximum = rank
    unlocked = []
    for title in texts:
        match = _NEW_SKILL.fullmatch(title.norm)
        if not match or not 650 < title.center[1] < 1950:
            continue
        name = _REQUIRED_RANK.split(match[1], maxsplit=1)[0].strip()
        rule = rule_for(name)
        if rule is None or rule.mode != "solo":
            continue
        for label in texts:
            if label is not title and (label.center[0] <= title.center[0] or
                                      abs(label.center[1] - title.center[1]) > 24):
                continue
            required = _REQUIRED_RANK.search(label.norm)
            if required and 0 < int(required[1]) <= learned and int(required[2]) == maximum:
                unlocked.append(rule.name)
                break
    return tuple(dict.fromkeys(unlocked))


def game_version(texts):
    if not term(texts, "settings", lo=400, hi=700):
        return None
    return next((m[1].replace(",", ".") for t in texts if t.center[1] > 2300 and
                 (m := re.fullmatch(r"(?:version|versao|versión)\s*:\s*(\d+[.,]\d{3}(?:\.\d+)?)", t.norm))), None)


def settings_page(texts):
    return bool(term(texts,"settings",lo=400,hi=700) and any(t.norm in ("music","musica","sound effects","efeitos sonoros")
                for t in texts))


def bag_cells(texts):
    if not (term(texts, "bag", lo=400, hi=650) or any(re.match(r"(?:you own|voce possui|possui|tienes)\s*:",t.norm) for t in texts)):
        return ()
    return tuple((t.center[0], t.center[1]-90) for t in sorted(texts,key=lambda t:(round(t.center[1]/100),t.center[0]))
                 if 650 < t.center[1] < 1800 and 250 < t.center[0] < 1200
                 and re.fullmatch(r"x?\d+(?:[.,]\d+)?[kmb]?", t.norm))


RESOURCE_NAMES = {
    "awakeningcrystals": "awakening_crystals", "cristaisdedespertar": "awakening_crystals",
    "ironbars": "iron_bars", "barrasdeferro": "iron_bars", "chromaticprisms": "chromatic_prisms",
    "prismascromaticos": "chromatic_prisms", "spiritbones": "spirit_bones", "ossosdeespirito": "spirit_bones",
    "memorystones": "memory_stones", "memory stone": "memory_stones", "pedrasdememoria": "memory_stones",
    "petfood": "pet_food", "alimentodepet": "pet_food", "herodust": "hero_dust", "podeheroi": "hero_dust",
    "mountpieces": "mount_pieces", "divinehammers": "divine_hammers", "martelosdivinos": "divine_hammers",
    "affinitybooks": "affinity_books", "arenapoints": "arena_points", "guildcoins": "guild_coins",
    "adventureskillpoints": "adventure_points", "specializationskillpoints": "specialization_points",
}


def bag_item(texts):
    owned = next(((t,m[1]) for t in texts if (m := re.fullmatch(
        r"(?:you own|voce possui|possui|tienes)\s*:\s*(\d+(?:[.,]\d+)?[kmb]?)",t.norm))), None)
    if owned is None:
        return None
    label, raw = owned
    names = [t for t in texts if abs(t.center[0]-label.center[0]) < 130
             and 100 < label.center[1]-t.center[1] < 250 and re.search(r"[a-z]{3}", t.norm)]
    if len(names) != 1:
        return None
    amount = parse_power(raw)
    return (names[0].text, amount, RESOURCE_NAMES.get(key(names[0].text))) if amount is not None else None
