# Экран загрузки: процедурные «фотографии» пейзажей + прогресс-бар.
#
# Фото генерируются чистым Python (без сети и зависимостей) при первом
# запуске и кэшируются в assets/loading/*.png. Каждый спрайт — свой пейзаж:
# горы, море, пустыня, поле, ночной город, арктика. Каждый запуск игры
# показывает случайный из них.
import math
import os
import random

import pygame

import _appdir

_DIR = _appdir.app_dir()
ASSETS = os.path.join(_DIR, "assets")
LOAD_DIR = os.path.join(ASSETS, "loading")

W, H = 1280, 760

# ---------------- генерация «фотографий» ----------------
# Каждый пейзаж: небо с градиентом + солнце/луна + слои силуэтов + зерно.
def _lerp(c1, c2, t):
    return tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))


def _sky(surf, top, bottom, horizon_y):
    for y in range(horizon_y):
        pygame.draw.line(surf, _lerp(top, bottom, y / max(1, horizon_y)), (0, y), (surf.get_width(), y))


def _sun(surf, x, y, r, color, glow):
    x, y, r = int(x), int(y), int(r)
    for gr, ga in ((r * 2.6, 28), (r * 1.7, 46), (r * 1.15, 70)):
        gr = int(gr)
        g = pygame.Surface((gr * 2, gr * 2), pygame.SRCALPHA)
        pygame.draw.circle(g, color + (ga,), (gr, gr), gr)
        surf.blit(g, (x - gr, y - gr))
    pygame.draw.circle(surf, color, (x, y), r)


def _ridge(surf, y_base, amp, color, seed, step=6):
    """Силуэт гор/холмов: сумма синусов со случайными фазами."""
    r = random.Random(seed)
    comps = [(r.uniform(0.35, 1.0), r.uniform(1.2, 2.4), r.uniform(0, 6.28)),
             (r.uniform(0.15, 0.35), r.uniform(3.0, 5.0), r.uniform(0, 6.28)),
             (r.uniform(0.05, 0.15), r.uniform(6.0, 9.0), r.uniform(0, 6.28))]
    norm = sum(a for a, _, _ in comps)
    w = surf.get_width()
    pts = [(0, surf.get_height())]
    for x in range(0, w + step, step):
        t = x / w
        yy = y_base - sum(a * math.sin(6.283 * f * t + p) for a, f, p in comps) / norm * amp
        pts.append((x, yy))
    pts.append((w, surf.get_height()))
    pygame.draw.polygon(surf, color, pts)


def _stars(surf, n, seed, y_max):
    r = random.Random(seed)
    for _ in range(n):
        x, y = r.randint(0, surf.get_width() - 1), r.randint(0, int(y_max))
        b = r.randint(120, 255)
        surf.set_at((x, y), (b, b, min(255, b + 20)))


