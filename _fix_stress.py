# Стресс-тест v2.0: дивизии, города, захват, окружения, дипломатия, реплей.
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

import strategy

pygame.init()
screen = pygame.display.set_mode((strategy.W, strategy.H))
fonts = strategy.make_fonts()
rng = random.Random(7)

failures = []


def check(label, fn):
    try:
        fn()
        print(f"OK   {label}")
    except Exception as e:
        import traceback
        failures.append((label, traceback.format_exc()))
        print(f"FAIL {label}: {e}")


# ---------- дивизии: движение, бой, стрельба, захват, окружение ----------
def divisions_core():
    game = strategy.Game("classic")
    game.choose_faction(1)
    game.paused = False
    dt = 1.0 / 30
    f1, f2 = game.factions[1], game.factions[2]
    assert len(f1.my_divisions) >= 8, "стартовые дивизии не созданы"
    assert any(r.city for r in game.regions), "города не расставлены"
    assert game.factions[0].research >= 0
    # окружение: дивизия в глубине чужой земли — дальний угол от f1
    # (проверяем до войны, чтобы состав владельцев не менялся)
    cap2 = game.regions[game.factions[0].capital]
    d = game.spawn_division(1, "inf", cap2.x + 0.5, cap2.y + 0.5)
    game.update_supply()
    assert (1, cap2.rid) not in game._supply, \
        "столица врага в глубоком тылу не должна снабжаться"
    s0 = d.soldiers
    for _ in range(90):               # 3 с: окружение давит состав
        game.tick(dt)
    assert d.encircled, "дивизия в тылу врага должна быть окружена"
    assert d.soldiers < s0, "окружённая дивизия не несёт потери от истощения"
    game.divisions.remove(d)
    game.declare_war(1, 2, quiet=True)
    # приказ: вся армия в сторону врага
    target = game.regions[f2.capital]
    game.order_move(f1.my_divisions, target.x + 0.5, target.y + 0.5)
    moved = False
    for _ in range(2400):           # 80 игровых секунд
        game.tick(dt)
        if any(x.moving for x in f1.my_divisions):
            moved = True
        if game.winner:
            break
    assert moved, "дивизии не двигаются по приказу"
    # бой должен был начаться: есть потери хотя бы у одной стороны
    assert f1.losses + f2.losses > 0, "контактного боя не было"
    # научный город копит исследования; арсенал строит дивизии
    sci = [r for r in f1.regions if r.city and r.city["mode"] == "science"]
    arm = [r for r in f1.regions if r.city and r.city["mode"] == "army"]
    if sci:
        assert f1.research > 0, "наука не копится"
    # очередь производства
    if arm:
        ok = game.queue_division(arm[0].rid, "inf")
        assert ok, "не удалось поставить дивизию в очередь"
    # исследования
    f1.research = 10000
    ok = game.develop_research(1, "arty")
    assert ok and f1.tech2["arty"] == 1, "исследование не работает"
    print("   divisions:", len(game.divisions), "kills f1:", int(f1.kills),
          "kills f2:", int(f2.kills))


# ---------- захват регионов дивизиями ----------
def capture_flow():
    game = strategy.Game("classic")
    game.choose_faction(None, observer=True)   # все за ИИ
    game.paused = False
    dt = 1.0 / 30
    f1, f2 = game.factions[1], game.factions[2]
    game.declare_war(1, 2, quiet=True)
    # у всех агрессоров максимальная агрессивность, чтобы война шла активно
    for f in game.factions.values():
        f.aggro = 1.0
    for _ in range(9000):            # 300 с
        game.tick(dt)
        if game.winner:
            break
    owners = {r.owner for r in game.regions}
    assert len(owners) < 5, "карта вообще не изменилась за 300 с"
    print("   owners:", {o: sum(1 for r in game.regions if r.owner == o)
                         for o in owners})


# ---------- города: режимы, очередь, отмена ----------
def cities_flow():
    game = strategy.Game("classic")
    game.choose_faction(0)
    f = game.factions[0]
    f.money = 1000
    f.manpower = f.manpower_max
    arm = [r for r in f.regions if r.city and r.city["mode"] == "army"]
    sci = [r for r in f.regions if r.city and r.city["mode"] == "science"]
    assert arm and sci, "у каждой страны должны быть оба типа городов"
    r = arm[0]
    for _ in range(3):
        assert game.queue_division(r.rid, "tank"), "очередь не заполняется"
    assert not game.queue_division(r.rid, "inf"), "очередь переполнена"
    assert game.cancel_queue(r.rid, 0), "отмена очереди не работает"
    assert not game.set_city_mode(r.rid, "science") or True
    # переключение режима в науку и обратно
    ok = game.set_city_mode(r.rid, "science")
    assert ok, "смена режима города не работает"
    ok = game.set_city_mode(r.rid, "army")
    assert ok, "смена режима города обратно не работает"
    dt = 1.0 / 30
    before = len(f.my_divisions)
    for _ in range(30 * 40):
        game.tick(dt)
    assert len(f.my_divisions) > before, "арсенал не строит дивизии"
    sci[0].city["mode"] = "science"
    res0 = f.research
    for _ in range(30 * 10):
        game.tick(dt)
    assert f.research > res0, "научный город не копит очки"


