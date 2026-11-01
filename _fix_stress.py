# Стресс-тест: прогоняет все редко используемые ветки strategy.py и battle_gui.py.
import os
import random
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

import strategy
import battle_gui

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


# ---------- strategy.py: партия с активными действиями игрока ----------
def strategy_session():
    game = strategy.Game()
    game.choose_faction(1)
    game.paused = False
    own = [r.rid for r in game.factions[1].regions]
    cap_rid = game.factions[1].capital
    # приказы игрока
    for rid in own:
        game.recruit(rid)
        game.develop_econ(rid)
    game.develop_tech(1, "atk")
    game.raise_conscript()
    game.send_move(own[0], own[1], 1, 0.6)
    # дипломатия игрока со всеми
    for kind in ("gift", "alliance", "nap", "trade", "peace", "war"):
        game.player_propose(kind, 2)
    # война для боевого пути
    game.declare_war(1, 2, quiet=True)
    n = game.neighbors(game.regions[cap_rid])[0]
    game.send_move(cap_rid, n.rid, 1, 0.9)
    # предложения игроку
    for kind in ("alliance", "nap", "trade", "peace", "gift", "demand"):
        game.propose(kind, 0, 1, amount=80)
    while game.pending_offers:
        game.resolve_offer(game.pending_offers.pop(), True)
    for kind in ("alliance", "nap", "trade", "peace", "gift", "demand"):
        game.propose(kind, 3, 1, amount=80)
    while game.pending_offers:
        game.resolve_offer(game.pending_offers.pop(), False)
    # долгая симуляция со случайными приказами
    for i in range(20000):
        game.tick(1.0 / 30)
        if i % 400 == 0:
            my = [r.rid for r in game.factions[1].regions]
            if my:
                game.recruit(rng.choice(my))
                game.develop_econ(rng.choice(my))
                game.develop_tech(1, rng.choice(["atk", "def", "log", "mor"]))
                src = rng.choice(my)
                ns = game.neighbors(game.regions[src])
                game.send_move(src, rng.choice(ns).rid, 1, rng.choice([0.5, 0.95]))
        if game.winner:
            break
    # отрисовка всех вкладок и состояний
    for tab in (0, 1, 2):
        game.tab = tab
        game.selected = game.factions[1].capital
        for rep in (False, True):
            game.show_numbers = rep
            strategy.draw(screen, game, fonts)
    game.selected = None
    strategy.draw(screen, game, fonts)
    # конец игры + повтор
    game.winner = "ПОБЕДА!"
    strategy.draw(screen, game, fonts)
    game.start_replay()
    game.replay_pos = float(len(game.history) - 1)
    game.replay_idx = len(game.history) - 1
    strategy.draw(screen, game, fonts)
    game.update_replay(0.5)
    game.replay_idx = 0
    game.replay_pos = 0.0
    strategy.draw(screen, game, fonts)
    game.replay = False
    game.selected = 0
    pygame.image.save(screen, "_fix_stress_strategy.png")


def strategy_observer_session():
    game = strategy.Game()
    game.choose_faction(None, observer=True)
    game.paused = False
    for _ in range(9000):
        game.tick(1.0 / 30)
        if game.winner:
            break
    game.selected = 5
    for tab in (0, 1, 2):
        game.tab = tab
        strategy.draw(screen, game, fonts)
    print("   observer time:", round(game.time, 1), "winner:", game.winner)


def battle_gui_session():
    pygame.display.set_mode((battle_gui.W, battle_gui.H))
    sim = battle_gui.BattleSim()
    ai = battle_gui.BattleAI(sim)
    for i in range(3000):
        sim.step(1)
        ai.update(1 / 30)
        if i % 111 == 0:
            for num in sim.order:
                sim.support_team(num)
                sim.create_front(num)
        if sim.finished:
            break
    print("   battle round:", sim.round, "finished:", sim.finished,
          "winner:", sim.winner, "expelled:", sim.expelled)
    for _ in range(12):
        battle_gui.draw(screen, sim, False, 1, 0, True)
    pygame.image.save(screen, "_fix_stress_battle.png")


check("strategy: сессия игрока", strategy_session)
check("strategy: сессия наблюдателя", strategy_observer_session)
check("battle_gui: длинный бой с приказами", battle_gui_session)

print()
if failures:
    for label, tb in failures:
        print("=" * 70)
        print("FAIL:", label)
        print(tb)
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
