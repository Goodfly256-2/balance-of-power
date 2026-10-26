# «Баланс сил: Стратегия» — игра на pygame.
# - карты от 6×6 до 10×10 с органичными «живыми» границами, реальное время с паузой;
# - 4 фракции + независимый центр; можно играть за любую или в режиме наблюдателя;
# - экономика: казна (налоги), людские ресурсы, содержание армии, развитие регионов;
# - армия: набор, развитие (атака/оборона/логистика/мораль);
# - дипломатия: отношения, пакты о ненападении, союзы, торговля, дань;
#   ИИ предлагает договоры, игрок может принять или отклонить;
# - у каждого бота свой характер (Воин/Стратег/Купец/Строитель), а страны
#   на старте различаются размером, экономикой и армией;
# - бой за регион решается автоматически;
# - несколько сценариев (разные карты и наборы стран) — см. SCENARIOS;
# - запускается как напрямую (strategy.py), так и из главного меню (menu.py):
#   run_game(scenario) показывает собственный экран выбора фракции и партию.
import math
import random
import pygame

import audio
import settings as user_settings
import version


# ============================ КОНФИГУРАЦИЯ ============================
GRID = 8
NEUTRAL = -1

TICK_RATE = 30              # шагов симуляции в секунду при скорости 1x
SPEEDS = [1, 2, 4, 8]
MOVE_TIME = 1.1             # секунд на переход между регионами
FIELD_MIN = 200             # ниже этого отряд в поле считается уничтоженным

# --- повтор/просмотр игры ---
HISTORY_INTERVAL = 1.0      # как часто сохраняется снимок карты (в игровых сек.)
HISTORY_LIMIT = 4000        # максимум снимков
REPLAY_SPS = 8.0            # снимков в секунду при просмотре (×скорость)

COMBAT_K = 0.08             # масштаб потерь в бою (баллы в секунду)
ATK_TECH, DEF_TECH, LOG_TECH, MOR_TECH = 0.55, 0.55, 0.30, 0.35

# --- доктрины (тактика) ---
# Три доктрины образуют треугольник противодействия: «Манёвры» бьют «Удар»,
# «Удар» ломает «Оборону», «Оборона» перемалывает «Манёвры» (+35% против
# проигрывающей стороне matchup'а). Смена доктрины стоит денег и дезорганизует
# армию (морале -8), но доступна всегда — подстройка под врага часть игры.
DOCTRINES = [
    {"key": "maneuver", "name": "Манёвры",
     "desc": "темп и охваты: быстрое движение, +атака в поле, слабая осада",
     "atk": 1.05, "def": 0.90, "speed": 1.30,
     "beats": "assault"},
    {"key": "assault", "name": "Удар",
     "desc": "блицкриг: мощная атака, но держать фронт тяжело",
     "atk": 1.30, "def": 0.75, "speed": 1.00,
     "beats": "defense"},
    {"key": "defense", "name": "Оборона",
     "desc": "эшелоны и укрепления: крепкая оборона, медленное наступление",
     "atk": 0.80, "def": 1.35, "speed": 0.85,
     "beats": "maneuver"},
]
DOCTRINE_COUNTER = 0.35      # бонус атаки против проигрывающего matchup'а
DOCTRINE_COST = 140          # базовая цена смены доктрины

# --- технологии (сверх базовых атк/обр/лог/мор) ---
TECH_TRACKS = [
    {"key": "arty",  "name": "Артиллерия",  "desc": "+урон в бою за регион",
     "cost": 190, "atk_region": 0.10},
    {"key": "radio", "name": "Связь",        "desc": "армии в поле держат удар дольше",
     "cost": 160, "field_def": 0.15},
    {"key": "fuel",  "name": "Мотопехота",   "desc": "быстрее переброска войск",
     "cost": 170, "speed": 0.10},
    {"key": "med",   "name": "Медицина",     "desc": "+мораль и прирост людей",
     "cost": 150, "morale": 0.10, "manpower": 0.10},
]
TECH_MAX = 3                  # максимальный уровень каждой технологии
WAR_LIST_LIMIT = 60          # сколько записей войн/потерь хранится в сводке

# --- идеологии стран ---
# Каждая даёт свой стиль игры: от экономики до тотальной войны. Назначается
# случайно при старте партии; видна в дипломатии и на экране выбора.
IDEOLOGIES = [
    {"key": "democracy", "name": "Демократия",
     "desc": "доход +10%, мораль растёт быстрее, агрессия ИИ ниже",
     "econ": 1.10, "morale": 0.12, "aggro": 0.85},
    {"key": "monarchy", "name": "Монархия",
     "desc": "люди +15%, оборона стабильна, дипломатия мягче",
     "manpower": 1.15, "def": 0.06, "diplo": 1.15},
    {"key": "fascism", "name": "Фашизм",
     "desc": "атака +10%, армия дешевле, соседи недолюбливают",
     "atk": 0.10, "recruit_cost": 0.85, "rel": -10},
    {"key": "communism", "name": "Коммунизм",
     "desc": "развитие регионов вдвое дешевле, доход скромнее",
     "dev_cost": 0.55, "econ": 0.92},
    {"key": "technocracy", "name": "Технократия",
     "desc": "технологии дешевле на 25%, казна растёт медленнее",
     "tech_cost": 0.75, "econ": 0.95},
]
IDEOLOGY_WARLIKE = {"fascism"}     # идеологии, тянущиеся к войне

# --- флаги стран ---
# Каждой фракции при создании выдаётся процедурный флаг (полосы/крест/кантон
# + эмблема в цвете страны) — рисуется в дипломатии, выборе и на столицах.
FLAG_STYLES = ["stripes", "cross", "canton", "diagonal", "border"]

# --- экономика ---
RECRUIT_AMOUNT = 2500
RECRUIT_COST = 45
MANPOWER_PER_RECRUIT = 2500     # людей на один набор
MANPOWER_RATE = 0.004           # людей/сек на единицу населения
MANPOWER_MAX_FRAC = 0.55        # запас не больше доли населения
MANPOWER_DEV_BONUS = 0.15       # +15% людских ресурсов за уровень развития региона
UPKEEP_PER_1K = 0.05            # денег/сек за 1000 войск (содержание армии)
ECON_DEV_COST = 55              # базовая стоимость развития региона
MAX_ECON_DEV = 5
ECON_DEV_INCOME = 0.25          # +25% дохода за уровень развития региона
DEV_BASE_COST = 70              # стоимость развития армии

# Уровни призыва: больше людей, но меньше дохода (как «законы о призыве»).
CONSCRIPT = [
    {"name": "Добровольцы",  "max": 1.00, "rate": 1.00, "income": 1.00},
    {"name": "Ограниченный", "max": 1.12, "rate": 1.25, "income": 0.94},
    {"name": "Обычный",      "max": 1.25, "rate": 1.50, "income": 0.88},
    {"name": "Расширенный",  "max": 1.40, "rate": 1.80, "income": 0.80},
    {"name": "Всеобщий",     "max": 1.60, "rate": 2.20, "income": 0.70},
    {"name": "Тотальный",    "max": 1.85, "rate": 2.80, "income": 0.58},
]
CONSCRIPT_COST_BASE = 120       # цена поднятия призыва растёт с уровнем

# --- дипломатия ---
GRACE_PERIOD = 45.0
NAP_DURATION = 240.0
TRADE_INCOME = 0.08             # +8% дохода по торговому соглашению
WAR_WEARINESS_TIME = 350.0      # ИИ утомляется войной much позже — воюет упорно

# --- ИИ ---
AI_MIL_TIMER = 1.2
AI_DIPLO_TIMER = 12.0

FACTION_DEFS = [
    ("Северный Альянс", (74, 144, 255), "промышленники"),
    ("Империя Зари", (235, 90, 70), "милитаристы"),
    ("Южный Синдикат", (90, 200, 120), "торговцы"),
    ("Орден Заката", (219, 170, 80), "фанатики"),
]
FACTION_HOME = [(0, 0), (7, 0), (0, 7), (7, 7)]

# Характеры ИИ: у каждой фракции свой стиль поведения (по одному на партию).
# need — множитель порога перевеса для атаки; econ/tech — множители шансов
# развития; diplo — множитель частоты дипломатии; neutral — множитель порога
# атаки на независимых (больше = осторожнее).
PERSONALITIES = [
    {"name": "Воин",      "aggro": (0.85, 1.00), "need": 0.90, "econ": 0.50, "tech": 1.50, "diplo": 0.50, "neutral": 0.95},
    {"name": "Стратег",   "aggro": (0.55, 0.75), "need": 1.00, "econ": 1.00, "tech": 1.10, "diplo": 1.00, "neutral": 1.05},
    {"name": "Купец",     "aggro": (0.25, 0.45), "need": 1.25, "econ": 1.50, "tech": 0.60, "diplo": 1.80, "neutral": 1.25},
    {"name": "Строитель", "aggro": (0.40, 0.60), "need": 1.10, "econ": 1.80, "tech": 0.70, "diplo": 1.20, "neutral": 1.10},
]

# Страны на старте: у каждой фракции свой тип — размер, армия, экономика.
# delta — сколько регионов страна забирает у соседей (<0 — отдаёт).
NATION_KINDS = [
    {"name": "обширная держава",     "delta": 3,  "army": 1.00, "econ": 0.95, "money": 280, "manpower": 1.15, "dev": 1},
    {"name": "богатое государство",  "delta": -2, "army": 0.85, "econ": 1.45, "money": 430, "manpower": 0.90, "dev": 3},
    {"name": "милитаристская",       "delta": -1, "army": 1.55, "econ": 0.70, "money": 300, "manpower": 1.45, "dev": 0},
    {"name": "сбалансированная",     "delta": 0,  "army": 1.00, "econ": 1.00, "money": 240, "manpower": 1.00, "dev": 2},
]

# ============================ СЦЕНАРИИ ============================
# Сетка, набор стран и стартовые условия. Столицы расставляются по углам
# (для двух стран — по диагонали, для шести — ещё и середины верхней/нижней
# кромки), владения на старте делятся «ближе к своей столице».
EXTRA_FACTION_DEFS = [
    ("Аметистовый Пакт", (164, 112, 214), "завоеватели"),
    ("Лига Приливов", (58, 190, 188), "мореплаватели"),
]

_CLASSIC_FACTIONS = list(FACTION_DEFS)

SCENARIOS = {
    "classic": {
        "name": "Классика",
        "desc": "Сбалансированная партия: четыре державы и независимый центр.",
        "grid": 8,
        "factions": _CLASSIC_FACTIONS,
        "neutral_core": True,
    },
    "duel": {
        "name": "Дуэль гигантов",
        "desc": "Две империи на карте 6×6. Дипломатия почти ни к чему.",
        "grid": 6,
        "factions": [_CLASSIC_FACTIONS[1], _CLASSIC_FACTIONS[0]],
        "neutral_core": False,
        "army_mult": 1.5,
    },
    "chaos": {
        "name": "Шесть держав",
        "desc": "Большая карта 10×10: шесть стран делят мир.",
        "grid": 10,
        "factions": _CLASSIC_FACTIONS + EXTRA_FACTION_DEFS,
        "neutral_core": True,
    },
    "siege": {
        "name": "Осаждённая твердыня",
        "desc": "У вас одна столица, у соседей — втрое больше земель и армий.",
        "grid": 8,
        "factions": _CLASSIC_FACTIONS,
        "neutral_core": False,
        "handicap": True,
    },
    "split": {
        "name": "Раскол",
        "desc": "Два враждебных блока: война начинается с первых секунд.",
        "grid": 8,
        "factions": _CLASSIC_FACTIONS,
        "neutral_core": True,
        "blocs": [[0, 2], [1, 3]],
        "grace": 5.0,
    },
    "anarchy": {
        "name": "Анархия",
        "desc": "Восемь стран на карте 10×10, без нейтрального центра. Выживет одна.",
        "grid": 10,
        "factions": _CLASSIC_FACTIONS + EXTRA_FACTION_DEFS + [
            ("Кримский Ханат", (198, 128, 96), "кочевники"),
            ("Вольные Города", (210, 210, 215), "республика"),
        ],
        "neutral_core": False,
        "army_mult": 0.9,
    },
}


