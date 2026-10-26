import random

armycount1 = 50000000
armycount2 = 5000000
ARMY1_START = armycount1   # стартовые силы — нужны для расчёта захвата территории
ARMY2_START = armycount2

# Generalbonus - бонус\опыт генерала
# landbonus - бонус от ландшафта
# tacticbonus - бонус от подходящей тактики 
# moralbonus - статический бонус от морали
# morale - текущая мораль в % (меняется в ходе битвы)
# Эффективность атаки на 1000 бойцов
# techbonus - бонус от технологий 0-10
generalbonus1, landbonus1, tacticbonus1 = 3, 0, 3
generalbonus2, landbonus2, tacticbonus2 = 3, 7, 4

# --- Бонусы за мораль и технологии ---
moralbonus1 = 0.0     # статический бонус морали
moralbonus2 = 0.5
morale1 = 10.0       # текущая мораль в % (динамика в ходе битвы)
morale2 = 100.0
techbonus1 = 0.2      # бонус за технологии
techbonus2 = 0.2

MORALE_WEIGHT = 0.3   # вклад 100% морали в rate
TECH_WEIGHT = 1.0
MORALE_MIN, MORALE_MAX = 5.0, 200.0   # границы морали

LIMIT = 2
MAX_ROUNDS = 1000000000000000000
DAMAGE_SCALE = 0.01

# --- Кто атакующий, кто защитник ---
is_attacker1 = True
is_attacker2 = False

ATTACKER_MALUS = 0.8     # атакующий сражается на 80% эффективности
DEFENDER_BONUS = 1.25    # защитник получает +25%

# --- Поддержка населения в процентах ---
support1 = 0.0
support2 = 100.0

def support_multiplier(support_percent):
    # 0% -> 0.5, 50% -> 1.0, 100% -> 1.5
    return 0.5 + support_percent / 100.0

def role_multiplier(is_attacker):
    return ATTACKER_MALUS if is_attacker else DEFENDER_BONUS

def compute_rate(general, land, tactic, moralbonus, morale, tech):
    # Эффективность на 1000 бойцов = генерал + земля + тактика + мораль + технологии
    morale_bonus = moralbonus + (morale / 100.0) * MORALE_WEIGHT
    tech_bonus = tech * TECH_WEIGHT
    return general + land + tactic + morale_bonus + tech_bonus

def compute_territory(a1, a2):
    """Какой % территории региона контролирует каждая сторона.

    Защитник — сторона с is_attacker = False — в начале владеет всей
    территорией (100%). Атакующий отвоёвывает её по мере уничтожения
    армии защитника, поэтому если атакующий разбит, территория остаётся
    у защитника, а если разбит защитник — атакующий забирает всё (100%).
    """
    if not is_attacker1:
        # защитник — сторона 1, сторону 2 считаем атакующей
        captured = (ARMY1_START - a1) / ARMY1_START * 100.0
        captured = max(0.0, min(100.0, captured))
        return 100.0 - captured, captured
    if not is_attacker2:
        # защитник — сторона 2, сторону 1 считаем атакующей
        captured = (ARMY2_START - a2) / ARMY2_START * 100.0
        captured = max(0.0, min(100.0, captured))
        return captured, 100.0 - captured
    # обе стороны атакующие — делим пропорционально силам
    total = a1 + a2
    if total == 0:
        return 50.0, 50.0
    t1 = a1 / total * 100.0
    return t1, 100.0 - t1

def update_morale(morale, my_losses, enemy_losses, my_army):
    """Мораль меняется по балансу потерь в раунде:
    убил больше, чем потерял — растёт, наоборот — падает."""
    swing = (enemy_losses - my_losses) / max(my_army, 1) * 100.0
    return max(MORALE_MIN, min(MORALE_MAX, morale + swing))

rate1 = compute_rate(generalbonus1, landbonus1, tacticbonus1, moralbonus1, morale1, techbonus1)
rate2 = compute_rate(generalbonus2, landbonus2, tacticbonus2, moralbonus2, morale2, techbonus2)

mod1 = role_multiplier(is_attacker1) * support_multiplier(support1)
mod2 = role_multiplier(is_attacker2) * support_multiplier(support2)

role1 = "АТАКУЮЩИЙ" if is_attacker1 else "ЗАЩИТНИК"
role2 = "АТАКУЮЩИЙ" if is_attacker2 else "ЗАЩИТНИК"


def simulate_battle(scale_factor=50):
    """
    Быстрая симуляция без вывода.
    scale_factor ускоряет битву — победитель от масштаба не зависит,
    меняется только скорость набора потерь.
    Возвращает 1 / 2 / 0 (ничья или взаимное уничтожение).
    """
    a1, a2 = armycount1, armycount2
    m1, m2 = morale1, morale2
    guard = 0
    while a1 >= LIMIT and a2 >= LIMIT and guard < 10_000_000:
        guard += 1
        r1 = compute_rate(generalbonus1, landbonus1, tacticbonus1, moralbonus1, m1, techbonus1)
        r2 = compute_rate(generalbonus2, landbonus2, tacticbonus2, moralbonus2, m2, techbonus2)
        luck1 = random.uniform(0.7, 1.3)
        luck2 = random.uniform(0.7, 1.3)
        d1 = a1 * r1 / 1000 * luck1 * DAMAGE_SCALE * mod1 * scale_factor
        d2 = a2 * r2 / 1000 * luck2 * DAMAGE_SCALE * mod2 * scale_factor
        dead2 = min(a2, round(d1))
        dead1 = min(a1, round(d2))
        a2 -= dead2
        a1 -= dead1
        m1 = update_morale(m1, dead1, dead2, a1)
        m2 = update_morale(m2, dead2, dead1, a2)

    if a1 < LIMIT and a2 < LIMIT:
        return 0
    if a1 < LIMIT:
        return 2
    if a2 < LIMIT:
        return 1
    return 0