def _grain(surf, seed, strength=5):
    """Лёгкое плёночное зерно: мелкие вычитания тёмных точек (без засвета)."""
    r = random.Random(seed)
    w, h = surf.get_width(), surf.get_height()
    noise = pygame.Surface((w // 3, h // 3))
    noise.fill((strength, strength, strength))    # тёмная база = почти нет влияния
    for _ in range(w * h // 250):
        x, y = r.randint(0, w // 3 - 1), r.randint(0, h // 3 - 1)
        v = r.randint(0, strength * 2)
        noise.set_at((x, y), (v, v, v))
    noise = pygame.transform.smoothscale(noise, (w, h))
    surf.blit(noise, (0, 0), special_flags=pygame.BLEND_RGB_SUB)


def _vignette(surf):
    w, h = surf.get_width(), surf.get_height()
    v = pygame.Surface((w, h), pygame.SRCALPHA)
    for i in range(60):
        a = int(60 * (1 - i / 60))
        pygame.draw.rect(v, (0, 0, 0, a),
                         (int(w * -0.2 + i * w * 0.14 / 6), int(h * -0.2 + i * h * 0.14 / 6),
                          w + int(w * 0.4 - i * w * 0.28 / 6), h + int(h * 0.4 - i * h * 0.28 / 6)),
                         width=max(1, int(h * 0.1)))
    return v


def _photo_mountains(w, h):
    """Горы на закате: оранжевое небо, три хребта, солнце."""
    surf = pygame.Surface((w, h))
    hor = int(h * 0.62)
    _sky(surf, (38, 34, 72), (244, 138, 70), hor)
    pygame.draw.rect(surf, (24, 22, 40), (0, hor, w, h - hor))
    _sun(surf, w * 0.68, hor - h * 0.10, int(h * 0.055), (255, 214, 150), True)
    _ridge(surf, hor + 6, h * 0.30, (62, 52, 88), 11)
    _ridge(surf, hor + h * 0.06, h * 0.22, (44, 38, 64), 22)
    _ridge(surf, hor + h * 0.13, h * 0.14, (26, 22, 40), 33)
    _grain(surf, 44)
    surf.blit(_vignette(surf), (0, 0))
    return surf


def _photo_sea(w, h):
    """Море ночью: лунная дорожка, волны-блики."""
    surf = pygame.Surface((w, h))
    hor = int(h * 0.52)
    _sky(surf, (10, 14, 34), (46, 60, 96), hor)
    pygame.draw.rect(surf, (16, 24, 44), (0, hor, w, h - hor))
    _stars(surf, 140, 7, hor - 10)
    _sun(surf, w * 0.30, hor - h * 0.14, int(h * 0.045), (222, 232, 250), True)
    r = random.Random(15)
    for i in range(46):                       # лунная дорожка
        yy = hor + 4 + i * (h - hor) / 46
        spread = 8 + i * 2.2
        x = w * 0.30 + r.uniform(-spread, spread)
        wl = r.uniform(14, 60) * (1 + i / 30)
        pygame.draw.line(surf, (190, 205, 235), (x - wl / 2, yy), (x + wl / 2, yy), 2)
    for i in range(26):                       # редкие блики по морю
        yy = hor + r.uniform(6, h - hor - 6)
        x = r.uniform(0, w)
        pygame.draw.line(surf, (70, 92, 128), (x, yy), (x + r.uniform(20, 70), yy), 1)
    _grain(surf, 16)
    surf.blit(_vignette(surf), (0, 0))
    return surf


def _photo_desert(w, h):
    """Пустыня: дюны, жаркое солнце, пыльная дымка."""
    surf = pygame.Surface((w, h))
    hor = int(h * 0.58)
    _sky(surf, (120, 160, 200), (250, 214, 160), hor)
    _sun(surf, w * 0.5, hor - h * 0.16, int(h * 0.06), (255, 240, 200), True)
    pygame.draw.rect(surf, (216, 176, 122), (0, hor, w, h - hor))   # база под дюнами
    r = random.Random(21)
    for i, (col, dy, amp) in enumerate((
            ((216, 176, 122), 0.02, 0.06), ((198, 152, 100), 0.09, 0.08),
            ((176, 128, 82), 0.16, 0.09), ((150, 104, 64), 0.24, 0.07))):
        pts = [(0, h)]
        base = hor + h * dy
        for x in range(0, w + 8, 8):
            t = x / w
            yy = base + amp * h * math.sin(6.283 * (1.3 * t + i * 0.37)) * math.cos(2.2 * t + i)
            pts.append((x, yy))
        pts.append((w, h))
        pygame.draw.polygon(surf, col, pts)
    for _ in range(3):                        # пыльная дымка
        haze = pygame.Surface((w, int(h * 0.2)), pygame.SRCALPHA)
        haze.fill((250, 220, 180, 26))
        surf.blit(haze, (0, hor + r.uniform(0, h * 0.3)))
    _grain(surf, 31)
    surf.blit(_vignette(surf), (0, 0))
    return surf


def _photo_field(w, h):
    """Поле с грозой: тёмное небо, одинокое дерево, трава."""
    surf = pygame.Surface((w, h))
    hor = int(h * 0.66)
    _sky(surf, (30, 34, 44), (110, 118, 118), hor)
    _ridge(surf, hor + 2, h * 0.05, (52, 60, 60), 51)
    pygame.draw.rect(surf, (54, 66, 42), (0, hor, w, h - hor))
    r = random.Random(63)
    for _ in range(240):                      # трава
        x = r.randint(0, w - 1)
        yy = r.randint(hor + 4, h - 2)
        depth = (yy - hor) / (h - hor)
        g = 60 + int(depth * 40)
        pygame.draw.line(surf, (g - 12, g + 12, g - 24), (x, yy),
                         (x + r.randint(-4, 4), yy - r.randint(4, int(10 + depth * 8))), 1)
    # одинокое дерево
    tx, ty = w * 0.62, hor + h * 0.10
    pygame.draw.line(surf, (26, 20, 16), (tx, ty), (tx - 8, ty - h * 0.12), 7)
    pygame.draw.line(surf, (26, 20, 16), (tx - 3, ty - h * 0.06), (tx + 26, ty - h * 0.15), 5)
    pygame.draw.line(surf, (26, 20, 16), (tx - 4, ty - h * 0.08), (tx - 30, ty - h * 0.16), 5)
    for _ in range(9):
        cx = tx + r.uniform(-44, 44)
        cy = ty - h * 0.14 + r.uniform(-26, 12)
        pygame.draw.circle(surf, (30, 44, 28), (int(cx), int(cy)), r.randint(12, 24))
    _grain(surf, 77, strength=6)
    surf.blit(_vignette(surf), (0, 0))
    return surf


def _photo_city(w, h):
    """Ночной город: силуэт небоскрёбов, окна, огни."""
    surf = pygame.Surface((w, h))
    hor = int(h * 0.78)
    _sky(surf, (8, 10, 26), (70, 40, 80), hor)
    _stars(surf, 90, 5, hor * 0.6)
    r = random.Random(9)
    x = -20
    while x < w + 20:                          # два слоя зданий
        bw = r.randint(46, 110)
        bh = r.randint(int(h * 0.18), int(h * 0.44))
        depth = r.random()
        col = (28, 30, 48) if depth > 0.5 else (16, 17, 30)
        top = hor - bh
        pygame.draw.rect(surf, col, (x, top, bw, bh + 40))
        # окна
        for wy in range(top + 8, hor - 6, 14):
            for wx in range(x + 6, x + bw - 8, 12):
                if r.random() < 0.42:
                    c = (255, 214, 120) if r.random() < 0.8 else (150, 210, 255)
                    pygame.draw.rect(surf, c, (wx, wy, 5, 7))
        # антенна
        if r.random() < 0.3:
            ax = x + bw // 2
            pygame.draw.line(surf, col, (ax, top), (ax, top - r.randint(14, 34)), 2)
        x += bw + r.randint(2, 14)
    pygame.draw.rect(surf, (10, 11, 18), (0, hor + 30, w, h - hor))
    _grain(surf, 91)
    surf.blit(_vignette(surf), (0, 0))
    return surf


def _photo_arctic(w, h):
    """Арктика: северное сияние над льдом."""
    surf = pygame.Surface((w, h))
    hor = int(h * 0.60)
    _sky(surf, (6, 10, 24), (24, 38, 60), hor)
    _stars(surf, 190, 3, hor - 6)
    r = random.Random(27)
    for band in range(4):                      # сияние
        aur = pygame.Surface((w, h), pygame.SRCALPHA)
        col = [(80, 240, 170), (110, 200, 255), (170, 120, 240), (90, 230, 210)][band]
        pts = []
        for x in range(0, w + 16, 16):
            t = x / w
            yy = hor * (0.30 + 0.13 * band) + 40 * math.sin(6.283 * 1.4 * t + band * 1.9) \
                 + 22 * math.sin(6.283 * 3.1 * t + band)
            pts.append((x, yy))
        for i in range(len(pts) - 1):
            for k in range(5):
                a = int(60 - k * 11)
                off = k * 9
                pygame.draw.line(aur, col + (a,), (pts[i][0], pts[i][1] + off),
                                 (pts[i + 1][0], pts[i + 1][1] + off), 3)
        surf.blit(aur, (0, 0))
    pygame.draw.rect(surf, (206, 218, 232), (0, hor, w, h - hor))       # лёд
    pygame.draw.rect(surf, (150, 168, 190), (0, hor, w, 5))
    for _ in range(30):                        # трещины и торосы
        x, yy = r.randint(0, w), r.randint(hor + 8, h - 4)
        pygame.draw.line(surf, (172, 188, 206), (x, yy), (x + r.randint(-60, 60), yy + r.randint(-6, 6)), 1)
    for _ in range(14):
        x, yy = r.randint(0, w), r.randint(hor + 10, h - 8)
        pygame.draw.polygon(surf, (188, 202, 218),
                            [(x, yy), (x + r.randint(10, 26), yy - r.randint(6, 16)), (x + r.randint(20, 40), yy)])
    _grain(surf, 55, strength=4)
    surf.blit(_vignette(surf), (0, 0))
    return surf


# Порядок = «фотографии»; каждая попадает в assets/loading/photo_N.png
PHOTOS = [
    ("Горы на закате", _photo_mountains),
    ("Лунное море", _photo_sea),
    ("Дюны", _photo_desert),
    ("Поле перед грозой", _photo_field),
    ("Ночной город", _photo_city),
    ("Северное сияние", _photo_arctic),
]


def ensure_photos(force=False):
    """Создаёт png-«фотографии», если их ещё нет. Возвращает список путей."""
    os.makedirs(LOAD_DIR, exist_ok=True)
    paths = []
    for i, (name, fn) in enumerate(PHOTOS):
        p = os.path.join(LOAD_DIR, f"photo_{i}.png")
        if force or not os.path.exists(p):
            pygame.image.save(fn(W // 2, H // 2), p)   # половинный размер — файл меньше
        paths.append((p, name))
    return paths


# ---------------- экран загрузки ----------------
TIPS = [
    "Доктрины: Манёвры бьют Удар, Удар ломает Оборону, Оборона перемалывает Манёвры",
    "Из региона под боем армия выйти не может — думай заранее",
    "Армии встретились на марше? Ждите перехвата у ближайшей провинции",
    "Держите торговые соглашения — это плюс 8% дохода за каждое",
    "Названия стран на карте — клавиша N, цифры — G",
    "Окно можно растягивать за край — карта масштабируется сама",
]


def _prepare(screen, photo, sub, min_time, title):
    """Внутренний цикл заставки: фото + заголовок + прогресс-бар + подсказка."""
    import time
    import version
    try:
        W_, H_ = screen.get_size()[0], screen.get_size()[1]
    except Exception:
        W_, H_ = W, H
    f_title = pygame.font.SysFont("segoeui", 46, bold=True)
    f_sub = pygame.font.SysFont("segoeui", 20, bold=True)
    f_body = pygame.font.SysFont("segoeui", 15)
    f_tip = pygame.font.SysFont("segoeui", 17, bold=True)

    tip = random.choice(TIPS)
    t0 = time.time()
    clock_ = pygame.time.Clock()
    while True:
        dt = clock_.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.event.post(event)          # отдать дальше главному циклу
                return
        k = min(1.0, (time.time() - t0) / min_time)
        if k >= 1.0:
            return
        fade = min(1.0, k * 3.0)
        frame = photo.copy()
        ov = pygame.Surface((W, H), pygame.SRCALPHA)
        ov.fill((8, 9, 12, int(120 * (1 - fade))))
        frame.blit(ov, (0, 0))
        band = pygame.Surface((W, 150), pygame.SRCALPHA)
        band.fill((0, 0, 0, 130))
        frame.blit(band, (0, H - 190))
        band2 = pygame.Surface((W, 120), pygame.SRCALPHA)
        band2.fill((0, 0, 0, 110))
        frame.blit(band2, (0, 0))

        img = f_title.render(title, True, (240, 242, 248))
        sh = f_title.render(title, True, (0, 0, 0))
        frame.blit(sh, (W // 2 - img.get_width() // 2 + 3, 26))
        frame.blit(img, (W // 2 - img.get_width() // 2, 22))
        if sub:
            sub_img = f_sub.render(sub, True, (235, 220, 170))
            frame.blit(sub_img, (W // 2 - sub_img.get_width() // 2, 76))
        # прогресс-бар
        bw, bh, bx, by = 520, 14, W // 2 - 260, H - 120
        pygame.draw.rect(frame, (40, 44, 54), (bx, by, bw, bh), border_radius=7)
        pygame.draw.rect(frame, (74, 144, 217), (bx, by, int(bw * k), bh), border_radius=7)
        pygame.draw.rect(frame, (90, 96, 110), (bx, by, bw, bh), width=1, border_radius=7)
        pct = f_body.render(f"{int(k * 100)}%", True, (220, 224, 232))
        frame.blit(pct, (bx + bw + 14, by - 2))
        lbl = f_body.render("загрузка…", True, (150, 156, 168))
        frame.blit(lbl, (bx, by + 22))
        tip_img = f_tip.render(tip, True, (235, 238, 244))
        frame.blit(tip_img, (W // 2 - tip_img.get_width() // 2, H - 62))
        credit = f_body.render(version.CREDIT, True, (140, 146, 158))
        frame.blit(credit, (W - credit.get_width() - 14, H - 26))

        frame = pygame.transform.smoothscale(frame, screen.get_size())
        screen.blit(frame, (0, 0))
        pygame.display.flip()


def _load_photo():
    photos = ensure_photos()
    path, name = random.choice(photos)
    try:
        photo = pygame.image.load(path).convert()
    except Exception:
        photo = pygame.Surface((W, H))
        photo.fill((20, 24, 34))
    return pygame.transform.smoothscale(photo, (W, H)), name


def show(screen, min_time=2.2):
    """Стартовая заставка: случайное фото, заголовок игры, прогресс, подсказка.

    Безопасна: любые ошибки -> мгновенный выход (игра не должна ломаться)."""
    try:
        import version
        photo, name = _load_photo()
        _prepare(screen, photo, name, min_time, version.GAME_TITLE)
    except Exception:
        return


def show_game(screen, scenario_name, min_time=1.6):
    """Загрузка между меню и партией: подготовка сценария «имя»."""
    try:
        import version
        photo, name = _load_photo()
        sub = f"подготовка сценария «{scenario_name}» · пейзаж: {name}"
        _prepare(screen, photo, sub, min_time, version.GAME_TITLE)
    except Exception:
        return


if __name__ == "__main__":
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    scr = pygame.display.set_mode((W, H))
    ensure_photos()
    print("photos:", [os.path.basename(p) for p, _ in ensure_photos()])


if __name__ == "__main__":
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame.init()
    scr = pygame.display.set_mode((W, H))
    ensure_photos()
    print("photos:", [os.path.basename(p) for p, _ in ensure_photos()])
