# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['discord.py'],
    pathex=['C:\\git\\Discord-Helper'],
    binaries=[],
    datas=[
        ('peb_mask.py', '.'),
        ('arduino_wrap.py', '.'),
    ],
    hiddenimports=[
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'serial.tools.list_ports_windows',
        'keyboard',
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
    name='DiscordHelper',
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
    icon='C:\\git\\Discord-Helper\\discord.ico',
)
