"""Rutas del proyecto que funcionan igual en modo dev y empaquetado.

Única fuente de verdad de rutas: `main`, `branding`, `comun` y los
módulos de flujo resuelven todo desde aquí, así que un solo lugar decide
qué cambia cuando la app corre desde el `.exe` en vez de
`python src/main.py`.

- **Dev** (`python src/main.py`): `PROJECT_ROOT` es la raíz del repo
  (padre de `src/`). Recursos en `<repo>/resources/` y salida en
  `<repo>/salida/`.
- **Empaquetado** (PyInstaller `--onefile`, `sys.frozen == True`):
  `PROJECT_ROOT` es la carpeta donde el usuario dejó el `.exe`, NO el
  temporal `_MEIPASS`. `salida/` queda al lado del `.exe`; el logo se lee
  de `_MEIPASS/resources/` (embebido y de solo lectura).

Este proyecto no tiene archivo de entrada que edite el usuario (los datos
salen de SAP), así que no hay carpeta `entrada/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# RAÍZ DEL PROYECTO
# ---------------------------------------------------------------------------


def project_root() -> Path:
    """Dev: padre de `src/`. Empaquetado: carpeta del `.exe`."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = project_root()
# Todo lo que genera la app: exports de SAP, Excel procesados y logs.
SALIDA_DIR = PROJECT_ROOT / "salida"
# El `.exe` no tiene consola: sin un archivo de log no hay forma de saber
# qué falló en el equipo del usuario.
LOGS_DIR = SALIDA_DIR / "logs"


# ---------------------------------------------------------------------------
# RECURSOS EMPAQUETADOS (SOLO LECTURA)
# ---------------------------------------------------------------------------


def bundled_resource_path(rel_path: str) -> Path:
    """Ruta a un recurso empaquetado en el `.exe`, o su equivalente en el
    repo en modo dev.

    Es de **solo lectura**: nunca escribir aquí, porque `sys._MEIPASS` es
    una carpeta temporal que PyInstaller borra al cerrar la app.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / rel_path
    return PROJECT_ROOT / rel_path
