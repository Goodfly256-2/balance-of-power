# Настройки игры: хранятся в settings.json рядом с кодом.
import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(_DIR, "settings.json")

DEFAULTS = {
    "music_volume": 0.55,     # 0..1, 0 — музыка выключена
    "show_numbers": False,    # показывать цифры на карте в новых партиях
    "show_names": True,       # названия стран на территориях
    "check_updates": True,    # проверять обновления при запуске
    "last_scenario": "classic",
}


def load():
    s = dict(DEFAULTS)
    try:
        with open(PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k in DEFAULTS:
                if k in data:
                    s[k] = data[k]
    except (OSError, ValueError):
        pass
    s["music_volume"] = min(1.0, max(0.0, float(s["music_volume"])))
    return s


def save(s):
    clean = {k: s.get(k, DEFAULTS[k]) for k in DEFAULTS}
    try:
        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(clean, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return clean
