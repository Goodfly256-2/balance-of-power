# СТАРЫЙ ПРОТОТИП — НЕ РАЗВИВАЕТСЯ.
# Это ранний тест сражения за одну провинцию. Актуальная игра — strategy.py
# («Баланс сил: Стратегия», карта 8×8). Файл оставлен только для истории.
#
# Интерфейс боя «Баланс сил» на pygame.
# - поддержка 3 команд (защитник в центре, два атакующих по краям);
# - регион — полоса, разбитая на отрезки-владения (owners); фронт — их граница;
#   владения рисуются «живой» картой: органичные границы, текстура, тонкие линии;
# - у атакующего в начале плацдарм 1%; потеряв всю территорию, он «оттесняется»
#   из региона, даже если армия цела (армия остаётся, но не воюет);
# - армии делятся/сливаются; кнопки «Поддержать» (переброска войск на фронт)
#   и «Создать фронт» (клин/клещи в тыл соседу — две новые линии боя);
# - количество солдат показано крупными числами у линии фронта;
# - режим наблюдателя: все команды играет ИИ, вы только смотрите.
import math
import random

import pygame

# ============================ КОНФИГУРАЦИЯ ============================
LIMIT = 2
DAMAGE_SCALE = 0.005        # бой реально идёт: солдаты гибнут
MORALE_WEIGHT = 0.3
TECH_WEIGHT = 1.0
MORALE_MIN, MORALE_MAX = 5.0, 200.0

ATTACKER_MALUS = 0.8
DEFENDER_BONUS = 1.25
FRONT_SPEED = 0.001         # скорость движения фронта за раунд

BEACHHEAD = 1.0             # стартовый плацдарм атакующего, % территории
NEW_FRONT_WIDTH = 6.0       # ширина клина при создании нового фронта, %
NEW_FRONT_COMMIT = 0.35     # доля войск, уходящая в клин
SUPPORT_FRACTION = 0.4      # доля войск при переброске «Поддержать»
MIN_FRONT_WIDTH = 0.4       # более узкие отрезки не создаём

# Команды слева направо: (номер, is_attacker, поддержка населения %)
TEAMS = [
    (1, True, 40.0),         # левая атакующая
    (2, False, 40.0),        # защитник (центр)
    (3, True, 40.0),         # правая атакующая
]

# Армии: (имя, команда, солдат, general, land, tactic, tech, moralbonus)
# Защитник может иметь по армии на каждый фронт (вторая — с другой стороны).
ARMIES = [
    ("Левая", 1, 7_00000_000, 0, 0, 0, 0.1, 0.0),
    ("Центр-Л", 2, 3_000_000, 900, 400, 70, 8, 8.0),
    ("Центр-П", 2, 3_000_000, 900, 400, 70, 8, 8.0),
    ("Правая", 3, 7_00000_000, 0, 0, 0, 0.1, 0.0),
]


# ============================ МОДЕЛЬ БОЯ ============================
def support_multiplier(percent):
    return 0.5 + percent / 100.0


def role_multiplier(is_attacker):
    return ATTACKER_MALUS if is_attacker else DEFENDER_BONUS


def compute_rate(general, land, tactic, moralbonus, morale, tech):
    return general + land + tactic + moralbonus + (morale / 100.0) * MORALE_WEIGHT + tech * TECH_WEIGHT


def update_morale(morale, my_losses, enemy_losses, my_army):
    swing = (enemy_losses - my_losses) / max(my_army, 1) * 100.0
    return max(MORALE_MIN, min(MORALE_MAX, morale + swing))


class Army:
    def __init__(self, name, team, soldiers, general, land, tactic, tech, moralbonus):
        self.name = name
        self.team = team
        self.start = soldiers
        self.soldiers = soldiers
        self.losses = 0
        self.general = general
        self.land = land
        self.tactic = tactic
        self.tech = tech
        self.moralbonus = moralbonus


class Team:
    def __init__(self, number, is_attacker, support):
        self.number = number
        self.is_attacker = is_attacker
        self.support = support
        self.morale = 100.0
        self.armies = []
        self.losses = 0          # накопительно, не зависит от слияний/разделений

    @property
    def soldiers(self):
        return sum(a.soldiers for a in self.armies)

    @property
    def mod(self):
        return role_multiplier(self.is_attacker) * support_multiplier(self.support)

    @property
    def role(self):
        return "АТАКУЮЩИЙ" if self.is_attacker else "ЗАЩИТНИК"


