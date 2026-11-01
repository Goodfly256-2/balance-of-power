# Сохранение и загрузка повторов партий (реплеев).
#
# Реплей = урезанная история партии: снимки карты раз в секунду (владельцы,
# силы, столицы) + метаданные (сценарий, страны, дата, победитель).
# Хранятся в replays/ рядом с кодом (или с exe). Папка grows ~1 МБ на партию.
import json
import os
import time

import _appdir

_DIR = _appdir.app_dir()
REPLAY_DIR = os.path.join(_DIR, "replays")


def save_replay(game):
    """Сохраняет историю партии в replays/. Возвращает путь или None."""
    try:
        os.makedirs(REPLAY_DIR, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        sc = game.scenario
        path = os.path.join(REPLAY_DIR, f"replay_{sc}_{stamp}.json")
        data = {
            "version": 1,
            "saved": time.strftime("%Y-%m-%d %H:%M"),
            "scenario": sc,
            "winner": game.winner,
            "duration": game.time,
            "observer": game.observer,
            "factions": [
                {
                    "name": f.name,
                    "color": list(f.color),
                    "ideology": f.ideology,
                    "flag_style": f.flag_style,
                }
                for f in game.factions.values()
            ],
            "snapshots": game.history,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        return path
    except (OSError, TypeError, ValueError):
        return None


def list_replays():
    """Список сохранённых реплеев: [{path, file, scenario, winner, saved}, ...].

    Читает каждый файл целиком (реплеи единицы МБ — это быстро)."""
    out = []
    try:
        files = sorted(os.listdir(REPLAY_DIR), reverse=True)
    except OSError:
        return out
    for fname in files:
        if not fname.endswith(".json"):
            continue
        p = os.path.join(REPLAY_DIR, fname)
        data = load_replay(p)
        info = {"path": p, "file": fname, "scenario": "?", "winner": "—", "saved": "?"}
        if data:
            info["scenario"] = data.get("scenario", "?")
            info["winner"] = data.get("winner") or "не завершена"
            info["saved"] = data.get("saved", "?")
            info["factions"] = data.get("factions", [])
        info["size_kb"] = max(1, os.path.getsize(p) // 1024) if os.path.exists(p) else 0
        out.append(info)
    return out


def load_replay(path):
    """Полностью загружает реплей. Возвращает dict или None."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def delete_replay(path):
    try:
        os.remove(path)
        return True
    except OSError:
        return False
