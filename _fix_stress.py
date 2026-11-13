# Стресс-тест v2.4: фронты, резерв, стойки, мини-атаки, нейтралы, реплей.
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pygame

import strategy

pygame.init()
screen = pygame.display.set_mode((strategy.W, strategy.H))
fonts = strategy.make_fonts()

failures = []


def check(label, fn):
    try:
        fn()
        print(f"OK   {label}")
    except Exception as e:
        import traceback
        failures.append((label, traceback.format_exc()))
        print(f"FAIL {label}: {e}")


def recruit_reserve():
    game = strategy.Game("classic")
    game.choose_faction(1)
    f = game.factions[1]
    f.money = 1000
    f.manpower = f.manpower_max
    n0 = f.reserve
    assert game.recruit(1), "набор не удался"
    assert f.reserve == n0 + strategy.RECRUIT_AMOUNT, "резерв не пополнен"
    assert f.money < 1000 and f.manpower < f.manpower_max
    print("   reserve:", int(f.reserve))


def front_lifecycle():
    game = strategy.Game("split")
    game.choose_faction(None, observer=True)
    game.paused = False
    dt = 1.0 / 30
    f1, f2 = game.factions[1], game.factions[2]
    game.break_nap(1, 2, quiet=True)
    assert game.declare_war(1, 2), "война не объявлена"
    fr = game.war_fronts.get((1, 2))
    assert fr is not None, "фронт не создан"
    # развёртывание: резерв растекается по фронту
    r0 = f1.reserve
    for _ in range(300):                     # 10 с
        game.tick(dt)
    assert fr.troops[1] > 0, "резерв не разворачивается на фронт"
    assert f1.reserve < r0, "резерв не убыл"
    assert fr.line, "у фронта нет линии границы"
    # мир: война кончилась, но фронт остаётся обороной границы
    game.make_peace(1, 2)
    assert not game.at_war(1, 2), "мир не заключён"
    assert (1, 2) in game.war_fronts, "фронт обороны границы пропал"
    assert game.war_fronts[(1, 2)].line, "у фронта обороны нет линии"


def attack_captures():
    game = strategy.Game("split")
    game.choose_faction(None, observer=True)
    game.paused = False
    game.ai_diplomacy = lambda f: None        # тест: без мира
    dt = 1.0 / 30
    f1, f2 = game.factions[1], game.factions[2]
    game.break_nap(1, 2, quiet=True)
    assert game.declare_war(1, 2)
    game.set_stance(1, 2, "att", fid=1)
    game.set_stance(1, 2, "def", fid=2)
    f1.reserve += 60000                       # подавляющее преимущество
    regions_before = len(f2.regions)
    losses_before = f1.losses + f2.losses
    for _ in range(3600):                     # 120 с войны
        game.tick(dt)
    assert f1.losses + f2.losses > losses_before, "потерь нет"
    assert len(f2.regions) < regions_before, "захватов при перевесе нет"
    print("   f2 regions:", regions_before, "->", len(f2.regions),
          "losses:", int(f1.losses + f2.losses))


def stances_and_concurrent():
    game = strategy.Game("split")
    game.choose_faction(None, observer=True)
    game.paused = False
    game.ai_diplomacy = lambda f: None
    dt = 1.0 / 30
    game.break_nap(1, 2, quiet=True)
    game.declare_war(1, 2)
    game.set_stance(1, 2, "att", fid=1)
    game.set_stance(1, 2, "att", fid=2)
    for f in (game.factions[1], game.factions[2]):
        f.reserve += 20000
        f.doctrine = 0                        # «Манёвры»: до 3 атак сразу
    game.factions[1].aggro = 1.0
    game.factions[2].aggro = 1.0
    max_conc = 0
    for _ in range(2400):
        game.tick(dt)
        max_conc = max(max_conc, sum(len(fr.battles)
                                     for fr in game.war_fronts.values()))
    assert max_conc >= 2, "одновременных мини-атак не было"
    # стойка обороны блокирует атаки стороны (ИИ-стойки заморожены)
    game.ai_military = lambda f: None
    game.set_stance(1, 2, "def", fid=1)
    game.set_stance(1, 2, "att", fid=2)
    for _ in range(900):                      # 30 с > макс. длины боя
        game.tick(dt)
    fr12 = game.war_fronts.get((1, 2))
    if fr12 is not None:
        assert all(b["att"] != 1 for b in fr12.battles), \
            "оборона продолжает атаковать"
    print("   max concurrent battles:", max_conc)


def neutral_expansion():
    game = strategy.Game("classic")           # есть нейтральный центр
    game.choose_faction(None, observer=True)
    game.paused = False
    game.ai_diplomacy = lambda f: None
    dt = 1.0 / 30
    neutrals_before = sum(1 for r in game.regions if r.owner == strategy.NEUTRAL)
    assert neutrals_before > 0, "нейтральных провинций нет"
    for _ in range(4500):                     # 150 с
        game.tick(dt)
    neutrals_after = sum(1 for r in game.regions if r.owner == strategy.NEUTRAL)
    assert neutrals_after < neutrals_before, "экспансия в нейтралы не идёт"
    print("   neutrals:", neutrals_before, "->", neutrals_after)


def player_ui_and_replay():
    game = strategy.Game("classic")
    game.choose_faction(1)
    game.paused = False
    game.ai_diplomacy = lambda f: None
    dt = 1.0 / 30
    f1, f2 = game.factions[1], game.factions[2]
    game.break_nap(1, 2, quiet=True)
    game.declare_war(1, 2)
    game.set_stance(1, 2, "att", fid=1)       # стойка игрока
    assert game.war_fronts[(1, 2)].stance[1] == "att"
    for _ in range(1200):
        game.tick(dt)
    # вкладки
    for tab in range(4):
        game.tab = tab
        game.selected = f1.capital
        strategy.draw(screen, game, fonts)
    strategy.draw(screen, game, fonts)
    # конец игры + повтор v3
    game.winner = "ПОБЕДА!"
    strategy.draw(screen, game, fonts)
    game.start_replay()
    game.replay_idx = len(game.history) - 1
    strategy.draw(screen, game, fonts)
    game.update_replay(0.5)
    strategy.draw(screen, game, fonts)
    game.replay = False
    snap = game.history[-1]
    assert "fronts" in snap, "снимок без фронтов"
    pygame.image.save(screen, "_fix_stress_strategy.png")


def observer_session():
    game = strategy.Game("anarchy")
    game.choose_faction(None, observer=True)
    game.paused = False
    for _ in range(9000):
        game.tick(1.0 / 30)
        if game.winner:
            break
    for tab in range(4):
        game.tab = tab
        game.selected = 5
        strategy.draw(screen, game, fonts)
    print("   observer time:", round(game.time, 1), "winner:", game.winner,
          "fronts:", len(game.war_fronts))


check("fronts: набор в резерв", recruit_reserve)
check("fronts: жизнь фронта (развёртывание/мир)", front_lifecycle)
check("fronts: атака при перевесе даёт захваты и потери", attack_captures)
check("fronts: стойки и одновременные атаки", stances_and_concurrent)
check("fronts: экспансия в нейтралы", neutral_expansion)
check("fronts: игрок, вкладки, реплей v3", player_ui_and_replay)
check("fronts: анархия, наблюдатель", observer_session)

print()
if failures:
    for label, tb in failures:
        print("=" * 70)
        print("FAIL:", label)
        print(tb)
    sys.exit(1)
print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ")
