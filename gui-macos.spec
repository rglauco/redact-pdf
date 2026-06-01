# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')

a = Analysis(
    ['redact_pdf.py'],
    pathex=[],
    binaries=ctk_binaries,
    datas=ctk_datas,
    hiddenimports=ctk_hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['windnd'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='redact-pdf',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='redact-pdf',
)

app = BUNDLE(
    coll,
    name='redact-pdf.app',
    icon=None,
    bundle_identifier='digital.gate2.redact-pdf',
    info_plist={
        'CFBundleDisplayName': 'Redact PDF',
        'CFBundleShortVersionString': '3.1.0',
        'NSHighResolutionCapable': True,
        'NSPrincipalClass': 'NSApplication',
    },
)
