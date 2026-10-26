# Музыка: генерация фоновых треков (чистый Python, без зависимостей)
# и управление воспроизведением через pygame.mixer.music.
#
# Треки создаются один раз и сохраняются в assets/. Мелодии простые
# и спокойные: медленные аккорды в меню, низкий пульсирующий дрон в игре.
# Все функции воспроизведения безопасны: если звук недоступен
# (нет аудиоустройства, dummy-драйвер), они молча ничего не делают.
import math
import os
import struct
import threading
import wave

import _appdir

SR = 44100
_DIR = _appdir.app_dir()
ASSETS = os.path.join(_DIR, "assets")
MENU_WAV = os.path.join(ASSETS, "menu_music.wav")
GAME_WAV = os.path.join(ASSETS, "game_music.wav")

_VOLUME = [0.55]   # текущая громкость (0..1)
_MUSIC_ON = [True]


# ---------------- генерация ----------------
def _midi_freq(m):
    return 440.0 * 2.0 ** ((m - 69) / 12.0)


def _write_wav(path, samples):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    peak = max(1e-9, max(abs(s) for s in samples))
    k = 0.5 / peak
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, s * k)) * 32767))
        for s in samples)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames)


def _pad_note(buf, freq, start, dur, amp, attack=1.1, release=1.4):
    """Мягкая «пэдовая» нота: сумма синусов + плавная огибающая."""
    n = len(buf)
    a = int(attack * SR)
    r = int(release * SR)
    s0 = int(start * SR)
    s1 = min(n, s0 + int(dur * SR))
    w1, w2, w3 = 6.283185 * freq / SR, 12.56637 * freq / SR, 18.84955 * freq / SR
    for i in range(max(0, s0), s1):
        t = i - s0
        env = min(1.0, t / a) if a else 1.0
        tail = s1 - i
        if tail < r:
            env *= tail / r
        v = (math.sin(w1 * t) + 0.38 * math.sin(w2 * t + 0.4)
             + 0.16 * math.sin(w3 * t + 1.1)) * env * amp
        buf[i] += v


def _bass_note(buf, freq, start, dur, amp):
    n = len(buf)
    s0 = int(start * SR)
    s1 = min(n, s0 + int(dur * SR))
    w = 6.283185 * freq / SR
    for i in range(max(0, s0), s1):
        t = i - s0
        env = min(1.0, t / (0.8 * SR)) * min(1.0, (s1 - i) / (0.9 * SR))
        buf[i] += math.sin(w * t) * env * amp


def _menu_track():
    """16 с, 4 аккорда по 4 с: Am — F — C — G. Спокойный пэд."""
    seg = 4.0
    total = 16.0
    buf = [0.0] * int(total * SR)
    chords = [
        (45, (57, 60, 64)),   # Am
        (41, (53, 57, 60)),   # F
        (48, (55, 60, 64)),   # C
        (43, (55, 59, 62)),   # G
    ]
    for idx, (bass, notes) in enumerate(chords):
        t0 = idx * seg
        # фаза не важна — огибающая гасит стыки между аккордами
        _bass_note(buf, _midi_freq(bass), t0, seg + 0.4, 0.34)
        for m in notes:
            _pad_note(buf, _midi_freq(m), t0, seg + 0.4, 0.16)
        # высокое «мерцание» — корневая нота через октаву
        _pad_note(buf, _midi_freq(notes[0] + 12), t0, seg + 0.4, 0.05,
                  attack=1.6, release=1.8)
    return buf


def _drum_note(buf, start, amp=0.3, freq=56.0, dur=0.6):
    """Глухой барабан: синус с быстрым экспоненциальным затуханием."""
    s0 = int(start * SR)
    s1 = min(len(buf), s0 + int(dur * SR))
    w = 6.283185 * freq / SR
    for i in range(max(0, s0), s1):
        t = i - s0
        env = math.exp(-t / (0.11 * SR))
        buf[i] += math.sin(w * t) * env * amp


def _lead_note(buf, freq, start, dur, amp):
    """Мелодическая нота: слегка скрипичный тембр с вибрато и медленной
    атакой — слышимая ведущая линия над аккордами."""
    s0 = int(start * SR)
    s1 = min(len(buf), s0 + int(dur * SR))
    w = 6.283185 * freq / SR
    vib = 6.283185 * 5.5 / SR          # вибрато 5.5 Гц
    for i in range(max(0, s0), s1):
        t = i - s0
        # атака 0.25 с, релиз 0.5 с
        env = min(1.0, t / (0.25 * SR)) * min(1.0, (s1 - i) / (0.5 * SR))
        vibrato = 1.0 + 0.004 * math.sin(vib * t)
        v = (math.sin(w * vibrato * t)
             + 0.35 * math.sin(2.0 * w * t)
             + 0.12 * math.sin(3.0 * w * t))
        buf[i] += v * env * amp


