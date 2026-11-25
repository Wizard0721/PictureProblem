# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=(
        collect_data_files('ziamath', includes=['fonts/*'])
        + collect_data_files('ziafont', includes=['fonts/*'])
        + collect_data_files('latex2mathml', includes=['unimathsymbols.txt'])
    ),
    hiddenimports=[],
    hookspath=[SPECPATH],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineQuick', 'PySide6.QtWebChannel', 'PySide6.QtQuick', 'PySide6.QtQml', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtCharts', 'PySide6.QtSql', 'PySide6.QtTest'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='截图解题',
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
    icon=['icon.ico'],
)
