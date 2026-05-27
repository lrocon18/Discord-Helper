# -*- mode: python ; coding: utf-8 -*-

import os

_root = os.path.abspath(os.path.join(os.path.dirname(SPEC), '..'))
_src  = os.path.join(_root, 'src')

a = Analysis(
    [os.path.join(_src, 'discord.py')],
    pathex=[_src],
    binaries=[],
    datas=[
        (os.path.join(_src, 'peb_mask.py'),     '.'),
        (os.path.join(_src, 'arduino_wrap.py'), '.'),
        (os.path.join(_src, 'hud.py'),          '.'),
    ],
    hiddenimports=[
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'serial.tools.list_ports_windows',
        'keyboard',
        'tkinter',
        'tkinter.ttk',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['cv2', 'PIL', 'numpy', 'mss', 'pyautogui'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Discord',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(os.path.dirname(SPEC), 'discord.ico'),
)