def _game_track():
    """32 с: минорная прогрессия Dm — Bb — F — C (×2) с настоящей мелодией
    сверху (ведущая линия на пэде-лиде) и глухим барабаном. Гармоничный,
    напевный фон войны вместо дрона."""
    seg = 4.0
    total = 32.0
    buf = [0.0] * int(total * SR)
    chords = [
        (38, (50, 53, 57)),   # Dm
        (34, (46, 50, 53)),   # Bb
        (41, (53, 57, 60)),   # F
        (36, (52, 55, 60)),   # C
        (38, (50, 53, 57)),   # Dm
        (34, (46, 50, 53)),   # Bb
        (31, (50, 55, 58)),   # Gm
        (33, (52, 57, 61)),   # A (доминанта)
    ]
    for idx, (bass, notes) in enumerate(chords):
        t0 = idx * seg
        _bass_note(buf, _midi_freq(bass), t0, seg + 0.3, 0.26)
        for m in notes:
            _pad_note(buf, _midi_freq(m), t0, seg + 0.3, 0.12,
                      attack=1.2, release=1.6)
        _drum_note(buf, t0, amp=0.26)
        _drum_note(buf, t0 + seg / 2.0, amp=0.14)
    # МЕЛОДИЯ: напевная линия в ре-миноре, по 2 ноты на аккорд,
    # вписана в гармонию (ноты аккорда + проходящие)
    melody = [
        # Dm
        (69, 0.0, 1.6), (72, 2.0, 1.6),          # A4, C5
        # Bb
        (70, 4.0, 1.6), (67, 6.0, 1.6),          # Bb4, G4
        # F
        (65, 8.0, 1.6), (69, 10.0, 1.6),         # F4, A4
        # C
        (67, 12.0, 1.8), (64, 14.2, 1.4),        # G4, E4
        # Dm (ответ — выше)
        (72, 16.0, 1.6), (74, 18.0, 1.6),        # C5, D5
        # Bb
        (72, 20.0, 1.6), (69, 22.0, 1.6),        # C5, A4
        # Gm
        (67, 24.0, 1.6), (70, 26.0, 1.6),        # G4, Bb4
        # A — доминанта, тянется обратно в Dm
        (69, 28.0, 3.4),                          # A4 (долгая)
    ]
    for midi, t0, dur in melody:
        _lead_note(buf, _midi_freq(midi), t0, dur, 0.22)
    return buf


def generate_tracks(force=False):
    """Создаёт wav-файлы, если их ещё нет (или force=True)."""
    made = []
    if force or not os.path.exists(MENU_WAV):
        _write_wav(MENU_WAV, _menu_track())
        made.append("menu")
    if force or not os.path.exists(GAME_WAV):
        _write_wav(GAME_WAV, _game_track())
        made.append("game")
    return made


# ---------------- воспроизведение ----------------
def _mixer_ok():
    try:
        import pygame
        return pygame.mixer.get_init() is not None
    except Exception:
        return False


def _play(path):
    if not _MUSIC_ON[0] or _VOLUME[0] <= 0.001:
        return
    try:
        import pygame
        pygame.mixer.music.load(path)
        pygame.mixer.music.set_volume(_VOLUME[0])
        pygame.mixer.music.play(-1)
    except Exception:
        pass


def set_volume(v):
    _VOLUME[0] = min(1.0, max(0.0, float(v)))
    try:
        import pygame
        pygame.mixer.music.set_volume(_VOLUME[0])
    except Exception:
        pass


def play_menu():
    if os.path.exists(MENU_WAV):
        _play(MENU_WAV)


def play_game():
    if os.path.exists(GAME_WAV):
        _play(GAME_WAV)


def stop():
    try:
        import pygame
        pygame.mixer.music.stop()
        pygame.mixer.music.unload()
    except Exception:
        pass


def ensure_async():
    """Генерация треков в фоне (при первом запуске занимает пару секунд)."""
    if os.path.exists(MENU_WAV) and os.path.exists(GAME_WAV):
        return
    threading.Thread(target=generate_tracks, daemon=True).start()
