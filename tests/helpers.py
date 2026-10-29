"""Utilidades compartidas por los tests.

Importar este módulo agrega `src/` al `sys.path`, así que cada archivo de
test solo tiene que agregar `tests/` (para encontrar `helpers`) y luego
importar los módulos del proyecto:

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import helpers  # agrega src/ al sys.path

    import comun

Así funcionan igual `python -m unittest discover tests` y
`python -m unittest tests.test_comun`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# ---------------------------------------------------------------------------
# SESIÓN SAP FALSA
# ---------------------------------------------------------------------------


class MockSession:
    """Sesión de SAP GUI falsa que registra cada acción en `actions`.

    `findById(id)` crea o reutiliza un elemento. Los métodos se registran
    como `(id, metodo, *args)` y las propiedades que se asignan como
    `(id, "propiedad=", valor)`, así los tests verifican la secuencia
    exacta de IDs, métodos y valores sin SAP. Los nombres en camelCase
    replican la API de SAP GUI Scripting.
    """

    def __init__(self) -> None:
        self._elements: dict[str, _MockElement] = {}
        self.actions: list[tuple] = []

    def findById(self, element_id: str) -> _MockElement:
        if element_id not in self._elements:
            self._elements[element_id] = _MockElement(self, element_id)
        return self._elements[element_id]


class _MockElement:
    # Propiedades que SAP GUI Scripting permite asignar y que vale la pena
    # registrar en `actions`.
    _PROPIEDADES = {
        "text",
        "caretPosition",
        "selected",
        "currentCellRow",
        "firstVisibleRow",
        "selectedRows",
    }

    def __init__(self, session: MockSession, element_id: str) -> None:
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_id", element_id)
        object.__setattr__(self, "text", "")
        object.__setattr__(self, "caretPosition", 0)
        object.__setattr__(self, "selected", False)

    def __setattr__(self, nombre: str, valor) -> None:
        if nombre in self._PROPIEDADES:
            self._session.actions.append((self._id, f"{nombre}=", valor))
        object.__setattr__(self, nombre, valor)

    def _registrar(self, metodo: str, *args) -> None:
        self._session.actions.append((self._id, metodo, *args))

    def press(self) -> None:
        self._registrar("press")

    def setFocus(self) -> None:
        self._registrar("setFocus")

    def maximize(self) -> None:
        self._registrar("maximize")

    def sendVKey(self, key: int) -> None:
        self._registrar("sendVKey", key)

    def select(self) -> None:
        self._registrar("select")

    def clickCurrentCell(self) -> None:
        self._registrar("clickCurrentCell")


# ---------------------------------------------------------------------------
# THREAD SÍNCRONO
# ---------------------------------------------------------------------------


class SyncFakeThread:
    """Reemplaza `threading.Thread` para que el worker corra en el acto.

    Uso: `patch("main.threading.Thread", side_effect=lambda target=None, **kw:
    SyncFakeThread(target))`.
    """

    def __init__(self, target=None, daemon=None, **kwargs) -> None:
        self.target = target

    def start(self) -> None:
        if self.target is not None:
            self.target()


# ---------------------------------------------------------------------------
# EXCEL
# ---------------------------------------------------------------------------


def crear_libro(ruta: Path, hojas: dict[str, list[list]]) -> Path:
    """Crea un `.xlsx` real con una hoja por clave de `hojas` (en orden)."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for fila in filas:
            ws.append(fila)
    wb.save(ruta)
    return ruta
