# Одноразовая генерация assets/icon.ico: красный щит с золотыми весами
# (символ «баланса сил»). Запуск: python _make_icon.py
import struct

import pygame

pygame.init()
S = 256
surf = pygame.Surface((S, S), pygame.SRCALPHA)

gold = (218, 165, 32)
dark = (128, 20, 30)
light = (165, 28, 42)
shield = [(58, 28), (198, 28), (198, 140), (128, 238), (58, 140)]
pygame.draw.polygon(surf, dark, shield)
pygame.draw.polygon(surf, gold, shield, 6)
hl = [(74, 40), (110, 40), (86, 150), (74, 150)]
pygame.draw.polygon(surf, light, hl)
bar_y = 96
pygame.draw.line(surf, gold, (88, bar_y), (168, bar_y), 6)
pygame.draw.line(surf, gold, (128, 66), (128, 170), 6)
pygame.draw.circle(surf, gold, (128, 60), 9)
for cx in (88, 168):
    pygame.draw.line(surf, gold, (cx, bar_y), (cx - 16, 132), 4)
    pygame.draw.line(surf, gold, (cx, bar_y), (cx + 16, 132), 4)
    pygame.draw.arc(surf, gold, (cx - 24, 118, 48, 28), 3.34, 6.08, 5)

# Настоящий ICO: BMP-записи (32bpp BGRA + AND-маска) на 4 размеров
sizes = [16, 32, 48, 256]
imgs = []
for sz in sizes:
    im = pygame.transform.smoothscale(surf, (sz, sz))
    raw = pygame.image.tostring(im, "BGRA")
    rows = [raw[y * sz * 4:(y + 1) * sz * 4] for y in range(sz)]
    bmp = b"".join(reversed(rows))
    mask_row = b"\x00" * ((sz + 31) // 32 * 4)
    bmp += mask_row * sz
    header = struct.pack("<IiiHHIIiiII", 40, sz, sz * 2, 1, 32, 0,
                         len(bmp), 0, 0, 0, 0)
    imgs.append((sz, header + bmp))

count = len(imgs)
offset = 6 + 16 * count
out = struct.pack("<HHH", 0, 1, count)
for sz, data in imgs:
    w = 0 if sz >= 256 else sz
    out += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(data), offset)
    offset += len(data)
for _, data in imgs:
    out += data
with open("assets/icon.ico", "wb") as f:
    f.write(out)
print("ICO ok,", len(out), "bytes")
