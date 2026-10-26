# Базовый каталог данных игры.
# В исходниках — папка проекта; в собранном exe (PyInstaller) — папка самого
# exe, чтобы settings.json, реплеи и сгенерированные ассеты жили рядом с
# игрой и переживали перезапуски (onefile распаковывается во временную
# папку, писать туда нельзя).
import os
import sys

if getattr(sys, "frozen", False):
    _DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _DIR = os.path.dirname(os.path.abspath(__file__))


def app_dir():
    return _DIR