def homes_for(n, g):
    """Стартовые клетки столиц для n фракций на сетке g×g."""
    if n == 2:
        return [(0, 0), (g - 1, g - 1)]
    if n == 3:
        return [(0, 0), (g - 1, 0), (g // 2, g - 1)]
    hs = [(0, 0), (g - 1, 0), (g - 1, g - 1), (0, g - 1)]
    if n > 4:
        m = g // 2
        hs += [(m, 0), (m, g - 1)]
    if n > 6:
        hs += [(0, m), (g - 1, m)]
    return hs[:n]


def apply_grid(g):
    """Переключает глобальную геометрию карты на сетку g×g и сбрасывает
    кэши «живых» границ. Вызывается из Game.setup() перед созданием регионов.
    (Функция определена здесь, но использует константы раздела отрисовки —
    это нормально: она вызывается уже после загрузки модуля.)"""
    global GRID, TILE, MAP_W, MAP_H, PANEL_X, PANEL_W, _TERRAIN_TEX
    GRID = g
    TILE = 74 if g <= 8 else max(48, 688 // g)
    MAP_W = MAP_H = GRID * TILE
    PANEL_X = MAP_X + MAP_W + 20
    PANEL_W = W - PANEL_X - 16
    _CORNER.clear()
    _EDGE_PTS.clear()
    _POLY.clear()
    _BBOX.clear()
    _MASK.clear()
    _SUBLINES.clear()
    _SPLITWAVE.clear()
    _TERRAIN_TEX = None

TERRAINS = [
    ("равнина", 0.00, 1.00),
    ("лес", 0.35, 0.85),
    ("холмы", 0.50, 0.90),
    ("горы", 0.80, 0.60),
]

REL_NAMES = [(70, "дружелюбие"), (20, "тепло"), (-20, "нейтрально"),
             (-60, "напряжение"), (-10 ** 9, "вражда")]

KIND_NAMES = {
    "alliance": "союз", "nap": "пакт о ненападении", "trade": "торговое соглашение",
    "peace": "мир", "gift": "дар", "demand": "требование дани",
}


# ============================ МОДЕЛЬ ============================
class Faction:
    def __init__(self, fid, name, color, trait="", is_player=False):
        self.fid = fid
        self.name = name
        self.color = color
        self.trait = trait
        self.is_player = is_player
        self.money = 240.0
        self.manpower = 8000.0
        self.manpower_max = 12000.0
        self.morale = 100.0
        self.tech = {"atk": 0, "def": 0, "log": 0, "mor": 0}
        self.tech2 = {t["key"]: 0 for t in TECH_TRACKS}   # новые технологии
        self.doctrine = 1            # индекс в DOCTRINES (старт — «Удар»)
        self.ideology = 0            # индекс в IDEOLOGIES (назначается в setup)
        self.flag_style = "stripes"  # стиль флага (назначается в setup)
        self.flag = None             # Surface флага (кэш, лениво)
        self.conscript = 0           # уровень призыва (0..len(CONSCRIPT)-1)
        self.relations = {}          # fid -> -100..100
        self.war = set()
        self.alliance = set()
        self.nap = {}                # fid -> время_окончания
        self.trade = set()
        self.alive = True
        self.ai_timer = 0.0
        self.diplo_timer = 0.0
        self.aggro = 0.85            # 0..1: насколько охотно идёт на войну
        self.personality = None      # характер ИИ (dict из PERSONALITIES)
        self.nation = None           # тип страны на старте (dict из NATION_KINDS)
        self.econ_mult = 1.0         # национальный множитель дохода
        self.capital = None
        self.war_start = {}          # fid -> время начала войны
        self.last_war = -999.0
        self.wars = []               # список войн: {fid, start, end, losses, kills}
        self.kills = 0.0             # суммарные уничтоженные войска врага
        self.losses = 0.0            # суммарные потери
        self.game = None

    @property
    def total_troops(self):
        total = sum(r.forces.get(self.fid, 0) for r in self.game.regions)
        total += sum(m.amount for m in self.game.moves if m.fid == self.fid)
        return total

    @property
    def regions(self):
        return [r for r in self.game.regions if r.owner == self.fid]


class Region:
    def __init__(self, rid, x, y, income, terrain, pop):
        self.rid = rid
        self.x = x
        self.y = y
        self.base_income = income
        self.terrain = terrain          # (name, def_bonus, income_mult)
        self.pop = pop                  # население
        self.dev = 0                    # уровень развития экономики
        self.owner = NEUTRAL
        self.forces = {NEUTRAL: 9000}   # fid -> soldiers
        self.capital_of = None
        self.flash = 0.0                # подсветка боя
        self.entry = {}                 # fid -> (dx, dy): откуда пришёл атакующий
        self.dshare = 0.0               # плавно отображаемая доля захвата

    def owner_forces(self):
        return self.forces.get(self.owner, 0.0)

    @property
    def income(self):
        return (self.base_income * self.terrain[2]
                * (1.0 + ECON_DEV_INCOME * self.dev))


class Move:
    def __init__(self, fid, amount, src, dst, duration):
        self.fid = fid
        self.amount = amount
        self.src = src
        self.dst = dst
        self.duration = duration
        self.t = 0.0
        self.frozen = False          # застыла в встречном бою на середине пути
        self.retreat = False         # отступает домой после перехвата

    @property
    def progress(self):
        return min(1.0, self.t / self.duration) if self.duration > 0 else 1.0


# ============================ ИГРА ============================
class Game:
    def __init__(self, scenario="classic", opts=None):
        opts = opts or {}
        self.rng = random.Random(20261004)
        self.scenario = scenario if scenario in SCENARIOS else "classic"
        self.on_exit = opts.get("on_exit")      # callback «вернуться в меню»
        self.show_names = opts.get("show_names", True)   # названия стран на карте
        self.regions = []
        self.factions = {}
        self.moves = []
        self.field_clashes = []
        self.captures = []              # анимации смены владельца региона
        self.log = []
        self.time = 0.0
        self.paused = True
        self.speed_idx = 0
        self._tick_acc = 0.0       # остаток дробных тиков между кадрами
        self.choosing = True
        self.player = None
        self.observer = False           # режим наблюдателя: все фракции за ИИ
        self.winner = None
        self.selected = None
        self.move_mode = False
        self.show_numbers = bool(opts.get("show_numbers", False))
        self.tab = 0                    # 0 обзор, 1 регион, 2 дипломатия
        self.pending_offers = []        # входящие предложения игроку
        self.player_offer_time = -999.0
        self.exit_requested = False     # пользователь просился в главное меню
        self.panel_scroll = {0: 0, 1: 0, 2: 0, 3: 0}   # прокрутка вкладок панели
        self.fullscreen = False         # полноэкранный режим (F11)
        self.replay_saved = False       # автосохранение повтора уже сделано
        # --- повтор/просмотр ---
        self.history = []               # снимки состояния карты
        self.hist_timer = 0.0
        self.replay = False
        self.replay_idx = 0
        self.replay_pos = 0.0           # дробная позиция для плавного проигрывания
        self.replay_playing = True
        self.replay_speed = 1.0
        self.setup()

    # -------- построение --------
    def setup(self):
        sc = SCENARIOS[self.scenario]
        apply_grid(sc["grid"])
        self.grace_time = sc.get("grace", GRACE_PERIOD)

        self.regions = []
        for y in range(GRID):
            for x in range(GRID):
                inc = 1.0 + self.rng.uniform(-0.15, 0.45)
                terr = self.rng.choices(TERRAINS, weights=[50, 25, 15, 10])[0]
                pop = int(self.rng.randint(1100, 3200) * terr[2])
                self.regions.append(Region(len(self.regions), x, y, inc, terr, pop))

        defs = sc["factions"]
        for fid, (name, color, trait) in enumerate(defs):
            f = Faction(fid, name, color, trait)
            f.game = self
            for other in range(len(defs)):
                if other != fid:
                    f.relations[other] = self.rng.randint(-12, 12)
            self.factions[fid] = f

        # характер ИИ и тип страны — по одному комплекту на партию
        # (пул продублирован, чтобы хватило и на шесть держав)
        pers = self.rng.sample(PERSONALITIES * 2, len(defs))
        kinds = self.rng.sample(NATION_KINDS * 2, len(defs))
        ideo_pool = list(range(len(IDEOLOGIES))) * 2
        for fid, f in self.factions.items():
            f.personality = pers[fid]
            f.nation = kinds[fid]
            f.aggro = self.rng.uniform(*pers[fid]["aggro"])
            f.ideology = self.rng.choice(ideo_pool)
            f.flag_style = self.rng.choice(FLAG_STYLES)
            ideo = IDEOLOGIES[f.ideology]
            f.aggro *= ideo.get("aggro", 1.0)

        # независимые (нейтральные) — псевдо-фракция для расчёта боя
        self.neutral = Faction(NEUTRAL, "Независимые", (120, 124, 132))
        self.neutral.game = self
        self.neutral.tech = {"atk": 0, "def": 1, "log": 0, "mor": 0}
        self.neutral.morale = 110.0

        # владения: каждый регион отходит стране, чья столица ближе
        homes = homes_for(len(defs), GRID)
        for r in self.regions:
            best, bd = 0, None
            for fid, (hx, hy) in enumerate(homes):
                d = (r.x - hx) ** 2 + (r.y - hy) ** 2
                if bd is None or d < bd:
                    best, bd = fid, d
            r.owner = best
            r.forces = {best: 0}
        # независимый центр
        if sc.get("neutral_core"):
            c = GRID // 2
            gar = int(6000 * (GRID / 8.0) ** 2)
            for (x, y) in [(c - 1, c - 1), (c, c - 1), (c - 1, c), (c, c)]:
                r = self.region_at(x, y)
                r.owner = NEUTRAL
                r.forces = {NEUTRAL: gar}

        # столицы (отмечаем до передачи регионов, чтобы столицы не переходили)
        for fid, (cx, cy) in enumerate(homes):
            cap = self.region_at(cx, cy)
            cap.capital_of = fid
            self.factions[fid].capital = cap.rid
            cap.terrain = TERRAINS[0]

        # страны различаются размером: «держава» забирает регионы у соседей
        givers = [fid for fid in self.factions if self.factions[fid].nation["delta"] < 0]
        for fid in self.factions:
            for _ in range(max(0, self.factions[fid].nation["delta"])):
                cands = [r for gid in givers for r in self.factions[gid].regions
                         if r.capital_of is None
                         and any(n.owner == fid for n in self.neighbors(r))]
                if not cands:
                    cands = [r for gid in givers for r in self.factions[gid].regions
                             if r.capital_of is None]
                if not cands:
                    break
                r = self.rng.choice(cands)
                r.owner = fid
                r.forces = {fid: next(iter(r.forces.values()))}

        # гарнизоны и развитие — по типу страны
        army_mult = sc.get("army_mult", 1.0)
        for fid, (cx, cy) in enumerate(homes):
            cap = self.region_at(cx, cy)
            kind = self.factions[fid].nation
            cap.dev = min(MAX_ECON_DEV, kind["dev"])
            cap.forces = {fid: int(26000 * kind["army"] * army_mult)}
            for r in self.regions:
                if r.owner == fid and r is not cap:
                    r.forces = {fid: int(self.rng.randint(7000, 11000)
                                         * kind["army"] * army_mult)}
                    if kind["dev"] > 1 and self.rng.random() < 0.35:
                        r.dev = self.rng.randint(1, kind["dev"] - 1)

        for f in self.factions.values():
            self.recalc_manpower(f, init=True)
            ideo = IDEOLOGIES[f.ideology]
            f.econ_mult = f.nation["econ"] * ideo.get("econ", 1.0)
            f.money = f.nation["money"] + self.rng.uniform(-25, 25)
            f.manpower = min(f.manpower_max,
                             f.manpower_max * f.nation["manpower"] * ideo.get("manpower", 1.0))

        # «Раскол»: два блока сразу в состоянии войны
        if "blocs" in sc:
            west, east = sc["blocs"]
            for a in west:
                for b in east:
                    self.factions[a].relations[b] = -85
                    self.factions[b].relations[a] = -85
                    self.declare_war(a, b, quiet=True)
            for bloc in (west, east):
                for a, b in zip(bloc, bloc[1:]):
                    self.make_alliance(a, b)
            self.log_msg("Блоки сформированы — война началась!")

        self.record_snapshot()
        self.log_msg("Выберите фракцию, чтобы начать игру.")

    # -------- запись истории для повтора --------
    def record_snapshot(self):
        self.history.append({
            "t": self.time,
            "owner": [r.owner for r in self.regions],
            "forces": [int(r.owner_forces()) for r in self.regions],
            "cap": [r.capital_of for r in self.regions],
        })
        if len(self.history) > HISTORY_LIMIT:
            self.history.pop(0)

    def start_replay(self):
        self.replay = True
        self.replay_idx = 0
        self.replay_pos = 0.0
        self.replay_playing = True
        self.replay_speed = 1.0

    def update_replay(self, dt):
        n = len(self.history)
        if not self.replay_playing or n == 0:
            return
        self.replay_pos += dt * REPLAY_SPS * self.replay_speed
        if self.replay_pos >= n - 1:
            self.replay_pos = float(n - 1)
            self.replay_playing = False
        self.replay_idx = int(self.replay_pos)

    def replay_snapshot(self):
        if not self.history:
            return None
        self.replay_idx = max(0, min(self.replay_idx, len(self.history) - 1))
        return self.history[self.replay_idx]

    # -------- утилиты --------
    def region_at(self, x, y):
        return self.regions[y * GRID + x]

    def neighbors(self, r):
        out = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = r.x + dx, r.y + dy
            if 0 <= nx < GRID and 0 <= ny < GRID:
                out.append(self.region_at(nx, ny))
        return out

    def log_msg(self, text):
        self.log.append(text)
        if len(self.log) > 40:
            self.log.pop(0)

    def choose_faction(self, fid, observer=False):
        self.observer = observer
        self.player = None if observer else fid
        self.choosing = False
        self.tab = 0
        for f in self.factions.values():
            f.is_player = (not observer and f.fid == fid)
        self.paused = True
        if observer:
            self.log_msg("Режим наблюдателя: все фракции играет ИИ. ПРОБЕЛ — пауза/пуск.")
        else:
            self.log_msg(f"Вы играете за «{self.factions[fid].name}». ПРОБЕЛ — пауза/пуск.")
            if SCENARIOS[self.scenario].get("handicap"):
                self._apply_siege_handicap(fid)
                self.record_snapshot()

    def _apply_siege_handicap(self, fid):
        """«Осаждённая твердыня»: у игрока остаётся только столица, остальные
        земли делят соседи и усиливают гарнизоны. Выжить — уже победа."""
        f = self.factions[fid]
        cap = self.regions[f.capital]
        others = [x for x in self.factions if x != fid]
        lands = [r for r in f.regions if r is not cap]
        self.rng.shuffle(lands)
        for i, r in enumerate(lands):
            force = int(r.forces.get(fid, 0))
            near = [n.owner for n in self.neighbors(r) if n.owner in others]
            new = self.rng.choice(near) if near else others[i % len(others)]
            r.owner = new
            r.forces = {new: force}
        for x in others:
            cf = self.regions[self.factions[x].capital]
            cf.forces[x] = cf.forces.get(x, 0) + 20000
        f.money = 150.0
        self.log_msg("Осада: ваши земли поделены соседями. Продержитесь!")

    # -------- дипломатические запросы --------
    def at_war(self, a, b):
        if a is None or b is None or a == b or a == NEUTRAL or b == NEUTRAL:
            return False
        return b in self.factions[a].war

    def allied(self, a, b):
        if a is None or b is None or a == b or a == NEUTRAL or b == NEUTRAL:
            return False
        return b in self.factions[a].alliance

    def has_nap(self, a, b):
        if a is None or b is None or a == b or a == NEUTRAL or b == NEUTRAL:
            return False
        return b in self.factions[a].nap and self.time < self.factions[a].nap[b]

    def has_trade(self, a, b):
        if a is None or b is None or a == b or a == NEUTRAL or b == NEUTRAL:
            return False
        return b in self.factions[a].trade

    def can_attack(self, fid, target):
        if target.owner == NEUTRAL:
            return True
        if self.allied(fid, target.owner) or self.has_nap(fid, target.owner):
            return False
        return self.at_war(fid, target.owner)

    # -------- аналитика карты --------
    def opposing(self, a, b):
        """Враждуют ли силы a и b прямо сейчас (для боя в одном регионе)."""
        if a == b:
            return False
        if a == NEUTRAL or b == NEUTRAL:
            return True
        return self.at_war(a, b)

    def control(self, r):
        """Возвращает (доля владельца, сильнейший чужак, его доля)."""
        owner_f = r.forces.get(r.owner, 0.0)
        foreign = [(v, f) for f, v in r.forces.items() if f != r.owner and v > 0.5]
        if not foreign:
            return 1.0, None, 0.0
        foreign.sort(reverse=True)
        v, f = foreign[0]
        total = owner_f + v
        share = v / total if total > 0 else 0.0
        return max(0.0, 1.0 - share), f, min(1.0, share)

    def battle_preview(self, r):
        """Что происходит в бою за регион: силы, урон в секунду за/против."""
        fids = [f for f, v in r.forces.items() if v > 0.5]
        info = {f: {"troops": r.forces[f], "dealt": 0.0, "taken": 0.0,
                    "owner": f == r.owner} for f in fids}
        for i in range(len(fids)):
            for j in range(i + 1, len(fids)):
                a, b = fids[i], fids[j]
                if not self.opposing(a, b):
                    continue
                fa, fb = r.forces[a], r.forces[b]
                ra = (self.defense_rate(a, r, enemy_fid=b) if a == r.owner
                      else self.attack_rate(a, enemy_fid=b))
                rb = (self.defense_rate(b, r, enemy_fid=a) if b == r.owner
                      else self.attack_rate(b, enemy_fid=a))
                dealt_a = fb * rb * COMBAT_K
                dealt_b = fa * ra * COMBAT_K
                info[a]["dealt"] += dealt_a
                info[a]["taken"] += dealt_b
                info[b]["dealt"] += dealt_b
                info[b]["taken"] += dealt_a
        return info

    def fronts(self, border_depth=2):
        """Один «фронт» = непрерывный участок границы между двумя владельцами.

        Числа на карте — не вся армия, а гарнизон приграничья: регионы каждой
        стороны в пределах border_depth клеток от границы с противником,
        суммированные вдоль фронта. У страны с двумя врагами — два независимых
        фронта (и два числа), даже если враги примыкают к тем же землям."""
        edges = []
        for r in self.regions:
            for dx, dy in ((1, 0), (0, 1)):
                nx, ny = r.x + dx, r.y + dy
                if not (0 <= nx < GRID and 0 <= ny < GRID):
                    continue
                n = self.region_at(nx, ny)
                if r.owner == n.owner:
                    continue
                pair = (min(r.owner, n.owner), max(r.owner, n.owner))
                edges.append({"pair": pair, "tiles": (r.rid, n.rid),
                              "mx": (r.x + n.x) / 2.0, "my": (r.y + n.y) / 2.0})

        parent = list(range(len(edges)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        by_tile = {}
        for idx, e in enumerate(edges):
            for t in e["tiles"]:
                by_tile.setdefault(t, []).append(idx)
        for idx, e in enumerate(edges):
            for t in e["tiles"]:
                for other in by_tile[t]:
                    if other != idx and edges[other]["pair"] == e["pair"]:
                        union(idx, other)
        # второй проход: соединяем рёбра одного фронта-пары, чьи клетки
        # ПРИМЫКАЮТ друг к другу (общей клетки нет, но это тот же фронт):
        # ребро (r1,n1) и ребро (r2,n2) соединены, если r1–r2 соседи и
        # n1–n2 соседи (или зеркально) — так прямой длинный фронт не рвётся
        # на куски по одной клетке
        def adjacent_tiles(e1, e2):
            a1, b1 = e1["tiles"]
            a2, b2 = e2["tiles"]
            ra1, rn1 = self.regions[a1], self.regions[b1]
            ra2, rn2 = self.regions[a2], self.regions[b2]
            s1 = (a1, b1)
            s2 = (a2, b2)
            for (x1, y1), (x2, y2) in ((s1, s2), (s2, s1)):
                if abs(ra1.x - ra2.x) + abs(ra1.y - ra2.y) == 1 \
                        and abs(rn1.x - rn2.x) + abs(rn1.y - rn2.y) == 1:
                    return True
            return False

        for idx in range(len(edges)):
            for jdx in range(idx + 1, len(edges)):
                if edges[idx]["pair"] != edges[jdx]["pair"]:
                    continue
                if find(idx) == find(jdx):
                    continue
                if adjacent_tiles(edges[idx], edges[jdx]):
                    union(idx, jdx)

        groups = {}
        for idx, e in enumerate(edges):
            groups.setdefault(find(idx), []).append(e)

        out = []
        for segs in groups.values():
            pair = segs[0]["pair"]
            tiles = set()
            for e in segs:
                tiles.update(e["tiles"])
            contested = False
            for rid in tiles:
                if len([f for f, v in self.regions[rid].forces.items() if v > 0.5]) > 1:
                    contested = True
                    break

            # гарнизон приграничья: BFS от фронта на border_depth вглубь
            troops = {pair[0]: 0.0, pair[1]: 0.0, "total": 0.0}
            side_pts = {pair[0]: [0.0, 0.0, 0], pair[1]: [0.0, 0.0, 0]}
            seen = set()
            for side in pair:
                frontier = [rid for rid in tiles
                            if self.regions[rid].owner == side]
                layer = set(frontier)
                depth_seen = set(frontier)
                for _ in range(max(0, border_depth - 1)):
                    nxt = set()
                    for rid in layer:
                        r = self.regions[rid]
                        for n in self.neighbors(r):
                            if (n.owner == side and n.rid not in depth_seen):
                                nxt.add(n.rid)
                                depth_seen.add(n.rid)
                    layer = nxt
                for rid in depth_seen:
                    reg = self.regions[rid]
                    v = 0.0
                    for f2 in pair:
                        fv = reg.forces.get(f2, 0.0)
                        if fv > 0.5:
                            v += fv
                    troops[side] += v
                    if rid not in seen:
                        seen.add(rid)
                    if reg.owner == side:
                        sp = side_pts[side]
                        sp[0] += reg.x + 0.5
                        sp[1] += reg.y + 0.5
                        sp[2] += 1
            troops["total"] = troops[pair[0]] + troops[pair[1]]
            mx = sum(e["mx"] for e in segs) / len(segs)
            my = sum(e["my"] for e in segs) / len(segs)
            sxx = sum((e["mx"] - mx) ** 2 for e in segs)
            syy = sum((e["my"] - my) ** 2 for e in segs)
            sxy = sum((e["mx"] - mx) * (e["my"] - my) for e in segs)
            angle = math.degrees(0.5 * math.atan2(2 * sxy, sxx - syy)) if len(segs) > 1 else 0.0
            pos = {}
            for side in pair:
                sx, sy, n = side_pts[side]
                pos[side] = (sx / n, sy / n) if n else (mx, my)

            # линия фронта для надписей: середины рёбер, упорядоченные вдоль
            # главной оси и сглаженные — текст изгибается по этой кривой
            mids = [(e["mx"], e["my"]) for e in segs]
            if len(mids) >= 2:
                cx0 = sum(p[0] for p in mids) / len(mids)
                cy0 = sum(p[1] for p in mids) / len(mids)
                axx = sum((p[0] - cx0) ** 2 for p in mids)
                ayy = sum((p[1] - cy0) ** 2 for p in mids)
                axy = sum((p[0] - cx0) * (p[1] - cy0) for p in mids)
                dir_ang = 0.5 * math.atan2(2 * axy, axx - ayy)
                d = (math.cos(dir_ang), math.sin(dir_ang))
                mids.sort(key=lambda p: (p[0] - cx0) * d[0] + (p[1] - cy0) * d[1])
                # текст читается слева направо (или сверху вниз на вертикали)
                if d[0] < 0 or (abs(d[0]) < 1e-6 and d[1] < 0):
                    mids.reverse()
                for _ in range(4):        # скользящее среднее — гладкая кривая
                    sm = [mids[0]]
                    for i in range(1, len(mids) - 1):
                        sm.append(((mids[i - 1][0] + 2 * mids[i][0] + mids[i + 1][0]) / 4,
                                   (mids[i - 1][1] + 2 * mids[i][1] + mids[i + 1][1]) / 4))
                    sm.append(mids[-1])
                    mids = sm
                # прореживание: убираем точки ближе трети тайла — меньше изломов
                th = TILE * 0.34
                pruned = [mids[0]]
                for p in mids[1:]:
                    if math.hypot(p[0] - pruned[-1][0], p[1] - pruned[-1][1]) * TILE >= th:
                        pruned.append(p)
                if len(pruned) >= 2:
                    mids = pruned
                    for _ in range(2):    # ещё раз сглаживаем после прореживания
                        sm = [mids[0]]
                        for i in range(1, len(mids) - 1):
                            sm.append(((mids[i - 1][0] + 2 * mids[i][0] + mids[i + 1][0]) / 4,
                                       (mids[i - 1][1] + 2 * mids[i][1] + mids[i + 1][1]) / 4))
                        sm.append(mids[-1])
                        mids = sm
            else:
                a, b = segs[0]["tiles"]
                if abs(a - b) == 1:       # вертикальная граница — путь вдоль неё
                    mids = [(segs[0]["mx"], segs[0]["my"] - 0.5),
                            (segs[0]["mx"], segs[0]["my"] + 0.5)]
                else:
                    mids = [(segs[0]["mx"] - 0.5, segs[0]["my"]),
                            (segs[0]["mx"] + 0.5, segs[0]["my"])]

            out.append({"pair": pair, "mx": mx, "my": my, "troops": troops,
                        "contested": contested, "angle": angle, "pos": pos,
                        "path": mids})
        return out

    def ideo_of(self, fid):
        f = self.factions.get(fid)
        return IDEOLOGIES[f.ideology] if f is not None and f is not self.neutral else IDEOLOGIES[0]

    # -------- приказы --------
    def recalc_manpower(self, f, init=False):
        pop = sum(r.pop * (1.0 + MANPOWER_DEV_BONUS * r.dev) for r in f.regions)
        info = CONSCRIPT[f.conscript]
        f.manpower_max = max(4000.0, pop * MANPOWER_MAX_FRAC * info["max"])
        f.manpower = min(f.manpower, f.manpower_max)

    def recruit(self, rid, fid=None):
        f = self.factions[fid if fid is not None else self.player]
        r = self.regions[rid]
        if r.owner != f.fid or f.money < RECRUIT_COST or f.manpower < MANPOWER_PER_RECRUIT:
            return False
        f.money -= RECRUIT_COST
        f.manpower -= MANPOWER_PER_RECRUIT
        r.forces[f.fid] = r.forces.get(f.fid, 0) + RECRUIT_AMOUNT
        return True

    def develop_econ(self, rid, fid=None):
        f = self.factions[fid if fid is not None else self.player]
        r = self.regions[rid]
        if r.owner != f.fid or r.dev >= MAX_ECON_DEV:
            return False
        cost = ECON_DEV_COST * (r.dev + 1) * self.ideo_of(f.fid).get("dev_cost", 1.0)
        if f.money < cost:
            return False
        f.money -= cost
        r.dev += 1
        self.log_msg(f"{f.name}: ({r.x},{r.y}) развитие экономики → {r.dev}")
        return True

    def develop_tech(self, fid, track):
        f = self.factions[fid]
        lvl = f.tech[track]
        cost = DEV_BASE_COST * (lvl + 1) * self.ideo_of(fid).get("tech_cost", 1.0)
        if f.money < cost:
            return False
        f.money -= cost
        f.tech[track] = lvl + 1
        names = {"atk": "атака", "def": "оборона", "log": "логистика", "mor": "мораль"}
        self.log_msg(f"{f.name}: {names[track]} → ур.{lvl + 1}")
        return True

    def army_speed(self, fid):
        f = self.factions[fid]
        doc = DOCTRINES[f.doctrine]
        fuel = f.tech2.get("fuel", 0) * TECH_TRACKS[2]["speed"]
        return MOVE_TIME / ((1.0 + LOG_TECH * f.tech["log"]) * doc["speed"] + fuel)

    def region_contested(self, r, fid=None):
        """В регионе идёт бой: чужие войска противостоят владельцу."""
        for f, v in r.forces.items():
            if v > 0.5 and f != r.owner and self.opposing(r.owner, f):
                if fid is None or fid in (r.owner, f):
                    return True
        return False

    # -------- призыв --------
    def conscript_info(self, fid):
        return CONSCRIPT[self.factions[fid].conscript]

    def conscript_cost(self, fid):
        return CONSCRIPT_COST_BASE * (self.factions[fid].conscript + 1)

    def raise_conscript(self, fid=None):
        """Поднять уровень призыва: больше людей, но меньше дохода."""
        f = self.factions[fid if fid is not None else self.player]
        if f.conscript >= len(CONSCRIPT) - 1:
            return False
        cost = self.conscript_cost(f.fid)
        if f.money < cost:
            return False
        f.money -= cost
        f.conscript += 1
        self.recalc_manpower(f)
        self.log_msg(f"{f.name}: призыв → «{CONSCRIPT[f.conscript]['name']}»")
        return True

    def send_move(self, src_id, dst_id, fid, frac):
        src = self.regions[src_id]
        dst = self.regions[dst_id]
        if src.owner != fid:
            return False
        if self.region_contested(src, fid):
            self.log_msg("Регион под боем — войска связаны обороной и не могут выйти.")
            return False
        available = src.forces.get(fid, 0)
        amount = int(available * frac)
        if amount < 200:
            return False
        if amount >= available:
            amount = int(available * 0.95)   # небольшой гарнизон остаётся дома
        if dst.owner != fid and dst.owner != NEUTRAL:
            if self.allied(fid, dst.owner):
                self.log_msg("Нельзя атаковать союзника.")
                return False
            if self.has_nap(fid, dst.owner):
                self.log_msg("Пакт о ненападении запрещает нападать.")
                return False
            if not self.at_war(fid, dst.owner):
                self.declare_war(fid, dst.owner)
        src.forces[fid] = available - amount
        self.moves.append(Move(fid, amount, src_id, dst_id, self.army_speed(fid)))
        return True

    # -------- дипломатия --------
    def declare_war(self, a, b, quiet=False):
        if a == b or a == NEUTRAL or b == NEUTRAL:
            return False
        if self.allied(a, b):
            self.break_alliance(a, b, quiet=True)
        if self.has_nap(a, b):
            if not quiet:
                self.log_msg(f"Пакт о ненападении мешает «{self.factions[a].name}» напасть.")
            return False
        self.factions[a].war.add(b)
        self.factions[b].war.add(a)
        self.factions[a].war_start[b] = self.time
        self.factions[b].war_start[a] = self.time
        self.factions[a].last_war = self.time
        self.factions[a].relations[b] = min(-40, self.factions[a].relations[b] - 30)
        self.factions[b].relations[a] = min(-40, self.factions[b].relations[a] - 30)
        for x, y in ((a, b), (b, a)):
            self.factions[x].wars.append({"fid": y, "start": self.time, "end": None,
                                          "losses": 0.0, "kills": 0.0})
            if len(self.factions[x].wars) > WAR_LIST_LIMIT:
                self.factions[x].wars.pop(0)
        if not quiet:
            self.log_msg(f"«{self.factions[a].name}» объявляет войну «{self.factions[b].name}»!")
        # СОЮЗНЫЙ ДОЛГ: на союзника напали — он обязательно вступает в войну
        # против агрессора. Нападавший на союзника знал, на что идёт.
        defender_allies = [x for x in self.factions[b].alliance
                           if x != a and x in self.factions
                           and self.factions[x].alive]
        for x in defender_allies:
            if not self.at_war(x, a):
                self.factions[x].war.add(a)
                self.factions[a].war.add(x)
                self.factions[x].war_start[a] = self.time
                self.factions[a].war_start[x] = self.time
                self.factions[x].last_war = self.time
                for u, v in ((x, a), (a, x)):
                    self.factions[u].wars.append({"fid": v, "start": self.time,
                                                  "end": None, "losses": 0.0,
                                                  "kills": 0.0})
                self.factions[x].relations[a] = min(-40, self.factions[x].relations[a] - 30)
                self.factions[a].relations[x] = min(-40, self.factions[a].relations[x] - 30)
                self.log_msg(f"СОЮЗНЫЙ ДОЛГ: «{self.factions[x].name}» вступает "
                             f"в войну против «{self.factions[a].name}»!")
        return True

    def make_peace(self, a, b):
        self.factions[a].war.discard(b)
        self.factions[b].war.discard(a)
        self.factions[a].war_start.pop(b, None)
        self.factions[b].war_start.pop(a, None)
        for x, y in ((a, b), (b, a)):
            for w in self.factions[x].wars:
                if w["fid"] == y and w["end"] is None:
                    w["end"] = self.time
        self.factions[a].relations[b] = min(30, self.factions[a].relations[b] + 25)
        self.factions[b].relations[a] = min(30, self.factions[b].relations[a] + 25)
        self.log_msg(f"Мир между «{self.factions[a].name}» и «{self.factions[b].name}».")

    def make_alliance(self, a, b):
        self.factions[a].war.discard(b)
        self.factions[b].war.discard(a)
        self.factions[a].alliance.add(b)
        self.factions[b].alliance.add(a)
        self.factions[a].nap.pop(b, None)
        self.factions[b].nap.pop(a, None)
        self.factions[a].relations[b] = max(45, self.factions[a].relations[b] + 30)
        self.factions[b].relations[a] = max(45, self.factions[b].relations[a] + 30)
        self.log_msg(f"Союз «{self.factions[a].name}» и «{self.factions[b].name}»!")

    def break_alliance(self, a, b, quiet=False):
        self.factions[a].alliance.discard(b)
        self.factions[b].alliance.discard(a)
        self.factions[a].relations[b] = max(-100, self.factions[a].relations[b] - 25)
        self.factions[b].relations[a] = max(-100, self.factions[b].relations[a] - 25)
        if not quiet:
            self.log_msg(f"Союз «{self.factions[a].name}» и «{self.factions[b].name}» расторгнут.")

    def sign_nap(self, a, b):
        until = self.time + NAP_DURATION
        self.factions[a].nap[b] = until
        self.factions[b].nap[a] = until
        self.factions[a].relations[b] = min(100, self.factions[a].relations[b] + 12)
        self.factions[b].relations[a] = min(100, self.factions[b].relations[a] + 12)
        self.log_msg(f"Пакт о ненападении: «{self.factions[a].name}» и «{self.factions[b].name}».")

    def break_nap(self, a, b, quiet=False):
        self.factions[a].nap.pop(b, None)
        self.factions[b].nap.pop(a, None)
        self.factions[a].relations[b] = max(-100, self.factions[a].relations[b] - 22)
        self.factions[b].relations[a] = max(-100, self.factions[b].relations[a] - 22)
        if not quiet:
            self.log_msg(f"«{self.factions[a].name}» разорвал пакт с «{self.factions[b].name}».")

    def trade_pact(self, a, b):
        self.factions[a].trade.add(b)
        self.factions[b].trade.add(a)
        self.factions[a].relations[b] = min(100, self.factions[a].relations[b] + 12)
        self.factions[b].relations[a] = min(100, self.factions[b].relations[a] + 12)
        self.log_msg(f"Торговое соглашение: «{self.factions[a].name}» и «{self.factions[b].name}».")

    def gift(self, a, b, amount=60):
        if self.factions[a].money < amount:
            return False
        self.factions[a].money -= amount
        self.factions[b].money += amount
        self.factions[a].relations[b] = min(100, self.factions[a].relations[b] + 15)
        self.factions[b].relations[a] = min(100, self.factions[b].relations[a] + 20)
        self.log_msg(f"«{self.factions[a].name}» дарит {amount} «{self.factions[b].name}».")
        return True

    # -------- предложения (принять / отклонить) --------
    def propose(self, kind, a, b, amount=0):
        if a == b or a == NEUTRAL or b == NEUTRAL:
            return
        offer = {"kind": kind, "from": a, "to": b, "amount": amount, "time": self.time}
        if b == self.player:
            if any(o["from"] == a for o in self.pending_offers):
                return
            self.pending_offers.append(offer)
            self.paused = True
            self.log_msg(f"«{self.factions[a].name}» предлагает: {KIND_NAMES[kind]}.")
        else:
            self.resolve_offer(offer, self.ai_accepts(offer))

    def ai_accepts(self, offer):
        kind = offer["kind"]
        a, b = offer["from"], offer["to"]
        fa, fb = self.factions[a], self.factions[b]
        rel = fb.relations.get(a, 0)
        if kind == "gift":
            return True
        if kind == "alliance":
            return rel >= 35 and not self.at_war(a, b) and not self.allied(a, b)
        if kind == "nap":
            return rel >= -30
        if kind == "trade":
            return rel >= 0
        if kind == "peace":
            if not self.at_war(a, b):
                return False
            war_len = fb.war_start.get(a, self.time)
            return (fb.total_troops < fa.total_troops * 2.2
                    or self.time - war_len > WAR_WEARINESS_TIME)
        if kind == "demand":
            # уступает тот, кто слабее требующего — иначе война дороже дани
            return fa.total_troops > fb.total_troops * 1.2
        return False

    def resolve_offer(self, offer, accepted):
        kind = offer["kind"]
        a, b, amt = offer["from"], offer["to"], offer["amount"]
        fa, fb = self.factions[a], self.factions[b]
        an, bn = fa.name, fb.name
        if accepted:
            if kind == "alliance":
                self.make_alliance(a, b)
            elif kind == "nap":
                self.sign_nap(a, b)
            elif kind == "trade":
                self.trade_pact(a, b)
            elif kind == "peace":
                self.make_peace(a, b)
            elif kind == "gift":
                amt = amt or 60
                if fa.money >= amt:
                    fa.money -= amt
                    fb.money += amt
                fa.relations[b] = min(100, fa.relations[b] + 15)
                fb.relations[a] = min(100, fb.relations[a] + 20)
                self.log_msg(f"«{an}» → дар {amt} «{bn}».")
            elif kind == "demand":
                pay = min(amt, fb.money)
                fb.money -= pay
                fa.money += pay
                fb.relations[a] = max(-100, fb.relations[a] - 8)
                self.log_msg(f"«{bn}» уступил {int(pay)} в пользу «{an}».")
        else:
            pen = {"alliance": -12, "nap": -6, "trade": -8, "peace": -15,
                   "gift": -5, "demand": -18}.get(kind, -5)
            fa.relations[b] = max(-100, fa.relations[b] + pen)
            fb.relations[a] = max(-100, fb.relations[a] + pen)
            self.log_msg(f"«{bn}» отклонил(а): {KIND_NAMES[kind]} от «{an}».")
            if kind == "demand" and b == self.player:
                if fa.total_troops > fb.total_troops * 1.6 and self.rng.random() < 0.35:
                    self.declare_war(a, b)
                    self.log_msg(f"«{an}» объявляет войну в ответ на отказ!")

    def player_propose(self, kind, target_fid):
        if self.player is None:
            return
        if kind == "gift":
            self.gift(self.player, target_fid)
            return
        if kind == "war":
            self.declare_war(self.player, target_fid)
            return
        if kind == "break_alliance":
            self.break_alliance(self.player, target_fid)
            return
        if kind == "break_nap":
            self.break_nap(self.player, target_fid)
            return
        self.propose(kind, self.player, target_fid)

    # -------- бой / сопротивление / экономика --------
    def doctrine_of(self, fid):
        f = self.factions.get(fid)
        return DOCTRINES[f.doctrine if f else 1]

    def matchup_bonus(self, my_doctrine, enemy_doctrine):
        """+DOCTRINE_COUNTER, если моя доктрина контрит доктрину врага."""
        return DOCTRINE_COUNTER if my_doctrine["beats"] == enemy_doctrine["key"] else 0.0

    def attack_rate(self, fid, enemy_fid=None, in_field=False):
        f = self.factions.get(fid, self.neutral)
        doc = DOCTRINES[f.doctrine] if f is not self.neutral else DOCTRINES[1]
        atk = 1.0 + ATK_TECH * f.tech["atk"] + MOR_TECH * f.tech["mor"]
        atk += doc["atk"] - 1.0
        atk += self.ideo_of(fid).get("atk", 0.0)
        if in_field:
            atk += 0.15 if doc["key"] == "maneuver" else 0.0
        # контр-бонус против доктрины врага
        if enemy_fid is not None:
            enemy = self.factions.get(enemy_fid)
            if enemy is not None:
                atk += self.matchup_bonus(doc, DOCTRINES[enemy.doctrine])
        # технологии
        atk += f.tech2.get("arty", 0) * TECH_TRACKS[0]["atk_region"]
        atk += f.morale / 100.0 * 0.3
        if f is not self.neutral and f.tech2.get("med"):
            atk += 0.03 * f.tech2["med"]
        return atk

    def defense_rate(self, fid, region, enemy_fid=None):
        f = self.factions.get(fid, self.neutral)
        doc = DOCTRINES[f.doctrine] if f is not self.neutral else DOCTRINES[1]
        de = 1.0 + DEF_TECH * f.tech["def"] + MOR_TECH * f.tech["mor"]
        de += doc["def"] - 1.0
        de += self.ideo_of(fid).get("def", 0.0)
        if enemy_fid is not None:
            enemy = self.factions.get(enemy_fid)
            if enemy is not None:
                # враг контрит меня — его доктрина пробивает мою оборону
                de -= self.matchup_bonus(DOCTRINES[enemy.doctrine], doc) * 0.5
        de += f.tech2.get("med", 0) * 0.02
        de += f.morale / 100.0 * 0.3 + region.terrain[1]
        return de

    def doctrine_change_cost(self, fid):
        return DOCTRINE_COST + 40 * sum(1 for w in self.factions[fid].wars if w["end"] is None)

    def set_doctrine(self, fid, idx):
        """Смена доктрины: стоит денег и слегка подрывает мораль."""
        f = self.factions[fid]
        if idx == f.doctrine or not 0 <= idx < len(DOCTRINES):
            return False
        cost = self.doctrine_change_cost(fid)
        if f.money < cost:
            return False
        f.money -= cost
        f.doctrine = idx
        f.morale = max(20.0, f.morale - 8.0)
        self.log_msg(f"{f.name}: армия переходит к доктрине «{DOCTRINES[idx]['name']}»")
        return True

    def tech2_cost(self, fid, key):
        f = self.factions[fid]
        track = next(t for t in TECH_TRACKS if t["key"] == key)
        lvl = f.tech2.get(key, 0)
        return int(track["cost"] * (1.0 + 0.9 * lvl) * self.ideo_of(fid).get("tech_cost", 1.0))

    def develop_tech2(self, fid, key):
        """Изучить/улучшить одну из новых технологий."""
        f = self.factions[fid]
        track = next((t for t in TECH_TRACKS if t["key"] == key), None)
        if track is None or f.tech2.get(key, 0) >= TECH_MAX:
            return False
        cost = self.tech2_cost(fid, key)
        if f.money < cost:
            return False
        f.money -= cost
        f.tech2[key] = f.tech2.get(key, 0) + 1
        self.log_msg(f"{f.name}: технология «{track['name']}» → ур.{f.tech2[key]}")
        return True

    def note_casualties(self, fid, loss, enemy_fid):
        """Учёт потерь стороны: сумма, запись в текущую войну, счёт убийств."""
        if loss <= 0 or fid == NEUTRAL:
            return
        f = self.factions[fid]
        f.losses += loss
        if enemy_fid != NEUTRAL and enemy_fid in self.factions:
            self.factions[enemy_fid].kills += loss
        war = next((w for w in f.wars if w["fid"] == enemy_fid and w["end"] is None), None)
        if war is None:
            war = next((w for w in f.wars if w["end"] is None), None)
        if war is not None:
            war["losses"] += loss

    def update_combat(self, dt):
        for r in self.regions:
            fids = [x for x, v in r.forces.items() if v > 0.5]
            if len(fids) < 2:
                continue
            losses = {}
            for i in range(len(fids)):
                for j in range(i + 1, len(fids)):
                    a, b = fids[i], fids[j]
                    if a != NEUTRAL and b != NEUTRAL and not self.at_war(a, b):
                        continue
                    fa = r.forces[a]
                    fb = r.forces[b]
                    ra = (self.defense_rate(a, r, enemy_fid=b) if a == r.owner
                          else self.attack_rate(a, enemy_fid=b))
                    rb = (self.defense_rate(b, r, enemy_fid=a) if b == r.owner
                          else self.attack_rate(b, enemy_fid=a))
                    losses[a] = losses.get(a, 0.0) + fb * rb * COMBAT_K * dt
                    losses[b] = losses.get(b, 0.0) + fa * ra * COMBAT_K * dt
                    r.flash = 1.0
            for x, d in losses.items():
                r.forces[x] = max(0.0, r.forces.get(x, 0.0) - d)
            # учёт потерь: главная причина потерь a — сильнейший враг в регионе
            for a in losses:
                foes = [(fb, b) for b, fb in
                        ((x, r.forces.get(x, 0.0)) for x in fids if x != a) if fb > 0.5]
                if foes:
                    _, main = max(foes)
                    self.note_casualties(a, losses[a], main)
            self.resolve_ownership(r)

    def resolve_ownership(self, r):
        present = {x: v for x, v in r.forces.items() if v > 0.5}
        r.forces = present
        if r.owner_forces() > 0.5:
            return
        candidates = [(v, x) for x, v in present.items() if x != r.owner]
        if not candidates:
            return
        v, new_owner = max(candidates)
        old = r.owner
        r.owner = new_owner
        r.entry = {}
        if new_owner != NEUTRAL:
            self.factions[new_owner].morale = min(150.0, self.factions[new_owner].morale + 4)
        if old != NEUTRAL:
            self.factions[old].morale = max(20.0, self.factions[old].morale - 5)
        who = "независимые" if new_owner == NEUTRAL else f"«{self.factions[new_owner].name}»"
        self.log_msg(f"({r.x},{r.y}) захвачен: {who}")
        r.capital_of = None if new_owner != r.capital_of else r.capital_of
        col = self.factions[new_owner].color if new_owner != NEUTRAL else NEUTRAL_COL
        self.captures.append({"rid": r.rid, "fid": new_owner, "col": col, "t": 0.0})

    def faction_income(self, fid):
        f = self.factions[fid]
        base = sum(r.income for r in f.regions)
        trade_bonus = 1.0
        for other in f.trade:
            if other in self.factions:
                trade_bonus += TRADE_INCOME
        return base * trade_bonus * CONSCRIPT[f.conscript]["income"] * f.econ_mult \
            * self.ideo_of(fid).get("econ", 1.0)

    def faction_upkeep(self, fid):
        return self.factions[fid].total_troops / 1000.0 * UPKEEP_PER_1K

    def faction_net(self, fid):
        return self.faction_income(fid) - self.faction_upkeep(fid)

    def update_economy(self, dt):
        for f in self.factions.values():
            if not f.alive:
                continue
            regs = f.regions
            info = CONSCRIPT[f.conscript]
            pop = sum(r.pop * (1.0 + MANPOWER_DEV_BONUS * r.dev) for r in regs)
            f.manpower_max = max(4000.0, pop * MANPOWER_MAX_FRAC * info["max"])
            f.manpower = min(f.manpower_max,
                             f.manpower + pop * MANPOWER_RATE * info["rate"] * dt)
            gross = self.faction_income(f.fid)
            upkeep = self.faction_upkeep(f.fid)
            f.money = max(0.0, f.money + (gross - upkeep) * dt)
            if f.money <= 0.01 and gross < upkeep:
                f.morale = max(20.0, f.morale - 0.4 * dt)
            # в мирное время morale медленно возвращается к спокойному уровню
            elif f.morale < 100.0:
                f.morale = min(100.0, f.morale + 0.7 * dt)
            else:
                f.morale = max(100.0, f.morale - 0.4 * dt)

    def update_moves(self, dt):
        # 1) встречные бои: враждебные армии, идущие навстречу по одному ребру,
        #    останавливаются на середине и сражаются (никто не проходит сквозь).
        self.field_clashes = []
        n = len(self.moves)
        for i in range(n):
            m1 = self.moves[i]
            if m1.amount <= 0:
                continue
            for j in range(i + 1, n):
                m2 = self.moves[j]
                if m2.amount <= 0:
                    continue
                if m1.src != m2.dst or m1.dst != m2.src:
                    continue
                if m1.fid == m2.fid:
                    continue
                if not self.opposing(m1.fid, m2.fid) or self.allied(m1.fid, m2.fid):
                    continue
                if m1.progress + m2.progress < 1.0:
                    continue
                self.field_clash(m1, m2, dt)
        # 2) перехват: враждебные армии, чьи пути пересекаются (общая цель или
        #    цель одной = источник другой). Слабый отряд уничтожается в поле,
        #    сильный отступает домой с потерями; перехватчик идёт дальше.
        for i in range(n):
            m1 = self.moves[i]
            if m1.amount <= 0 or m1.frozen or m1.retreat:
                continue
            for j in range(n):
                if i == j:
                    continue
                m2 = self.moves[j]
                if m2.amount <= 0 or m2.fid == m1.fid or m2.retreat:
                    continue
                if not self.opposing(m1.fid, m2.fid):
                    continue
                crossing = (m1.dst == m2.dst
                            or (m1.dst == m2.src and m2.src != m1.src))
                if not crossing:
                    continue
                # перехватывает тот, кто ближе к точке пересечения
                ambusher, victim = (m1, m2) if m1.progress >= m2.progress else (m2, m1)
                if victim.frozen or victim.retreat:
                    continue
                self.intercept_move(victim, ambusher)
        # 3) движение уцелевших
        done = []
        for m in self.moves:
            if m.frozen:
                if m.amount < FIELD_MIN:
                    done.append(m)
                continue
            m.t += dt
            if m.retreat:
                # отступление: армия возвращается в исходный регион
                m.t += dt * 2.0            # бегство вдвое быстрее
                if m.t >= m.duration:
                    src = self.regions[m.src]
                    src.forces[m.fid] = src.forces.get(m.fid, 0.0) + m.amount
                    done.append(m)
                continue
            if m.t >= m.duration:
                dst = self.regions[m.dst]
                src = self.regions[m.src]
                dst.forces[m.fid] = dst.forces.get(m.fid, 0.0) + m.amount
                if dst.owner != m.fid:
                    dst.entry[m.fid] = (src.x - dst.x, src.y - dst.y)
                self.resolve_ownership(dst)
                done.append(m)
        for m in done:
            self.moves.remove(m)

    def intercept_move(self, victim, ambusher):
        """Перехват на марше: слабого уничтожают в поле, сильный отступает.

        Отношение сил решает исход: victim < 60% от ambushера — разгром,
        иначе отступление домой с потерями (примерно треть отряда)."""
        ratio = victim.amount / max(1.0, ambusher.amount)
        vfid, afid = victim.fid, ambusher.fid
        va = victim.amount
        v_rate = self.attack_rate(vfid, enemy_fid=afid, in_field=True)
        a_rate = self.attack_rate(afid, enemy_fid=vfid, in_field=True)
        if ratio < 0.6:
            # разгромлен в поле
            victim.amount = 0.0
            self.note_casualties(vfid, va, afid)
            self.log_msg(f"Армия {self.fname(vfid)} разгромлена на марше "
                         f"у провинции ({self.regions[victim.dst].x},{self.regions[victim.dst].y})")
        else:
            # вынужденное отступление: потери от огня на марше, остатки домой
            edge = min(1.0, 0.15 + 0.35 * (1.0 - min(1.0, ratio)) * a_rate / max(0.1, v_rate))
            lost = int(va * min(0.5, edge))
            victim.amount = max(0.0, va - lost)
            self.note_casualties(vfid, lost, afid)
            if victim.amount < FIELD_MIN:
                victim.amount = 0.0
                self.log_msg(f"Отступающая армия {self.fname(vfid)} добита на марше")
            else:
                # разворот: источником становится прежняя цель
                victim.src, victim.dst = victim.dst, victim.src
                victim.t = 0.0
                victim.retreat = True
                victim.duration = max(0.4, victim.duration)
                self.log_msg(f"Армия {self.fname(vfid)} перехвачена и отступает "
                             f"(потери {fmt(lost)})")
        if victim.amount <= 0.0:
            victim.frozen = False
            victim.retreat = False

    def field_clash(self, m1, m2, dt):
        """Встречный бой в поле между двумя движущимися армиями."""
        new = not m1.frozen
        m1.t = m1.duration * 0.5
        m2.t = m2.duration * 0.5
        m1.frozen = True
        m2.frozen = True
        r1 = self.attack_rate(m1.fid, enemy_fid=m2.fid, in_field=True)
        r2 = self.attack_rate(m2.fid, enemy_fid=m1.fid, in_field=True)
        a1, a2 = m1.amount, m2.amount
        m1.amount = max(0.0, a1 - a2 * r2 * COMBAT_K * dt)
        m2.amount = max(0.0, a2 - a1 * r1 * COMBAT_K * dt)
        self.note_casualties(m1.fid, a1 - m1.amount, m2.fid)
        self.note_casualties(m2.fid, a2 - m2.amount, m1.fid)
        self.field_clashes.append((m1, m2))
        if new:
            self.log_msg(f"Встречный бой: {self.fname(m1.fid)} × {self.fname(m2.fid)}")
        if m1.amount < FIELD_MIN <= m2.amount:
            m2.frozen = False
        elif m2.amount < FIELD_MIN <= m1.amount:
            m1.frozen = False

    def fname(self, fid):
        if fid == NEUTRAL:
            return "независимые"
        return self.factions[fid].name

    def attack_dir(self, r, fid):
        """Направление (dx,dy), откуда идёт атака fid на регион r."""
        best, best_f = None, -1.0
        for n in self.neighbors(r):
            if n.owner == fid and n.owner_forces() > best_f:
                best_f = n.owner_forces()
                best = (n.x - r.x, n.y - r.y)
        if best:
            return best
        d = r.entry.get(fid)
        if d and (d[0] or d[1]):
            return d
        for n in self.neighbors(r):
            if fid in n.forces:
                return (n.x - r.x, n.y - r.y)
        return (-1, 0)

    # -------- ИИ --------
    def update_ai(self, dt):
        for f in self.factions.values():
            if f.is_player or not f.alive:
                continue
            f.ai_timer -= dt
            f.diplo_timer -= dt
            if f.ai_timer <= 0:
                f.ai_timer = AI_MIL_TIMER
                self.ai_military(f)
            if f.diplo_timer <= 0:
                f.diplo_timer = AI_DIPLO_TIMER
                self.ai_diplomacy(f)

    def ai_military(self, f):
        if not f.regions:
            return
        p = f.personality or PERSONALITIES[1]
        border = [r for r in f.regions if any(n.owner != f.fid for n in self.neighbors(r))]
        if border and f.money >= 150 and f.manpower >= MANPOWER_PER_RECRUIT:
            target = min(border, key=lambda r: r.forces.get(f.fid, 0))
            self.recruit(target.rid, f.fid)
        # развитие экономики и армии — в меру характера
        if f.money >= ECON_DEV_COST * 3 and self.rng.random() < 0.35 * p["econ"]:
            owned = [r for r in f.regions if r.dev < MAX_ECON_DEV]
            if owned:
                r = max(owned, key=lambda x: x.base_income)
                self.develop_econ(r.rid, f.fid)
        if f.money >= DEV_BASE_COST * 4 and self.rng.random() < 0.45 * p["tech"]:
            self.develop_tech(f.fid, self.rng.choice(["atk", "atk", "atk", "def", "log", "mor"]))
        # атаки: ИИ охотно бьёт по соседним провинциям, при силах можно бить
        # в несколько сторон из одного региона; против игрока — осторожнее
        for r in sorted(f.regions, key=lambda x: -x.forces.get(f.fid, 0)):
            avail = r.forces.get(f.fid, 0)
            if avail < 5000:
                continue
            for n in self.neighbors(r):
                if n.owner == f.fid or self.allied(f.fid, n.owner):
                    continue
                if n.owner == NEUTRAL:
                    if avail < n.forces.get(NEUTRAL, 0.0) * 0.92 * p["neutral"]:
                        continue
                else:
                    if not self.at_war(f.fid, n.owner) or self.has_nap(f.fid, n.owner):
                        continue
                    need = (0.92 + (1.0 - f.aggro) * 0.30) * p["need"]
                    if n.owner == self.player:
                        # против игрока нужен заметно больший перевес,
                        # и атака решается не каждый момент
                        need += 0.5
                        if self.rng.random() < 0.35:
                            continue
                    if avail < n.forces.get(n.owner, 0.0) * need:
                        continue
                # не оголяем регион совсем: чем сильнее вражеские соседи, тем меньше бросаем
                danger = sum(nb.forces.get(nb.owner, 0.0) for nb in self.neighbors(r)
                             if nb.owner != f.fid and nb.owner != NEUTRAL
                             and self.opposing(f.fid, nb.owner))
                frac = 0.75 - 0.35 * min(1.0, danger / max(1.0, avail))
                if frac < 0.25:
                    continue
                self.send_move(r.rid, n.rid, f.fid, frac)
                avail = r.forces.get(f.fid, 0)
                if avail < 4000:
                    break

    def can_offer_player(self):
        return (self.player is not None
                and self.time - self.player_offer_time > 60
                and not self.pending_offers)

    def ai_diplomacy(self, f):
        others = [g for g in self.factions.values() if g.fid != f.fid and g.alive]
        if not others:
            return
        p = f.personality or PERSONALITIES[1]
        my = f.total_troops
        # 1) мир, если война затянулась или мы слабее
        for gid in list(f.war):
            g = self.factions.get(gid)
            if not g or not g.alive:
                continue
            long_war = self.time - f.war_start.get(gid, self.time) > WAR_WEARINESS_TIME
            if my < g.total_troops * 0.6 or long_war:
                if g.fid == self.player:
                    if self.can_offer_player():
                        self.player_offer_time = self.time
                        self.propose("peace", f.fid, g.fid)
                else:
                    self.make_peace(f.fid, gid)
                break
        # 2) дружественные договоры (к игроку — не чаще раза в минуту)
        for g in others:
            if self.at_war(f.fid, g.fid) or self.allied(f.fid, g.fid):
                continue
            to_player = (g.fid == self.player)
            if to_player and not self.can_offer_player():
                continue
            rel = f.relations.get(g.fid, 0)
            p_mul = 0.5 if to_player else 1.0
            kind = None
            if rel > 55 and not self.has_nap(f.fid, g.fid) and self.rng.random() < 0.2 * p_mul * p["diplo"]:
                kind = "alliance"
            elif rel > 5 and not self.has_nap(f.fid, g.fid) and self.rng.random() < 0.2 * p_mul * p["diplo"]:
                kind = "nap"
            elif rel > 10 and not self.has_trade(f.fid, g.fid) and self.rng.random() < 0.15 * p_mul * p["diplo"]:
                kind = "trade"
            if kind:
                if to_player:
                    self.player_offer_time = self.time
                self.propose(kind, f.fid, g.fid)
                break
        # 3) объявление войны: между ИИ часто, против игрока — редко.
        #    Особый случай — ПРЕДАТЕЛЬСТВО: при большом перевесе или истощении
        #    союзника войной союзник сам становится целью (союзники не входят
        #    в обычные кандидаты). Предательство рушит репутацию у всех.
        if self.time > GRACE_PERIOD and self.rng.random() < f.aggro * 0.35:
            allies = [g for g in others if self.allied(f.fid, g.fid)]
            traitor_pool = [
                g for g in allies
                if my > g.total_troops * (1.02 + (1.0 - f.aggro) * 0.25 + 0.25)
                or (any(self.at_war(g.fid, gid) and
                        self.factions[gid].total_troops > g.total_troops * 1.1
                        for gid in g.war if gid != f.fid and gid in self.factions)
                    and my > g.total_troops * 1.15)]
            if traitor_pool and self.rng.random() < f.aggro * 0.5:
                weak = min(traitor_pool, key=lambda g: g.total_troops)
                self.break_alliance(f.fid, weak.fid)
                for g in others:          # «предатель!» — всем минус репутация
                    if g.fid not in (f.fid, weak.fid):
                        f.relations[g.fid] = f.relations.get(g.fid, 0) - 18
                        g.relations[f.fid] = g.relations.get(f.fid, 0) - 30
                self.log_msg(f"ПРЕДАТЕЛЬСТВО: «{f.name}» разрывает союз и нападает!")
                if self.has_nap(f.fid, weak.fid):
                    self.break_nap(f.fid, weak.fid)
                self.declare_war(f.fid, weak.fid)
            else:
                cand = [g for g in others
                        if not self.at_war(f.fid, g.fid)
                        and f.relations.get(g.fid, 0) < 5]
                cand = [g for g in cand
                        if g.fid != self.player or self.rng.random() < 0.3]
                if cand:
                    weak = min(cand, key=lambda g: g.total_troops)
                    # между ИИ порог невысок: фракции растут примерно одинаково,
                    # и при более strict пороге войны почти не начинаются.
                    # Против игрока — только с явным перевесом и редко.
                    if weak.fid == self.player:
                        need = 1.65 + (1.0 - f.aggro) * 0.6
                        cooldown = 90
                    else:
                        need = 1.02 + (1.0 - f.aggro) * 0.25
                        cooldown = 35
                    if (my > weak.total_troops * need
                            and self.time - f.last_war > cooldown):
                        if self.has_nap(f.fid, weak.fid):
                            self.break_nap(f.fid, weak.fid)   # пакты тоже рвутся
                        self.declare_war(f.fid, weak.fid)

        # 5) ПОМОЩЬ СОЮЗНИКАМ — два вида: Золото и Люди.
        # Истощённому войной союзнику переводим золото и людские резервы.
        allies = [self.factions[gid] for gid in f.alliance
                  if gid in self.factions and self.factions[gid].alive]
        for al in allies:
            enemies_of_ally = [gid for gid in al.war
                               if gid in self.factions and gid != f.fid]
            if not enemies_of_ally:
                continue
            ally_struggling = any(
                self.factions[gid].total_troops > al.total_troops * 0.9
                for gid in enemies_of_ally)
            if not ally_struggling:
                continue
            if self.rng.random() < 0.25 * p["diplo"]:
                # ЗОЛОТО: четверть казны
                gold = int(min(f.money * 0.25, 80 + f.total_troops / 500))
                if gold < 20:
                    gold = 0
                # ЛЮДИ: 15% наших людских резервов — пополнение союзнику
                men = int(f.manpower * 0.15)
                if men < 500:
                    men = 0
                if gold:
                    f.money -= gold
                    al.money += gold
                if men:
                    f.manpower -= men
                    al.manpower = min(al.manpower_max, al.manpower + men)
                if gold or men:
                    al.relations[f.fid] = min(100, al.relations.get(f.fid, 0) + 6)
                    parts = []
                    if gold:
                        parts.append(f"золото {gold}")
                    if men:
                        parts.append(f"люди {fmt(men)}")
                    self.log_msg(f"{f.name} → помощь союзнику «{al.name}»: "
                                 + ", ".join(parts))
                break
        # 4) требование дани у игрока (можно отклонить), не чаще раза в минуту
        if (self.can_offer_player()
                and self.time > GRACE_PERIOD
                and not self.at_war(f.fid, self.player)
                and not self.has_nap(f.fid, self.player)
                and not self.allied(f.fid, self.player)):
            pf = self.factions[self.player]
            if my > pf.total_troops * 1.15 and f.relations.get(self.player, 0) < 25 and self.rng.random() < 0.07:
                amount = int(50 + my / 4000)
                self.player_offer_time = self.time
                self.propose("demand", f.fid, self.player, amount=min(amount, 200))

    # -------- шаг --------
    def tick(self, dt):
        if self.winner or self.choosing:
            return
        self.time += dt
        self.update_moves(dt)
        self.update_combat(dt)
        self.update_economy(dt)
        self.update_ai(dt)
        for r in self.regions:
            r.flash = max(0.0, r.flash - dt * 2.2)
        for cap in self.captures:
            cap["t"] += dt / 0.9
        self.captures = [c for c in self.captures if c["t"] < 1.0]
        self.hist_timer += dt
        if self.hist_timer >= HISTORY_INTERVAL:
            self.hist_timer -= HISTORY_INTERVAL
            self.record_snapshot()
        self.check_winner()
        if self.winner:
            self.record_snapshot()

    def check_winner(self):
        alive = [f for f in self.factions.values() if f.alive]
        for f in alive:
            if not f.regions and f.total_troops < 1:
                f.alive = False
        alive = [f for f in self.factions.values() if f.alive]
        if self.player is not None:
            if not self.factions[self.player].alive:
                self.winner = "ПОРАЖЕНИЕ"
                self.log_msg("Ваша фракция уничтожена.")
            elif len(alive) == 1 and alive[0].fid == self.player:
                self.winner = "ПОБЕДА!"
                self.log_msg("Вы объединили регион!")
        elif len(alive) <= 1:
            if self.observer and alive:
                self.winner = f"ИГРА ОКОНЧЕНА · победил «{alive[0].name}»"
            else:
                self.winner = "ИГРА ОКОНЧЕНА"
        if self.winner and not getattr(self, "replay_saved", False) and self.time > 5.0:
            import replays
            p = replays.save_replay(self)
            self.replay_saved = True
            if p:
                self.log_msg("Повтор партии сохранён в replays/.")


# ============================ ОТРИСОВКА ============================
W, H = 1280, 760
TOPBAR_H = 48
TILE = 74
MAP_X, MAP_Y = 16, 60
MAP_W = MAP_H = GRID * TILE
PANEL_X = MAP_X + MAP_W + 20
PANEL_W = W - PANEL_X - 16

BG = (17, 19, 24)
PANEL = (26, 29, 36)
CARD = (35, 39, 48)
CARD2 = (44, 49, 60)
BORDER = (60, 66, 80)
TEXT = (228, 232, 240)
MUTED = (150, 156, 168)
GRID_COL = (15, 16, 20)
NEUTRAL_COL = (120, 124, 132)
ACCENT = (74, 144, 217)
GOOD = (96, 210, 140)
WARN = (235, 190, 90)
BAD = (226, 96, 80)


def R(x, y, w, h):
    return pygame.Rect(x, y, w, h)


def fmt(n):
    return f"{int(n):,}".replace(",", " ")


def front_troops_text(v):
    """Компактная численность для подписи фронта: 12 345 / 188к / 2.4M."""
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 100_000:
        return f"{round(v / 1000)}к"
    return fmt(v)


def faction_color(game, fid):
    if fid == NEUTRAL:
        return NEUTRAL_COL
    return game.factions[fid].color


def mix(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def troop_k(troops):
    """Число войск в тысячах: 35 при 35 000."""
    if troops <= 0:
        return "0"
    k = troops / 1000.0
    if k < 1.0:
        return "<1"
    return str(int(round(k)))


def make_flag(f, w=30, h=20):
    """Процедурный флаг страны: стиль из FLAG_STYLES, цвета — цвет фракции.

    Кэшируется в f.flag (у каждого размера свой — храним dict по размеру)."""
    key = (w, h)
    cache = getattr(f, "_flag_cache", None)
    if cache is None:
        cache = f._flag_cache = {}
    if key in cache:
        return cache[key]
    col = f.color
    dark = mix(col, (10, 10, 16), 0.62)
    light = mix(col, (255, 255, 255), 0.62)
    surf = pygame.Surface((w, h))
    style = f.flag_style
    if style == "stripes":
        for i, c in enumerate((dark, col, light)):
            pygame.draw.rect(surf, c, (0, i * h // 3, w, h // 3 + 1))
    elif style == "cross":
        surf.fill(light)
        pygame.draw.rect(surf, col, (0, h // 2 - 3, w, 6))
        pygame.draw.rect(surf, col, (w // 3 - 3, 0, 6, h))
        pygame.draw.rect(surf, dark, (w // 3 - 1, h // 2 - 1, 2, 2))
    elif style == "canton":
        surf.fill(col)
        pygame.draw.rect(surf, dark, (0, 0, w // 2, h // 2))
        for i in range(3):
            pygame.draw.rect(surf, light, (0, (h * 2 // 3) + i * 3, w, 2))
    elif style == "diagonal":
        surf.fill(col)
        pygame.draw.polygon(surf, dark, [(0, 0), (w, 0), (0, h)])
        pygame.draw.polygon(surf, light, [(w, h), (w, h // 3), (w // 3, h)])
    else:  # border
        surf.fill(col)
        pygame.draw.rect(surf, dark, (0, 0, w, h), 4)
        pygame.draw.circle(surf, light, (w // 2, h // 2), min(w, h) // 5)
        pygame.draw.circle(surf, dark, (w // 2, h // 2), min(w, h) // 5, 1)
    # тёмная рамка вокруг флага
    pygame.draw.rect(surf, (18, 20, 26), (0, 0, w, h), 1)
    cache[key] = surf
    return surf


def draw_flag(screen, x, y, size, f):
    """Флаг страны f (Faction) с высотой size; фавтическая ширина 1.5×."""
    if f is None or f == NEUTRAL or not hasattr(f, "flag_style"):
        # старый флажок-«треугольник» для прочих случаев
        col = f.color if f is not None and hasattr(f, "color") else (120, 124, 132)
        pygame.draw.line(screen, (228, 231, 238), (x, y), (x, y + size + 2), 2)
        pts = [(x + 2, y), (x + size, y + size * 0.30), (x + 2, y + size * 0.60)]
        pygame.draw.polygon(screen, col, pts)
        return
    img = make_flag(f, int(size * 1.5), size)
    screen.blit(img, (x, y))


def counter_rect(font, cx, cy, troops, big=False):
    text = troop_k(troops)
    tw, th = font.size(text)
    pad, flag_w = 6, 12
    h = 26 if big else 22
    w = pad + flag_w + 4 + tw + pad
    return R(int(cx - w / 2), int(cy - h / 2), w, h)


def draw_counter_rect(screen, font, rect, color, troops, dim=False):
    pygame.draw.rect(screen, (18, 20, 26), rect, border_radius=5)
    pygame.draw.rect(screen, mix(color, (0, 0, 0), 0.35) if dim else color,
                     rect, width=2, border_radius=5)
    h = rect.h
    fx = rect.x + 6
    fy = rect.y + h // 2 - 5
    # мини-флажок: цвет армии (фракция здесь неизвестна — рисуем треугольный)
    pygame.draw.polygon(screen, color, [(fx, fy), (fx + 9, fy + 2.5), (fx, fy + 5)])
    text = troop_k(troops)
    img = font.render(text, True, MUTED if dim else (240, 242, 247))
    screen.blit(img, (fx + 13, rect.centery - img.get_height() // 2))


def find_spot(rect, placed, bounds):
    if not any(rect.colliderect(p) for p in placed):
        return rect
    step = rect.h + 3
    for off in range(1, 9):
        for dy in (step * off, -step * off):
            for dx in (0, rect.w // 2 + 8, -(rect.w // 2 + 8)):
                cand = rect.move(dx, dy)
                cand.clamp_ip(bounds)
                if not any(cand.colliderect(p) for p in placed):
                    return cand
    return rect


def draw_clash(screen, x, y):
    """Вспышка встречного боя."""
    for ang, col, ln in ((0, (255, 236, 150), 14), (90, (255, 236, 150), 14),
                         (45, (255, 170, 90), 11), (-45, (255, 170, 90), 11)):
        rad = math.radians(ang)
        dx, dy = math.cos(rad) * ln, math.sin(rad) * ln
        pygame.draw.line(screen, col, (x - dx, y - dy), (x + dx, y + dy), 3)
    pygame.draw.circle(screen, (255, 250, 220), (int(x), int(y)), 4)


def _text_along_path(screen, font, text, path, offset_px, side=1, anchor="center",
                     fill=(255, 255, 255), outline=(10, 10, 14), placed_rects=None):
    """Рисует текст, изогнутый вдоль ломаной path (в тайловых координатах).

    Каждая буква ставится на свой участок кривой и поворачивается по
    касательной; side=1 — слева/выше пути, side=-1 — справа/ниже.
    anchor: "start" — от начала пути, "end" — прижат к концу, "center".
    placed — список Rect уже нарисованных надписей (для защиты от наложений).
    Возвращает True, если текст поместился. path упорядочен слева направо."""
    if len(path) < 2:
        return False
    pts = [(MAP_X + (p[0] + 0.5) * TILE, MAP_Y + (p[1] + 0.5) * TILE) for p in path]
    segs = []
    total = 0.0
    for i in range(len(pts) - 1):
        dx, dy = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
        ln = math.hypot(dx, dy) or 1e-6
        segs.append((pts[i], pts[i + 1], ln))
        total += ln
    if total < 10:
        return False
    # если кривая сильно изогнута на отрезке текста (полуостров, вилка) —
    # изгиб делать нельзя: буквы свернутся. Рисуем только на плавных путях.
    dirs = []
    for (a, b, ln) in segs:
        dirs.append(math.atan2(b[1] - a[1], b[0] - a[0]))
    # суммарный поворот: и соседние изломы, и общий разворот пути
    spread = 0.0
    for i in range(1, len(dirs)):
        d = abs(dirs[i] - dirs[i - 1])
        if d > math.pi:
            d = 2 * math.pi - d
        spread += d
    if len(dirs) >= 2:
        d0 = abs(dirs[-1] - dirs[0])
        if d0 > math.pi:
            d0 = 2 * math.pi - d0
        spread = max(spread, d0)
    if spread > 0.25 * math.pi:
        return False
    widths = [font.size(c)[0] for c in text]
    # пробелы-разделители тысяч сжимаем втрое — экономит длину без потерь
    widths = [max(1, w // 3) if ch == " " else w for ch, w in zip(text, widths)]
    text_w = sum(widths)
    if anchor == "start":
        start = total * 0.08
    elif anchor == "end":
        start = total * 0.92 - text_w
    else:
        start = (total - text_w) / 2.0
    if start < 0 or start + text_w > total:
        return False                      # фронт короче надписи — не рисуем
    # считаем ВСЕ буквы заранее; если хоть одна накладывается на нарисованное
    # раньше — отказываемся целиком: никаких обрывков «1 57 06»
    letters = []
    cur = start
    for ch, w in zip(text, widths):
        mid = cur + w / 2.0
        acc = 0.0
        a = b = None
        ln = 1.0
        for (pa_, pb_, ln_) in segs:
            if acc + ln_ >= mid:
                a, b, ln = pa_, pb_, ln_
                break
            acc += ln_
        if a is None:
            return False
        t = (mid - acc) / ln
        x = a[0] + (b[0] - a[0]) * t
        y = a[1] + (b[1] - a[1]) * t
        nx_, ny_ = -(b[1] - a[1]) / ln, (b[0] - a[0]) / ln
        if side < 0:
            nx_, ny_ = -nx_, -ny_
        px = x + nx_ * offset_px
        py = y + ny_ * offset_px
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        # буква наклоняется по фронту, но не переворачивается
        if ang > 90.0:
            ang -= 180.0
        elif ang < -90.0:
            ang += 180.0
        ang = max(-60.0, min(60.0, ang))
        img = render_outline(font, ch, fill=fill, outline=outline, thickness=2)
        if abs(ang) > 0.5:
            img = pygame.transform.rotate(img, -ang)
        rect = pygame.Rect(int(px - img.get_width() / 2), int(py - img.get_height() / 2),
                           img.get_width(), img.get_height())
        if placed_rects is not None and any(rect.colliderect(r) for r in placed_rects):
            return False
        letters.append((img, rect))
        cur += w
    for img, rect in letters:
        screen.blit(img, rect.topleft)
        if placed_rects is not None:
            placed_rects.append(rect)
    return True


def render_outline(font, text, fill=(255, 255, 255), outline=(8, 8, 11), thickness=2):
    base = font.render(text, True, fill)
    out = font.render(text, True, outline)
    w, h = base.get_size()
    surf = pygame.Surface((w + 2 * thickness, h + 2 * thickness), pygame.SRCALPHA)
    for dx in range(-thickness, thickness + 1):
        for dy in range(-thickness, thickness + 1):
            if dx * dx + dy * dy <= thickness * thickness + 1:
                surf.blit(out, (thickness + dx, thickness + dy))
    surf.blit(base, (thickness, thickness))
    return surf


def draw_card(screen, rect, color=CARD, border=BORDER, radius=10, border_w=1):
    if isinstance(screen, _ShiftedSurface):
        screen.draw("rect", color, rect, border_radius=radius)
        if border_w:
            screen.draw("rect", border, rect, width=border_w, border_radius=radius)
        return
    pygame.draw.rect(screen, color, rect, border_radius=radius)
    if border_w:
        pygame.draw.rect(screen, border, rect, width=border_w, border_radius=radius)


def draw_button(screen, font, rect, text, color, text_col=(255, 255, 255),
                active=False, disabled=False):
    try:
        win_size = pygame.display.get_surface().get_size()
    except Exception:
        win_size = (W, H)
    mx, my = map_mouse(pygame.mouse.get_pos(), win_size)
    hover = rect.collidepoint((mx, my)) and not disabled
    base = (50, 54, 64) if disabled else (mix(color, (255, 255, 255), 0.15) if hover else color)
    draw_rect_local = (lambda c, r, **kw: screen.draw("rect", c, r, **kw)) \
        if isinstance(screen, _ShiftedSurface) else \
        (lambda c, r, **kw: pygame.draw.rect(screen, c, r, **kw))
    draw_rect_local(base, rect, border_radius=8)
    if active:
        draw_rect_local((255, 235, 120), rect, width=2, border_radius=8)
    if not disabled:
        draw_rect_local(mix(base, (0, 0, 0), 0.35), rect, width=1, border_radius=8)
    col = (120, 124, 132) if disabled else text_col
    img = font.render(text, True, col)
    screen.blit(img, (rect.centerx - img.get_width() // 2,
                      rect.centery - img.get_height() // 2))


def draw_bar(screen, rect, frac, color, bg=(48, 52, 62)):
    if isinstance(screen, _ShiftedSurface):
        screen.draw("rect", bg, rect, border_radius=3)
        w = int(rect.w * max(0.0, min(1.0, frac)))
        if w > 0:
            screen.draw("rect", color, (rect.x, rect.y, w, rect.h), border_radius=3)
        return
    pygame.draw.rect(screen, bg, rect, border_radius=3)
    w = int(rect.w * max(0.0, min(1.0, frac)))
    if w > 0:
        pygame.draw.rect(screen, color, (rect.x, rect.y, w, rect.h), border_radius=3)


# ============================ ОРГАНИЧНАЯ ГЕОМЕТРИЯ КАРТЫ ============================
# Провинции остаются логической сеткой 8x8, но рисуются «живыми» полигонами:
# углы слегка смещены, каждое ребро — плавная волна. Соседи используют ОДНУ И ТУ ЖЕ
# кривую общего ребра, поэтому щелей нет, а границы перестают быть прямыми.
_GEO = random.Random(20261004)
_CORNER = {}
_EDGE_PTS = {}
_POLY = {}
_BBOX = {}
_MASK = {}
_SUBLINES = {}
_SPLITWAVE = {}
_TERRAIN_TEX = None


def _wave(seed, n=17, amp=9.5):
    """Профиль смещения ребра: сумма синусов с огибающей, обнуляющейся на концах."""
    r = random.Random(seed)
    a1, f1, p1 = r.uniform(3.5, amp), r.uniform(1.1, 2.1), r.uniform(0, 6.283)
    a2, f2, p2 = r.uniform(1.5, 4.5), r.uniform(2.4, 4.6), r.uniform(0, 6.283)
    a3, f3, p3 = r.uniform(0.6, 2.0), r.uniform(5.0, 8.5), r.uniform(0, 6.283)
    out = []
    for i in range(n):
        t = i / (n - 1)
        env = math.sin(math.pi * t)
        out.append((a1 * math.sin(6.283185 * f1 * t + p1)
                    + a2 * math.sin(6.283185 * f2 * t + p2)
                    + a3 * math.sin(6.283185 * f3 * t + p3)) * env)
    return out


def _corner(x, y):
    key = (x, y)
    if key not in _CORNER:
        jx = 0.0 if x in (0, GRID) else _GEO.uniform(-7.5, 7.5)
        jy = 0.0 if y in (0, GRID) else _GEO.uniform(-7.5, 7.5)
        _CORNER[key] = (MAP_X + x * TILE + jx, MAP_Y + y * TILE + jy)
    return _CORNER[key]


def edge_pts(kind, ix, iy):
    """Точки сеточного ребра: 'h' — горизонталь (ix,iy)->(ix+1,iy), 'v' — вертикаль (ix,iy)->(ix,iy+1)."""
    key = (kind, ix, iy)
    pts = _EDGE_PTS.get(key)
    if pts is not None:
        return pts
    if kind == 'h':
        ax, ay = _corner(ix, iy)
        bx, by = _corner(ix + 1, iy)
        px, py = 0.0, 1.0
        seed = (ix * 73856093) ^ (iy * 19349663) ^ 0x51
    else:
        ax, ay = _corner(ix, iy)
        bx, by = _corner(ix, iy + 1)
        px, py = 1.0, 0.0
        seed = (ix * 73856093) ^ (iy * 19349663) ^ 0x97
    prof = _wave(seed % 99991)
    n = len(prof)
    pts = []
    for i, d in enumerate(prof):
        t = i / (n - 1)
        pts.append((ax + (bx - ax) * t + px * d, ay + (by - ay) * t + py * d))
    _EDGE_PTS[key] = pts
    return pts


def region_poly(ix, iy):
    key = (ix, iy)
    p = _POLY.get(key)
    if p is not None:
        return p
    top = edge_pts('h', ix, iy)
    right = edge_pts('v', ix + 1, iy)
    bottom = edge_pts('h', ix, iy + 1)[::-1]
    left = edge_pts('v', ix, iy)[::-1]
    p = top + right[1:] + bottom[1:] + left[1:]
    _POLY[key] = p
    return p


def region_bbox(ix, iy):
    key = (ix, iy)
    b = _BBOX.get(key)
    if b is None:
        poly = region_poly(ix, iy)
        xs = [q[0] for q in poly]
        ys = [q[1] for q in poly]
        b = R(int(min(xs)) - 1, int(min(ys)) - 1,
              int(max(xs) - min(xs)) + 3, int(max(ys) - min(ys)) + 3)
        _BBOX[key] = b
    return b


def region_mask(ix, iy):
    """Белый полигон провинции (альфа-клип для слоёв боя)."""
    key = (ix, iy)
    m = _MASK.get(key)
    if m is None:
        b = region_bbox(ix, iy)
        m = pygame.Surface((b.w, b.h), pygame.SRCALPHA)
        loc = [(px - b.x, py - b.y) for px, py in region_poly(ix, iy)]
        pygame.draw.polygon(m, (255, 255, 255, 255), loc)
        _MASK[key] = m
    return m


def sublines(ix, iy):
    """Тонкие «внутренние» линии внутри провинции — как на карте-примере."""
    key = (ix, iy)
    if key in _SUBLINES:
        return _SUBLINES[key]
    r = random.Random(ix * 101 + iy * 7 + 5)
    poly = region_poly(ix, iy)
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    edges = [edge_pts('h', ix, iy), edge_pts('h', ix, iy + 1),
             edge_pts('v', ix, iy), edge_pts('v', ix + 1, iy)]
    lines = []
    for _ in range(2):
        i1, i2 = r.sample(range(4), 2)
        e1, e2 = edges[i1], edges[i2]
        a = e1[r.randint(5, 11)]
        b = e2[r.randint(5, 11)]
        ctl = (cx + r.uniform(-16, 16), cy + r.uniform(-16, 16))
        pts = []
        for k in range(15):
            t = k / 14.0
            mt = 1.0 - t
            pts.append((mt * mt * a[0] + 2 * mt * t * ctl[0] + t * t * b[0],
                        mt * mt * a[1] + 2 * mt * t * ctl[1] + t * t * b[1]))
        lines.append(pts)
    _SUBLINES[key] = lines
    return lines


def terrain_tex():
    """Статичная «ландшафтная» текстура: мягкий шум, чуть варьирующий заливку."""
    global _TERRAIN_TEX
    if _TERRAIN_TEX is None:
        rng = random.Random(4242)

        def layer(size, lo, hi):
            s = pygame.Surface(size)
            for yy in range(size[1]):
                for xx in range(size[0]):
                    v = rng.randint(lo, hi)
                    s.set_at((xx, yy), (v, v, v))
            return pygame.transform.smoothscale(s, (MAP_W, MAP_H))

        tex = layer((37, 37), 236, 255)
        tex.blit(layer((118, 118), 246, 255), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        _TERRAIN_TEX = tex
    return _TERRAIN_TEX


def _split_wave(key):
    """Общая волна линии раздела для целого фронта.

    Смещение — функция глобальной координаты вдоль фронта, одинаковая для
    соседних тайлов, поэтому граница боя непрерывна и без ступенек."""
    w = _SPLITWAVE.get(key)
    if w is None:
        r = random.Random(key[0] * 73856093 ^ key[1] * 19349663 ^ key[2] * 83492791)
        comps = [(r.uniform(0.45, 1.0), r.uniform(0.9, 1.6), r.uniform(0, 6.283)),
                 (r.uniform(0.22, 0.45), r.uniform(1.9, 3.0), r.uniform(0, 6.283)),
                 (r.uniform(0.08, 0.2), r.uniform(3.8, 6.0), r.uniform(0, 6.283))]
        norm = sum(a for a, _, _ in comps)
        w = ([(a / norm, f, p) for a, f, p in comps], r.uniform(1.7, 2.6) * TILE)
        _SPLITWAVE[key] = w
    return w


def split_line(d, frac, gx, gy):
    """Волнистая линия раздела владелец/оккупант (локальные координаты тайла).

    Соседние тайлы одного фронта используют одну статичную волну по глобальной
    координате: линия раздела гладкая, непрерывная и не дёргается во времени.
    Амплитуда ограничена шириной полосы оккупанта, чтобы узкий плацдарм
    не «схлопывало»."""
    amp = max(1.5, min(5.5, 0.34 * frac * TILE))
    if d in ((1, 0), (-1, 0)):
        comps, wl = _split_wave((0, gx, 1 if d == (1, 0) else -1))
    else:
        comps, wl = _split_wave((1, gy, 1 if d == (0, 1) else -1))
    n = 13
    pts = []
    for i in range(n):
        s = i / (n - 1)
        along = -6 + (TILE + 12) * s
        u = (gy if d in ((1, 0), (-1, 0)) else gx) * TILE + along
        w = sum(a * math.sin(6.283185 * u / (wl * f) + p) for a, f, p in comps) * amp
        if d in ((1, 0), (-1, 0)):
            x = TILE * (1.0 - frac) if d == (1, 0) else TILE * frac
            pts.append((x + w, along))
        else:
            y = TILE * (1.0 - frac) if d == (0, 1) else TILE * frac
            pts.append((along, y + w))
    return pts


def band_poly(d, pts):
    """Замкнутый полигон зоны оккупанта: линия раздела + дальние углы тайла
    (обход продолжен так, чтобы многоугольник не самопересекался)."""
    if d == (1, 0):
        return pts + [(TILE + 12, TILE + 12), (TILE + 12, -12)]
    if d == (-1, 0):
        return pts + [(-12, TILE + 12), (-12, -12)]
    if d == (0, 1):
        return pts + [(TILE + 12, TILE + 12), (-12, TILE + 12)]
    return pts + [(TILE + 12, -12), (-12, -12)]


# --- раскладка ---
TAB_Y, TAB_H = MAP_Y + 8, 34
CONTENT_Y = TAB_Y + TAB_H + 10
BTN_PAUSE = R(W - 16 - 3 * 118 - 2 * 8, 9, 118, 30)
BTN_SPEED = R(W - 16 - 2 * 118 - 1 * 8, 9, 118, 30)
BTN_NUM = R(W - 16 - 1 * 118, 9, 118, 30)

DIPLO_CARD_H = 92
DIPLO_BTNS = [("gift", "Дар"), ("alliance", "Союз"), ("nap", "Пакт"),
              ("trade", "Торг."), ("peace", "Мир"), ("war", "Война")]


TAB_LABELS = ["Обзор", "Регион", "Дипломатия", "Войны"]


def tab_rects():
    w = (PANEL_W - 16 - (len(TAB_LABELS) - 1) * 6) // len(TAB_LABELS)
    return [R(PANEL_X + 8 + i * (w + 6), TAB_Y, w, TAB_H) for i in range(len(TAB_LABELS))]


def offer_rects():
    w, h = 470, 196
    x = MAP_X + MAP_W // 2 - w // 2
    y = MAP_Y + MAP_H // 2 - h // 2
    card = R(x, y, w, h)
    accept = R(x + 36, y + h - 62, 168, 44)
    refuse = R(x + w - 36 - 168, y + h - 62, 168, 44)
    return card, accept, refuse


def end_button_rects(with_menu=False):
    if with_menu:
        watch = R(W // 2 - 356, H // 2 + 168, 220, 54)
        again = R(W // 2 - 124, H // 2 + 168, 220, 54)
        menu = R(W // 2 + 108, H // 2 + 168, 220, 54)
        return watch, again, menu
    watch = R(W // 2 - 236, H // 2 + 168, 220, 54)
    again = R(W // 2 + 16, H // 2 + 168, 220, 54)
    return watch, again, None


def replay_bar_rect():
    return R(MAP_X + 12, MAP_Y + MAP_H + 14, MAP_W - 24, 8)


def replay_btns():
    y = MAP_Y + MAP_H + 30
    # транспорт слева, «СОХРАНИТЬ»+«ВЫХОД» прижаты к правому краю карты;
    # если на узкой карте они не помещаются — «СОХРАНИТЬ» не рисуем вовсе
    # (партия всё равно автосохраняется при завершении)
    btns = {
        "play": R(MAP_X + 12, y, 100, 34),
        "back": R(MAP_X + 120, y, 60, 34),
        "fwd": R(MAP_X + 188, y, 60, 34),
        "speed": R(MAP_X + 256, y, 84, 34),
        "exit": R(MAP_X + MAP_W - 108, y, 96, 34),
    }
    # на узких картах скорость не влезает целиком — сжимаем до ширины 44
    if btns["speed"].right > btns["exit"].x - 8:
        btns["speed"] = R(btns["exit"].x - 52, y, 44, 34)
    save = R(MAP_X + MAP_W - 236, y, 116, 34)
    widest_left = max(btns["speed"].right, btns["fwd"].right)
    btns["save"] = save if save.x > widest_left + 8 else None
    return btns


def draw_topbar(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    pygame.draw.rect(screen, (23, 26, 32), (0, 0, W, TOPBAR_H))
    pygame.draw.line(screen, BORDER, (0, TOPBAR_H), (W, TOPBAR_H), 1)
    screen.blit(f_head.render("БАЛАНС СИЛ", True, TEXT), (16, 6))
    sc = SCENARIOS.get(getattr(game, "scenario", "classic"))
    sub = f"сценарий «{sc['name']}»" if sc else "стратегия"
    screen.blit(f_tiny.render(sub, True, MUTED), (16, 28))
    if game.choosing:
        return
    if game.observer:
        screen.blit(f_head.render("РЕЖИМ НАБЛЮДАТЕЛЯ", True, (255, 220, 120)), (210, 8))
        alive_n = sum(1 for f in game.factions.values() if f.alive)
        mins, secs = int(game.time) // 60, int(game.time) % 60
        screen.blit(f_chip.render(f"фракций в игре: {alive_n}   ·   время {mins:02d}:{secs:02d}",
                                  True, TEXT), (420, 14))
        draw_button(screen, f_chip, BTN_PAUSE, "ПРОДОЛЖИТЬ" if game.paused else "ПАУЗА",
                    (55, 170, 95) if game.paused else (200, 120, 60))
        draw_button(screen, f_chip, BTN_SPEED, f"×{SPEEDS[game.speed_idx]}", (110, 90, 180))
        draw_button(screen, f_chip, BTN_NUM, "ЦИФРЫ", (70, 100, 130) if game.show_numbers else (60, 64, 74),
                    active=game.show_numbers)
        return
    pf = game.factions[game.player]
    inc = game.faction_income(pf.fid)
    upk = game.faction_upkeep(pf.fid)
    net = inc - upk
    x = 210

    def chip(label, value, value_col, width):
        nonlocal x
        r = R(x, 8, width, 32)
        draw_card(screen, r, (31, 35, 43), (50, 56, 68), 8, 1)
        screen.blit(f_tiny.render(label, True, MUTED), (r.x + 10, r.y + 2))
        screen.blit(f_chip.render(value, True, value_col), (r.x + 10, r.y + 15))
        x += width + 8

    chip("Казна", f"{int(pf.money)}", WARN, 96)
    chip("Баланс", f"{net:+.1f}/с", GOOD if net >= 0 else BAD, 128)
    chip("Люди", fmt(pf.manpower), (120, 190, 255), 118)
    chip("Регионы", str(len(pf.regions)), TEXT, 92)
    chip("Войска", fmt(pf.total_troops), TEXT, 122)
    chip("Мораль", f"{int(pf.morale)}", GOOD if pf.morale > 70 else WARN, 96)

    draw_button(screen, f_chip, BTN_PAUSE, "ПРОДОЛЖИТЬ" if game.paused else "ПАУЗА",
                (55, 170, 95) if game.paused else (200, 120, 60))
    draw_button(screen, f_chip, BTN_SPEED, f"×{SPEEDS[game.speed_idx]}", (110, 90, 180))
    draw_button(screen, f_chip, BTN_NUM, "ЦИФРЫ", (70, 100, 130) if game.show_numbers else (60, 64, 74),
                active=game.show_numbers)


def draw_map(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    rng = R(MAP_X, MAP_Y, MAP_W, MAP_H)
    pygame.draw.rect(screen, (64, 68, 64), rng)
    sel = game.selected
    neighbor_ids = set()
    if sel is not None:
        neighbor_ids = {n.rid for n in game.neighbors(game.regions[sel])}
    move_targets = set()
    if sel is not None and game.player is not None and game.regions[sel].owner == game.player:
        move_targets = set(neighbor_ids)

    # ---- проход 1: провинции — полупрозрачный цвет страны поверх фона
    #      с текстурой (как на примере); спорные — слоями в буфер ----
    contested = []
    splits = {}
    fills = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
    for r in game.regions:
        col = faction_color(game, r.owner)
        owner_share, inv_fid, inv_share = game.control(r)
        # плавная и динамичная доля захвата: быстрая сходимость без рывков
        # (draw ~60 к/с, поэтому коэффициент подобран под кадр)
        r.dshare += (inv_share - r.dshare) * 0.22
        if inv_fid is not None and r.dshare > 0.02:
            contested.append((r, col, inv_fid))
        # координаты полигонов абсолютные — приводим к локальным координатам
        # surface, иначе заливка уезжает относительно линий границ
        pygame.draw.polygon(fills, col + (195,),
                            [(px - MAP_X, py - MAP_Y) for px, py in region_poly(r.x, r.y)])
    screen.blit(fills, (MAP_X, MAP_Y))

    occ = {r.rid: (r.dshare, game.attack_dir(r, inv_fid), inv_fid)
           for r, col, inv_fid in contested}
    for r, col, inv_fid in contested:
        b = region_bbox(r.x, r.y)
        ox, oy = MAP_X + r.x * TILE, MAP_Y + r.y * TILE
        frac, d, _ = occ[r.rid]
        # сглаживаем долю захвата вдоль линии боя — без ступенек между тайлами
        vals = [frac, frac]
        for nrid in ((r.rid + GRID, r.rid - GRID) if d in ((1, 0), (-1, 0))
                     else (r.rid - 1, r.rid + 1)):
            ninfo = occ.get(nrid)
            if ninfo is None or ninfo[1] != d or ninfo[2] != inv_fid:
                continue
            if nrid in (r.rid - 1, r.rid + 1) and abs(game.regions[nrid].x - r.x) != 1:
                continue          # не переходим через край строки
            vals.append(ninfo[0])
        frac = min(0.97, max(0.03, sum(vals) / len(vals)))
        pts = split_line(d, frac, r.x, r.y)
        splits[r.rid] = (pts, d, ox, oy)
        # полоса оккупанта — полупрозрачный цвет захватчика поверх заливки
        surf = pygame.Surface((b.w, b.h), pygame.SRCALPHA)
        band = [(px + ox - b.x, py + oy - b.y) for px, py in band_poly(d, pts)]
        pygame.draw.polygon(surf, faction_color(game, inv_fid) + (180,), band)
        surf.blit(region_mask(r.x, r.y), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(surf, (b.x, b.y))

    # ---- проход 2: тонкие внутренние линии (как на примере) ----
    ls = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
    for r in game.regions:
        for ln in sublines(r.x, r.y):
            pygame.draw.lines(ls, (255, 255, 255, 46), False,
                              [(px - MAP_X, py - MAP_Y) for px, py in ln], 1)
    screen.blit(ls, (MAP_X, MAP_Y))

    # ---- проход 3: ландшафтная текстура (без лесов/иконок, только светотень) ----
    screen.blit(terrain_tex(), (MAP_X, MAP_Y), special_flags=pygame.BLEND_RGBA_MULT)

    # ---- проход 4: границы владений — тёмные «государственные» линии ----
    fx = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
    for r in game.regions:
        for dx, dy in ((1, 0), (0, 1)):
            nx, ny = r.x + dx, r.y + dy
            if not (0 <= nx < GRID and 0 <= ny < GRID):
                continue
            n = game.region_at(nx, ny)
            if n.owner == r.owner:
                continue
            pts = edge_pts('v', r.x + 1, r.y) if dx == 1 else edge_pts('h', r.x, r.y + 1)
            mp = [(px - MAP_X, py - MAP_Y) for px, py in pts]
            hot = (r.owner == NEUTRAL or n.owner == NEUTRAL
                   or game.at_war(r.owner, n.owner))
            pygame.draw.lines(fx, (16, 17, 22, 190), False, mp, 2)
            if hot:
                pygame.draw.lines(fx, (255, 190, 120, 60), False, mp, 1)
    screen.blit(fx, (MAP_X, MAP_Y))

    # ---- проход 5: линия боя внутри провинции (спокойная, статичная) ----
    fxs = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
    for r, col, inv_fid in contested:
        pts, d, ox, oy = splits[r.rid]
        mp = [(ox + px - MAP_X, oy + py - MAP_Y) for px, py in pts]
        pygame.draw.lines(fxs, (28, 16, 10, 170), False, mp, 3)
        pygame.draw.lines(fxs, (255, 244, 220, 80), False, mp, 1)
    screen.blit(fxs, (MAP_X, MAP_Y))

    # ---- проход 6: вспышки боя ----
    for r in game.regions:
        if r.flash > 0:
            m = region_mask(r.x, r.y).copy()
            m.fill((255, 205, 100, int(80 * r.flash)), special_flags=pygame.BLEND_RGBA_MULT)
            b = region_bbox(r.x, r.y)
            screen.blit(m, (b.x, b.y))

    # ---- проход 6.5: анимация захвата — цвет вливается волной от центра ----
    for cap in game.captures:
        r = game.regions[cap["rid"]]
        t = cap["t"]
        if not 0.0 <= t < 1.0:
            continue
        b = region_bbox(r.x, r.y)
        col = cap["col"]
        # фаза 1 (t 0..0.45): радиальная волна от центра — быстрый старт,
        # мягкое торможение (ease-out)
        wav = min(1.0, t / 0.45)
        wav = 1.0 - (1.0 - wav) ** 3
        rad = wav * math.hypot(b.w, b.h) / 2 + 2
        m = region_mask(r.x, r.y).copy()
        glow = pygame.Surface((b.w, b.h), pygame.SRCALPHA)
        cx, cy = b.w / 2, b.h / 2
        # мягкий градиентный диск: несколько колец с падающей альфой
        rings = 7
        for i in range(rings, 0, -1):
            rr = rad * i / rings
            a = int(215 * (1.0 - i / (rings + 1.2)))
            pygame.draw.circle(glow, col + (a,), (int(cx), int(cy)), int(rr))
        glow.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(glow, (b.x, b.y))
        # расходящееся кольцо фронта волны (толще и ярче к старту)
        ring_a = int(230 * (1.0 - wav) ** 0.7)
        if ring_a > 4:
            ring = pygame.Surface((b.w, b.h), pygame.SRCALPHA)
            pygame.draw.circle(ring, (255, 255, 255, ring_a), (int(cx), int(cy)),
                               int(rad), 3 if ring_a > 120 else 2)
            ring.blit(m, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(ring, (b.x, b.y))
        # фаза 2 (t 0.3..1): вспышка затухает по ease-out, контур пульсирует
        if t > 0.3:
            pulse = (1.0 - (t - 0.3) / 0.7) ** 1.6
            flash_a = int(80 * pulse)
            fm = m.copy()
            fm.fill(col[:3] + (flash_a,), special_flags=pygame.BLEND_RGBA_MULT)
            screen.blit(fm, (b.x, b.y))
            poly = [(px, py) for px, py in region_poly(r.x, r.y)]
            pygame.draw.polygon(screen, mix(col, (255, 255, 255), 0.55),
                                poly, max(1, int(3 * pulse)))

    # ---- проход 7: столицы, числа, сопротивление, выделение ----
    for r in game.regions:
        x = MAP_X + r.x * TILE
        y = MAP_Y + r.y * TILE
        if r.capital_of is not None and r.capital_of == r.owner:
            draw_flag(screen, x + TILE - 26, y + 6, 14,
                      game.factions.get(r.owner))
        owner_share, inv_fid, inv_share = game.control(r)
        if r.rid not in splits:
            present = [(v, f) for f, v in r.forces.items() if v > 0.5]
            # цифры войск — только у выбранного региона и его соседей (G — все)
            if game.show_numbers or r.rid == sel or r.rid in neighbor_ids:
                present.sort(key=lambda t: (t[1] != r.owner, -t[0]))
                sz = f_small if r.rid == sel else f_tiny
                v = present[0][0] if present else 0
                f = present[0][1] if present else r.owner
                rr = counter_rect(sz, x + TILE // 2, y + TILE // 2, v)
                draw_counter_rect(screen, sz, rr, faction_color(game, f), v)
        if inv_fid is not None and 0.03 < inv_share < 0.985:
            txt = f"{int(round(inv_share * 100))}%"
            pc = f_tiny.render(txt, True, (255, 236, 170))
            psh = f_tiny.render(txt, True, (20, 15, 0))
            d = game.attack_dir(r, inv_fid)
            left_side = (d == (1, 0))
            top_side = (d != (0, -1))
            px = x + 4 if left_side else x + TILE - pc.get_width() - 4
            py = y + 4 if top_side else y + TILE - pc.get_height() - 7
            screen.blit(psh, (px + 1, py + 1))
            screen.blit(pc, (px, py))
        if sel == r.rid:
            pygame.draw.polygon(screen, (255, 236, 120), region_poly(r.x, r.y), 3)
        elif r.rid in move_targets:
            pygame.draw.polygon(screen, (255, 180, 60), region_poly(r.x, r.y), 2)

    # ---- проход 8: численность войск вдоль крупных фронтов ----
    # гарнизон приграничья (2 клетки) каждой стороны; у страны с двумя врагами
    # — по числу на каждого. Идеал читаемости: число горизонтально, стоит на
    # «своём» участке границы и отступлено вглубь своей территории; изгиб
    # вдоль пути — только для длинных плавных горизонтальных фронтов
    labels = []
    for fr in game.fronts():
        fid_a, fid_b = fr["pair"]
        va, vb = fr["troops"][fid_a], fr["troops"][fid_b]
        if (va < 1 and vb < 1) or va + vb < 4000:
            continue
        if not (fr["contested"] or game.at_war(fid_a, fid_b)):
            continue
        labels.append((va + vb, front_troops_text(va), front_troops_text(vb), fr))
    placed = []
    map_rect = R(MAP_X + 4, MAP_Y + 4, MAP_W - 8, MAP_H - 8)
    for _, ta, tb, fr in sorted(labels, key=lambda t: -t[0]):
        pts = fr["path"]
        if len(pts) < 2 or fr["pos"] is None:
            continue
        p0, p1 = pts[0], pts[-1]
        vx, vy = p1[0] - p0[0], p1[1] - p0[1]
        pa = fr["pos"].get(fr["pair"][0])
        cross = vx * (pa[0] - p0[0]) - vy * (pa[1] - p0[1]) if pa else 0.0
        side_a = 1 if cross > 0 else -1
        scr = [(MAP_X + (p[0] + 0.5) * TILE, MAP_Y + (p[1] + 0.5) * TILE)
               for p in pts]
        plen = sum(math.hypot(scr[i + 1][0] - scr[i][0], scr[i + 1][1] - scr[i][1])
                   for i in range(len(scr) - 1))
        horizontal = abs(vx) >= abs(vy) * 1.4
        enough = plen > (len(ta) + len(tb)) * 17
        if horizontal and enough:
            ok_a = _text_along_path(screen, f_front, ta, pts, 30, side=side_a,
                                    anchor="start", placed_rects=placed)
            ok_b = _text_along_path(screen, f_front, tb, pts, 30, side=-side_a,
                                    anchor="end", placed_rects=placed)
            if ok_a and ok_b:
                continue
        # горизонтальные числа: точка пути на «своём» участке, отступ вглубь
        for fid, txt in ((fr["pair"][0], ta), (fr["pair"][1], tb)):
            pp = fr["pos"].get(fid)
            if pp is None:
                continue
            cs = (MAP_X + (pp[0] + 0.5) * TILE, MAP_Y + (pp[1] + 0.5) * TILE)
            img = render_outline(f_front, txt)
            my_side = side_a if fid == fr["pair"][0] else -side_a
            # точки пути со стороны этой страны
            own = []
            for i in range(1, len(scr)):
                a_, b_ = scr[i - 1], scr[i]
                c2 = (b_[0] - a_[0]) * (cs[1] - a_[1]) - (b_[1] - a_[1]) * (cs[0] - a_[0])
                own.append((i, c2 * my_side >= 0))
            idxs = [i for i, is_own in own if is_own] or list(range(1, len(scr)))
            # кандидаты: середина, четверти, края — ближайшие к центру своего участка
            mid = idxs[len(idxs) // 2]
            order = [mid] + sorted(set(idxs) - {mid},
                                   key=lambda i: abs(i - mid))[:len(idxs)]
            best = None
            for i in order:
                p = scr[min(i, len(scr) - 1)]
                dx, dy = cs[0] - p[0], cs[1] - p[1]
                d = math.hypot(dx, dy) or 1.0
                bx = p[0] + dx / d * 0.52 * TILE
                by = p[1] + dy / d * 0.52 * TILE
                rect = pygame.Rect(int(bx - img.get_width() / 2),
                                   int(by - img.get_height() / 2),
                                   img.get_width(), img.get_height())
                rect.clamp_ip(map_rect)
                if not any(rect.inflate(10, 10).colliderect(r) for r in placed):
                    best = rect
                    break
            if best is None:
                best = pygame.Rect(int(cs[0] - img.get_width() / 2),
                                   int(cs[1] - img.get_height() / 2),
                                   img.get_width(), img.get_height())
                best.clamp_ip(map_rect)
                if any(best.inflate(10, 10).colliderect(r) for r in placed):
                    continue
            placed.append(best.inflate(6, 6))
            screen.blit(img, best.topleft)

    # ---- движущиеся армии ----
    if game.moves:
        clash_off = {}
        for m1, m2 in getattr(game, "field_clashes", []):
            clash_off[id(m1)] = 1
            clash_off[id(m2)] = -1
        trail = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
        for m in game.moves:
            a = game.regions[m.src]
            b = game.regions[m.dst]
            ax = a.x * TILE + TILE / 2
            ay = a.y * TILE + TILE / 2
            bx = b.x * TILE + TILE / 2
            by = b.y * TILE + TILE / 2
            frac = 0.5 if m.frozen else 1.0
            ex = ax + (bx - ax) * frac
            ey = ay + (by - ay) * frac
            pygame.draw.line(trail, faction_color(game, m.fid) + (110,),
                             (ax, ay), (ex, ey), 3)
        screen.blit(trail, (MAP_X, MAP_Y))
        for m in game.moves:
            a = game.regions[m.src]
            b = game.regions[m.dst]
            ax = MAP_X + a.x * TILE + TILE / 2
            ay = MAP_Y + a.y * TILE + TILE / 2
            bx = MAP_X + b.x * TILE + TILE / 2
            by = MAP_Y + b.y * TILE + TILE / 2
            t = 0.5 if m.frozen else m.progress
            px = ax + (bx - ax) * t
            py = ay + (by - ay) * t
            if m.frozen:
                dx, dy = bx - ax, by - ay
                length = math.hypot(dx, dy) or 1.0
                sign = clash_off.get(id(m), 1)
                px += -dy / length * 15 * sign
                py += dx / length * 15 * sign
                draw_clash(screen, ax + (bx - ax) * 0.5, ay + (by - ay) * 0.5)
            col = faction_color(game, m.fid)
            rect = counter_rect(f_tiny, px, py, m.amount)
            rect.clamp_ip(R(MAP_X + 2, MAP_Y + 2, MAP_W - 4, MAP_H - 4))
            draw_counter_rect(screen, f_tiny, rect, col, m.amount)

    # ---- проход 9: названия стран на их территориях ----
    if game.show_names:
        regions_of = {}
        for r in game.regions:
            if r.owner != NEUTRAL:
                regions_of.setdefault(r.owner, []).append(r)
        name_font = pygame.font.SysFont("segoeui", max(15, int(TILE * 0.26)), bold=True)
        for fid, regs in regions_of.items():
            f = game.factions[fid]
            mx = sum(r.x for r in regs) / len(regs)
            my = sum(r.y for r in regs) / len(regs)
            # подпись в регионе, ближайшем к центру масс владений
            home = min(regs, key=lambda r: (r.x - mx) ** 2 + (r.y - my) ** 2)
            img = render_outline(name_font, f.name.upper(),
                                 fill=(255, 255, 255), outline=(10, 10, 14), thickness=2)
            max_w = MAP_W - 24
            if img.get_width() > max_w:
                img = pygame.transform.smoothscale(
                    img, (max_w, max(10, int(img.get_height() * max_w / img.get_width()))))
            lbl = pygame.Surface((img.get_width() + 8, img.get_height() + 4), pygame.SRCALPHA)
            lbl.blit(img, (4, 2))
            lbl.set_alpha(170)
            px = int(MAP_X + (home.x + 0.5) * TILE - lbl.get_width() / 2)
            py = int(MAP_Y + (home.y + 0.5) * TILE - lbl.get_height() / 2)
            px = max(MAP_X + 4, min(px, MAP_X + MAP_W - lbl.get_width() - 4))
            py = max(MAP_Y + 4, min(py, MAP_Y + MAP_H - lbl.get_height() - 4))
            screen.blit(lbl, (px, py))

    pygame.draw.rect(screen, (72, 78, 90), rng, width=2, border_radius=2)


# ------------------------- ПАНЕЛЬ -------------------------
def panel_header(screen, fonts, pf):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    r = R(PANEL_X + 10, CONTENT_Y, PANEL_W - 20, 16)
    screen.blit(f_head.render(f"«{pf.name}»", True, pf.color), (PANEL_X + 16, CONTENT_Y - 4))
    sub = pf.trait + (f" · {pf.nation['name']}" if pf.nation else "")
    screen.blit(f_small.render(sub, True, MUTED),
                (PANEL_X + 16 + f_head.size(f"«{pf.name}»")[0] + 12, CONTENT_Y + 1))


def draw_overview_tab(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    y = CONTENT_Y + 24

    if game.observer:
        # турнирная таблица вместо «своих» ресурсов
        screen.blit(f_head.render("Расклад сил", True, TEXT), (PANEL_X + 16, y - 2))
        stats = sorted(game.factions.values(),
                       key=lambda f: (-len(f.regions), -f.total_troops))
        max_regs = max((len(f.regions) for f in stats), default=1) or 1
        yy = y + 24
        for f in stats:
            cr = R(PANEL_X + 10, yy, PANEL_W - 20, 74)
            draw_card(screen, cr, CARD if f.alive else (28, 30, 36), BORDER, 9, 1)
            pygame.draw.rect(screen, f.color, (cr.x + 10, cr.y + 10, 6, 54), border_radius=3)
            screen.blit(f_head.render(clip_text(f_head, f.name, 190), True,
                                      TEXT if f.alive else MUTED), (cr.x + 24, cr.y + 6))
            screen.blit(f_small.render(f"регионов {len(f.regions)}   войск {fmt(f.total_troops)}",
                                       True, TEXT if f.alive else MUTED), (cr.x + 24, cr.y + 28))
            doc = DOCTRINES[f.doctrine]["name"]
            screen.blit(f_tiny.render(
                f"{f.nation['name']} · {f.personality['name']} · доктрина: {doc}"
                if f.nation and f.personality else "", True, MUTED), (cr.x + 24, cr.y + 46))
            screen.blit(f_tiny.render(f"убито {fmt(f.kills)} · потери {fmt(f.losses)}",
                                      True, MUTED), (cr.right - 220, cr.y + 8))
            screen.blit(f_tiny.render("в игре" if f.alive else "уничтожена",
                                      True, GOOD if f.alive else BAD), (cr.right - 84, cr.y + 26))
            draw_bar(screen, R(cr.x + 24, cr.y + 62, cr.w - 48, 6),
                     len(f.regions) / max_regs, f.color)
            yy += 82
        # график хода партии: доля регионов каждой страны по снимкам истории
        gh = 130
        gr = R(PANEL_X + 10, yy + 4, PANEL_W - 20, gh)
        draw_card(screen, gr, (24, 27, 34), BORDER, 9, 1)
        screen.blit(f_small.render("Ход партии (доля регионов по времени)", True, MUTED),
                    (gr.x + 12, gr.y + 6))
        hist = game.history
        if len(hist) >= 2:
            step = max(1, len(hist) // 160)
            n = len(game.factions)
            totals = GRID * GRID
            for i in range(0, len(hist), step):
                x = gr.x + 12 + int((gr.w - 24) * i / max(1, len(hist) - 1))
                snap = hist[i]
                ycur = gr.y + 24
                for fid in game.factions:
                    cnt = snap["owner"].count(fid)
                    h = int((gh - 36) * cnt / totals)
                    if h > 0:
                        pygame.draw.rect(screen, faction_color(game, fid),
                                         (x, ycur, 3, h))
                    ycur += h
        else:
            screen.blit(f_small.render("данных пока мало…", True, MUTED),
                        (gr.x + 12, gr.y + 30))
        # журнал ниже
        ly = yy + gh + 12
        lr = R(PANEL_X + 10, ly, PANEL_W - 20, max(60, H - 24 - ly))
        draw_card(screen, lr, (31, 35, 43), BORDER, 9, 1)
        screen.blit(f_head.render("Журнал", True, TEXT), (PANEL_X + 16, ly - 22))
        lines_fit = max(1, (lr.h - 12) // 17)
        for i, line in enumerate(game.log[-lines_fit:]):
            screen.blit(f_small.render(line, True, TEXT), (lr.x + 12, lr.y + 6 + i * 17))
        return

    pf = game.factions[game.player]

    # ресурсные карточки
    gross = game.faction_income(pf.fid)
    upk = game.faction_upkeep(pf.fid)
    net = gross - upk
    items = [
        ("Казна", f"{int(pf.money)}", WARN),
        ("Доход", f"{gross:.1f}/с", GOOD),
        ("Содержание", f"-{upk:.1f}/с", BAD),
        ("Итого", f"{net:+.1f}/с", GOOD if net >= 0 else BAD),
        ("Люди", fmt(pf.manpower), (120, 190, 255)),
        ("Войска", fmt(pf.total_troops), TEXT),
        ("Регионы", str(len(pf.regions)), TEXT),
        ("Мораль", f"{int(pf.morale)}", GOOD if pf.morale > 70 else WARN),
    ]
    cw = (PANEL_W - 20 - 3 * 8) // 4
    for i, (lab, val, col) in enumerate(items):
        cx = PANEL_X + 10 + (i % 4) * (cw + 8)
        cy = y + (i // 4) * 60
        cr = R(cx, cy, cw, 52)
        draw_card(screen, cr, CARD, BORDER, 9, 1)
        screen.blit(f_tiny.render(lab, True, MUTED), (cr.x + 10, cr.y + 7))
        screen.blit(f_head.render(val, True, col), (cr.x + 10, cr.y + 22))

    # людские ресурсы — полоса
    y2 = y + 2 * 60 + 4
    rr = R(PANEL_X + 10, y2, PANEL_W - 20, 44)
    draw_card(screen, rr, CARD, BORDER, 9, 1)
    screen.blit(f_small.render("Людские ресурсы", True, MUTED), (rr.x + 10, rr.y + 6))
    screen.blit(f_small.render(f"{fmt(pf.manpower)} / {fmt(pf.manpower_max)}", True, TEXT),
                (rr.right - 220, rr.y + 6))
    draw_bar(screen, R(rr.x + 10, rr.y + 26, rr.w - 20, 8),
             pf.manpower / max(1, pf.manpower_max), (120, 190, 255))

    # доктрины: треугольник контр-системы Манёвры → Удар → Оборона
    y3 = y2 + 56
    screen.blit(f_head.render("Доктрина армии", True, TEXT), (PANEL_X + 16, y3))
    doc = DOCTRINES[pf.doctrine]
    dw = (PANEL_W - 20 - 2 * 8) // 3
    for i, d in enumerate(DOCTRINES):
        br = R(PANEL_X + 10 + i * (dw + 8), y3 + 26, dw, 56)
        cur = i == pf.doctrine
        # подсказка контры: кого эта доктрина бьёт
        beats = next(x for x in DOCTRINES if x["key"] == d["beats"])["name"]
        draw_button(screen, f_chip, br, d["name"],
                    (70, 120, 170) if cur else (60, 64, 74),
                    active=cur, disabled=not cur and pf.money < game.doctrine_change_cost(pf.fid))
        screen.blit(f_tiny.render(f"атака ×{d['atk']:.2f} · оборона ×{d['def']:.2f}",
                                  True, MUTED), (br.x + 8, br.y + 22))
        screen.blit(f_tiny.render(f"сильно против: {beats}",
                                  True, (255, 210, 130)), (br.x + 8, br.y + 38))
    # строка описания текущей доктрины и цены смены
    dinfo = f"{doc['desc']}   ·   смена: {game.doctrine_change_cost(pf.fid)} (морале -8)"
    screen.blit(f_small.render(dinfo, True, MUTED), (PANEL_X + 16, y3 + 88))

    # технологии
    y4 = y3 + 108
    screen.blit(f_head.render("Технологии", True, TEXT), (PANEL_X + 16, y4))
    tw = (PANEL_W - 20 - 3 * 8) // 4
    for i, t in enumerate(TECH_TRACKS):
        lvl = pf.tech2.get(t["key"], 0)
        cost = game.tech2_cost(pf.fid, t["key"])
        maxed = lvl >= TECH_MAX
        br = R(PANEL_X + 10 + i * (tw + 8), y4 + 26, tw, 46)
        col = (60, 130, 110) if lvl > 0 else (60, 64, 74)
        draw_button(screen, f_chip, br, t["name"], col,
                    disabled=maxed or pf.money < cost)
        state = f"ур.{lvl}/{TECH_MAX} · {cost}" if not maxed else f"ур.{lvl} — максимум"
        screen.blit(f_tiny.render(state, True, TEXT if not maxed else MUTED),
                    (br.x + 8, br.bottom - 15))
    screen.blit(f_small.render(
        " · ".join(f"{t['name']}: {t['desc']}" for t in TECH_TRACKS), True, MUTED),
        (PANEL_X + 16, y4 + 78))

    # базовая подготовка (уроны атаки/обороны/логистики/морали)
    yb = y4 + 96
    bw = (PANEL_W - 20 - 3 * 8) // 4
    names = {"atk": "АТАКА", "def": "ОБОРОНА", "log": "ЛОГИСТИКА", "mor": "МОРАЛЬ"}
    for i, key in enumerate(["atk", "def", "log", "mor"]):
        br = R(PANEL_X + 10 + i * (bw + 8), yb, bw, 34)
        lvl = pf.tech[key]
        cost = DEV_BASE_COST * (lvl + 1)
        draw_button(screen, f_tiny, br, f"{names[key]} {lvl}", (95, 85, 175),
                    disabled=pf.money < cost)
        screen.blit(f_tiny.render(f"{cost}", True, MUTED), (br.right - 26, br.y + 10))
    y4b = yb + 40

    # уровень призыва: больше людских ресурсов, но меньше дохода
    ci = CONSCRIPT[pf.conscript]
    br2 = R(PANEL_X + 10, y4b + 2, PANEL_W - 20, 36)
    if pf.conscript < len(CONSCRIPT) - 1:
        ccost = game.conscript_cost(pf.fid)
        nxt = CONSCRIPT[pf.conscript + 1]
        label = (f"ПРИЗЫВ: {ci['name']} → {nxt['name']} ({ccost})   "
                 f"люди ×{nxt['rate']:.2f} · доход {int(nxt['income'] * 100)}%")
        draw_button(screen, f_chip, br2, label, (120, 80, 150), disabled=pf.money < ccost)
    else:
        draw_button(screen, f_chip, br2, f"ПРИЗЫВ: {ci['name']} (максимум)",
                    (60, 64, 74), disabled=True)

    # журнал
    y5 = y4b + 50
    screen.blit(f_head.render("Журнал", True, TEXT), (PANEL_X + 16, y5))
    lr = R(PANEL_X + 10, y5 + 26, PANEL_W - 20, H - 24 - (y5 + 26))
    draw_card(screen, lr, (31, 35, 43), BORDER, 9, 1)
    lines = game.log[-10:]
    for i, line in enumerate(lines):
        screen.blit(f_small.render(line, True, TEXT), (lr.x + 12, lr.y + 8 + i * 17))


def draw_region_tab(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    pf = game.factions[game.player] if game.player is not None else game.neutral
    if game.selected is None:
        rr = R(PANEL_X + 10, CONTENT_Y, PANEL_W - 20, 90)
        draw_card(screen, rr, CARD, BORDER, 9, 1)
        screen.blit(f_body.render("Кликните по региону на карте.", True, MUTED),
                    (rr.x + 16, rr.y + 30))
        return
    r = game.regions[game.selected]
    own = ("ваш" if r.owner == game.player else
           ("независимый" if r.owner == NEUTRAL else game.factions[r.owner].name))
    rr = R(PANEL_X + 10, CONTENT_Y, PANEL_W - 20, 150)
    draw_card(screen, rr, CARD, BORDER, 9, 1)
    pygame.draw.rect(screen, faction_color(game, r.owner), (rr.x, rr.y, 6, rr.h),
                     border_top_left_radius=9, border_bottom_left_radius=9)
    screen.blit(f_head.render(f"({r.x},{r.y})  {r.terrain[0]}", True, TEXT), (rr.x + 16, rr.y + 8))
    screen.blit(f_small.render(f"владелец: {own}", True, MUTED), (rr.x + 16, rr.y + 34))
    screen.blit(f_small.render(
        f"Гарнизон {fmt(r.owner_forces())}   Доход {r.income:.2f}/с   Развитие {r.dev}/{MAX_ECON_DEV}",
        True, TEXT), (rr.x + 16, rr.y + 54))
    screen.blit(f_small.render(f"Население {fmt(r.pop)}", True, TEXT),
                (rr.x + 16, rr.y + 74))

    # бой
    fids = [f for f, v in r.forces.items() if v > 0.5]
    if len(fids) > 1:
        screen.blit(f_head.render("Бой за регион", True, (255, 170, 120)), (rr.x + 16, rr.y + 100))
        info = game.battle_preview(r)
        order = sorted(info.items(), key=lambda kv: -kv[1]["troops"])
        bx = rr.x + 150
        for i, (fid, d) in enumerate(order[:2]):
            by = rr.y + 100 + i * 22
            col = faction_color(game, fid)
            name = "независ." if fid == NEUTRAL else game.factions[fid].name
            role = "оборона" if d["owner"] else "атака"
            pygame.draw.rect(screen, col, (bx, by + 3, 10, 10), border_radius=2)
            screen.blit(f_small.render(f"{name[:15]}", True, TEXT), (bx + 16, by))
            screen.blit(f_small.render(f"{fmt(d['troops'])}", True, TEXT), (bx + 190, by))
            screen.blit(f_small.render(f"-{d['taken']:.0f}/с", True, BAD), (bx + 300, by))
            screen.blit(f_small.render(role, True, MUTED), (bx + 380, by))

    # действия — только для игрока; наблюдатель смотрит без кнопок
    if game.player is not None:
        ay = CONTENT_Y + 162
        can = r.owner == game.player
        cost_dev = ECON_DEV_COST * (r.dev + 1)
        draw_button(screen, f_chip, R(PANEL_X + 10, ay, 292, 42), f"НАБРАТЬ ({RECRUIT_COST})",
                    (55, 150, 90), disabled=not (can and pf.money >= RECRUIT_COST
                                                 and pf.manpower >= MANPOWER_PER_RECRUIT))
        draw_button(screen, f_chip, R(PANEL_X + 314, ay, 292, 42), "ДВИНУТЬ (ПКМ)",
                    (60, 120, 200), active=game.move_mode, disabled=not can)
        draw_button(screen, f_chip, R(PANEL_X + 10, ay + 50, PANEL_W - 20, 42),
                    f"РАЗВИТЬ ЭКОНОМИКУ ({cost_dev})   +{int(r.dev*ECON_DEV_INCOME*100)}% → +{int((r.dev+1)*ECON_DEV_INCOME*100)}%",
                    (95, 85, 175), disabled=not (can and r.dev < MAX_ECON_DEV and pf.money >= cost_dev))

    # соседние регионы
    ny = CONTENT_Y + 292
    screen.blit(f_head.render("Соседние регионы", True, TEXT), (PANEL_X + 16, ny - 26))
    mx, my = map_mouse(pygame.mouse.get_pos(), pygame.display.get_surface().get_size())
    oy = getattr(game, "panel_scroll", {}).get(1, 0)     # мышь в системе прокрутки
    my += oy
    for i, n in enumerate(game.neighbors(r)):
        nr = R(PANEL_X + 10, ny + i * 36, PANEL_W - 20, 32)
        hover = nr.collidepoint(mx, my)
        draw_card(screen, nr, CARD2 if hover else CARD, BORDER, 8, 1)
        pygame.draw.rect(screen, faction_color(game, n.owner), (nr.x + 8, nr.y + 7, 5, 18), border_radius=2)
        owner = ("ваш" if n.owner == game.player else
                 ("независ." if n.owner == NEUTRAL else game.factions[n.owner].name))
        screen.blit(f_small.render(f"({n.x},{n.y}) {n.terrain[0]}", True, TEXT), (nr.x + 22, nr.y + 7))
        screen.blit(f_small.render(f"{fmt(n.owner_forces())}", True, TEXT), (nr.x + 250, nr.y + 7))
        tag = ""
        tcol = MUTED
        if n.owner != NEUTRAL and n.owner != game.player:
            if game.allied(game.player, n.owner):
                tag, tcol = "союз", GOOD
            elif game.at_war(game.player, n.owner):
                tag, tcol = "война", BAD
            elif game.has_nap(game.player, n.owner):
                tag, tcol = "пакт", (120, 190, 255)
        screen.blit(f_small.render(owner, True, tcol), (nr.x + 360, nr.y + 7))
        if tag:
            screen.blit(f_tiny.render(tag, True, tcol), (nr.right - 70, nr.y + 10))

    # подсказка по экономике региона
    hy = ny + len(game.neighbors(r)) * 36 + 12
    hr = R(PANEL_X + 10, hy, PANEL_W - 20, 70)
    draw_card(screen, hr, (31, 35, 43), BORDER, 9, 1)
    screen.blit(f_small.render("Доход региона = база × местность × развитие", True, MUTED),
                (hr.x + 12, hr.y + 8))
    screen.blit(f_small.render("Развитие: +25% дохода и +15% людских ресурсов за уровень", True, MUTED),
                (hr.x + 12, hr.y + 28))


def faction_short(name):
    return "".join(w[0] for w in name.split() if w)[:2].upper()


def clip_text(font, text, max_w):
    if font.size(text)[0] <= max_w:
        return text
    cut = text
    while cut and font.size(cut + "…")[0] > max_w:
        cut = cut[:-1]
    return cut + "…"


def draw_relations_matrix(screen, game, fonts, y):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    fids = sorted(game.factions)
    screen.blit(f_head.render("Отношения между фракциями", True, TEXT), (PANEL_X + 16, y))
    label_w = 150
    cell_w = (PANEL_W - 20 - label_w) // len(fids)
    cell_h = 40
    x0 = PANEL_X + 10 + label_w
    gy = y + 26
    for j, fid in enumerate(fids):
        cx = x0 + j * cell_w + cell_w // 2
        img = f_chip.render(faction_short(game.factions[fid].name), True, game.factions[fid].color)
        screen.blit(img, (cx - img.get_width() // 2, gy))
    ry0 = gy + 22
    for i, a in enumerate(fids):
        ry = ry0 + i * cell_h
        screen.blit(f_chip.render(faction_short(game.factions[a].name), True, game.factions[a].color),
                    (PANEL_X + 16, ry + 12))
        screen.blit(f_small.render(clip_text(f_small, game.factions[a].name, label_w - 46), True, MUTED),
                    (PANEL_X + 46, ry + 13))
        for j, b in enumerate(fids):
            cr = R(x0 + j * cell_w + 3, ry + 3, cell_w - 6, cell_h - 6)
            if a == b:
                draw_card(screen, cr, (28, 31, 38), BORDER, 6, 1)
                continue
            if game.allied(a, b):
                col, lab = GOOD, "союз"
            elif game.at_war(a, b):
                col, lab = BAD, "война"
            elif game.has_nap(a, b):
                col, lab = (120, 190, 255), "пакт"
            elif game.has_trade(a, b):
                col, lab = WARN, "торг."
            else:
                col, lab = (96, 102, 114), "—"
            draw_card(screen, cr, mix(col, (12, 14, 18), 0.74), mix(col, (0, 0, 0), 0.35), 6, 1)
            img = f_tiny.render(lab, True, col)
            screen.blit(img, (cr.centerx - img.get_width() // 2, cr.centery - img.get_height() // 2))
    ly = ry0 + len(fids) * cell_h + 8
    lx = PANEL_X + 16
    for col, lab in ((GOOD, "союз"), (BAD, "война"), ((120, 190, 255), "пакт"), (WARN, "торговля")):
        pygame.draw.rect(screen, col, (lx, ly + 3, 12, 12), border_radius=3)
        img = f_tiny.render(lab, True, MUTED)
        screen.blit(img, (lx + 17, ly + 2))
        lx += 17 + img.get_width() + 16


WAR_SORTS = [("time", "по времени"), ("losses", "по потерям"), ("kills", "по нанесённому")]


def draw_wars_tab(screen, game, fonts):
    """Вкладка «Войны»: текущие и прошедшие войны, битвы, потери; сортировка."""
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    observer = game.player is None
    pf = game.factions[game.player] if not observer else game.factions[0]
    y = CONTENT_Y

    # сортировка
    sort = getattr(game, "war_sort", "time")
    sx = PANEL_X + 10
    screen.blit(f_small.render("Сортировка:", True, MUTED), (sx, y + 7))
    sx += 90
    for key, label in WAR_SORTS:
        br = R(sx, y, 118, 24)
        draw_button(screen, f_tiny, br, label, (70, 100, 130), active=(sort == key))
        sx += 124
    y += 32

    # строки войн: у игрока — свои войны, у наблюдателя — все пары
    rows = []
    for f in game.factions.values():
        if not observer and f.fid != pf.fid:
            continue
        for w in f.wars:
            rows.append((f, w))
    # дедупликация: пара (a,b) и (b,a) — одна война; показываем запись стороны a
    seen = set()
    uniq = []
    for f, w in rows:
        pair = tuple(sorted((f.fid, w["fid"])))
        if pair in seen:
            continue
        seen.add(pair)
        uniq.append((f, w))
    rows = uniq

    def sort_key(item):
        f, w = item
        if sort == "losses":
            return -(w["losses"] + w["kills"])
        if sort == "kills":
            return -(w["kills"] - w["losses"])
        return -w["start"]

    rows.sort(key=sort_key)
    if not rows:
        screen.blit(f_body.render("Войн пока не было — тишь и гладь.", True, MUTED),
                    (PANEL_X + 16, y + 8))
        return

    # сводная статистика фракций
    stats = sorted(game.factions.values(),
                   key=lambda f: -(f.kills if observer else 0)) if observer else []
    rh = 44
    for f, w in rows[:12]:
        other = game.factions.get(w["fid"])
        cr = R(PANEL_X + 10, y, PANEL_W - 20, rh)
        active = w["end"] is None
        draw_card(screen, cr, CARD if active else (28, 30, 36), BORDER, 8, 1)
        pygame.draw.rect(screen, f.color, (cr.x + 8, cr.y + 8, 5, rh - 16), border_radius=2)
        pygame.draw.rect(screen, other.color, (cr.x + 15, cr.y + 8, 5, rh - 16), border_radius=2)
        pair = f"{f.name} × {other.name if other else '?'}"
        screen.blit(f_small.render(clip_text(f_small, pair, 330), True,
                                   TEXT if active else MUTED), (cr.x + 26, cr.y + 6))
        mins = int((w["end"] or game.time) - w["start"]) // 60
        state = "ИДЁТ" if active else f"{mins} мин"
        screen.blit(f_tiny.render(state, True, BAD if active else MUTED),
                    (cr.right - 60, cr.y + 6))
        # потери сторон: у f — w['losses'] (свои), w['kills'] — нанесённые
        a_loss = f.losses if not active else f.losses
        line2 = (f"потери {fmt(w['losses'])}   ·   нанесено {fmt(w['kills'])}"
                 f"   ·   доктрины: {DOCTRINES[f.doctrine]['name']} / "
                 f"{DOCTRINES[other.doctrine]['name'] if other else '—'}")
        screen.blit(f_tiny.render(line2, True, MUTED), (cr.x + 26, cr.y + 24))
        y += rh + 6

    # глобальная таблица потерь
    y += 8
    screen.blit(f_head.render("Сводка потерь", True, TEXT), (PANEL_X + 16, y))
    y += 26
    stats = sorted(game.factions.values(), key=lambda f: -f.kills)
    hdr = R(PANEL_X + 10, y, PANEL_W - 20, 22)
    screen.blit(f_tiny.render("страна", True, MUTED), (hdr.x + 26, y + 4))
    screen.blit(f_tiny.render("убито", True, MUTED), (hdr.x + 320, y + 4))
    screen.blit(f_tiny.render("потери", True, MUTED), (hdr.x + 400, y + 4))
    screen.blit(f_tiny.render("K/L", True, MUTED), (hdr.right - 40, y + 4))
    y += 24
    for f in stats:
        rr = R(PANEL_X + 10, y, PANEL_W - 20, 26)
        draw_card(screen, rr, CARD, BORDER, 6, 1)
        pygame.draw.rect(screen, f.color, (rr.x + 8, rr.y + 6, 5, 14), border_radius=2)
        screen.blit(f_small.render(clip_text(f_small, f.name, 280), True, TEXT),
                    (rr.x + 26, rr.y + 5))
        screen.blit(f_small.render(fmt(f.kills), True, GOOD), (rr.x + 320, rr.y + 5))
        screen.blit(f_small.render(fmt(f.losses), True, BAD), (rr.x + 400, rr.y + 5))
        kl = f.kills / max(1.0, f.losses)
        screen.blit(f_small.render(f"{kl:.2f}", True, GOOD if kl >= 1 else WARN),
                    (rr.right - 46, rr.y + 5))
        y += 30


def draw_diplo_tab(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    pf = game.factions[game.player] if game.player is not None else None
    others = [f for f in game.factions.values() if f.fid != game.player]
    y = CONTENT_Y
    for i, f in enumerate(others):
        cr = R(PANEL_X + 10, y, PANEL_W - 20, DIPLO_CARD_H)
        draw_card(screen, cr, CARD, BORDER, 9, 1)
        draw_flag(screen, cr.x + 10, cr.y + 10, 26, f)      # флаг страны
        screen.blit(f_head.render(f.name, True, TEXT), (cr.x + 44, cr.y + 8))
        reln = f.relations.get(game.player, 0)
        rel_name = next(n for t, n in REL_NAMES if reln >= t)
        # вся армия страны и идеология — главные данные о враге
        army_col = GOOD if f.total_troops < (pf.total_troops if pf else 0) * 0.8 else (
            BAD if pf and f.total_troops > pf.total_troops * 1.25 else TEXT)
        screen.blit(f_small.render(f"армия: {fmt(f.total_troops)}", True, army_col),
                    (cr.x + 44, cr.y + 30))
        ideo = IDEOLOGIES[f.ideology]["name"]
        screen.blit(f_small.render(f"идеология: {ideo}", True, (200, 170, 110)),
                    (cr.x + 44, cr.y + 46))
        tags = []
        if pf is not None:
            if game.allied(game.player, f.fid):
                tags.append(("СОЮЗ", GOOD))
            if game.at_war(game.player, f.fid):
                tags.append(("ВОЙНА", BAD))
            if game.has_nap(game.player, f.fid):
                tags.append(("ПАКТ", (120, 190, 255)))
            if game.has_trade(game.player, f.fid):
                tags.append(("ТОРГОВЛЯ", WARN))
        tx = cr.x + 44
        for tname, tcol in tags:
            tw = f_tiny.size(tname)[0] + 14
            pygame.draw.rect(screen, mix(tcol, (0, 0, 0), 0.6), (tx, cr.y + 64, tw, 18), border_radius=4)
            screen.blit(f_tiny.render(tname, True, tcol), (tx + 7, cr.y + 67))
            tx += tw + 6
        screen.blit(f_small.render(f"отношения: {reln} ({rel_name})", True, MUTED),
                    (cr.x + 44, cr.y + 84 - 8))

        # кнопки 2x3
        bw, bh, gap = 96, 26, 6
        bx0 = cr.x + PANEL_W - 20 - (3 * bw + 2 * gap) - 12
        for j, (kind, label) in enumerate(DIPLO_BTNS):
            brow, bcol = divmod(j, 3)
            br = R(bx0 + bcol * (bw + gap), cr.y + 10 + brow * (bh + 6), bw, bh)
            disabled = False
            col = (70, 100, 140)
            if kind == "gift":
                col = (90, 120, 60); disabled = pf is None or pf.money < 60
            elif kind == "alliance":
                col = (70, 140, 90); disabled = game.allied(game.player, f.fid) or game.at_war(game.player, f.fid)
            elif kind == "nap":
                col = (70, 120, 170); disabled = game.has_nap(game.player, f.fid) or game.at_war(game.player, f.fid)
            elif kind == "trade":
                col = (140, 110, 60); disabled = game.has_trade(game.player, f.fid) or game.at_war(game.player, f.fid)
            elif kind == "peace":
                col = (70, 110, 170); disabled = not game.at_war(game.player, f.fid)
            elif kind == "war":
                if game.allied(game.player, f.fid):
                    label = "Разрыв"; col = (150, 90, 90)
                elif game.has_nap(game.player, f.fid):
                    label = "Разрыв пакта"; col = (150, 110, 70)
                else:
                    col = (170, 70, 70); disabled = game.at_war(game.player, f.fid)
            disabled = disabled or game.observer
            draw_button(screen, f_tiny, br, label, col, disabled=disabled)
        y += DIPLO_CARD_H + 8
    draw_relations_matrix(screen, game, fonts, y + 10)


def draw_offers(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    if not game.pending_offers:
        return
    offer = game.pending_offers[0]
    card, accept, refuse = offer_rects()
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill((0, 0, 0, 120))
    screen.blit(ov, (0, 0))
    draw_card(screen, card, (33, 37, 46), ACCENT, 12, 2)
    a = game.factions[offer["from"]]
    screen.blit(f_tiny.render("ДИПЛОМАТИЧЕСКОЕ ПРЕДЛОЖЕНИЕ", True, MUTED), (card.x + 24, card.y + 18))
    screen.blit(f_head.render(f"«{a.name}»", True, a.color), (card.x + 24, card.y + 40))
    line = f"предлагает: {KIND_NAMES[offer['kind']]}"
    if offer["kind"] == "demand":
        line += f"  (дань {offer['amount']})"
    screen.blit(f_body.render(line, True, TEXT), (card.x + 24, card.y + 74))
    rel = a.relations.get(game.player, 0)
    screen.blit(f_small.render(f"Отношения: {rel}", True, MUTED), (card.x + 24, card.y + 104))
    draw_button(screen, f_chip, accept, "ПРИНЯТЬ", (55, 150, 90))
    draw_button(screen, f_chip, refuse, "ОТКЛОНИТЬ", (170, 70, 70))


def draw_choose(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill((8, 9, 12, 235))
    screen.blit(ov, (0, 0))
    title = "ВЫБЕРИТЕ ФРАКЦИЮ"
    screen.blit(f_title.render(title, True, TEXT), (W // 2 - f_title.size(title)[0] // 2, 26))
    sc = SCENARIOS[game.scenario]
    sub = f"сценарий «{sc['name']}» · {sc['desc']}"
    screen.blit(f_small.render(sub, True, MUTED), (W // 2 - f_small.size(sub)[0] // 2, 62))
    screen.blit(f_small.render("страны различаются размером, экономикой и армией",
                               True, MUTED), (W // 2 - 200, 78))
    cards, per_row = choose_cards(len(game.factions))
    h = cards[0].h
    defs = [(f.name, f.color, f.trait) for f in game.factions.values()]
    for i, (name, color, trait) in enumerate(defs):
        cr = cards[i]
        draw_card(screen, cr, CARD, BORDER, 12, 1)
        head_h = 76 if h < 360 else 96
        pygame.draw.rect(screen, color, (cr.x, cr.y, cr.w, head_h),
                         border_top_left_radius=12, border_top_right_radius=12)
        screen.blit(f_head.render(clip_text(f_head, name, cr.w - 32), True, (255, 255, 255)),
                    (cr.x + 16, cr.y + 14))
        screen.blit(f_small.render(clip_text(f_small, trait, cr.w - 32), True, (240, 240, 240)),
                    (cr.x + 16, cr.y + 38))
        f = game.factions[i]
        kind = f.nation["name"] if f.nation else ""
        ideo = IDEOLOGIES[f.ideology]["name"]
        draw_flag(screen, cr.x + cr.w - 56, cr.y + 14, 22, f)
        screen.blit(f_body.render(f"регионов: {len(f.regions)}", True, TEXT),
                    (cr.x + 16, cr.y + head_h + 14))
        screen.blit(f_body.render(f"казна: {int(f.money)}", True, TEXT),
                    (cr.x + 16, cr.y + head_h + 34))
        screen.blit(f_body.render(f"армия: {fmt(f.total_troops)}", True, TEXT),
                    (cr.x + 16, cr.y + head_h + 54))
        screen.blit(f_body.render(clip_text(f_body, f"идеология: {ideo}", cr.w - 32),
                                  True, (200, 170, 110)), (cr.x + 16, cr.y + head_h + 74))
        screen.blit(f_small.render(f"клавиша {i + 1}", True, MUTED), (cr.x + 16, cr.y + h - 68))
        draw_button(screen, f_chip, R(cr.x + 16, cr.y + h - 44, cr.w - 32, 32),
                    "ИГРАТЬ", color)
    # карточка наблюдателя
    cr = cards[len(defs)]
    col = (150, 155, 168)
    draw_card(screen, cr, (32, 35, 43), col, 12, 2)
    head_h = 76 if h < 360 else 96
    pygame.draw.rect(screen, col, (cr.x, cr.y, cr.w, head_h),
                     border_top_left_radius=12, border_top_right_radius=12)
    screen.blit(f_head.render("НАБЛЮДАТЕЛЬ", True, (255, 255, 255)), (cr.x + 16, cr.y + 14))
    screen.blit(f_small.render("партия ИИ против ИИ", True, (240, 240, 240)), (cr.x + 16, cr.y + 38))
    for j, line in enumerate(("все фракции за ИИ", "войны и дипломатия", "на автопилоте")):
        screen.blit(f_body.render(line, True, TEXT), (cr.x + 16, cr.y + head_h + 14 + j * 20))
    screen.blit(f_small.render(f"клавиша {len(defs) + 1}", True, MUTED), (cr.x + 16, cr.y + h - 68))
    draw_button(screen, f_chip, R(cr.x + 16, cr.y + h - 44, cr.w - 32, 32),
                "СМОТРЕТЬ", (85, 92, 106))
    # авторство и кнопка возврата в меню
    credit = f_small.render(version.CREDIT, True, MUTED)
    screen.blit(credit, (W - credit.get_width() - 16, H - credit.get_height() - 12))
    draw_button(screen, f_chip, R(16, H - 48, 120, 32), "В МЕНЮ", (90, 60, 60))


def draw_bottom(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    y = MAP_Y + MAP_H + 10
    card = R(MAP_X, y, MAP_W, H - y - 14)
    draw_card(screen, card, PANEL, BORDER, 10, 1)
    screen.blit(f_small.render(
        "ЛКМ — выбрать · ПКМ — двинуть · SHIFT — все · ПРОБЕЛ — пауза · S — скорость · G — цифры · N — названия · TAB — вкладки · ESC — меню",
        True, MUTED), (card.x + 14, card.y + 9))
    ly = card.y + 36
    x = card.x + 14
    for f in game.factions.values():
        pygame.draw.rect(screen, f.color, (x, ly + 1, 13, 13), border_radius=3)
        name = f.name + (" (вы)" if f.fid == game.player else "")
        img = f_small.render(name, True, TEXT if f.fid == game.player else MUTED)
        screen.blit(img, (x + 19, ly))
        x += 19 + img.get_width() + 20
    st = "ПАУЗА" if game.paused else f"ИДЁТ ВРЕМЯ ×{SPEEDS[game.speed_idx]}"
    screen.blit(f_small.render(st, True, WARN if game.paused else GOOD),
                (card.x + 14, card.y + 60))
    if game.winner:
        screen.blit(f_head.render(game.winner, True, WARN),
                    (card.right - 200, card.y + 58))


def draw_replay_map(screen, game, fonts, snap):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    rng = R(MAP_X, MAP_Y, MAP_W, MAP_H)
    pygame.draw.rect(screen, (13, 14, 18), rng)
    # заливки полупрозрачным цветом — единый стиль с игровой картой
    fills = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
    for r in game.regions:
        owner = snap["owner"][r.rid]
        base = faction_color(game, owner)
        pygame.draw.polygon(fills, base + (205,),
                            [(px - MAP_X, py - MAP_Y) for px, py in region_poly(r.x, r.y)])
    screen.blit(fills, (MAP_X, MAP_Y))
    ls = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
    for r in game.regions:
        for ln in sublines(r.x, r.y):
            pygame.draw.lines(ls, (255, 255, 255, 26), False,
                              [(px - MAP_X, py - MAP_Y) for px, py in ln], 1)
    screen.blit(ls, (MAP_X, MAP_Y))
    screen.blit(terrain_tex(), (MAP_X, MAP_Y), special_flags=pygame.BLEND_RGBA_MULT)
    # тёмные границы владений
    fx = pygame.Surface((MAP_W, MAP_H), pygame.SRCALPHA)
    for r in game.regions:
        for dx, dy in ((1, 0), (0, 1)):
            nx, ny = r.x + dx, r.y + dy
            if not (0 <= nx < GRID and 0 <= ny < GRID):
                continue
            n = game.region_at(nx, ny)
            if snap["owner"][n.rid] == snap["owner"][r.rid]:
                continue
            pts = edge_pts('v', r.x + 1, r.y) if dx == 1 else edge_pts('h', r.x, r.y + 1)
            mp = [(px - MAP_X, py - MAP_Y) for px, py in pts]
            pygame.draw.lines(fx, (10, 11, 15, 200), False, mp, 2)
    screen.blit(fx, (MAP_X, MAP_Y))
    # столицы-флаги + гарнизоны в тысячах
    for r in game.regions:
        x = MAP_X + r.x * TILE
        y = MAP_Y + r.y * TILE
        owner = snap["owner"][r.rid]
        if snap["cap"][r.rid] is not None and snap["cap"][r.rid] == owner:
            draw_flag(screen, x + TILE - 26, y + 5, 13,
                      game.factions.get(owner))
        forces = snap["forces"][r.rid]
        if forces > 0:
            rr = counter_rect(f_tiny, x + TILE // 2, y + TILE // 2, forces)
            draw_counter_rect(screen, f_tiny, rr, faction_color(game, owner), forces)
    # названия стран на территориях (крупнейший кластер каждой страны)
    if getattr(game, "show_names", True):
        regions_of = {}
        for r in game.regions:
            if snap["owner"][r.rid] != NEUTRAL:
                regions_of.setdefault(snap["owner"][r.rid], []).append(r)
        name_font = pygame.font.SysFont("segoeui", max(15, int(TILE * 0.26)), bold=True)
        for fid, regs in regions_of.items():
            f = game.factions.get(fid)
            if f is None:
                continue
            mx = sum(r.x for r in regs) / len(regs)
            my = sum(r.y for r in regs) / len(regs)
            home = min(regs, key=lambda r: (r.x - mx) ** 2 + (r.y - my) ** 2)
            img = render_outline(name_font, f.name.upper(),
                                 fill=(255, 255, 255), outline=(10, 10, 14), thickness=2)
            lbl = pygame.Surface((img.get_width() + 8, img.get_height() + 4), pygame.SRCALPHA)
            lbl.blit(img, (4, 2))
            lbl.set_alpha(175)
            px = int(MAP_X + (home.x + 0.5) * TILE - lbl.get_width() / 2)
            py = int(MAP_Y + (home.y + 0.5) * TILE - lbl.get_height() / 2)
            px = max(MAP_X + 4, min(px, MAP_X + MAP_W - lbl.get_width() - 4))
            py = max(MAP_Y + 4, min(py, MAP_Y + MAP_H - lbl.get_height() - 4))
            screen.blit(lbl, (px, py))
    pygame.draw.rect(screen, (72, 78, 90), rng, width=2, border_radius=2)


def draw_replay_panel(screen, game, fonts, snap):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    p = R(PANEL_X, MAP_Y, PANEL_W, H - MAP_Y - 12)
    draw_card(screen, p, PANEL, BORDER, 12, 1)
    screen.blit(f_head.render("Ход партии", True, TEXT), (PANEL_X + 16, MAP_Y + 12))
    stats = []
    n = len(snap["owner"])
    total_regs = max(1, n)
    for f in game.factions.values():
        regs = sum(1 for o in snap["owner"] if o == f.fid)
        tr = int(sum(snap["forces"][i] for i in range(n) if snap["owner"][i] == f.fid))
        stats.append((f, regs, tr))
    stats.sort(key=lambda t: (-t[1], -t[2]))
    y = MAP_Y + 48
    max_regs = max((s[1] for s in stats), default=1) or 1
    leader = stats[0] if stats else None
    for f, regs, tr in stats:
        cr = R(PANEL_X + 10, y, PANEL_W - 20, 66)
        draw_card(screen, cr, CARD, BORDER, 9, 1)
        draw_flag(screen, cr.x + 10, cr.y + 10, 20, f)
        tag = "лидер" if leader and f is leader[0] else ""
        screen.blit(f_head.render(clip_text(f_head, f.name, cr.w - 150), True, TEXT),
                    (cr.x + 58, cr.y + 6))
        if tag:
            screen.blit(f_tiny.render("ЛИДЕР", True, WARN), (cr.right - 58, cr.y + 10))
        screen.blit(f_small.render(f"регионов {regs}   ·   войск {fmt(tr)}", True, MUTED),
                    (cr.x + 58, cr.y + 28))
        draw_bar(screen, R(cr.x + 58, cr.y + 50, cr.w - 80, 8), regs / max_regs, f.color)
        y += 74
    # график доли территорий по времени + маркер текущего кадра
    gh = 110
    gr = R(PANEL_X + 10, y + 8, PANEL_W - 20, gh)
    draw_card(screen, gr, (24, 27, 34), BORDER, 9, 1)
    screen.blit(f_small.render("Территории по времени", True, MUTED), (gr.x + 12, gr.y + 6))
    hist = game.history
    if len(hist) >= 2:
        step = max(1, len(hist) // 150)
        for i in range(0, len(hist), step):
            x = gr.x + 10 + int((gr.w - 20) * i / max(1, len(hist) - 1))
            ycur = gr.y + 26
            hgt = gr.h - 36
            for fid in game.factions:
                cnt = hist[i]["owner"].count(fid)
                hh = int(hgt * cnt / total_regs)
                if hh > 0:
                    pygame.draw.rect(screen, faction_color(game, fid), (x, ycur, 3, hh))
                ycur += hh
        # маркер текущей позиции
        mx = gr.x + 10 + int((gr.w - 20) * game.replay_idx / max(1, len(hist) - 1))
        pygame.draw.line(screen, (240, 244, 250), (mx, gr.y + 24), (mx, gr.bottom - 10), 2)
        pygame.draw.circle(screen, (240, 244, 250), (mx, gr.y + 24), 3)
    tr = R(PANEL_X + 10, y + gh + 16, PANEL_W - 20, 66)
    draw_card(screen, tr, (31, 35, 43), BORDER, 9, 1)
    screen.blit(f_small.render("Итог: " + (game.winner or "партия продолжается"), True, WARN),
                (tr.x + 12, tr.y + 10))
    screen.blit(f_small.render("Клик по полосе — перемотка. «СОХРАНИТЬ» — файл в replays/.",
                               True, MUTED), (tr.x + 12, tr.y + 34))
    saved_note = getattr(game, "replay_saved", False)
    screen.blit(f_small.render("автосохранение выполнено" if saved_note
                               else "автосохранение — при завершении партии",
                               True, GOOD if saved_note else MUTED), (tr.x + 12, tr.y + 52))


def draw_replay(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    screen.fill(BG)
    pygame.draw.rect(screen, (23, 26, 32), (0, 0, W, TOPBAR_H))
    pygame.draw.line(screen, BORDER, (0, TOPBAR_H), (W, TOPBAR_H), 1)
    screen.blit(f_head.render("ПРОСМОТР ПАРТИИ", True, TEXT), (16, 6))
    screen.blit(f_tiny.render("повтор хода игры", True, MUTED), (16, 28))
    snap = game.replay_snapshot()
    if snap is None:
        screen.blit(f_body.render("Нет данных для повтора.", True, MUTED), (MAP_X, MAP_Y))
        return
    total = max(1, len(game.history) - 1)
    idx = game.replay_idx
    screen.blit(f_small.render(f"{idx + 1} / {len(game.history)}   ·   {game.history[idx]['t']:.0f} с",
                               True, TEXT), (W - 280, 16))

    draw_replay_map(screen, game, fonts, snap)
    draw_replay_panel(screen, game, fonts, snap)

    cy = MAP_Y + MAP_H + 10
    card = R(MAP_X, cy, MAP_W, H - cy - 14)
    draw_card(screen, card, PANEL, BORDER, 10, 1)
    bar = replay_bar_rect()
    frac = idx / total
    pygame.draw.rect(screen, (48, 52, 62), bar, border_radius=4)
    pygame.draw.rect(screen, ACCENT, (bar.x, bar.y, int(bar.w * frac), bar.h), border_radius=4)
    hx = bar.x + int(bar.w * frac)
    pygame.draw.circle(screen, (240, 244, 250), (hx, bar.centery), 8)
    pygame.draw.circle(screen, ACCENT, (hx, bar.centery), 8, 2)

    btns = replay_btns()
    draw_button(screen, f_chip, btns["play"], "ПАУЗА" if game.replay_playing else "ПУСК",
                (200, 120, 60) if game.replay_playing else (55, 170, 95))
    draw_button(screen, f_chip, btns["back"], "«", (70, 80, 100))
    draw_button(screen, f_chip, btns["fwd"], "»", (70, 80, 100))
    draw_button(screen, f_chip, btns["speed"], f"×{int(game.replay_speed)}", (110, 90, 180))
    if btns["save"] is not None:
        draw_button(screen, f_chip, btns["save"], "СОХРАНИТЬ", (70, 120, 90))
    draw_button(screen, f_chip, btns["exit"], "ВЫХОД", (150, 70, 70))


def draw_end(screen, game, fonts):
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    ov = pygame.Surface((W, H), pygame.SRCALPHA)
    ov.fill((6, 7, 10, 222))
    screen.blit(ov, (0, 0))
    msg = f_title.render(game.winner or "", True, WARN)
    screen.blit(msg, (W // 2 - msg.get_width() // 2, 92))
    sub = f_body.render(f"партия длилась {game.time / 60:.1f} мин", True, MUTED)
    screen.blit(sub, (W // 2 - sub.get_width() // 2, 136))
    cards = list(game.factions.values())
    w, gap = 250, 20
    x0 = (W - (len(cards) * w + (len(cards) - 1) * gap)) // 2
    y = H // 2 - 70
    for i, f in enumerate(cards):
        cr = R(x0 + i * (w + gap), y, w, 190)
        draw_card(screen, cr, CARD, BORDER, 12, 1)
        pygame.draw.rect(screen, f.color, (cr.x, cr.y, cr.w, 8),
                         border_top_left_radius=12, border_top_right_radius=12)
        screen.blit(f_head.render(f.name, True, TEXT), (cr.x + 16, cr.y + 20))
        if f.fid == game.player:
            screen.blit(f_small.render("ВЫ", True, GOOD), (cr.x + 16, cr.y + 46))
        screen.blit(f_body.render(f"Регионы: {len(f.regions)}", True, TEXT), (cr.x + 16, cr.y + 76))
        screen.blit(f_body.render(f"Войска: {fmt(f.total_troops)}", True, TEXT), (cr.x + 16, cr.y + 104))
        screen.blit(f_body.render(f"Казна: {int(f.money)}", True, TEXT), (cr.x + 16, cr.y + 132))
        screen.blit(f_small.render("в игре" if f.alive else "уничтожена", True, GOOD if f.alive else BAD),
                    (cr.x + 16, cr.y + 160))
    watch, again, menu = end_button_rects(with_menu=game.on_exit is not None)
    draw_button(screen, f_chip, watch, "ПРОСМОТР ПАРТИИ", ACCENT)
    draw_button(screen, f_chip, again, "НОВАЯ ИГРА", (70, 140, 90))
    if menu is not None:
        draw_button(screen, f_chip, menu, "В МЕНЮ", (150, 70, 70))


def draw(screen, game, fonts):
    screen.fill(BG)
    f_title, f_head, f_body, f_small, f_tiny, f_num, f_front, f_chip = fonts
    if game.replay:
        draw_replay(screen, game, fonts)
        return
    if game.choosing:
        draw_choose(screen, game, fonts)
        return
    draw_topbar(screen, game, fonts)
    draw_map(screen, game, fonts)

    # панель
    p = R(PANEL_X, MAP_Y, PANEL_W, H - MAP_Y - 12)
    draw_card(screen, p, PANEL, BORDER, 12, 1)
    for i, (rect, label) in enumerate(zip(tab_rects(), TAB_LABELS)):
        draw_button(screen, f_chip, rect, label,
                    ACCENT if game.tab == i else (48, 53, 64), active=(game.tab == i))
    # контент вкладки: рисуется в клип-область под заголовком вкладок,
    # вертикальная прокрутка — колёсиком (game.panel_scroll)
    tab_draws = {0: draw_overview_tab, 1: draw_region_tab,
                 2: draw_diplo_tab, 3: draw_wars_tab}
    clip = pygame.Rect(PANEL_X + 2, CONTENT_Y + 2, PANEL_W - 4, H - CONTENT_Y - 14)
    oy = game.panel_scroll.get(game.tab, 0)
    sub = pygame.Surface((PANEL_W, clip.h), pygame.SRCALPHA)
    # сдвиг: абсолютные координаты вкладки -> локальные координаты sub-surface
    # (панель начинается в CONTENT_Y, прокрутка добавляет oy)
    shifted = _ShiftedSurface(sub, -PANEL_X, -(CONTENT_Y + 2) - oy)
    # на время отрисовки вкладки pygame.draw направляется через фассад со сдвигом
    real_draw = pygame.draw
    pygame.draw = _ShiftDraw(shifted)
    try:
        tab_draws[game.tab](shifted, game, fonts)
    finally:
        pygame.draw = real_draw
    screen.blit(sub, (clip.x, clip.y))

    # нижняя панель управления
    draw_bottom(screen, game, fonts)
    draw_offers(screen, game, fonts)

    if game.winner:
        draw_end(screen, game, fonts)


class _ShiftDraw:
    """Фассад pygame.draw со сдвигом координат для прокрутки панелей."""
    _orig = pygame.draw     # оригинальный модуль, пока он ещё не подменён

    def __init__(self, proxy):
        self._p = proxy

    def rect(self, s, color, rect, *a, **k):
        return self._orig.rect(self._p._surf, color, self._p._r(rect), *a, **k)

    def ellipse(self, s, color, rect, *a, **k):
        return self._orig.ellipse(self._p._surf, color, self._p._r(rect), *a, **k)

    def arc(self, s, color, rect, *a, **k):
        return self._orig.arc(self._p._surf, color, self._p._r(rect), *a, **k)

    def polygon(self, s, color, pts, *a, **k):
        return self._orig.polygon(self._p._surf, color, [self._p._p(pt) for pt in pts], *a, **k)

    def circle(self, s, color, pos, r, *a, **k):
        return self._orig.circle(self._p._surf, color, self._p._p(pos), r, *a, **k)

    def line(self, s, color, p1, p2, *a, **k):
        return self._orig.line(self._p._surf, color, self._p._p(p1), self._p._p(p2), *a, **k)

    def lines(self, s, color, closed, pts, *a, **k):
        return self._orig.lines(self._p._surf, color, closed, [self._p._p(pt) for pt in pts], *a, **k)

    def aaline(self, s, color, p1, p2, *a, **k):
        return self._orig.aaline(self._p._surf, color, self._p._p(p1), self._p._p(p2), *a, **k)

    def aalines(self, s, color, closed, pts, *a, **k):
        return self._orig.aalines(self._p._surf, color, closed, [self._p._p(pt) for pt in pts], *a, **k)


class _ShiftedSurface:
    """Прокси над Surface: сдвигает Y на -oy в draw-функциях вкладок.

    Функции панели рисуют в абсолютных координатах (PANEL_X, CONTENT_Y+…).
    Прокси уходит Y на -oy, поэтому при blit в клип-область контент
    прокручивается, а клип обрезает всё лишнее."""
    def __init__(self, surf, dx, dy):
        self._surf = surf
        self._dx = dx          # PANEL_X -> 0
        self._dy = dy          # -oy
        self.get_size = surf.get_size
        self.get_width = surf.get_width
        self.get_height = surf.get_height

    def _p(self, pos):
        # точка из абсолютных координат -> локальные координаты sub-surface
        if isinstance(pos, (tuple, list)) and len(pos) >= 2:
            return (pos[0] + self._dx, pos[1] + self._dy)
        return pos

    def _r(self, rect):
        r = pygame.Rect(rect)
        r.x += self._dx
        r.y += self._dy
        return r

    def blit(self, src, dest, *a, **k):
        return self._surf.blit(src, self._p(dest), *a, **k)

    def fill(self, color, rect=None, *a, **k):
        return self._surf.fill(color, self._r(rect) if rect else None, *a, **k)

    def draw(self, what, *args, **kwargs):
        # сигнатура без surface: draw("rect", color, rect, **kw),
        # draw("polygon", color, points, **kw), draw("circle", color, pos, r),
        # draw("line(s)", color, p1, p2, **kw)
        # ВАЖНО: pygame.draw сейчас может быть подменён фассадом _ShiftDraw,
        # поэтому зовём оригинальный модуль напрямую — иначе двойной сдвиг.
        args = list(args)
        if what in ("rect", "ellipse", "arc"):
            args[1] = self._r(args[1])
        elif what == "polygon":
            args[1] = [self._p(pt) for pt in args[1]]
        elif what == "circle":
            args[1] = self._p(args[1])
        elif what in ("line", "lines"):
            args[1] = self._p(args[1])
            if len(args) > 2 and isinstance(args[2], (tuple, list)):
                if isinstance(args[2][0], (tuple, list)):
                    args[2] = [self._p(pt) for pt in args[2]]
                else:
                    args[2] = self._p(args[2])
        return getattr(_ShiftDraw._orig, what)(self._surf, *args, **kwargs)


# ============================ ВВОД ============================
def tile_under(game, pos):
    x, y = pos
    if MAP_X <= x < MAP_X + MAP_W and MAP_Y <= y < MAP_Y + MAP_H:
        return (y - MAP_Y) // TILE * GRID + (x - MAP_X) // TILE
    return None


def choose_cards(n=None):
    """Карточки выбора фракций: подстраиваются под их число (2–8 + наблюдатель)."""
    n = (len(FACTION_DEFS) if n is None else n) + 1     # + карточка наблюдателя
    per_row = min(5, max(3, (n + 1) // 2))
    rows = (n + per_row - 1) // per_row
    w = min(236, (W - 120 - (per_row - 1) * 14) // per_row)
    h = 290 if rows > 1 else 380
    x0 = (W - (per_row * w + (per_row - 1) * 14)) // 2
    y0 = max(88, (H - 90 - rows * (h + 14)) // 2 + 60)
    return [R(x0 + (i % per_row) * (w + 14), y0 + (i // per_row) * (h + 14), w, h)
            for i in range(n)], per_row


def handle_click(game, pos, button):
    # прокрутка вкладки панели колёсиком
    if button in (4, 5) and not game.choosing and not game.replay:
        sc = game.panel_scroll.get(game.tab, 0)
        game.panel_scroll[game.tab] = max(0, sc + (60 if button == 5 else -60))
        return
    if game.replay:
        if button == 1:
            n = len(game.history)
            b = replay_btns()
            if b["play"].collidepoint(pos):
                if not game.replay_playing and game.replay_pos >= n - 1:
                    game.replay_pos, game.replay_idx = 0.0, 0
                game.replay_playing = not game.replay_playing
            elif b["back"].collidepoint(pos):
                game.replay_pos = max(0.0, game.replay_pos - 5)
                game.replay_idx = int(game.replay_pos)
                game.replay_playing = False
            elif b["fwd"].collidepoint(pos):
                game.replay_pos = min(float(max(0, n - 1)), game.replay_pos + 5)
                game.replay_idx = int(game.replay_pos)
                game.replay_playing = False
            elif b["speed"].collidepoint(pos):
                game.replay_speed = {1.0: 2.0, 2.0: 4.0, 4.0: 1.0}.get(game.replay_speed, 1.0)
            elif b["exit"].collidepoint(pos):
                game.replay = False
            elif b.get("save") is not None and b["save"].collidepoint(pos):
                import replays
                p = replays.save_replay(game)
                game.log_msg("Повтор сохранён в replays/." if p else "Не удалось сохранить повтор.")
                game.replay_saved = True
            else:
                bar = replay_bar_rect()
                if bar.inflate(0, 18).collidepoint(pos) and n > 1:
                    frac = (pos[0] - bar.x) / max(1, bar.w)
                    game.replay_pos = max(0.0, min(1.0, frac)) * (n - 1)
                    game.replay_idx = int(game.replay_pos)
                    game.replay_playing = False
        return
    if game.choosing:
        if button == 1:
            cards, per_row = choose_cards(len(game.factions))
            if R(16, H - 48, 120, 32).collidepoint(pos) and game.on_exit:
                game.exit_requested = True
                return
            for i, cr in enumerate(cards):
                if cr.collidepoint(pos):
                    if i < len(game.factions):
                        game.choose_faction(i)
                    else:
                        game.choose_faction(None, observer=True)
                    return
        return
    if game.winner:
        if button == 1:
            watch, again, menu = end_button_rects(with_menu=game.on_exit is not None)
            if watch.collidepoint(pos):
                game.start_replay()
            elif again.collidepoint(pos):
                game.__init__(game.scenario, {
                    "on_exit": game.on_exit,
                    "show_names": game.show_names,
                    "show_numbers": game.show_numbers,
                })
            elif menu is not None and menu.collidepoint(pos):
                game.exit_requested = True
        return
    # модальное предложение
    if game.pending_offers:
        card, accept, refuse = offer_rects()
        if button == 1 and accept.collidepoint(pos):
            game.resolve_offer(game.pending_offers.pop(0), True)
            return
        if button == 1 and refuse.collidepoint(pos):
            game.resolve_offer(game.pending_offers.pop(0), False)
            return
        return

    # верхняя панель
    if button == 1 and BTN_PAUSE.collidepoint(pos):
        game.paused = not game.paused
        return
    if button == 1 and BTN_SPEED.collidepoint(pos):
        game.speed_idx = (game.speed_idx + 1) % len(SPEEDS)
        return
    if button == 1 and BTN_NUM.collidepoint(pos):
        game.show_numbers = not game.show_numbers
        return

    # вкладки
    for i, tr in enumerate(tab_rects()):
        if button == 1 and tr.collidepoint(pos):
            game.tab = i
            return

    # координаты внутри прокрученной вкладки: экранная y = вкладочная − oy,
    # поэтому обратное преобразование — просто прибавить oy.
    if pos[1] >= CONTENT_Y and pos[0] >= PANEL_X:
        oy = game.panel_scroll.get(game.tab, 0)
        pos = (pos[0], pos[1] + oy)

    if game.player is None:
        # наблюдатель: только выбор региона на карте
        rid = tile_under(game, pos)
        if rid is not None:
            game.selected = rid
        return

    pf = game.factions[game.player]
    r = game.regions[game.selected] if game.selected is not None else None

    if game.tab == 1 and r is not None:
        ay = CONTENT_Y + 162
        if button == 1 and R(PANEL_X + 10, ay, 292, 42).collidepoint(pos):
            game.recruit(r.rid)
            return
        if button == 1 and R(PANEL_X + 314, ay, 292, 42).collidepoint(pos):
            if r.owner == game.player:
                game.move_mode = not game.move_mode
            return
        if button == 1 and R(PANEL_X + 10, ay + 50, PANEL_W - 20, 42).collidepoint(pos):
            game.develop_econ(r.rid)
            return
        for i, n in enumerate(game.neighbors(r)):
            nr = R(PANEL_X + 10, CONTENT_Y + 292 + i * 36, PANEL_W - 20, 32)
            if button == 1 and nr.collidepoint(pos):
                game.selected = n.rid
                if n.owner != game.player:
                    game.move_mode = False
                return

    if game.tab == 0:
        y3 = CONTENT_Y + 24 + 2 * 60 + 4 + 56
        # доктрины: 3 кнопки
        dw = (PANEL_W - 20 - 2 * 8) // 3
        for i in range(len(DOCTRINES)):
            br = R(PANEL_X + 10 + i * (dw + 8), y3 + 26, dw, 56)
            if button == 1 and br.collidepoint(pos):
                if i != game.factions[game.player].doctrine:
                    game.set_doctrine(game.player, i)
                return
        # технологии: 4 кнопки
        y4 = y3 + 108
        tw = (PANEL_W - 20 - 3 * 8) // 4
        for i, t in enumerate(TECH_TRACKS):
            br = R(PANEL_X + 10 + i * (tw + 8), y4 + 26, tw, 46)
            if button == 1 and br.collidepoint(pos):
                game.develop_tech2(game.player, t["key"])
                return
        # базовая подготовка
        yb = y4 + 96
        bw = (PANEL_W - 20 - 3 * 8) // 4
        for i, key in enumerate(["atk", "def", "log", "mor"]):
            br = R(PANEL_X + 10 + i * (bw + 8), yb, bw, 34)
            if button == 1 and br.collidepoint(pos):
                game.develop_tech(game.player, key)
                return
        br2 = R(PANEL_X + 10, yb + 42, PANEL_W - 20, 36)
        if button == 1 and br2.collidepoint(pos):
            game.raise_conscript()
            return

    if game.tab == 2:
        others = [f for f in game.factions.values() if f.fid != game.player]
        y = CONTENT_Y
        for f in others:
            cr = R(PANEL_X + 10, y, PANEL_W - 20, DIPLO_CARD_H)
            bw, bh, gap = 96, 26, 6
            bx0 = cr.x + PANEL_W - 20 - (3 * bw + 2 * gap) - 12
            for j, (kind, label) in enumerate(DIPLO_BTNS):
                brow, bcol = divmod(j, 3)
                br = R(bx0 + bcol * (bw + gap), cr.y + 10 + brow * (bh + 6), bw, bh)
                if button == 1 and br.collidepoint(pos):
                    if kind == "war":
                        if game.allied(game.player, f.fid):
                            game.player_propose("break_alliance", f.fid)
                        elif game.has_nap(game.player, f.fid):
                            game.player_propose("break_nap", f.fid)
                        else:
                            game.player_propose("war", f.fid)
                    else:
                        game.player_propose(kind, f.fid)
                    return
            y += DIPLO_CARD_H + 8

    if game.tab == 3:
        sx = PANEL_X + 100
        for key, _ in WAR_SORTS:
            br = R(sx, CONTENT_Y, 118, 24)
            if button == 1 and br.collidepoint(pos):
                game.war_sort = key
                return
            sx += 124

    # карта
    rid = tile_under(game, pos)
    if rid is None:
        return
    if button == 3:
        if game.selected is not None and game.selected != rid:
            src = game.regions[game.selected]
            dst = game.regions[rid]
            if dst in game.neighbors(src):
                frac = 0.95 if (pygame.key.get_mods() & pygame.KMOD_SHIFT) else 0.6
                game.send_move(src.rid, dst.rid, game.player, frac)
        return
    if game.move_mode and game.selected is not None and rid != game.selected:
        src = game.regions[game.selected]
        dst = game.regions[rid]
        if dst in game.neighbors(src) and src.owner == game.player:
            game.send_move(src.rid, dst.rid, game.player, 0.6)
            game.move_mode = False
            return
    game.selected = rid
    if game.regions[rid].owner == game.player:
        game.tab = 1
    if game.regions[rid].owner != game.player:
        game.move_mode = False


def handle_key(game, key):
    if key == pygame.K_F11:
        game.fullscreen = not game.fullscreen
        try:
            if game.fullscreen:
                pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                pygame.display.set_mode((W, H), pygame.RESIZABLE)
        except Exception:
            pass
        return
    if game.replay:
        n = len(game.history)
        if key == pygame.K_SPACE:
            if not game.replay_playing and game.replay_pos >= n - 1:
                game.replay_pos, game.replay_idx = 0.0, 0
            game.replay_playing = not game.replay_playing
        elif key == pygame.K_ESCAPE:
            game.replay = False
        elif key == pygame.K_LEFT:
            game.replay_pos = max(0.0, game.replay_pos - 3)
            game.replay_idx = int(game.replay_pos)
            game.replay_playing = False
        elif key == pygame.K_RIGHT:
            game.replay_pos = min(float(max(0, n - 1)), game.replay_pos + 3)
            game.replay_idx = int(game.replay_pos)
            game.replay_playing = False
        return
    if game.choosing:
        if key == pygame.K_ESCAPE and game.on_exit:
            game.exit_requested = True
            return
        n = len(game.factions)
        if pygame.K_1 <= key <= pygame.K_9 and key - pygame.K_1 < n:
            game.choose_faction(key - pygame.K_1)
        elif key - pygame.K_1 == n or key == pygame.K_0:
            game.choose_faction(None, observer=True)
        return
    if key == pygame.K_SPACE:
        game.paused = not game.paused
    elif key == pygame.K_s:
        game.speed_idx = (game.speed_idx + 1) % len(SPEEDS)
    elif key == pygame.K_m and game.selected is not None:
        game.move_mode = not game.move_mode
    elif key == pygame.K_g:
        game.show_numbers = not game.show_numbers
    elif key == pygame.K_n:
        game.show_names = not game.show_names
    elif key == pygame.K_TAB:
        game.tab = (game.tab + 1) % len(TAB_LABELS)
    elif key == pygame.K_ESCAPE:
        if game.on_exit:
            game.exit_requested = True
        else:
            game.move_mode = False


# ============================ ЗАПУСК ============================
def make_fonts():
    return (pygame.font.SysFont("segoeui", 22, bold=True),
            pygame.font.SysFont("segoeui", 17, bold=True),
            pygame.font.SysFont("segoeui", 14),
            pygame.font.SysFont("segoeui", 12),
            pygame.font.SysFont("segoeui", 11, bold=True),
            pygame.font.SysFont("segoeui", 18, bold=True),
            pygame.font.SysFont("segoeui", 26, bold=True),
            pygame.font.SysFont("segoeui", 13, bold=True))


def shot_mode(argv):
    """Автотест-режим: проматывает партию и сохраняет кадр в PNG (без окна).

    Ключи: --shot ПУТЬ [--ticks N] [--faction N] [--scenario ID] [--observer]
           [--numbers] [--no-names]
    """
    import os
    import sys
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    out = argv[argv.index("--shot") + 1]
    ticks = int(argv[argv.index("--ticks") + 1]) if "--ticks" in argv else 3600
    faction = int(argv[argv.index("--faction") + 1]) if "--faction" in argv else 1
    scenario = argv[argv.index("--scenario") + 1] if "--scenario" in argv else "classic"
    observer = "--observer" in argv
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    game = Game(scenario, {
        "show_numbers": "--numbers" in argv,
        "show_names": "--no-names" not in argv,
    })
    fonts = make_fonts()
    game.choose_faction(None if observer else faction, observer=observer)
    game.paused = False
    dt = 1.0 / 30
    for _ in range(ticks):
        game.tick(dt)
        if game.winner:
            break
    for _ in range(10):        # дать дшару/анимациям догнать состояние
        draw(screen, game, fonts)
    pygame.image.save(screen, out)
    pygame.quit()
    print(f"shot saved: {out} (time={game.time:.0f}s, winner={game.winner})")
    return 0


def run_game(scenario="classic", opts=None, screen=None, caption=None):
    """Полный цикл партии: экран выбора фракции, игра, повтор.

    Вызывается из главного меню (menu.py) или напрямую при запуске strategy.py.
    opts["on_exit"] — функция возврата в меню; opts["show_names"/"show_numbers"]
    применяются к новой партии. Окно изменяемого размера: игра рисуется в
    виртуальный буфер 1280×760 и масштабируется под реальное окно, мышь
    пересчитывается обратно. Возвращает управление после выхода из партии.
    """
    opts = dict(opts or {})
    if screen is None:
        screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    pygame.display.set_caption(caption or f"Баланс сил: Стратегия — {SCENARIOS.get(scenario, SCENARIOS['classic'])['name']}")

    game = Game(scenario, opts)
    fonts = make_fonts()
    buf = pygame.Surface((W, H))       # виртуальный буфер фиксированного размера

    running = True
    while running:
        dt = clock().tick(60) / 1000.0
        win_size = None
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.VIDEORESIZE:
                win_size = event.size
            elif event.type == pygame.KEYDOWN:
                handle_key(game, event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                handle_click(game, map_mouse(event.pos, win_size or screen.get_size()), event.button)
            elif event.type == pygame.MOUSEBUTTONUP:
                pass

        # музыка: спокойный трек на выборе фракции, боевой — в партии
        if game.choosing:
            audio.play_menu()
        else:
            audio.play_game()

        if game.replay:
            game.update_replay(dt)
        elif not game.paused and not game.choosing and not game.winner:
            rate = TICK_RATE * SPEEDS[game.speed_idx]
            # дробные тики копятся между кадрами, иначе из-за усечения int()
            # скорости ×1 и ×2 дают одинаковое число шагов
            game._tick_acc = min(game._tick_acc + rate * dt, rate * 2)
            steps = int(game._tick_acc)
            game._tick_acc -= steps
            for _ in range(steps):
                game.tick(1.0 / TICK_RATE)

        draw(buf, game, fonts)
        # масштабируем виртуальный кадр под текущий размер окна (сохраняя пропорции)
        blit_scaled(screen, buf, win_size or screen.get_size())
        pygame.display.flip()

        if game.exit_requested:          # ESC / «В МЕНЮ»
            running = False

    audio.stop()
    # уход из незавершённой партии дольше минуты — тоже сохраняем повтор
    if not game.replay_saved and game.time > 60.0 and not game.choosing:
        import replays
        replays.save_replay(game)
        game.replay_saved = True
    if opts.get("on_exit"):
        cb = opts["on_exit"]
        if cb:
            try:
                cb()
            except Exception:
                pass
        return None
    pygame.quit()
    return game.winner


_clock = None


def clock():
    """Общий таймер кадров (создаётся лениво, чтобы не ломать shot-режим)."""
    global _clock
    if _clock is None:
        _clock = pygame.time.Clock()
    return _clock


def map_mouse(pos, win_size):
    """Пересчёт координат мыши из окна в виртуальный буфер 1280×760."""
    ww, wh = win_size
    scale = min(ww / W, wh / H)
    off_x = (ww - W * scale) / 2
    off_y = (wh - H * scale) / 2
    return (int((pos[0] - off_x) / max(scale, 0.0001)),
            int((pos[1] - off_y) / max(scale, 0.0001)))


def blit_scaled(screen, buf, win_size):
    """Кадр буфера → окно: масштаб с сохранением пропорций, чёрные поля."""
    ww, wh = win_size
    scale = min(ww / W, wh / H)
    nw, nh = max(1, int(W * scale)), max(1, int(H * scale))
    if (ww, wh) == (W, H):
        screen.blit(buf, (0, 0))
        return
    screen.fill((8, 9, 12))
    frame = pygame.transform.smoothscale(buf, (nw, nh))
    screen.blit(frame, ((ww - nw) // 2, (wh - nh) // 2))


if __name__ == "__main__":
    import sys
    if "--shot" in sys.argv:
        sys.exit(shot_mode(sys.argv))
    pygame.init()
    audio.ensure_async()
    run_game("classic")