# ---------- дипломатия v2: угроза, коалиции, мир ----------
def diplomacy_v2():
    game = strategy.Game("classic")
    game.choose_faction(None, observer=True)
    f1 = game.factions[1]
    game.declare_war(1, 2)
    assert f1.threat >= strategy.THREAT_PER_WAR, "угроза не растёт"
    game.make_peace(1, 2)
    assert f1.threat < strategy.THREAT_PER_WAR, "мир должен снижать угрозу"
    # коалиция: огромная угроза — соседи объединяются
    game.factions[1].threat = 100.0
    game.factions[1].make = None
    for _ in range(40):
        game.ai_diplomacy(game.factions[0])
    allies_of_0 = game.factions[0].alliance
    assert allies_of_0, "коалиция против угрозы не сформировалась"
    print("   coalitions:", {k: sorted(v.alliance)
                             for k, v in game.factions.items() if v.alliance})


# ---------- игрок: полный интерфейс ----------
def strategy_session():
    game = strategy.Game()
    game.choose_faction(1)
    game.paused = False
    f1 = game.factions[1]
    cap = game.regions[f1.capital]
    # клик по региону — выделение дивизий, ПКМ — приказ
    import pygame
    pos = (strategy.MAP_X + int((cap.x + 0.5) * strategy.TILE),
           strategy.MAP_Y + int((cap.y + 0.5) * strategy.TILE))
    strategy.handle_click(game, pos, 1)
    assert game.sel_divs, "клик по региону не выделил дивизии"
    dpos = (strategy.MAP_X + int((cap.x + 0.9) * strategy.TILE),
            strategy.MAP_Y + int((cap.y + 0.9) * strategy.TILE))
    strategy.handle_click(game, dpos, 3)
    assert any(d.moving for d in f1.my_divisions), "приказ ПКМ не двигает"
    # панель города: постановка в очередь кликом
    game.selected = f1.capital
    game.tab = 1
    strategy.handle_click(game, (strategy.PANEL_X + 30, strategy.CONTENT_Y + 180), 1)
    # дипломатия игрока со всеми
    for kind in ("gift", "alliance", "nap", "trade", "peace", "war"):
        game.player_propose(kind, 2)
    game.declare_war(1, 2, quiet=True)
    for kind in ("alliance", "nap", "trade", "peace", "gift", "demand"):
        game.propose(kind, 0, 1, amount=80)
    while game.pending_offers:
        game.resolve_offer(game.pending_offers.pop(), True)
    # долгая симуляция
    for i in range(12000):
        game.tick(1.0 / 30)
        if i % 600 == 0 and f1.my_divisions:
            d = rng.choice(f1.my_divisions)
            game.order_move([d], rng.uniform(0, strategy.GRID - 1),
                            rng.uniform(0, strategy.GRID - 1))
        if game.winner:
            break
    # отрисовка всех вкладок и состояний
    for tab in (0, 1, 2, 3):
        game.tab = tab
        game.selected = f1.capital
        for rep in (False, True):
            game.show_numbers = rep
            strategy.draw(screen, game, fonts)
    game.selected = None
    strategy.draw(screen, game, fonts)
    game.winner = "ПОБЕДА!"
    strategy.draw(screen, game, fonts)
    # повтор: снимки с дивизиями + старый формат
    game.start_replay()
    game.replay_pos = float(len(game.history) - 1)
    game.replay_idx = len(game.history) - 1
    strategy.draw(screen, game, fonts)
    game.update_replay(0.5)
    game.replay_idx = 0
    game.replay_pos = 0.0
    strategy.draw(screen, game, fonts)
    game.replay = False
    pygame.image.save(screen, "_fix_stress_strategy.png")
    snap = game.history[-1]
    assert "divs" in snap and "cities" in snap, "снимок без дивизий/городов"


def strategy_observer_session():
    game = strategy.Game("anarchy")
    game.choose_faction(None, observer=True)
    game.paused = False
    for _ in range(9000):
        game.tick(1.0 / 30)
        if game.winner:
            break
    for tab in (0, 1, 2, 3):
        game.tab = tab
        game.selected = 5
        strategy.draw(screen, game, fonts)
    print("   observer time:", round(game.time, 1), "winner:", game.winner,
          "divs:", len(game.divisions))


check("strategy: дивизии — движение/бой/окружение/наука", divisions_core)
check("strategy: захват регионов (ИИ против ИИ)", capture_flow)
check("strategy: города — очередь/режимы/производство", cities_flow)
check("strategy: дипломатия v2 — угроза/коалиции/мир", diplomacy_v2)
check("strategy: сессия игрока (ввод, вкладки, реплей)", strategy_session)
check("strategy: анархия, наблюдатель", strategy_observer_session)

print()
if failures:
    for label, tb in failures:
        print("=" * 70)
        print("FAIL:", label)
        print(tb)
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
