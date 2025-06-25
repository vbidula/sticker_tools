# sticker.spec
# -*- mode: python -*-
import sys
from PyInstaller.utils.hooks import collect_all

# collect PyQt6 so Qt plugins land in the bundle
datas, binaries, hiddenimports = collect_all('PyQt6')

# add your ffmpeg binary alongside the exe
binaries += [
    ('bin/ffmpeg.exe', '.'),      # (source, target folder inside dist)
    ('bin/ffprobe.exe', '.'),
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name='uk',
    icon='src/gui/appicons/app.ico',
    debug=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='uk_dist'
)