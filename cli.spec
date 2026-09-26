# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for Udemy Enroller Unified CLI (cli.exe / cli)."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Base directory
BASE_DIR = Path(os.getcwd())

datas = [
    (str(BASE_DIR / "app" / "templates"), "app/templates"),
    (str(BASE_DIR / "app" / "static"), "app/static"),
]

# Hidden imports for dynamic and lazy loaders
hiddenimports = [
    "main",
    "loguru",
    "sqlite3",
    "cryptography",
    "bcrypt",
    "sqlalchemy",
    "sqlalchemy.sql.default_comparator",
    "sqlalchemy.dialects.sqlite",
    "cloudscraper",
    "requests",
    "httpx",
    "bs4",
    "lxml",
    "uvicorn",
    "fastapi",
    "typer",
    "rich",
    "pydantic",
    "pydantic_settings",
]
hiddenimports += collect_submodules("app")

a = Analysis(
    ["cli.py"],
    pathex=[str(BASE_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "tkinter.test", "customtkinter", "unittest", "pytest"],
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
    name="cli",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console application for Rich terminal output
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