class BattleSim:
    def __init__(self):
        self.reset()

    def reset(self):
        self.teams = {}
        self.order = []
        for num, is_attacker, support in TEAMS:
            self.teams[num] = Team(num, is_attacker, support)
            self.order.append(num)
        for name, team, soldiers, gen, land, tac, tech, mb in ARMIES:
            self.teams[team].armies.append(Army(name, team, soldiers, gen, land, tac, tech, mb))

        self.n = len(self.order)
        self.index = {num: i for i, num in enumerate(self.order)}
        self.defender_num = next((num for num in self.order if not self.teams[num].is_attacker),
                                 self.order[0])
        d = self.index[self.defender_num]

        # отрезки-владения: у атакующих у краёв плацдарм BEACHHEAD, остальное — защитнику
        self.owners = list(self.order)
        bounds = [0.0] * (self.n + 1)
        for i in range(1, d + 1):
            bounds[i] = bounds[i - 1] + BEACHHEAD
        bounds[self.n] = 100.0
        for i in range(self.n - 1, d, -1):
            bounds[i] = bounds[i + 1] - BEACHHEAD
        self.bounds = bounds
        self.display = [float(b) for b in self.bounds]

        self.expelled = set()       # атакующие, вытесненные из региона

        # привязка армий к фронтам (границам), затем авто-деление/слияние
        self.army_front = {}
        for num in self.order:
            fronts = self._fronts_for(num)
            if not fronts:
                continue
            for j, a in enumerate(self.teams[num].armies):
                self.army_front[id(a)] = fronts[j % len(fronts)]
        self._reorganize()

        self.round = 0
        self.finished = False
        self.winner = None
        self.log = []

    # ---------------- территория / фронты ----------------
    def territory(self):
        t = {num: 0.0 for num in self.order}
        for i, o in enumerate(self.owners):
            t[o] += self.bounds[i + 1] - self.bounds[i]
        return t

    def ease_display(self, alpha=0.2):
        """Плавно подтягивать отображаемые границы к настоящим (для плавности картинки)."""
        if len(self.display) != len(self.bounds):
            self.display = [float(b) for b in self.bounds]
        for i in range(len(self.bounds)):
            self.display[i] += (self.bounds[i] - self.display[i]) * alpha

    def display_x(self, rect):
        return [rect.x + rect.w * b / 100.0 for b in self.display]

    def _front_indices(self):
        """Индексы границ-фронтов (между разными командами)."""
        return [j for j in range(1, len(self.owners))
                if self.owners[j - 1] != self.owners[j]]

    def _fronts_for(self, num):
        """Все границы, к которым выходит команда num."""
        res = []
        for j in self._front_indices():
            if self.owners[j - 1] == num or self.owners[j] == num:
                res.append(j)
        return res

    def _other_at(self, j, num):
        """Команда по другую сторону границы j от num."""
        if self.owners[j - 1] == num:
            return self.owners[j]
        if self.owners[j] == num:
            return self.owners[j - 1]
        return None

    def _neighbors(self, num):
        res = set()
        for i, o in enumerate(self.owners):
            if o != num:
                continue
            if i > 0 and self.owners[i - 1] != num:
                res.add(self.owners[i - 1])
            if i + 1 < len(self.owners) and self.owners[i + 1] != num:
                res.add(self.owners[i + 1])
        return {x for x in res if x not in self.expelled}

    def _active_armies(self):
        return [a for num in self.order if num not in self.expelled
                for a in self.teams[num].armies if a.soldiers > 0]

    # ---------------- армии: деление / слияние ----------------
    def _split(self, army, take):
        """Отделить от армии `take` солдат в новый отряд и вернуть его."""
        take = int(min(max(take, 0), army.soldiers - 1))
        if take <= 0:
            return None
        det = Army(army.name, army.team, take, army.general, army.land,
                   army.tactic, army.tech, army.moralbonus)
        army.soldiers -= take
        self.teams[army.team].armies.append(det)
        return det

    def _merge(self, base, other):
        """Влить отряд `other` в `base`."""
        if other is base:
            return
        base.soldiers += other.soldiers
        base.losses += other.losses
        team = self.teams[base.team]
        if other in team.armies:
            team.armies.remove(other)
        self.army_front.pop(id(other), None)

    def _enemy_force(self, num, fronts):
        """Сколько вражеских солдат стоит на каждом фронте команды num."""
        force = {}
        for j in fronts:
            other = self._other_at(j, num)
            if other is None or other in self.expelled:
                force[j] = 0
                continue
            force[j] = sum(x.soldiers for x in self.teams[other].armies
                           if x.soldiers > 0 and self.army_front.get(id(x)) == j)
        return force

    def _remap_armies(self, old_fronts):
        """После изменения числа отрезков переназначить армии на ближайшие фронты."""
        new_fronts = self._front_indices()
        for num in self.order:
            cands = [j for j in new_fronts
                     if self.owners[j - 1] == num or self.owners[j] == num]
            for a in self.teams[num].armies:
                j = self.army_front.get(id(a))
                if j in new_fronts and (self.owners[j - 1] == num or self.owners[j] == num):
                    continue
                if not cands:
                    self.army_front.pop(id(a), None)
                    continue
                old_x = old_fronts.get(j)
                if old_x is None:
                    self.army_front[id(a)] = cands[0]
                else:
                    self.army_front[id(a)] = min(cands, key=lambda k: abs(self.bounds[k] - old_x))

    def _normalize(self):
        """Упорядочить границы и слить соседние отрезки одной команды.

        Отрезки нулевой ширины не выбрасываем: команда, зажатая в ноль,
        продолжает бой (важно для защитника — его нельзя «оттеснить»).
        """
        old_fronts = {j: self.bounds[j] for j in self._front_indices()}
        self.bounds[0] = 0.0
        self.bounds[-1] = 100.0
        for j in range(1, len(self.bounds) - 1):
            lo, hi = self.bounds[j - 1], self.bounds[j + 1]
            self.bounds[j] = min(max(self.bounds[j], lo), hi)

        owners = [self.owners[0]]
        bounds = [self.bounds[0], self.bounds[1]]
        for i in range(1, len(self.owners)):
            if owners[-1] == self.owners[i]:
                bounds[-1] = self.bounds[i + 1]
            else:
                owners.append(self.owners[i])
                bounds.append(self.bounds[i + 1])
        self.owners = owners
        self.bounds = bounds
        self._remap_armies(old_fronts)

    def _remove_team_intervals(self, num):
        """Убрать из региона все отрезки команды (после «оттеснения»)."""
        old_fronts = {j: self.bounds[j] for j in self._front_indices()}
        owners = []
        bounds = [self.bounds[0]]
        for i, o in enumerate(self.owners):
            if o == num:
                if owners:                       # отрезок поглощается соседом
                    bounds[-1] = self.bounds[i + 1]
                continue
            if owners and owners[-1] == o:
                bounds[-1] = self.bounds[i + 1]
            else:
                owners.append(o)
                bounds.append(self.bounds[i + 1])
        if not owners:
            owners = [self.defender_num]
            bounds = [0.0, 100.0]
        bounds[0] = 0.0
        bounds[-1] = 100.0
        self.owners = owners
        self.bounds = bounds
        self._remap_armies(old_fronts)

    def _reorganize(self):
        """Деление и слияние армий по фронтам.

        У команды на каждом её фронте — свой отряд; численность пропорциональна
        количеству врага на этом фронте. Перераспределяем только при реальной
        необходимости (пустой фронт с врагом, несколько отрядов на фронте,
        отряд там, где врага нет) — чтобы не переписывать заданные армии.
        """
        for num in self.order:
            if num in self.expelled:
                continue
            team = self.teams[num]
            fronts = self._fronts_for(num)
            if not fronts:
                continue

            # убираем полностью погибшие отряды
            for a in [a for a in team.armies if a.soldiers <= 0]:
                team.armies.remove(a)
                self.army_front.pop(id(a), None)
            total = sum(a.soldiers for a in team.armies)
            if total <= 0:
                continue

            enemy = self._enemy_force(num, fronts)
            k = len(fronts)
            if k == 1:
                desired = {fronts[0]: int(total)}
            else:
                weights = {j: float(enemy[j]) for j in fronts}
                tw = sum(weights.values())
                if tw <= 0:
                    weights = {j: 1.0 for j in fronts}
                    tw = float(k)
                raw = {j: total * weights[j] / tw for j in fronts}
                desired = {j: int(raw[j]) for j in fronts}
                rem = int(total) - sum(desired.values())
                frac = sorted(fronts, key=lambda j: raw[j] - desired[j], reverse=True)
                for i in range(max(0, rem)):
                    desired[frac[i % k]] += 1

            by_front = {}
            for a in list(team.armies):
                j = self.army_front.get(id(a))
                if j not in fronts:
                    j = fronts[0]
                    self.army_front[id(a)] = j
                by_front.setdefault(j, []).append(a)

            need = any(len(arr) > 1 for arr in by_front.values())
            for j in fronts:
                if enemy.get(j, 0) > 0 and j not in by_front:
                    need = True
                if enemy.get(j, 0) <= 0 and j in by_front and len(team.armies) > 1:
                    need = True
            if not need:
                continue

            # 1) свести все отряды одного фронта в один
            for j, arr in by_front.items():
                base = arr[0]
                for other in arr[1:]:
                    self._merge(base, other)

            # 2) прикрыть пустой фронт — отделить часть от крупнейшей армии
            have = {self.army_front.get(id(a)): a for a in team.armies}
            for j in fronts:
                if desired.get(j, 0) >= 2 and j not in have:
                    donor = max(team.armies, key=lambda x: x.soldiers)
                    det = self._split(donor, max(1, donor.soldiers // 2))
                    if det is not None:
                        self.army_front[id(det)] = j
                        have[j] = det

            # 3) где врага нет — отряд не нужен
            for a in list(team.armies):
                j = self.army_front.get(id(a))
                if desired.get(j, 0) < 1 and len(team.armies) > 1:
                    team.armies.remove(a)
                    self.army_front.pop(id(a), None)
                    dst = max(team.armies, key=lambda x: x.soldiers)
                    dst.soldiers += a.soldiers
                    dst.losses += a.losses

            # 4) подгоняем размеры отрядов (перелив солдат)
            armies_now = list(team.armies)
            diff = {id(a): desired.get(self.army_front.get(id(a)), 0) - a.soldiers
                    for a in armies_now}
            givers = [a for a in armies_now if diff[id(a)] < 0]
            gi = 0
            for need_a in sorted([a for a in armies_now if diff[id(a)] > 0],
                                 key=lambda x: -diff[id(x)]):
                want = diff[id(need_a)]
                while want > 0 and gi < len(givers):
                    g = givers[gi]
                    avail = -diff[id(g)]
                    if avail <= 0:
                        gi += 1
                        continue
                    give = min(want, avail)
                    g.soldiers -= give
                    need_a.soldiers += give
                    diff[id(g)] += give
                    diff[id(need_a)] -= give
                    want -= give
                    if diff[id(g)] >= 0:
                        gi += 1

    # ---------------- приказы игрока ----------------
    def support_team(self, num):
        """Перебросить войска на самый угрожаемый фронт команды."""
        if num in self.expelled:
            return False
        fronts = self._fronts_for(num)
        if len(fronts) < 2:
            return False
        enemy = self._enemy_force(num, fronts)
        target = max(fronts, key=lambda j: enemy.get(j, 0))
        others = [j for j in fronts if j != target]
        if not others:
            return False
        source = min(others, key=lambda j: enemy.get(j, 0))
        team = self.teams[num]
        src = [a for a in team.armies
               if a.soldiers > 0 and self.army_front.get(id(a)) == source]
        if not src:
            return False
        donor = max(src, key=lambda a: a.soldiers)
        det = self._split(donor, max(1, int(donor.soldiers * SUPPORT_FRACTION)))
        if det is None:
            return False
        self.army_front[id(det)] = target
        self._log(f"Команда {num}: подкрепление на фронт")
        return True

    def create_front(self, num):
        """Создать новый фронт — клин (клещи) в тыл соседу."""
        if num in self.expelled:
            return False
        fronts = self._fronts_for(num)
        if not fronts:
            return False

        # цель — сосед, против которого на нашем фронте больше всего врага
        target = None
        for j in fronts:
            other = self._other_at(j, num)
            if other is None or other in self.expelled:
                continue
            force = sum(a.soldiers for a in self.teams[other].armies
                        if a.soldiers > 0 and self.army_front.get(id(a)) == j)
            if target is None or force > target[1]:
                target = (j, force, other)
        if target is None:
            return False
        j, _, b = target

        # отрезок соседа b, который выходит на наш фронт
        if self.owners[j] == b:
            i = j
        elif self.owners[j - 1] == b:
            i = j - 1
        else:
            return False

        width = min(NEW_FRONT_WIDTH, (self.bounds[i + 1] - self.bounds[i]) * 0.6)
        if width < MIN_FRONT_WIDTH:
            return False

        # клин врезается в середину отрезка соседа -> враг зажат с двух сторон
        center = (self.bounds[i] + self.bounds[i + 1]) / 2.0
        p0, p1 = center - width / 2.0, center + width / 2.0
        old_fronts = {fj: self.bounds[fj] for fj in self._front_indices()}
        self.owners = self.owners[:i] + [b, num, b] + self.owners[i + 1:]
        self.bounds = self.bounds[:i + 1] + [p0, p1] + self.bounds[i + 1:]
        self._remap_armies(old_fronts)

        # выделяем войска в клин с самой крупной армии команды
        pocket_front = i + 1
        armies = [a for a in self.teams[num].armies
                  if a.soldiers > 0 and self.army_front.get(id(a)) is not None]
        if armies:
            src = max(armies, key=lambda a: a.soldiers)
            det = self._split(src, max(1, int(src.soldiers * NEW_FRONT_COMMIT)))
            if det is not None:
                self.army_front[id(det)] = pocket_front
        self._log(f"Команда {num}: создан новый фронт")
        return True

    # ---------------- раунд боя ----------------
    def _log(self, text):
        self.log.append(text)
        if len(self.log) > 5:
            self.log.pop(0)

    def _battle_round(self):
        self.round += 1
        self._reorganize()         # деление/слияние армий по фронтам
        active = self._active_armies()

        # 1) урон каждой армии
        dmg = {}
        for a in active:
            team = self.teams[a.team]
            r = compute_rate(a.general, a.land, a.tactic, a.moralbonus, team.morale, a.tech)
            luck = random.uniform(0.7, 1.3)
            dmg[id(a)] = a.soldiers * r / 1000.0 * luck * DAMAGE_SCALE * team.mod

        # 2) бьют всех соседей (по соседним командам), деля урон поровну.
        #    Для территории считаем отдельно: фронт держат армии, приписанные
        #    к нему (army_front). Нет армии на фронте — его продавливает враг.
        damage_to = {id(a): 0.0 for a in active}
        front_press = {}
        for num in self.order:
            if num in self.expelled:
                continue
            team = self.teams[num]
            nbrs = self._neighbors(num)
            by_team = {x: [b for b in active if b.team == x] for x in nbrs}
            by_team = {x: v for x, v in by_team.items() if v}
            if not by_team:
                continue
            for a in team.armies:
                d = dmg.get(id(a), 0.0)
                if d <= 0:
                    continue
                share = d / len(by_team)      # урон делится по соседним КОМАНДАМ
                for x, arr in by_team.items():
                    each = share / len(arr)
                    for b in arr:
                        damage_to[id(b)] += each
                j = self.army_front.get(id(a))
                if j is not None:
                    front_press[(num, j)] = front_press.get((num, j), 0.0) + share

        # 3) потери
        round_losses = {num: 0.0 for num in self.order}
        for a in active:
            if a.soldiers <= 0:
                continue
            dead = min(a.soldiers, round(damage_to.get(id(a), 0.0)))
            a.soldiers -= dead
            a.losses += dead
            round_losses[a.team] += dead
            self.teams[a.team].losses += dead

        # 4) мораль
        for num in self.order:
            if num in self.expelled:
                continue
            team = self.teams[num]
            nbrs = self._neighbors(num)
            enemy_losses = sum(round_losses[m] for m in nbrs)
            team.morale = update_morale(team.morale, round_losses[num], enemy_losses, team.soldiers)

        # 5) движение фронтов: давление только от армий этого фронта
        for j in self._front_indices():
            left, right = self.owners[j - 1], self.owners[j]
            dl = front_press.get((left, j), 0.0)
            dr = front_press.get((right, j), 0.0)
            if dl + dr > 0:
                self.bounds[j] += FRONT_SPEED * (dl - dr) / (dl + dr)
        self._normalize()

        # 6) «оттеснение»: атакующий, потерявший всю территорию, выходит из региона
        self._check_expulsion()

        # 7) завершение
        alive = [num for num in self.order
                 if num not in self.expelled and self.teams[num].soldiers >= LIMIT]
        attackers_alive = [num for num in self.order if self.teams[num].is_attacker
                           and num not in self.expelled and self.teams[num].soldiers >= LIMIT]
        if self.defender_num not in alive:
            self.finished = True
            self.winner = "ПОБЕДА АТАКУЮЩИХ"
            self._log(f"Раунд {self.round}: защитник уничтожен")
        elif not attackers_alive:
            self.finished = True
            self.winner = f"ПОБЕДА ЗАЩИТНИКА (команда {self.defender_num})"
            self._log(f"Раунд {self.round}: атакующие отбиты")
        elif len(alive) <= 1:
            self.finished = True
            self.winner = f"ПОБЕДА КОМАНДЫ {alive[0]}" if alive else "ВСЕ РАЗБИТЫ"
            self._log(f"Раунд {self.round}: {self.winner.lower()}")
        elif self.round % 100 == 0:
            t = self.territory()
            self._log(f"Р.{self.round}: " + " / ".join(f"{t[m]:.0f}%" for m in self.order))

        if self.finished:
            self._snap_territory(alive)

    def _check_expulsion(self):
        t = self.territory()
        for num in self.order:
            if (self.teams[num].is_attacker and num not in self.expelled
                    and t.get(num, 0.0) <= 1e-6):
                self.expelled.add(num)
                for a in self.teams[num].armies:
                    self.army_front.pop(id(a), None)
                self._remove_team_intervals(num)
                self._log(f"Раунд {self.round}: атакующий {num} оттеснён")

    def _snap_territory(self, alive):
        """По завершении раздать всю территорию выжившим пропорционально силам."""
        if not alive:
            return
        total = sum(self.teams[num].soldiers for num in alive) or 1
        owners = []
        bounds = [0.0]
        acc = 0.0
        for num in self.order:
            if num in alive:
                owners.append(num)
                acc += self.teams[num].soldiers / total * 100.0
                bounds.append(acc)
        bounds[-1] = 100.0
        self.owners = owners
        self.bounds = bounds

    def step(self, n=1):
        done = 0
        for _ in range(n):
            if self.finished:
                break
            self._battle_round()
            done += 1
        return done


# ============================ КОНСТАНТЫ UI ============================
W, H = 1160, 740
REGION_RECT = pygame.Rect(25, 90, 780, 520)

PALETTE = [(70, 140, 255), (235, 70, 70), (90, 200, 120), (210, 140, 255)]
PALETTE_LIGHT = [(120, 185, 255), (255, 130, 120), (150, 235, 180), (225, 180, 255)]

BG_DARK = (26, 28, 34)
BG_PANEL = (38, 41, 48)
TEXT = (230, 233, 238)
MUTED = (150, 154, 162)
GRID = (52, 56, 64)
REGION_BORDER = (200, 200, 210)

PANEL_W = 310
PANEL_H = 116
PANEL_GAP = 10
PANEL_X = W - PANEL_W - 20

BTN_W, BTN_H, BTN_GAP, BTN_X0, BTN_Y = 148, 42, 7, 25, 660


def _btn(i):
    return pygame.Rect(BTN_X0 + i * (BTN_W + BTN_GAP), BTN_Y, BTN_W, BTN_H)


BTN_PAUSE = _btn(0)
BTN_STEP = _btn(1)
BTN_RESET = _btn(2)
BTN_SUPPORT = _btn(3)
BTN_FRONT = _btn(4)
BTN_OBS = _btn(5)


def panel_rect(idx):
    return pygame.Rect(PANEL_X, 90 + idx * (PANEL_H + PANEL_GAP), PANEL_W, PANEL_H)


def fmt(n):
    return f"{n:,}".replace(",", " ")


def mix(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


# ============================ «ЖИВАЯ» КАРТА РЕГИОНА ============================
_WAVE_CACHE = {}


def wave_profile(seed, n=41):
    """Нормированный (max|x|=1) статичный профиль изгиба границы владения."""
    prof = _WAVE_CACHE.get(seed)
    if prof is not None:
        return prof
    r = random.Random(seed)
    a1, f1, p1 = r.uniform(0.35, 1.0), r.uniform(1.1, 2.1), r.uniform(0, 6.283)
    a2, f2, p2 = r.uniform(0.15, 0.45), r.uniform(2.4, 4.6), r.uniform(0, 6.283)
    a3, f3, p3 = r.uniform(0.06, 0.20), r.uniform(5.0, 8.5), r.uniform(0, 6.283)
    prof = []
    for i in range(n):
        t = i / (n - 1)
        env = math.sin(math.pi * t)
        prof.append((a1 * math.sin(6.283185 * f1 * t + p1)
                     + a2 * math.sin(6.283185 * f2 * t + p2)
                     + a3 * math.sin(6.283185 * f3 * t + p3)) * env)
    m = max(1e-6, max(abs(v) for v in prof))
    prof = [v / m for v in prof]
    _WAVE_CACHE[seed] = prof
    return prof


def curve_x(pts, y):
    """X точки кривой на высоте y (линейная интерполяция, y монотонна)."""
    if y <= pts[0][1]:
        return pts[0][0]
    for k in range(1, len(pts)):
        if y <= pts[k][1]:
            t = (y - pts[k - 1][1]) / max(1e-6, pts[k][1] - pts[k - 1][1])
            return pts[k - 1][0] + (pts[k][0] - pts[k - 1][0]) * t
    return pts[-1][0]


_REGION_TEX = None


def region_tex():
    """Ландшафтная светотень поверх территорий (без иконок/лесов)."""
    global _REGION_TEX
    if _REGION_TEX is None:
        rng = random.Random(4242)

        def layer(size, lo, hi):
            s = pygame.Surface(size)
            for yy in range(size[1]):
                for xx in range(size[0]):
                    v = rng.randint(lo, hi)
                    s.set_at((xx, yy), (v, v, v))
            return pygame.transform.smoothscale(s, (REGION_RECT.w, REGION_RECT.h))

        tex = layer((40, 26), 216, 252)
        tex.blit(layer((150, 96), 240, 255), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        _REGION_TEX = tex
    return _REGION_TEX


_REGION_LINES = None


def region_lines():
    """Тонкие «внутренние» линии карты — как на примере."""
    global _REGION_LINES
    if _REGION_LINES is None:
        r = REGION_RECT
        rnd = random.Random(99)
        lines = []
        for _ in range(11):
            horiz = rnd.random() < 0.5
            a = rnd.uniform(0.15, 0.85)
            amp = rnd.uniform(18, 55)
            ph = rnd.uniform(0, 6.283)
            f = rnd.uniform(1.2, 2.6)
            pts = []
            for k in range(25):
                t = k / 24.0
                if horiz:
                    x = r.w * t
                    y = r.h * a + math.sin(t * 6.283185 * f + ph) * amp
                else:
                    y = r.h * t
                    x = r.w * a + math.sin(t * 6.283185 * f + ph) * amp * 0.6
                pts.append((x, y))
            lines.append(pts)
        _REGION_LINES = lines
    return _REGION_LINES


# ============================ ИИ НАБЛЮДАТЕЛЯ ============================
class BattleAI:
    """Командует всеми сторонами: переброски на угрожаемый фронт и клинья."""

    def __init__(self, sim):
        self.sim = sim
        self.cd = {num: random.uniform(0.5, 2.0) for num in sim.order}

    def update(self, dt):
        sim = self.sim
        if sim.finished:
            return
        for num in sim.order:
            if num in sim.expelled:
                continue
            self.cd[num] -= dt
            if self.cd[num] > 0:
                continue
            self.cd[num] = random.uniform(0.8, 2.2)
            fronts = sim._fronts_for(num)
            if len(fronts) >= 2:
                enemy = sim._enemy_force(num, fronts)
                hi, lo = max(enemy.values()), min(enemy.values())
                if hi > 0 and hi > lo * 1.6 and random.random() < 0.55:
                    sim.support_team(num)
                    continue
            if random.random() < 0.10 and sim.round > 15:
                sim.create_front(num)


# ============================ ОТРИСОВКА ============================
def draw_label(screen, font, text, x, y, color=TEXT):
    screen.blit(font.render(text, True, color), (x, y))


def draw_progress(screen, x, y, w, h, frac, color):
    pygame.draw.rect(screen, (20, 22, 26), (x, y, w, h), border_radius=h // 2)
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        pygame.draw.rect(screen, color, (x, y, int(w * frac), h), border_radius=h // 2)


def render_outline(font, text, fill=(255, 255, 255), outline=(12, 14, 20), thick=4):
    """Крупный текст с толстой обводкой — как числа на карте в примере."""
    base = font.render(text, True, fill)
    w, h = base.get_size()
    surf = pygame.Surface((w + 2 * thick, h + 2 * thick), pygame.SRCALPHA)
    out = font.render(text, True, outline)
    for dx in range(-thick, thick + 1):
        for dy in range(-thick, thick + 1):
            if dx * dx + dy * dy <= thick * thick:
                surf.blit(out, (thick + dx, thick + dy))
    surf.blit(base, (thick, thick))
    return surf


def draw_front_glow(surf, pts, height):
    """Мягкое свечение зоны боя вдоль изогнутой линии границы. Рисуется на
    отдельном слое и затем накладывается на территории, поэтому цвет смешивается."""
    t = pygame.time.get_ticks() / 1000.0
    band = 60
    ys = list(range(0, height + 1, 8))
    wn = [math.sin(y * 0.021 + t * 1.5) * 0.55
          + math.sin(y * 0.052 - t * 1.05) * 0.30
          + math.sin(y * 0.011 + t * 0.7) * 0.15 for y in ys]

    def band_pts(half, s):
        left = [(curve_x(pts, y) - half + wn[i] * s, y) for i, y in enumerate(ys)]
        right = [(curve_x(pts, y) + half + wn[i] * s * 0.85, y) for i, y in enumerate(ys)]
        return left + right[::-1]

    pygame.draw.polygon(surf, (18, 9, 4, 95), band_pts(band * 0.8, 3.2))
    for half in range(band, 0, -4):
        alpha = 12 if half > 8 else 16
        pygame.draw.polygon(surf, (255, 190, 92, alpha),
                            band_pts(half, 4.5 + half * 0.14))
    pygame.draw.polygon(surf, (255, 236, 190, 120), band_pts(4.0, 4.0))
    line = [(curve_x(pts, y) + wn[i] * 2.6, y) for i, y in enumerate(ys)]
    pygame.draw.lines(surf, (255, 252, 240, 225), False, line, 3)


def displayed_territory(sim):
    t = {num: 0.0 for num in sim.order}
    for i, o in enumerate(sim.owners):
        t[o] += sim.display[i + 1] - sim.display[i]
    return t


def build_curves(sim, r):
    """Кривые границ владений в локальных координатах региона.
    Соседние отрезки используют одну и ту же кривую общего края — щелей нет.
    Узкие владения (плацдарм 1%) рисуем с минимальной шириной, чтобы их было видно;
    амплитуда изгиба ограничена шириной самых узких соседних отрезков."""
    nseg = len(sim.owners)
    xs = [r.w * b / 100.0 for b in sim.display]
    min_w = 9.0
    for i in range(1, nseg):
        xs[i] = max(xs[i], xs[i - 1] + min_w)
    for i in range(nseg - 1, 0, -1):
        xs[i] = min(xs[i], xs[i + 1] - min_w)
    curves = []
    for j in range(nseg + 1):
        if j == 0 or j == nseg:
            curves.append([(xs[j], 0.0), (xs[j], float(r.h))])
            continue
        seg_l = xs[j] - xs[j - 1]
        seg_r = xs[j + 1] - xs[j]
        amp = max(2.5, min(16.0, 0.42 * min(seg_l, seg_r)))
        prof = wave_profile(j * 131 + 7)
        m = len(prof)
        curves.append([(xs[j] + prof[i] * amp, r.h * i / (m - 1)) for i in range(m)])
    return curves


def draw_region(screen, sim, font_num):
    r = REGION_RECT
    sim.ease_display()          # плавное движение фронта

    mask = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), (0, 0, r.w, r.h), border_radius=24)

    content = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
    content.fill((16, 15, 14, 255))

    curves = build_curves(sim, r)

    # территории команд — полигоны между соседними кривыми
    for i, o in enumerate(sim.owners):
        ci = sim.index.get(o, 0) % len(PALETTE)
        poly = curves[i] + curves[i + 1][::-1]
        pygame.draw.polygon(content, PALETTE[ci], poly)

    # тонкие внутренние линии карты
    ls = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
    for ln in region_lines():
        pygame.draw.lines(ls, (255, 255, 255, 26), False, ln, 1)
    content.blit(ls, (0, 0))

    # ландшафтная текстура (светотень)
    content.blit(region_tex(), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    # тёмные «государственные» обводки по границам владений
    for j in range(1, len(sim.owners)):
        ci = sim.index.get(sim.owners[j - 1], 0) % len(PALETTE)
        pygame.draw.lines(content, mix(PALETTE[ci], (6, 7, 9), 0.62), False, curves[j], 3)

    # фронты: свечение отдельным слоем поверх территорий
    effects = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
    for j in sim._front_indices():
        if 0 < j < len(curves) - 1:
            draw_front_glow(effects, curves[j], r.h)
    content.blit(effects, (0, 0))

    content.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    screen.blit(content, (r.x, r.y))
    pygame.draw.rect(screen, (10, 11, 14), r, width=8, border_radius=26)
    pygame.draw.rect(screen, REGION_BORDER, r, width=3, border_radius=26)

    # крупные числа количества армий вдоль линий фронта
    gap = 8
    ref_w = render_outline(font_num, "0").get_height()  # после поворота ширина = высота текста
    for j in sim._front_indices():
        fx = r.x + curve_x(curves[j], r.h / 2.0)
        left_num = sim.owners[j - 1]
        right_num = sim.owners[j]
        la = [a for a in sim.teams[left_num].armies
              if sim.army_front.get(id(a)) == j and a.soldiers > 0]
        ra = [a for a in sim.teams[right_num].armies
              if sim.army_front.get(id(a)) == j and a.soldiers > 0]

        w = ref_w
        left_xs = [max(r.x + 4, int(fx - gap - w - k * (w + gap))) for k in range(len(la))]
        right_xs = [min(r.right - 4 - w, int(fx + gap + k * (w + gap))) for k in range(len(ra))]
        if left_xs and right_xs and right_xs[0] < left_xs[0] + w + gap:
            shift = left_xs[0] + w + gap - right_xs[0]
            right_xs = [min(r.right - 4 - w, x + shift) for x in right_xs]
            if right_xs[0] < left_xs[0] + w + gap:
                shift = left_xs[0] + w + gap - right_xs[0]
                left_xs = [max(r.x + 4, x - shift) for x in left_xs]

        for k, a in enumerate(la):
            img = pygame.transform.rotate(render_outline(font_num, str(a.soldiers)), 90)
            screen.blit(img, (left_xs[k], r.centery - img.get_height() // 2))
        for k, a in enumerate(ra):
            img = pygame.transform.rotate(render_outline(font_num, str(a.soldiers)), -90)
            screen.blit(img, (right_xs[k], r.centery - img.get_height() // 2))


def draw_team_panel(screen, sim, idx, rect, font_b, font_sm, terr, selected):
    num = sim.order[idx]
    team = sim.teams[num]
    color = PALETTE[idx % len(PALETTE)]
    color_l = PALETTE_LIGHT[idx % len(PALETTE)]
    x, y, w, h = rect

    pygame.draw.rect(screen, BG_PANEL, rect, border_radius=10)
    pygame.draw.rect(screen, color, (x, y, 7, h))
    if selected:
        pygame.draw.rect(screen, (255, 220, 90), rect, width=3, border_radius=10)
    screen.blit(font_sm.render(f"КОМАНДА {num} — {team.role}", True, color_l), (x + 16, y + 5))

    screen.blit(font_b.render(f"Всего {fmt(team.soldiers)}", True, TEXT), (x + 16, y + 27))
    loss_img = font_b.render(f"потери {fmt(team.losses)}", True, (255, 130, 120))
    screen.blit(loss_img, (x + w - 16 - loss_img.get_width(), y + 27))

    screen.blit(font_b.render("Мораль", True, MUTED), (x + 16, y + 49))
    draw_progress(screen, x + 16, y + 67, w - 32, 13, team.morale / 100.0, color)

    if num in sim.expelled:
        screen.blit(font_b.render("ОТТЕСНЁН ИЗ РЕГИОНА", True, (255, 120, 90)), (x + 16, y + 84))
    else:
        screen.blit(font_b.render(f"Территория {terr:.1f}%", True, MUTED), (x + 16, y + 84))


def draw_button(screen, font, rect, text, color, disabled=False):
    base = (58, 61, 68) if disabled else color
    pygame.draw.rect(screen, base, rect, border_radius=9)
    img = font.render(text, True, (140, 144, 152) if disabled else (255, 255, 255))
    screen.blit(img, (rect.centerx - img.get_width() // 2, rect.centery - img.get_height() // 2))


def draw(screen, sim, paused, speed, selected, observer=False):
    screen.fill(BG_DARK)
    font_t = pygame.font.SysFont("segoeui", 26, bold=True)
    font_b = pygame.font.SysFont("segoeui", 16)
    font_sm = pygame.font.SysFont("segoeui", 17, bold=True)
    font_num = pygame.font.SysFont("segoeui", 38, bold=True)

    draw_label(screen, font_t, "БАЛАНС СИЛ — БИТВА ЗА РЕГИОН", 30, 22, (255, 255, 255))
    if observer:
        draw_label(screen, font_sm, "РЕЖИМ НАБЛЮДАТЕЛЯ", 520, 26, (255, 220, 120))
    pygame.draw.rect(screen, (60, 64, 72), (5, 64, W - 10, 3))

    draw_region(screen, sim, font_num)

    terr = displayed_territory(sim)
    for idx in range(sim.n):
        draw_team_panel(screen, sim, idx, panel_rect(idx), font_b, font_sm,
                        terr.get(sim.order[idx], 0.0), idx == selected and not observer)

    y = 90 + sim.n * (PANEL_H + PANEL_GAP) + 6
    screen.blit(font_sm.render(f"Раунд: {sim.round}", True, TEXT), (PANEL_X, y))
    if sim.finished:
        screen.blit(font_sm.render(sim.winner, True, (255, 220, 90)), (PANEL_X, y + 26))
    else:
        st = "Идёт бой..." if not paused else "Пауза"
        col = (120, 220, 120) if not paused else (230, 200, 120)
        screen.blit(font_b.render(st, True, col), (PANEL_X, y + 29))
    y += 54

    screen.blit(font_b.render("Журнал боя", True, MUTED), (PANEL_X, y))
    for i, line in enumerate(sim.log):
        screen.blit(font_b.render(line, True, TEXT), (PANEL_X, y + 22 + i * 19))

    # подсказка о приказы / наблюдатель
    if observer:
        draw_label(screen, font_b, "Приказы отдаёт ИИ — просто следите за боем  (O — выйти из наблюдателя)",
                   25, 632, (255, 220, 120))
    else:
        sel_num = sim.order[selected]
        sel_col = PALETTE_LIGHT[selected % len(PALETTE_LIGHT)]
        screen.blit(font_b.render(
            f"Для приказов выбрана команда {sel_num}  (клик по панели / клавиши 1–{sim.n})",
            True, sel_col), (25, 632))

    color_pause = (80, 130, 240) if paused else (55, 210, 100)
    draw_button(screen, font_b, BTN_PAUSE, "ПАУЗА / ПУСК", color_pause)
    draw_button(screen, font_b, BTN_STEP, "ШАГ +10", (230, 165, 60))
    draw_button(screen, font_b, BTN_RESET, "СБРОС", (230, 80, 80))
    draw_button(screen, font_b, BTN_SUPPORT, "ПОДДЕРЖАТЬ", (60, 160, 220), disabled=observer)
    draw_button(screen, font_b, BTN_FRONT, "СОЗДАТЬ ФРОНТ", (170, 120, 230), disabled=observer)
    draw_button(screen, font_b, BTN_OBS, "НАБЛЮДАТЕЛЬ", (255, 220, 120) if observer else (85, 92, 106))
    draw_label(screen, font_b, f"Скорость: {speed} р./кадр  (+/-)", 30, 710, MUTED)


def main():
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Баланс сил — Битва за регион")
    clock = pygame.time.Clock()

    sim = BattleSim()
    paused = False
    speed = 150
    selected = sim.index[sim.defender_num]
    observer = False
    ai = BattleAI(sim)

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_RIGHT:
                    sim.step(10)
                elif event.key == pygame.K_r:
                    sim.reset()
                    paused = False
                    selected = sim.index[sim.defender_num]
                    ai = BattleAI(sim)
                elif event.key == pygame.K_o:
                    observer = not observer
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    speed = min(50000, speed * 2)
                elif event.key == pygame.K_MINUS:
                    speed = max(5, speed // 2)
                elif pygame.K_1 <= event.key <= pygame.K_1 + sim.n - 1 and not observer:
                    selected = event.key - pygame.K_1
                elif event.key == pygame.K_s and not observer:
                    sim.support_team(sim.order[selected])
                elif event.key == pygame.K_f and not observer:
                    sim.create_front(sim.order[selected])
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = event.pos
                if BTN_PAUSE.collidepoint(pos):
                    paused = not paused
                elif BTN_STEP.collidepoint(pos):
                    sim.step(10)
                elif BTN_RESET.collidepoint(pos):
                    sim.reset()
                    paused = False
                    selected = sim.index[sim.defender_num]
                    ai = BattleAI(sim)
                elif BTN_OBS.collidepoint(pos):
                    observer = not observer
                elif not observer and BTN_SUPPORT.collidepoint(pos):
                    sim.support_team(sim.order[selected])
                elif not observer and BTN_FRONT.collidepoint(pos):
                    sim.create_front(sim.order[selected])
                elif not observer:
                    for idx in range(sim.n):
                        if panel_rect(idx).collidepoint(pos):
                            selected = idx
                            break

        if not paused:
            sim.step(speed)
            if observer:
                ai.update(dt)

        draw(screen, sim, paused, speed, selected, observer)
        pygame.display.flip()

    pygame.quit()


def shot_mode(argv):
    """Автотест-режим: сматывает бой и сохраняет кадр в PNG (без окна)."""
    import os
    import sys
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    out = argv[argv.index("--shot") + 1]
    rounds = int(argv[argv.index("--rounds") + 1]) if "--rounds" in argv else 120
    observer = "--observer" in argv
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    sim = BattleSim()
    ai = BattleAI(sim)
    for _ in range(rounds):
        sim.step(1)
        if observer:
            ai.update(1 / 30.0)
        if sim.finished:
            break
    for _ in range(12):        # дать фронтовым кривым догнать состояние
        draw(screen, sim, False, 1, 0, observer)
    pygame.image.save(screen, out)
    pygame.quit()
    print(f"shot saved: {out} (round={sim.round}, finished={sim.finished})")
    return 0


if __name__ == "__main__":
    import sys
    if "--shot" in sys.argv:
        sys.exit(shot_mode(sys.argv))
    main()
