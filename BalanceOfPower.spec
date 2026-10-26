# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec для Balance of Power (Windows, onefile, окно без консоли).
a = Analysis(
    ['menu.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['_appdir'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy.tests'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BalanceOfPower',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets\\icon.ico' if __import__('os').path.exists('assets\\icon.ico') else None,
)
