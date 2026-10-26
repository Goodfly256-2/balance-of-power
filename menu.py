# Главное меню «Balance of Power»: вкладки «Играть», «Что новенького?»,
# «Повторы», «Настройки».
# - Играть: выбор сценария (карта и страны) и запуск strategy.run_game;
# - Что новенького?: список изменений из version.CHANGELOG и авто-проверка
#   обновлений (version.check_updates);
# - Настройки: громкость музыки, цифры на карте, названия стран, проверка
#   обновлений; всё сохраняется в settings.json (settings.py).
# Внизу окна — строка авторства: version.CREDIT.
import math
import os
import sys
import threading

import pygame

import audio
import loading
import replays
import settings as user_settings
import strategy
import version

W, H = 1280, 760
BG = (17, 19, 24)
PANEL = (26, 29, 36)
CARD = (35, 39, 48)
BORDER = (60, 66, 80)
TEXT = (228, 232, 240)
MUTED = (150, 156, 168)
ACCENT = (74, 144, 217)
GOOD = (96, 210, 140)
WARN = (235, 190, 90)
BAD = (226, 96, 80)

# ---- Донаты: сеть Polygon, USDT / USDC / POL ----
# Один адрес EVM на все три токена. Замените DONATE_ADDRESS на свой.
DONATE_ADDRESS = "0xa247dd17104ee5fae4b7576cf82872a4071b03ae"
DONATE_CHAIN = "Polygon"
DONATE_TOKENS = ("USDT", "USDC", "POL")
POLYGON_SCAN = "https://polygonscan.com/address/" + DONATE_ADDRESS


