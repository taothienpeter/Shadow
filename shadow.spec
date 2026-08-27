# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Specification for Shadow (AI Desktop Assistant).
Builds a clean, windowless, background Tray application with all required assets.
"""

import sys
import os
from pathlib import Path

block_cipher = None

# Base directory
base_dir = os.path.abspath(SPECPATH)

# Data files to bundle with the binary
candidate_datas = [
    (os.path.join(base_dir, 'client', 'ui', 'styles.qss'), 'client/ui'),
    (os.path.join(base_dir, 'client', 'data'), 'client/data'),
    (os.path.join(base_dir, '.env.example'), '.'),
]
datas = [(src, dst) for src, dst in candidate_datas if os.path.exists(src)]

# Hidden imports to guarantee full reflection
hidden_imports = [
    'PyQt6.QtCore',
    'PyQt6.QtWidgets',
    'PyQt6.QtGui',
    'pydantic_settings',
    'pydantic',
    'pydantic_core',
    'mss',
    'PIL',
    'PIL.Image',
    'PIL.ImageGrab',
    'httpx',
    'psutil',
    'winreg',
    'ctypes',
    'ctypes.wintypes',
    'win32gui',
    'win32con',
    'win32process',
    'win32api',
    'win32ui',
    'http.server',
    'email',
    'email.message',
    'asyncio',
    'concurrent.futures',
]

a = Analysis(
    [os.path.join(base_dir, 'client', 'main.py')],
    pathex=[base_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
        'numpy.testing',
        'unittest',
        'pydoc',
        'pdb',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Shadow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                  # Windowed application — No black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Shadow',
)
