# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Markdown Viewer.
Build: pyinstaller markdown_viewer.spec
Output: dist/markdown_viewer.exe
"""
from pathlib import Path

block_cipher = None

ROOT = Path(".").resolve()

datas = [
    (str(ROOT / "src"), "src"),
    (str(ROOT / "assets" / "icon.ico"), "assets"),
    (str(ROOT / "assets" / "icon.png"), "assets"),
]

hiddenimports = [
    "src.core.file_loader",
    "src.core.file_type_detector",
    "src.core.frontmatter",
    "src.core.parser",
    "src.core.yaml_renderer",
    "src.ui",
    "src.utils.config",
    "src.utils.file_association",
    "src.utils.search",
]

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "setuptools",
        "pytest",
        "pytest_qt",
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
    name="markdown_viewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="markdown_viewer",
)
