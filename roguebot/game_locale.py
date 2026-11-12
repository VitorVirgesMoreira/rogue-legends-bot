"""Named concepts shared by localized event screens; never positional choices."""

from roguebot.vision import normalize

TERMS = {
    "party": {"en": ("party expedition",), "es": ("expedicion en grupo", "expedicion de grupo"),
              "pt": ("expedicao em grupo", "expedicao de grupo", "expedicao da equipe")},
    "party_word": {"en": ("party",), "es": ("grupo",), "pt": ("grupo", "em grupo", "equipe")},
    "expedition": {"en": ("expedition",), "es": ("expedicion",), "pt": ("expedicao",)},
    "match": {"en": ("match",), "es": ("emparejar", "buscar grupo"), "pt": ("encontrar grupo", "buscar grupo", "parear")},
    "codex": {"en": ("skill codex",), "es": ("codice de habilidades",), "pt": ("codice de habilidades", "codex de habilidades", "codice de pericias")},
    "claim": {"en": ("tap anywhere to claim",), "es": ("toca en cualquier lugar para reclamar",),
              "pt": ("toque em qualquer lugar para resgatar", "toque em qualquer lugar para coletar", "toque em qualquer lugar para reivindicar")},
    "matching": {"en": ("finding players", "party formed"), "es": ("buscando jugadores", "grupo formado"),
                 "pt": ("procurando jogadores", "buscando jogadores", "grupo formado", "equipe formada")},
    "route": {"en": ("tap to vote", "moving on", "movingon", "waiting for the party"),
              "es": ("toca para votar", "avanzando", "esperando al grupo"),
              "pt": ("toque para votar", "avancando", "aguardando o grupo", "aguardando a equipe")},
    "campfire": {"en": ("taking a break",), "es": ("tomando un descanso",), "pt": ("fazendo uma pausa", "descansando")},
    "chaos": {"en": ("chaos realm",), "es": ("reino del caos",), "pt": ("reino do caos",)},
    "conquest": {"en": ("guild conquest",), "es": ("conquista de gremios", "conquista del gremio"),
                 "pt": ("conquista de guildas", "conquista da guilda")},
}


def variants(concept):
    return tuple(v for values in TERMS[concept].values() for v in values)


def is_term(value, concept):
    return normalize(value) in variants(concept)


def contains_term(value, concept):
    text = normalize(value)
    return any(v in text for v in variants(concept))


def language(texts, concept):
    norms = {t.norm for t in texts}
    return next((lang for lang, values in TERMS[concept].items() if norms.intersection(values)), None)


