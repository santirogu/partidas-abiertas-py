"""fbl5n.py — Descarga las partidas abiertas de deudores (FBL5N) a Excel.

Replica `resources/grabaciones/FBL5N.vbs` y entrega el archivo tal como lo
exporta SAP, sin procesarlo. Es la misma secuencia que FBL1N con los
campos de deudor (`DD_*`); las diferencias con la grabación son las mismas:
`/n`, sociedades elegidas por el usuario, disposición por nombre y archivo
en `salida/` como `FBL5N_AAAAMMDD_HHMMSS.xlsx`.

Cumple el contrato de los módulos de flujo que usa la GUI:
`validar_configuracion()`, `get_sap_session()` y `descargar(...)`.

REQUISITOS
==========
Windows con SAP GUI abierto, sesión iniciada y scripting habilitado.

USO
===
    python src/fbl5n.py FECHA_CLAVE [SOCIEDAD ...]

    python src/fbl5n.py 28.10.2026            # todas las sociedades
    python src/fbl5n.py 28.10.2026 ISA XM     # solo ISA y XM
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path

from comun import (
    SOCIEDADES,
    abrir_transaccion,
    cargar_valor_unico,
    configurar_logging,
    crear_avisador,
    ejecutar,
    ejecutar_reporte,
    elegir_disposicion,
    elegir_fecha_en_calendario,
    exportar_hoja_calculo,
    get_sap_session,
    nombre_con_timestamp,
    pegar_seleccion_multiple,
    terminar_exportacion,
    validar_disposicion,
    validar_fecha_clave,
    validar_sociedades,
)
from paths import SALIDA_DIR

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

TRANSACCION = "FBL5N"
PREFIJO_SALIDA = "FBL5N"  # salida: FBL5N_AAAAMMDD_HHMMSS.xlsx

# Nombre corto de la disposición (columna "Disposición" del diálogo
# "Seleccionar disposición"). PENDIENTE: FBL5N.vbs la elige por fila (169)
# y falta que el equipo usuario confirme el nombre. Mientras sea None, la
# app avisa y no se conecta a SAP.
DISPOSICION: str | None = None

# IDs de FBL5N.vbs.
ID_BTN_DEUDORES = "wnd[0]/usr/btn%_DD_KUNNR_%_APP_%-VALU_PUSH"
ID_BTN_SOCIEDADES = "wnd[0]/usr/btn%_DD_BUKRS_%_APP_%-VALU_PUSH"
ID_CAMPO_FECHA_CLAVE = "wnd[0]/usr/ctxtPA_STIDA"
ID_CHK_PARTIDAS_NORMALES = "wnd[0]/usr/chkX_NORM"
ID_CHK_OPERACIONES_CME = "wnd[0]/usr/chkX_SHBV"

TODOS_LOS_DEUDORES = "*"
# El export de ejemplo de todas las sociedades pesa ~3,7 MB (28 mil filas).
TIMEOUT_ARCHIVO_SEG = 120.0


# ---------------------------------------------------------------------------
# VALIDACIONES
# ---------------------------------------------------------------------------


def validar_configuracion() -> str:
    """Devuelve la disposición o lanza `ValueError` si aún no se configuró."""
    return validar_disposicion(DISPOSICION, TRANSACCION)


# ---------------------------------------------------------------------------
# PASOS: una función por paso; la sesión siempre es el 1.er argumento
# ---------------------------------------------------------------------------


def seleccionar_deudores(session) -> None:
    """Todos los deudores (`*` en la selección múltiple, como la grabación)."""
    cargar_valor_unico(session, ID_BTN_DEUDORES, TODOS_LOS_DEUDORES)


def seleccionar_sociedades(session, sociedades: Iterable[str]) -> None:
    pegar_seleccion_multiple(session, ID_BTN_SOCIEDADES, sociedades)


def fijar_fecha_clave(session, fecha_clave: date) -> None:
    elegir_fecha_en_calendario(session, ID_CAMPO_FECHA_CLAVE, fecha_clave)


def marcar_clases_de_partida(session) -> None:
    """Partidas normales + operaciones CME, como en la grabación."""

    def _marcar() -> None:
        session.findById(ID_CHK_PARTIDAS_NORMALES).selected = True
        session.findById(ID_CHK_OPERACIONES_CME).selected = True

    ejecutar("Marcar partidas normales y operaciones CME", _marcar)


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------


def descargar(
    session,
    sociedades: Iterable[str],
    fecha_clave: date | str,
    carpeta_destino: Path = SALIDA_DIR,
    progreso: Callable[[str], None] | None = None,
) -> tuple[str, str]:
    """Descarga FBL5N y devuelve `(carpeta, nombre_archivo)`.

    Aborta en el primer error: cada paso depende del anterior. Todo se
    valida antes de tocar SAP. `progreso(texto)` recibe el paso en curso.
    """
    socs = validar_sociedades(sociedades)
    fecha = validar_fecha_clave(fecha_clave)
    disposicion = validar_configuracion()

    carpeta = Path(carpeta_destino)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre_con_timestamp(PREFIJO_SALIDA)
    avisar = crear_avisador(progreso)

    avisar(f"FBL5N: {len(socs)} sociedad(es), fecha clave {fecha:%d.%m.%Y}")
    avisar("Paso 1 de 7: abriendo FBL5N…")
    abrir_transaccion(session, TRANSACCION)
    avisar("Paso 2 de 7: seleccionando deudores y sociedades…")
    seleccionar_deudores(session)
    seleccionar_sociedades(session, socs)
    avisar("Paso 3 de 7: fijando la fecha clave…")
    fijar_fecha_clave(session, fecha)
    marcar_clases_de_partida(session)
    avisar("Paso 4 de 7: ejecutando el reporte (puede tardar varios minutos)…")
    ejecutar_reporte(session)
    avisar(f"Paso 5 de 7: aplicando la disposición {disposicion}…")
    elegir_disposicion(session, disposicion)
    avisar("Paso 6 de 7: exportando a Excel…")
    archivo = exportar_hoja_calculo(session, carpeta, nombre)
    avisar("Paso 7 de 7: esperando a que SAP termine de guardar…")
    terminar_exportacion(session, archivo, TIMEOUT_ARCHIVO_SEG)
    avisar(f"FBL5N listo: {archivo}")
    return str(carpeta), nombre


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """0 = OK · 1 = error (validación o SAP) · 2 = uso incorrecto."""
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("Uso: python src/fbl5n.py FECHA_CLAVE [SOCIEDAD ...]", file=sys.stderr)
        return 2
    fecha_clave, sociedades = argv[0], argv[1:] or list(SOCIEDADES)
    configurar_logging()
    try:
        validar_sociedades(sociedades)
        validar_fecha_clave(fecha_clave)
        validar_configuracion()
        session = get_sap_session()
        carpeta, nombre = descargar(session, sociedades, fecha_clave)
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {Path(carpeta) / nombre}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
