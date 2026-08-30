# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules


hiddenimports = collect_submodules("webview")

a = Analysis(
    ["desktop.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("index.html", "."),
        ("LICENSE", "."),
        ("THIRD_PARTY_NOTICES.md", "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pyarrow", "streamlit"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Log Analysis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Log Analysis",
)
