# sticker.spec
# -*- mode: python -*-
import sys
import glob
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Only include the Qt modules and plugins you actually use
hiddenimports = collect_submodules('PyQt6')

datas = collect_data_files(
    'PyQt6',
    includes=[
        'Qt6/plugins/platforms/*',
        'Qt6/plugins/imageformats/*'
    ],
    excludes=[
        'Qt6/translations/*'
    ]
)
# Include app icons and status animations
datas += [(f, 'src/gui/appicons') for f in glob.glob('src/gui/appicons/*')]
datas += [(f, 'src/gui/icons') for f in glob.glob('src/gui/icons/*')]
datas += [(f, 'src/gui/status_animations') for f in glob.glob('src/gui/status_animations/*')]

# Add your ffmpeg/ffprobe binaries alongside the exe
binaries = [
    ('bin/ffmpeg.exe', '.'),
    ('bin/ffprobe.exe', '.')
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        'PyQt6.QtWebEngineCore',
        'PyQt6.QtWebEngineWidgets',
        'PyQt6.QtQml',
        'PyQt6.QtNetwork',
        'PyQt6.QtSerialPort',
        'PyQt6.QtCharts',
        'PyQt6.QtMultimedia',
        'PyQt6.QtPrintSupport',
        'PyQt6.QtSql',
        'PyQt6.QtSvg',
    ],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    exclude_binaries=False,
    name='ukrclassics',
    icon='src/gui/appicons/app.ico',
    debug=False,
    strip=True,  # strip symbols to reduce size
    upx=True,    # compress with UPX
    console=False,
    onefile=True,
    windowed=True,
)

distpath = 'dist'