def win_probability(n_sims=500, scale_factor=50):
    wins1 = wins2 = draws = 0
    for _ in range(n_sims):
        w = simulate_battle(scale_factor=scale_factor)
        if w == 1:
            wins1 += 1
        elif w == 2:
            wins2 += 1
        else:
            draws += 1
    n = n_sims
    return wins1 / n * 100, wins2 / n * 100, draws / n * 100


print(f"БОЛЬШАЯ БИТВА: {armycount1:,} vs {armycount2:,}".replace(",", " "))
print(f"Сторона 1: {role1}, поддержка населения {support1:.1f}%, коэффициент {mod1:.3f}")
print(f"Сторона 2: {role2}, поддержка населения {support2:.1f}%, коэффициент {mod2:.3f}")

# --- Прогноз победы методом Монте-Карло ---
N_SIMS = 500
p1, p2, pd = win_probability(n_sims=N_SIMS, scale_factor=50)

print(f"\nПРОГНОЗ ПОБЕДЫ ({N_SIMS} симуляций):")
print(f"  Победа первых: {p1:6.1f}%")
print(f"  Победа вторых: {p2:6.1f}%")
print(f"  Ничья / взаимное уничтожение: {pd:5.1f}%")
print("-" * 60)

i = 0
losses1 = 0
losses2 = 0
m1, m2 = morale1, morale2

while armycount1 >= LIMIT and armycount2 >= LIMIT and i < MAX_ROUNDS:
    i += 1

    # rate пересчитывается каждый раунд с учётом текущей морали
    rate1 = compute_rate(generalbonus1, landbonus1, tacticbonus1, moralbonus1, m1, techbonus1)
    rate2 = compute_rate(generalbonus2, landbonus2, tacticbonus2, moralbonus2, m2, techbonus2)

    luck1 = random.uniform(0.7, 1.3)
    luck2 = random.uniform(0.7, 1.3)

    damage1 = armycount1 * rate1 / 1000 * luck1 * DAMAGE_SCALE * mod1
    damage2 = armycount2 * rate2 / 1000 * luck2 * DAMAGE_SCALE * mod2

    dead1 = min(armycount1, round(damage2))
    dead2 = min(armycount2, round(damage1))

    armycount1 -= dead1
    armycount2 -= dead2
    losses1 += dead1
    losses2 += dead2

    # мораль меняется по исходу раунда (убил больше, чем потерял — растёт)
    m1 = update_morale(m1, dead1, dead2, armycount1)
    m2 = update_morale(m2, dead2, dead1, armycount2)

    # доля захваченной территории региона пропорциональна оставшейся армии
    terr1, terr2 = compute_territory(armycount1, armycount2)

    share1 = armycount1 / 1_000_000
    share2 = armycount2 / 1_000_000

    if share1 > share2:
        advantage = "ПЕРЕВЕС ПЕРВЫХ"
    elif share2 > share1:
        advantage = "ПЕРЕВЕС ВТОРЫХ"
    else:
        advantage = "РАВНОВЕСИЕ"

    print(
        f"Раунд {i}: потери {dead1:,} / {dead2:,}; "
        f"осталось {armycount1:,} / {armycount2:,}; "
        f"мораль {m1:.0f}% / {m2:.0f}%; "
        f"территория 1-х — {terr1:5.1f}%, 2-х — {terr2:5.1f}%; {advantage}"
        .replace(",", " ")
    )

fterr1, fterr2 = compute_territory(armycount1, armycount2)

if armycount1 < LIMIT and armycount2 < LIMIT:
    print("ОБЕ АРМИИ РАЗБИТЫ")
elif armycount1 < LIMIT:
    print("ПОБЕДА ВТОРЫХ")
    print(f"  Захвачено вторыми: {fterr2:.1f}% территории (первым осталось {fterr1:.1f}%)")
elif armycount2 < LIMIT:
    print("ПОБЕДА ПЕРВЫХ")
    print(f"  Захвачено первыми: {fterr1:.1f}% территории (вторым осталось {fterr2:.1f}%)")
else:
    print("НИЧЬЯ: достигнут лимит раундов")

print(f"  Контроль территории: первые — {fterr1:.1f}%, вторые — {fterr2:.1f}%")

print(f"Всего потерь: первые — {losses1:,}, вторые — {losses2:,}".replace(",", " "))

# --- Фактический исход относительно прогноза ---
print("\nСравнение с прогнозом:")
print(f"  Прогноз: победа первых {p1:.1f}%, победа вторых {p2:.1f}%, ничья {pd:.1f}%")