PORTUGUESE_SKILLS = {
    "Cota-de-Espinhos": "Thornmail", "Determinação": "Resolve", "Elo-Divino": "Divine Link",
    "Inflexível": "Unyielding", "Avançar": "Ascend", "Médica": "Medica",
    "Golpe da Piedade": "Mercy Strike", "Golpes Apaziguadores": "Quelling Strikes",
    "Arma de Fogo": "Fire Weapon", "Arma Flamejante": "Fire Weapon", "Arma de Gelo": "Ice Weapon",
    "Arma de Raio": "Lightning Weapon", "Arma Eletrica": "Lightning Weapon", "Onda de Fogo": "Fire Wave",
    "Bola de Fogo Mortal": "Deadly Fireball", "Chamas Mortais": "Deadly Flames", "Mestre do Fogo": "Fire Mastery",
    "Maestria de Fogo": "Fire Mastery", "Maestria do Fogo": "Fire Mastery", "Senhor do Fogo": "Fire Lord",
    "Piromania": "Pyromania", "Frenesi Flamejante": "Blazing Frenzy", "Meteoro": "Meteor",
    "Golpe Flamejante": "Flame Strike", "Bola de Fogo Suprema": "Ultimate Fireball",
    "Bola de Fogo Definitiva": "Ultimate Fireball", "Golpe Flamejante Definitivo": "Ultimate Flame Strike",
    "Foco Elemental": "Elemental Focus", "Estrelas Elementais": "Elemental Stars",
    "Cutilada": "Cleave", "Clivagem": "Cleave", "Cutilada Definitiva": "Ultimate Cleave",
    "Maestria de Cutilada": "Cleave Mastery", "Maestria de Ferida": "Wound Mastery",
    "Cortes Profundos": "Deep Cuts", "Golpe de Ferida": "Wound Strike", "Ciclone de Aco": "Steel Cyclone",
    "Sede de Sangue": "Bloodlust", "Lambendo Feridas": "Licking Wounds", "Oportunista": "Opportunist",
    "Adrenalina": "Adrenaline Rush", "Furia Ardente": "Burning Rage", "Emocao da Batalha": "Thrill of Battle",
    "Golpe Venenoso": "Poison Strike", "Nuvem Venenosa": "Poison Cloud", "Veneno Profundo": "Deep Venom",
    "Maestria de Veneno": "Poison Mastery", "Mestre do Veneno": "Poison Mastery", "Contagio": "Contagion",
    "Corrosao": "Corrosion", "Experimento Especial": "Special Experiment", "Retaliacao Toxica": "Toxic Retaliation",
    "Veneno Furtivo": "Sneaky Poison", "Explosao Venenosa": "Venom Burst", "Postura da Serpente": "Serpent Stance",
    "Veneno Definitivo": "Ultimate Poison", "Veneno Supremo": "Ultimate Poison",
    "Maestria de Gelo": "Ice Mastery", "Mestre do Gelo": "Ice Mastery", "Frio Fragil": "Fragile Cold",
    "Frio Congelante": "Freezing Cold", "Golpe Gelado": "Frost Strike", "Nova Gelada": "Frost Nova",
    "Parede de Gelo": "Ice Wall", "Espinhos de Gelo": "Ice Spikes", "Gelo Mortal": "Deadly Ice",
    "Gelo Eterno": "Evercold", "Carambano Definitivo": "Ultimate Icicle", "Carambano de Contra-ataque": "Counter Icicle",
    "Alta Voltagem": "High Voltage", "Corrente Energizante": "Energizing Current", "Sobrecarga": "Overload",
    "Raio Repetido": "Repeated Bolt", "Tempestade Eletrica": "Thunderstorm", "Deus do Trovao": "Thunder God",
    "Descarga Estatica": "Static Discharge", "Raio por Rodada": "Round Bolt", "Raio Definitivo": "Ultimate Bolt",
    "Raio de Combo": "Combo Bolt", "Bateria Carregada": "Charged Battery", "Eletroparalisia": "Electroparalysis",
    "Maestria de Raio": "Lightning Mastery", "Maestria de Relampago": "Lightning Mastery",
    "Arremesso Critico": "Critical Throw", "Arremesso de Shuriken": "Shuriken Throw",
    "Shuriken Curativa": "Heal Shuriken", "Shuriken Curativo": "Heal Shuriken", "Shuriken Energizante": "Energizing Shuriken",
    "Shuriken Venenosa": "Poison Shuriken", "Shuriken de Ferida": "Wound Shuriken", "Shuriken Fuma": "Fuma Shuriken",
    "Estrelas Mortais": "Deadly Stars", "Arremesso Rapido": "Quick Throw", "Parceiro das Sombras": "Shadow Partner",
    "Mil Cortes": "Thousand Cuts", "Lotus da Morte": "Death Lotus", "Maestria de Shuriken": "Shuriken Mastery",
    "Lento e Constante": "Slow And Steady", "Devagar e Sempre": "Slow And Steady", "Antidoto": "Antidote",
    "Dissipar": "Dispel", "Recuperacao": "Recovery", "Roubo de Vida": "Lifesteal", "Vampirico": "Vampiric",
    "Guerreiro": "Warrior", "Mago": "Wizard", "Canhao de Vidro": "Glass Cannon", "Musculoso": "Beefcake",
    "Treinador de Pets": "Pet Trainer", "Treinador de Animais": "Pet Trainer", "Lutador Habilidoso": "Skilled Fighter",
    "Maestria Critica": "Critical Mastery", "Taxa de Acerto Critico": "Critical Hit Rate Up",
    "Aumento de Taxa Critica": "Critical Hit Rate Up", "Dano de Acerto Critico": "Critical Hit Damage Up",
    "Maestria de Combo": "Combo Mastery", "Maestria de Contra-ataque": "Counter Mastery",
    "Taxa de Combo": "Combo Rate Up", "Taxa de Contra-ataque": "Counter Rate Up", "Taxa de Esquiva": "Dodge Rate Up",
    "Escudo de Ataque": "Strike Shield", "Escudo Definitivo": "Ultimate Shield", "Escudo Enfurecido": "Enraged Shield",
    "Recuperacao Enfurecida": "Enraged Recovery", "Forca Enfurecida": "Enraged Strength",
    "Esquiva Enfurecida": "Enraged Dodge", "Resistencia Enfurecida": "Enraged Durability",
    "Bencao Sagrada": "Holy Blessing", "Intervencao Divina": "Divine Intervention", "Julgamento Divino": "Divine Judgement",
    "Ressurreicao": "Resurrection", "Ultima Resistencia": "Last Stand", "Zero Absoluto": "Absolute Zero",
    "Crescimento Constante": "Steady Growth", "Poder Crescente": "Ramping Power", "Defesa Crescente": "Ramping Defense",
    "Golpe de Abertura": "Opening Strike", "Heroismo": "Heroism", "Transfusao": "Transfusion",
    "Concoquicao Especial": "Special Concoction", "Esquiva Espiritual": "Spirit Dodge",
    "Maestria de Arma": "Weapon Mastery", "Resistencia a Supremo": "Ultimate Resistance",
    "Vinculo Divino": "Divine Link", "Inspiracao": "Inspiration", "Legado": "Legacy", "Provocar": "Provoke",
    "Determinacao": "Resolve", "Sacrificio": "Sacrifice", "Armadura de Espinhos": "Thornmail", "Inabalavel": "Unyielding",
    "Ascender": "Ascend", "Bencao": "Blessing", "Medico de Combate": "Combat Medic", "Caricia Divina": "Divine Caress",
    "Dignidade Essencial": "Essential Dignity", "Generosidade": "Generosity", "Balada Motivadora": "Motivating Ballad",
    "Sangue por Sangue": "Blood for Blood", "Marca da Morte": "Death Mark", "Instinto Assassino": "Killer Instinct",
    "Letalidade": "Lethality", "Golpe de Misericordia": "Mercy Strike", "Golpes Supressores": "Quelling Strikes",
    "Golpes Furiosos": "Raging Strikes", "Oportunidade Suprema": "Ultimate Opportunity",
}