def mix(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def R(x, y, w, h):
    return pygame.Rect(x, y, w, h)


def draw_button(screen, font, rect, text, color, text_col=(255, 255, 255),
                active=False, disabled=False):
    mx, my = strategy.map_mouse(pygame.mouse.get_pos(), pygame.display.get_surface().get_size())
    hover = rect.collidepoint((mx, my)) and not disabled
    base = (50, 54, 64) if disabled else (mix(color, (255, 255, 255), 0.15) if hover else color)
    pygame.draw.rect(screen, base, rect, border_radius=8)
    if active:
        pygame.draw.rect(screen, (255, 235, 120), rect, width=2, border_radius=8)
    if not disabled:
        pygame.draw.rect(screen, mix(base, (0, 0, 0), 0.35), rect, width=1, border_radius=8)
    col = (120, 124, 132) if disabled else text_col
    img = font.render(text, True, col)
    screen.blit(img, (rect.centerx - img.get_width() // 2,
                      rect.centery - img.get_height() // 2))


def draw_card(screen, rect, color=CARD, border=BORDER, radius=10, border_w=1):
    pygame.draw.rect(screen, color, rect, border_radius=radius)
    if border_w:
        pygame.draw.rect(screen, border, rect, width=border_w, border_radius=radius)


def clip_text(font, text, max_w):
    if font.size(text)[0] <= max_w:
        return text
    cut = text
    while cut and font.size(cut + "…")[0] > max_w:
        cut = cut[:-1]
    return cut + "…"


# ---------------- фон меню ----------------
_DECOR = {}


def draw_background(screen, t):
    """Спокойный фон: виньетка + медленно плывущие «фронтиры»-линии."""
    key = "bg"
    surf = _DECOR.get(key)
    if surf is None:
        surf = pygame.Surface((W, H))
        for y in range(H):
            k = y / H
            surf.fill(mix((21, 24, 31), (10, 11, 16), k), (0, y, W, 1))
        _DECOR[key] = surf
    screen.blit(surf, (0, 0))
    lines = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(5):
        amp = 26 + i * 9
        y0 = 130 + i * 130
        speed = 0.11 + i * 0.03
        pts = []
        for x in range(0, W + 24, 24):
            yy = y0 + math.sin(x * 0.008 + t * speed + i * 1.7) * amp
            pts.append((x, yy))
        col = (74, 144, 217, 26 - i * 4)
        pygame.draw.lines(lines, col, False, pts, 2)
    screen.blit(lines, (0, 0))


# ---------------- раскладка ----------------
def tab_rects():
    labels = ["Играть", "Что новенького?", "Повторы", "Настройки", "Поддержать"]
    w, gap = 220, 10
    x0 = W // 2 - (len(labels) * w + (len(labels) - 1) * gap) // 2
    return [R(x0 + i * (w + gap), 120, w, 44) for i in range(len(labels))], labels


def scenario_rects():
    """Карточки сценариев: вертикальный список с полным описанием."""
    n = len(strategy.SCENARIOS)
    card_h = 64
    gap = 10
    top = 210
    x0 = (W - 780) // 2
    return [R(x0, top + i * (card_h + gap), 780, card_h) for i in range(n)]


class Menu:
    def __init__(self, screen):
        self.screen = screen
        self.tab = 0
        self.time = 0.0
        self.settings = user_settings.load()
        self.chosen_scenario = self.settings.get("last_scenario", "classic")
        if self.chosen_scenario not in strategy.SCENARIOS:
            self.chosen_scenario = "classic"
        self.update_status = "checking"    # checking | none | available | error
        self.update_info = None
        self.fonts = (
            pygame.font.SysFont("segoeui", 44, bold=True),   # 0 title
            pygame.font.SysFont("segoeui", 24, bold=True),   # 1 head
            pygame.font.SysFont("segoeui", 17),              # 2 body
            pygame.font.SysFont("segoeui", 14),              # 3 small
            pygame.font.SysFont("segoeui", 20, bold=True),   # 4 chip/button
            pygame.font.SysFont("segoeui", 34, bold=True),   # 5 scenario name
        )
        audio.set_volume(self.settings["music_volume"])
        audio.ensure_async()
        audio.play_menu()
        if self.settings.get("check_updates", True):
            threading.Thread(target=self._check_updates, daemon=True).start()
        else:
            self.update_status = "none"

    def _check_updates(self):
        info = version.check_updates()
        self.update_info = info
        if info.get("error"):
            self.update_status = "error"
        elif info.get("available"):
            self.update_status = "available"
        else:
            self.update_status = "none"

    # -------- отрисовка --------
    def draw(self):
        f_title, f_head, f_body, f_small, f_chip, f_sc = self.fonts
        screen = self.screen
        draw_background(screen, self.time)

        # заголовок
        t = version.GAME_TITLE
        img = f_title.render(t, True, TEXT)
        x = W // 2 - img.get_width() // 2
        sh = f_title.render(t, True, (0, 0, 0))
        screen.blit(sh, (x + 3, 44))
        screen.blit(img, (x, 40))
        sub = f_small.render(f"версия {version.VERSION}", True, MUTED)
        screen.blit(sub, (W // 2 - sub.get_width() // 2, 92))

        rects, labels = tab_rects()
        for i, (r, lab) in enumerate(zip(rects, labels)):
            active = self.tab == i
            draw_button(screen, f_chip, r, lab,
                        ACCENT if active else (48, 53, 64), active=active)

        if self.tab == 0:
            self.draw_play()
        elif self.tab == 1:
            self.draw_news()
        elif self.tab == 2:
            self.draw_replays_tab()
        elif self.tab == 3:
            self.draw_settings()
        else:
            self.draw_donate()

        # строка авторства
        credit = f_small.render(version.CREDIT, True, MUTED)
        screen.blit(credit, (W - credit.get_width() - 16, H - credit.get_height() - 12))

    def draw_play(self):
        f_title, f_head, f_body, f_small, f_chip, f_sc = self.fonts
        screen = self.screen
        hint = "Выберите сценарий и нажмите «В БОЙ»:"
        screen.blit(f_body.render(hint, True, MUTED), (W // 2 - f_body.size(hint)[0] // 2, 178))
        rects = scenario_rects()
        for i, (key, sc) in enumerate(strategy.SCENARIOS.items()):
            r = rects[i]
            sel = self.chosen_scenario == key
            draw_card(screen, r, CARD if not sel else (40, 52, 66),
                      ACCENT if sel else BORDER, 10, 2 if sel else 1)
            # ряд 1: название + флажки стран у кнопки
            screen.blit(f_head.render(clip_text(f_head, sc["name"], r.w - 130), True, TEXT),
                        (r.x + 14, r.y + 8))
            n_flags = min(8, len(sc["factions"]))
            fx = r.right - 92 - 14 - n_flags * 11
            for name, color, trait in sc["factions"][:n_flags]:
                pygame.draw.rect(screen, color, (fx, r.y + 13, 8, 11), border_radius=2)
                fx += 11
            # ряд 2: описание слева, сведения о карте справа
            grid = sc["grid"]
            info = f"карта {grid}×{grid} · стран: {len(sc['factions'])}"
            iw = f_small.size(info)[0]
            screen.blit(f_small.render(clip_text(f_small, sc["desc"], r.w - 28 - iw - 130), True, MUTED),
                        (r.x + 14, r.y + 36))
            screen.blit(f_small.render(info, True, MUTED), (r.right - 106 - iw, r.y + 36))
            draw_button(screen, f_small, R(r.right - 92, r.y + 16, 80, 32),
                        "В БОЙ", (70, 140, 90) if sel else (60, 64, 74))
        if self.update_status == "available" and self.update_info:
            info = self.update_info
            msg = f"Доступно обновление {info['remote']}! Подробности — во вкладке «Что новенького?»."
            img = f_body.render(msg, True, WARN)
            screen.blit(img, (W // 2 - img.get_width() // 2, H - 110))

    def draw_news(self):
        f_title, f_head, f_body, f_small, f_chip, f_sc = self.fonts
        screen = self.screen
        card = R((W - 760) // 2, 176, 760, H - 176 - 96)
        draw_card(screen, card, PANEL, BORDER, 12)
        y = card.y + 14
        # статус обновлений
        if self.update_status == "checking":
            dots = "." * (1 + int(self.time * 2) % 3)
            msg = f"Проверка обновлений{dots}"
            screen.blit(f_body.render(msg, True, MUTED), (card.x + 20, y))
            y += 26
        elif self.update_status == "available":
            info = self.update_info
            msg = f"Доступна новая версия: {info['remote']} (у вас {version.VERSION})"
            screen.blit(f_head.render(msg, True, WARN), (card.x + 20, y))
            if info.get("notes"):
                screen.blit(f_body.render(clip_text(f_body, info["notes"], card.w - 40), True, TEXT),
                            (card.x + 20, y + 28))
            btn = R(card.right - 150, y - 2, 130, 34)
            draw_button(screen, f_small, btn, "СКАЧАТЬ", (70, 140, 90))
            self._download_btn = (btn, info.get("url", version.UPDATE_URL))
            y += 58 if info.get("notes") else 40
        elif self.update_status == "error":
            screen.blit(f_body.render("Проверка обновлений не удалась: нет доступа к серверу.",
                                      True, MUTED), (card.x + 20, y))
            y += 26
        else:
            screen.blit(f_body.render("У вас установлена последняя версия.", True, GOOD),
                        (card.x + 20, y))
            y += 26
        y += 10
        # список изменений (с прокруткой колёсиком; обрезка по низу карточки)
        clip_bottom = card.bottom - 8
        pygame.draw.rect(screen, PANEL, (card.x + 1, clip_bottom, card.w - 2, card.bottom - clip_bottom))
        pygame.draw.rect(screen, BORDER, card, width=1, border_radius=12)
        sc = getattr(self, "news_scroll", 0)
        max_off = max(0, self._news_height - (clip_bottom - y - 4)) if hasattr(self, "_news_height") else 0
        sc = min(sc, max_off) if max_off > 0 else 0
        yy = y - sc
        for ver, date, items in version.CHANGELOG:
            if yy > clip_bottom:
                break
            if yy + 28 > card.y:
                screen.blit(f_head.render(f"Версия {ver} — {date}", True, TEXT), (card.x + 20, yy))
            yy += 28
            for it in items:
                words = it.split()
                line = ""
                for w in words:
                    trial = (line + " " + w).strip()
                    if f_body.size(trial)[0] > card.w - 70:
                        if yy + 22 > card.y and yy + 22 <= clip_bottom:
                            screen.blit(f_body.render("• " + line, True, MUTED), (card.x + 36, yy))
                        yy += 22
                        line = w
                    else:
                        line = trial
                if yy + 22 > card.y and yy + 22 <= clip_bottom:
                    screen.blit(f_body.render("• " + line, True, MUTED), (card.x + 36, yy))
                yy += 22
            yy += 12
        self._news_height = (yy - y) + sc
        # индикатор прокрутки
        if self._news_height > clip_bottom - y:
            bar_h = max(30, int((clip_bottom - y - 8) * (clip_bottom - y) / self._news_height))
            bar_y = y + 4 + int((clip_bottom - y - 8 - bar_h) * sc / max(1, self._news_height - (clip_bottom - y - 8)))
            pygame.draw.rect(screen, (70, 78, 92),
                             (card.right - 10, bar_y, 5, bar_h), border_radius=3)

    def draw_donate(self):
        """Вкладка «Поддержать»: адрес Polygon для USDT / USDC / POL."""
        f_title, f_head, f_body, f_small, f_chip, f_sc = self.fonts
        screen = self.screen
        card = R((W - 760) // 2, 176, 760, 380)
        draw_card(screen, card, PANEL, BORDER, 12)
        y = card.y + 18
        screen.blit(f_head.render("Поддержать разработку", True, TEXT), (card.x + 20, y))
        y += 34
        for line in ("Если игра понравилась — можно отправить донат в криптовалюте.",
                     "Сеть: Polygon. Принимаем USDT, USDC и POL на один адрес."):
            screen.blit(f_body.render(line, True, MUTED), (card.x + 20, y))
            y += 24
        y += 12

        # адрес: моноширинный, кнопка «КОПИРОВАТЬ»
        screen.blit(f_head.render("Адрес (Polygon):", True, TEXT), (card.x + 20, y))
        y += 30
        addr_rect = R(card.x + 20, y, card.w - 40, 44)
        draw_card(screen, addr_rect, (18, 20, 26), BORDER, 8, 1)
        f_mono = pygame.font.SysFont("consolas", 20, bold=True)
        shown = clip_text(f_mono, DONATE_ADDRESS, addr_rect.w - 24)
        img = f_mono.render(shown, True, (240, 244, 250))
        screen.blit(img, (addr_rect.x + 12,
                          addr_rect.centery - img.get_height() // 2))
        self._addr_rect = addr_rect

        btn = R(card.right - 170, card.y + card.h - 66, 150, 40)
        copied = getattr(self, "_copied_until", 0) > self.time
        draw_button(screen, f_chip, btn,
                    "СКОПИРОВАНО!" if copied else "КОПИРОВАТЬ",
                    (70, 140, 90) if not copied else (55, 110, 75))
        self._copy_btn = btn

        y2 = card.y + card.h - 58
        screen.blit(f_small.render(
            "Проверить адрес: polygonscan.com", True, MUTED), (card.x + 20, y2 + 10))
        self._scan_btn = R(card.x + 20, y2, 240, 34)
        draw_button(screen, f_small, self._scan_btn, "ОТКРЫТЬ POLYGONSCAN",
                    (70, 100, 130))
        # подсказка о токенах справа от кнопки
        tok = " · ".join(DONATE_TOKENS) + f"  ·  {DONATE_CHAIN}"
        screen.blit(f_small.render(tok, True, MUTED),
                    (self._scan_btn.right + 14, y2 + 10))

    def draw_settings(self):
        f_title, f_head, f_body, f_small, f_chip, f_sc = self.fonts
        screen = self.screen
        card = R((W - 620) // 2, 190, 620, 380)
        draw_card(screen, card, PANEL, BORDER, 12)
        self._sliders = []
        self._toggles = []
        y = card.y + 18

        screen.blit(f_head.render("Звук", True, TEXT), (card.x + 20, y))
        y += 30
        vol = self.settings["music_volume"]
        track = R(card.x + 20, y + 6, card.w - 200, 12)
        pygame.draw.rect(screen, (48, 52, 62), track, border_radius=6)
        pygame.draw.rect(screen, ACCENT, (track.x, track.y, int(track.w * vol), 12), border_radius=6)
        pygame.draw.circle(screen, (240, 244, 250), (track.x + int(track.w * vol), track.centery), 8)
        screen.blit(f_body.render(f"Музыка: {int(vol * 100)}%", True, MUTED),
                    (track.right + 14, y))
        self._sliders.append(("music_volume", track))
        y += 44

        screen.blit(f_head.render("Карта", True, TEXT), (card.x + 20, y))
        y += 30
        for key, label in (("show_numbers", "Показывать цифры на карте"),
                           ("show_names", "Названия стран на территориях"),
                           ("check_updates", "Проверять обновления при запуске")):
            on = bool(self.settings.get(key))
            btn = R(card.x + 20, y, 46, 26)
            draw_button(screen, f_small, btn, "ВКЛ" if on else "ВЫКЛ",
                        (55, 140, 90) if on else (90, 95, 105), active=on)
            screen.blit(f_body.render(label, True, TEXT), (btn.right + 14, y + 4))
            self._toggles.append((key, btn))
            y += 38

        y += 6
        screen.blit(f_head.render("Обновления", True, TEXT), (card.x + 20, y))
        y += 30
        draw_button(screen, f_small, R(card.x + 20, y, 210, 34),
                    "ПРОВЕРИТЬ СЕЙЧАС", (70, 100, 130))
        self._check_btn = R(card.x + 20, y, 210, 34)
        y += 48
        screen.blit(f_small.render("Настройки сохраняются автоматически (settings.json).",
                                   True, MUTED), (card.x + 20, y))

    # -------- события --------
    def _launch(self, key, screen):
        """Запуск партии: экран загрузки -> run_game -> возврат музыки меню.

        Важно: рисуем в реальное окно (pygame.display.get_surface()), а не в
        виртуальный буфер меню — иначе игра рендерится «в пустоту» и окно
        выглядит зависшим."""
        win = pygame.display.get_surface() or screen
        self.settings["last_scenario"] = key
        user_settings.save(self.settings)
        audio.stop()
        loading.show_game(win, strategy.SCENARIOS[key]["name"])
        strategy.run_game(key, {
            "on_exit": self._back_to_menu,
            "show_names": self.settings.get("show_names", True),
            "show_numbers": self.settings.get("show_numbers", False),
        }, screen=win, caption="Balance of Power")
        audio.set_volume(self.settings["music_volume"])
        audio.play_menu()

    def click(self, pos, button):
        if button != 1:
            return False
        rects, _ = tab_rects()
        for i, r in enumerate(rects):
            if r.collidepoint(pos):
                self.tab = i
                return True

        if self.tab == 0:
            for i, (key, sc) in enumerate(strategy.SCENARIOS.items()):
                r = scenario_rects()[i]
                if r.collidepoint(pos):
                    launch = R(r.right - 92, r.y + 16, 80, 32).collidepoint(pos)
                    if launch or self.chosen_scenario == key:
                        # клик по «В БОЙ» или повторный по выбранной карточке — старт
                        self._launch(key, self.screen)
                    else:
                        self.chosen_scenario = key
                    return True
            return False

        if self.tab == 1:
            btn = getattr(self, "_download_btn", None)
            if btn and btn[0].collidepoint(pos):
                import webbrowser
                webbrowser.open(btn[1])
                return True
            return False

        if self.tab == 2:
            # список повторов: клик по карточке — воспроизведение, по «×» — удаление
            self._replay_items = replays.list_replays()
            for i, info in enumerate(self._replay_items):
                r = replay_card_rect(i)
                if r.collidepoint(pos):
                    if R(r.right - 34, r.y + 8, 26, 26).collidepoint(pos):
                        replays.delete_replay(info["path"])
                        self._replay_items = replays.list_replays()
                        return True
                    self.open_replay(info["path"], self.screen)
                    return True
            return False

        if self.tab == 3:
            for key, sl in getattr(self, "_sliders", []):
                if sl.inflate(0, 24).collidepoint(pos):
                    frac = min(1.0, max(0.0, (pos[0] - sl.x) / max(1, sl.w)))
                    self.settings[key] = round(frac, 2)
                    audio.set_volume(self.settings[key])
                    user_settings.save(self.settings)
                    return True
            for key, btn in getattr(self, "_toggles", []):
                if btn.collidepoint(pos):
                    self.settings[key] = not self.settings.get(key)
                    user_settings.save(self.settings)
                    return True
            if getattr(self, "_check_btn", None) and self._check_btn.collidepoint(pos):
                self.update_status = "checking"
                threading.Thread(target=self._check_updates, daemon=True).start()
                return True
            return False

        if self.tab == 4:
            # донат: клик по адресу или кнопке — копировать; по кнопке — скан
            import pygame.scrap
            btn = getattr(self, "_copy_btn", None)
            addr = getattr(self, "_addr_rect", None)
            if btn and btn.collidepoint(pos) or (addr and addr.collidepoint(pos)):
                try:
                    pygame.scrap.init()
                    pygame.scrap.put_text(DONATE_ADDRESS)
                except Exception:
                    try:
                        import subprocess
                        subprocess.run(["clip"], input=DONATE_ADDRESS.encode("utf-16-le"),
                                       check=False)
                    except Exception:
                        pass
                self._copied_until = self.time + 2.0
                return True
            scan = getattr(self, "_scan_btn", None)
            if scan and scan.collidepoint(pos):
                import webbrowser
                webbrowser.open(POLYGON_SCAN)
                return True
            return False
        return False

    def drag(self, pos):
        """Зажатая мышь — тянем слайдер громкости."""
        for key, sl in getattr(self, "_sliders", []):
            if sl.inflate(30, 40).collidepoint(pos):
                frac = min(1.0, max(0.0, (pos[0] - sl.x) / max(1, sl.w)))
                self.settings[key] = round(frac, 2)
                audio.set_volume(self.settings[key])
                user_settings.save(self.settings)
                return True
        return False

    def _back_to_menu(self):
        audio.play_menu()

    # -------- вкладка «Повторы» --------
    def open_replay(self, path, screen):
        win = pygame.display.get_surface() or screen
        data = replays.load_replay(path)
        if not data:
            return
        audio.stop()
        ReplayViewer(win, data).run()
        audio.set_volume(self.settings["music_volume"])
        audio.play_menu()

    def draw_replays_tab(self):
        f_title, f_head, f_body, f_small, f_chip, f_sc = self.fonts
        screen = self.screen
        items = getattr(self, "_replay_items", None)
        if items is None:
            items = self._replay_items = replays.list_replays()
        hint = "Сохранённые партии (автосохранение — при завершении). Клик — смотреть:"
        screen.blit(f_body.render(hint, True, MUTED), (W // 2 - f_body.size(hint)[0] // 2, 178))
        if not items:
            msg = "Пока нет сохранённых повторов."
            img = f_head.render(msg, True, MUTED)
            screen.blit(img, (W // 2 - img.get_width() // 2, 300))
            return
        for i, info in enumerate(items[:8]):
            r = replay_card_rect(i)
            draw_card(screen, r, CARD, BORDER, 10, 1)
            # мини-флаги стран партии
            fx = r.x + 14
            for f in info.get("factions", [])[:6]:
                col = tuple(f.get("color", (120, 124, 132)))
                pygame.draw.rect(screen, col, (fx, r.y + 10, 16, 11), border_radius=2)
                fx += 19
            f_name = pygame.font.SysFont("segoeui", 21, bold=True)
            screen.blit(f_name.render(SC_NAME.get(info.get("scenario"), info.get("scenario", "?")),
                                      True, TEXT), (r.x + 14, r.y + 24))
            scr_line = f"{info.get('saved', '?')}   ·   итог: {info.get('winner', '—')}"
            screen.blit(f_small.render(clip_text(f_small, scr_line, r.w - 220), True, MUTED),
                        (r.x + 14, r.y + 44))
            kb_line = f"{info['size_kb']} КБ"
            screen.blit(f_small.render(kb_line, True, MUTED),
                        (r.right - 106, r.y + 44))
            draw_button(screen, f_small, R(r.right - 34, r.y + 14, 26, 26), "×", (150, 70, 70))
            draw_button(screen, f_small, R(r.right - 120, r.y + 16, 80, 32), "СМОТРЕТЬ",
                        (70, 140, 90))


SC_NAME = {k: sc["name"] for k, sc in strategy.SCENARIOS.items()}


def replay_card_rect(i):
    return R((W - 760) // 2, 208 + i * 72, 760, 64)


class ReplayViewer:
    """Проигрыватель сохранённого повтора (replays/*.json) в реальном окне.

    Восстанавливает партию: сценарий, страны (цвета/флаги/идеологии), историю
    снимков; использует штатную отрисовку strategy (карта, флаги, панели)."""

    def __init__(self, screen, data):
        self.screen = screen
        self.data = data
        self.game = strategy.Game(data.get("scenario", "classic"), {
            "show_names": True,
        })
        g = self.game
        # подменяем фракции данными реплея (цвет/флаг/идеология/имена)
        saved = data.get("factions", [])
        for fid, f in enumerate(list(g.factions.values())[:len(saved)]):
            f.color = tuple(saved[fid].get("color", f.color))
            f.flag_style = saved[fid].get("flag_style", f.flag_style)
            f._flag_cache = {}
            f.ideology = saved[fid].get("ideology", f.ideology)
        g.history = data.get("snapshots", [])
        g.winner = data.get("winner")
        g.observer = True
        g.choosing = False
        g.player = None
        g.start_replay()
        self.fonts = strategy.make_fonts()
        self.buf = pygame.Surface((strategy.W, strategy.H))
        self.caption = (f"Повтор: {SC_NAME.get(data.get('scenario'), '?')} — "
                        f"{data.get('saved', '')}")

    def run(self):
        pygame.display.set_caption(self.caption)
        running = True
        while running:
            dt = strategy.clock().tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.event.post(event)     # отдать меню на обработку
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                        running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    strategy.handle_click(self.game, event.pos, event.button)

            self.game.update_replay(dt)
            strategy.draw(self.buf, self.game, self.fonts)
            strategy.blit_scaled(self.screen, self.buf, self.screen.get_size())
            pygame.display.flip()
        pygame.display.set_caption(f"Balance of Power — v{version.VERSION}")


def main():
    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    pygame.init()
    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    pygame.display.set_caption(f"Balance of Power — v{version.VERSION}")
    loading.show(screen, min_time=2.2)          # заставка со случайным «фото»
    menu = Menu(screen)
    buf = pygame.Surface((W, H))      # виртуальный буфер 1280×760

    running = True
    while running:
        dt = min(0.05, pygame.time.Clock().tick(60) / 1000.0)
        menu.time += dt
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_1:
                    menu.tab = 0
                elif event.key == pygame.K_2:
                    menu.tab = 1
                elif event.key == pygame.K_3:
                    menu.tab = 2
                elif event.key == pygame.K_4:
                    menu.tab = 3
                elif event.key == pygame.K_5:
                    menu.tab = 4
                elif event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_RETURN and menu.tab == 0:
                    menu._launch(menu.chosen_scenario, screen)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                mpos = strategy.map_mouse(event.pos, screen.get_size())
                if event.button == 4 and menu.tab == 1:      # колесо вверх
                    menu.news_scroll = max(0, getattr(menu, "news_scroll", 0) - 44)
                elif event.button == 5 and menu.tab == 1:    # колесо вниз
                    menu.news_scroll = getattr(menu, "news_scroll", 0) + 44
                else:
                    menu.click(mpos, event.button)
            elif event.type == pygame.MOUSEMOTION:
                if event.buttons[0]:
                    menu.drag(strategy.map_mouse(event.pos, screen.get_size()))

        menu.screen = buf
        menu.draw()
        strategy.blit_scaled(screen, buf, screen.get_size())
        pygame.display.flip()

    audio.stop()
    pygame.quit()


if __name__ == "__main__":
    main()
