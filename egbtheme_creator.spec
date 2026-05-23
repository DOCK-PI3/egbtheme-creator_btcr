# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('dist/updater.exe', '.'), # Incluimos el updater.exe
        ('iconos', 'iconos'),
        ('scripts', 'scripts'),
        ('es_theme_editor.ico', '.'), # Icono de la aplicación
    ],
    hiddenimports=[
        'requests',
        'requests.adapters',
        'requests.api',
        'requests.auth',
        'requests.cookies',
        'requests.models',
        'requests.sessions',
        'requests.utils',
        'urllib3',
        'urllib3.util',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='egbtheme-creator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI
    icon='es_theme_editor.ico'  # Icono de la aplicación
)