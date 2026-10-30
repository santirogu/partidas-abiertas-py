"""sociedades.py — Lista de sociedades que usan las descargas.

La lista ya no está fija en el código: el usuario la administra desde la
pantalla "Sociedades" de la app (agregar, modificar, quitar y restaurar).
Se guarda en `configuracion/sociedades.json`, junto al `.exe`, así que
cada analista tiene la suya y no depende de la red.

La primera vez se crea con la lista inicial empaquetada
(`resources/sociedades_iniciales.json`: las 24 de `Sociedades.xlsx`,
2026-10-29) y después nunca se sobrescribe, ni al actualizar la app.

Las operaciones (`agregar`, `modificar`, `quitar`) son puras: reciben y
devuelven listas, y quien las llama decide cuándo `guardar`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

from paths import CONFIG_DIR, bundled_resource_path

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

ARCHIVO = CONFIG_DIR / "sociedades.json"
INICIALES_PATH = bundled_resource_path("resources/sociedades_iniciales.json")
VERSION_FORMATO = 1

# Códigos de sociedad de SAP: hasta 4 letras o números.
PATRON_CODIGO = re.compile(r"^[A-Z0-9]{1,4}$")
LARGO_MAXIMO_NOMBRE = 60


class Sociedad(NamedTuple):
    codigo: str
    nombre: str = ""  # opcional, solo para que lo lean las personas


# ---------------------------------------------------------------------------
# VALIDACIONES (puras)
# ---------------------------------------------------------------------------


def normalizar_codigo(codigo: str) -> str:
    """Código en mayúsculas y sin espacios, o `ValueError` si no es válido."""
    texto = (codigo or "").strip()
    if not texto:
        raise ValueError("Escribe el código de la sociedad.")
    norm = texto.upper()
    if not PATRON_CODIGO.match(norm):
        raise ValueError(
            f"«{texto}» no es un código de sociedad válido: debe tener de 1 a 4 "
            "letras o números, sin espacios."
        )
    return norm


def normalizar_nombre(nombre: str) -> str:
    """Nombre sin espacios de más, o `ValueError` si es demasiado largo."""
    norm = " ".join((nombre or "").split())
    if len(norm) > LARGO_MAXIMO_NOMBRE:
        raise ValueError(f"El nombre puede tener hasta {LARGO_MAXIMO_NOMBRE} caracteres.")
    return norm


def _ordenar(lista: Iterable[Sociedad]) -> list[Sociedad]:
    return sorted(lista, key=lambda s: s.codigo)


def _existe(lista: list[Sociedad], codigo: str) -> bool:
    return any(s.codigo == codigo for s in lista)


# ---------------------------------------------------------------------------
# OPERACIONES (puras)
# ---------------------------------------------------------------------------


def agregar(lista: list[Sociedad], codigo: str, nombre: str = "") -> list[Sociedad]:
    nueva = Sociedad(normalizar_codigo(codigo), normalizar_nombre(nombre))
    if _existe(lista, nueva.codigo):
        raise ValueError(f"La sociedad {nueva.codigo} ya está en la lista.")
    return _ordenar([*lista, nueva])


def modificar(
    lista: list[Sociedad], codigo_actual: str, codigo: str, nombre: str = ""
) -> list[Sociedad]:
    """Reemplaza la sociedad `codigo_actual` (puede cambiar su código)."""
    if not _existe(lista, codigo_actual):
        raise ValueError(f"La sociedad {codigo_actual} ya no está en la lista.")
    nueva = Sociedad(normalizar_codigo(codigo), normalizar_nombre(nombre))
    if nueva.codigo != codigo_actual and _existe(lista, nueva.codigo):
        raise ValueError(f"La sociedad {nueva.codigo} ya está en la lista.")
    return _ordenar([nueva if s.codigo == codigo_actual else s for s in lista])


def quitar(lista: list[Sociedad], codigo: str) -> list[Sociedad]:
    if not _existe(lista, codigo):
        raise ValueError(f"La sociedad {codigo} ya no está en la lista.")
    resto = [s for s in lista if s.codigo != codigo]
    if not resto:
        raise ValueError("La lista debe tener al menos una sociedad.")
    return resto


# ---------------------------------------------------------------------------
# ARCHIVO
# ---------------------------------------------------------------------------


def _leer(ruta: Path) -> list[Sociedad]:
    """Lee y valida un archivo de sociedades; `ValueError` si está dañado."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        filas = datos["sociedades"]
        lista = [
            Sociedad(normalizar_codigo(f["codigo"]), normalizar_nombre(f.get("nombre", "")))
            for f in filas
        ]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(
            f"El archivo de sociedades está dañado ({ruta}). Abre «Editar "
            "sociedades» y pulsa «Restaurar lista inicial»."
        ) from exc
    if not lista:
        raise ValueError(f"El archivo de sociedades no tiene ninguna sociedad ({ruta}).")
    vistas: set[str] = set()
    for s in lista:
        if s.codigo in vistas:
            raise ValueError(f"La sociedad {s.codigo} está repetida en {ruta}.")
        vistas.add(s.codigo)
    return _ordenar(lista)


def asegurar_archivo(archivo: Path | None = None) -> tuple[Path, bool]:
    """Crea el archivo con la lista inicial si no existe.

    Returns:
        `(ruta, True si se acaba de crear)`. Nunca sobrescribe el archivo
        del usuario.
    """
    ruta = archivo if archivo is not None else ARCHIVO
    if ruta.exists():
        return ruta, False
    if not INICIALES_PATH.exists():
        raise ValueError(
            "Falta la lista inicial de sociedades dentro de la app "
            "(resources/sociedades_iniciales.json)."
        )
    ruta.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INICIALES_PATH, ruta)
    return ruta, True


def cargar(archivo: Path | None = None) -> list[Sociedad]:
    """La lista del usuario (la crea con la inicial si aún no existe)."""
    ruta, _ = asegurar_archivo(archivo)
    return _leer(ruta)


def codigos(archivo: Path | None = None) -> list[str]:
    """Solo los códigos, en orden alfabético."""
    return [s.codigo for s in cargar(archivo)]


def guardar(lista: list[Sociedad], archivo: Path | None = None) -> None:
    """Guarda la lista. Escribe primero un temporal y luego lo reemplaza,
    para que un corte a mitad de camino no deje el archivo dañado."""
    ruta = archivo if archivo is not None else ARCHIVO
    if not lista:
        raise ValueError("La lista debe tener al menos una sociedad.")
    datos = {
        "version": VERSION_FORMATO,
        "sociedades": [{"codigo": s.codigo, "nombre": s.nombre} for s in _ordenar(lista)],
    }
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=".sociedades-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(temporal, ruta)
    except BaseException:
        Path(temporal).unlink(missing_ok=True)
        raise


def restaurar_iniciales(archivo: Path | None = None) -> list[Sociedad]:
    """Vuelve a la lista inicial empaquetada y la devuelve."""
    if not INICIALES_PATH.exists():
        raise ValueError("Falta la lista inicial de sociedades dentro de la app.")
    lista = _leer(INICIALES_PATH)
    guardar(lista, archivo)
    return lista
