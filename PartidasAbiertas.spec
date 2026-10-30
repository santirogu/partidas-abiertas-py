# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para Partidas Abiertas.

Genera `dist/PartidasAbiertas.exe` (un solo archivo, sin consola).

Build (EN WINDOWS: PyInstaller no hace cross-compile):

    .venv/Scripts/pyinstaller PartidasAbiertas.spec --clean --noconfirm

En macOS/Linux produce un binario de esa plataforma: solo sirve como
dry-run para comprobar que el spec y los imports resuelven.

Junto al `.exe` la app crea, en el primer arranque:
    configuracion/sociedades.json   lista de sociedades del usuario
    salida/                         exports de SAP y logs/app.log
Ninguna de las dos se empaqueta: son del usuario.
"""

import sys as _sys

NOMBRE_EXE = "PartidasAbiertas"
TITULO_APP = "Partidas Abiertas"  # igual que comun.TITULO_APP
COLOR_PRIMARIO = "#1A3A6C"  # igual que branding.COLOR_PRIMARIO

# Los módulos de flujo se importan con importlib según main.OPCIONES
# (`Opcion.modulo`), así que PyInstaller no los detecta solo: sin esta
# lista el .exe abre pero falla al pulsar cualquier opción.
# tests/test_spec.py verifica que coincida con main.OPCIONES.
MODULOS_DE_FLUJO = ["fbl1n", "fbl5n", "y_fi_grl_004", "fagll03"]

# Recursos de solo lectura que la app lee con paths.bundled_resource_path.
# Las grabaciones .vbs y los ejemplos de resources/ NO se empaquetan.
DATOS = [
    ("resources/logo.png", "resources"),
    ("resources/sociedades_iniciales.json", "resources"),
]

_icon = "resources/logo.png" if _sys.platform == "win32" else None

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=[],
    datas=DATOS,
    hiddenimports=[
        *MODULOS_DE_FLUJO,
        # pywin32: se importan dentro de funciones (try/except ImportError).
        "win32com.client",
        "pythoncom",
        "win32clipboard",
        # ImageTk (logo) y tkcalendar (DateEntry con locale es_CO; el hook
        # de babel ya empaqueta los datos de idioma).
        "PIL._tkinter_finder",
        "babel.numbers",
        "babel.dates",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "pandas", "scipy"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

# upx=False: comprimir con UPX hace más probable que el antivirus de los
# equipos corporativos marque el .exe por error. A cambio pesa un poco más.
_opciones_exe = dict(
    name=NOMBRE_EXE,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)

# El arranque en frío del .exe tarda varios segundos: el splash avisa que la
# app está cargando. main._cerrar_splash() lo cierra al mostrar la ventana.
# PyInstaller no soporta splash en macOS.
if _sys.platform in ("win32", "linux"):
    splash = Splash(
        "resources/logo.png",
        binaries=a.binaries,
        datas=a.datas,
        text_pos=(10, 260),  # dentro de la imagen (469x286)
        text_size=10,
        text_color=COLOR_PRIMARIO,
        text_default=f"Cargando {TITULO_APP}…",
        always_on_top=True,
    )
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        splash,
        splash.binaries,
        [],
        **_opciones_exe,
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **_opciones_exe)
