# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

a = Analysis(
    ['..\\src\\app.py'],
    pathex=[],
    binaries=[
        ('..\\bin\\yt-dlp.exe', '.'),
        ('..\\bin\\ffmpeg.exe', '.'),
        ('..\\bin\\ffprobe.exe', '.'),
        ('..\\bin\\deno.exe', '.'),
    ],
    datas=[
        ('logo_square.png', '.'),
        ('icon.ico', '.'),
    ],
    hiddenimports=[
        'PIL', 'PIL.Image', 'PIL.ImageTk', 'PIL._tkinter_finder',
        'requests', 'urllib3', 'charset_normalizer', 'idna', 'certifi',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MikagueiDownloader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
