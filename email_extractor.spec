# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Email Extractor.
Build command:  pyinstaller email_extractor.spec
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# ── Source directory ────────────────────────────────────────────────────────
SRC = os.path.dirname(os.path.abspath(SPEC))   # noqa: F821 (SPEC is injected)

# ── Collect data files from third-party packages ────────────────────────────
datas = []

# tldextract: snapshot TLD list + cache files shipped with the package
datas += collect_data_files("tldextract", includes=["*.dat", "*.txt", ".tld_set_snapshot", ".suffix_cache"])

# certifi: CA bundle for HTTPS requests
try:
    import certifi
    datas += [(certifi.where(), "certifi")]
except ImportError:
    pass

# Our templates folder
datas += [(os.path.join(SRC, "templates"), "templates")]

# ── Hidden imports (dynamically imported modules) ───────────────────────────
hiddenimports = [
    "lxml.etree",
    "lxml._elementpath",
    "bs4",
    "bs4.builder._lxml",
    "bs4.builder._htmlparser",
    "tldextract",
    "fake_useragent",
    "requests",
    "flask",
    "werkzeug",
    "werkzeug.serving",
    "jinja2",
    "click",
    "certifi",
    "charset_normalizer",
    "idna",
    "urllib3",
]

hiddenimports += collect_submodules("werkzeug")
hiddenimports += collect_submodules("flask")

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    [os.path.join(SRC, "launcher.py")],
    pathex=[SRC],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "PIL", "scipy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,       # onedir mode — faster startup
    name="邮箱提取器",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,                # keep console window so user sees the URL
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="邮箱提取器",
)
