# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH).parent
packaging_root = Path(SPECPATH)

datas = [
    (str(project_root / "GDI-BLUE_mesh-background-1.jpg"), "."),
    (str(project_root / "GDI-ICON.jpg"), "."),
    (str(project_root / "gdi-ainsworth-logo.png"), "."),
    (
        str(project_root / "Costing sheets" / "Costing Sheet Multiple Location.2026.xlsx"),
        "Costing sheets",
    ),
    (
        str(project_root / "Costing sheets" / "Costing Sheet.template 2026.xlsx"),
        "Costing sheets",
    ),
]
datas += collect_data_files("customtkinter")

analysis = Analysis(
    [str(project_root / "app.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ERICsQuoter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(packaging_root / "GDI-ICON.ico"),
    version=str(packaging_root / "version-info.txt"),
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ERICsQuoter",
)
