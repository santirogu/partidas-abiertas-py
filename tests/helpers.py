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
import types
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
        # IDs que "no están en pantalla": findById lanza error (o devuelve
        # None con raise_=False), como el SAP real.
        self.faltantes: set[str] = set()
        # id → callback que corre al hacer `press()` sobre ese control
        # (p. ej. para que aparezca una ventana después de un botón).
        self.al_presionar: dict[str, object] = {}

    def findById(self, element_id: str, raise_: bool = True) -> _MockElement | None:
        if element_id in self.faltantes:
            if raise_:
                raise RuntimeError(f"The control could not be found by id: {element_id}")
            return None
        if element_id not in self._elements:
            self._elements[element_id] = _MockElement(self, element_id)
        return self._elements[element_id]

    def configurar_grilla(
        self, element_id: str, columna: str, valores: list[str], visibles: int = 10
    ) -> _MockElement:
        """Prepara una grilla ALV con `valores` en `columna` (una fila por
        valor) para `GetCellValue`, `RowCount` y `VisibleRowCount`."""
        grilla = self.findById(element_id)
        object.__setattr__(grilla, "RowCount", len(valores))
        object.__setattr__(grilla, "VisibleRowCount", visibles)
        object.__setattr__(grilla, "_celdas", {(i, columna): v for i, v in enumerate(valores)})
        return grilla

    def mostrar(self, element_id: str, texto: str) -> None:
        """Pone `texto` en un control sin registrarlo como acción (lo que SAP
        muestra, p. ej. el título de la ventana o la barra de estado)."""
        object.__setattr__(self.findById(element_id), "text", texto)

    @property
    def ActiveWindow(self) -> _MockElement:  # nombre de la API de SAP
        return self.findById("wnd[0]")

    def simular_lista_tras_ejecutar(self, id_campo_seleccion: str) -> None:
        """Al pulsar Ejecutar, SAP deja la pantalla de selección y muestra la
        lista: `id_campo_seleccion` deja de existir. Sin esto, la sesión
        falsa se comporta como un reporte sin resultados."""
        self.al_presionar["wnd[0]/tbar[1]/btn[8]"] = lambda: self.faltantes.add(id_campo_seleccion)


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
        "selectionInterval",
    }

    def __init__(self, session: MockSession, element_id: str) -> None:
        object.__setattr__(self, "_session", session)
        object.__setattr__(self, "_id", element_id)
        object.__setattr__(self, "text", "")
        object.__setattr__(self, "caretPosition", 0)
        object.__setattr__(self, "selected", False)
        object.__setattr__(self, "_celdas", {})

    def __setattr__(self, nombre: str, valor) -> None:
        if nombre in self._PROPIEDADES:
            self._session.actions.append((self._id, f"{nombre}=", valor))
        object.__setattr__(self, nombre, valor)

    def _registrar(self, metodo: str, *args) -> None:
        self._session.actions.append((self._id, metodo, *args))

    def GetCellValue(self, fila: int, columna: str) -> str:
        return self._celdas.get((fila, columna), "")

    def close(self) -> None:
        self._registrar("close")

    def press(self) -> None:
        self._registrar("press")
        callback = self._session.al_presionar.get(self._id)
        if callback is not None:
            callback()

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


def fake_win32clipboard(abrir_falla_veces: int = 0) -> types.ModuleType:
    """Módulo `win32clipboard` falso: guarda el texto en `.contenido`.

    `OpenClipboard` falla las primeras `abrir_falla_veces` veces, como
    cuando otro programa tiene el portapapeles ocupado.
    """
    modulo = types.ModuleType("win32clipboard")
    modulo.CF_UNICODETEXT = 13
    modulo.contenido = None
    modulo.llamadas = []
    fallos = {"restantes": abrir_falla_veces}

    def open_clipboard() -> None:
        modulo.llamadas.append("OpenClipboard")
        if fallos["restantes"] > 0:
            fallos["restantes"] -= 1
            raise OSError("Acceso denegado")

    def set_text(texto: str, formato: int) -> None:
        modulo.llamadas.append("SetClipboardText")
        modulo.contenido = (texto, formato)

    modulo.OpenClipboard = open_clipboard
    modulo.EmptyClipboard = lambda: modulo.llamadas.append("EmptyClipboard")
    modulo.SetClipboardText = set_text
    modulo.CloseClipboard = lambda: modulo.llamadas.append("CloseClipboard")
    return modulo


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
