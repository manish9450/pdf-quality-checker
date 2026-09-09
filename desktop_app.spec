# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for PDF Quality Checker (desktop version).
#
# Build with:
#     pyinstaller desktop_app.spec
#
# Output goes to dist/PDFQualityChecker/ (a folder containing the exe
# plus its dependencies -- "onedir" mode, not a single-file exe; see
# the note in the project README about why onedir is safer re: antivirus
# false positives than PyInstaller's --onefile mode).

a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        # Uncomment the line below once you've copied your Tesseract
        # install into a tesseract_bundled/ folder next to this spec
        # file (see README: "Packaging into a standalone exe").
        ('tesseract_bundled', 'tesseract_bundled'),
    ],
    hiddenimports=[
        'pytesseract',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PDFQualityChecker',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # no console window -- this is the "real app" look
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PDFQualityChecker',
)
