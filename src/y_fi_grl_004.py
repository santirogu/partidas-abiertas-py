"""y_fi_grl_004.py — Descarga el maestro del plan de cuentas (Y_FI_GRL_004).

Replica `resources/grabaciones/Y_FI_GRL_004.vbs` ("Lista el plan de
cuentas para cualquier Sociedad") y entrega el archivo tal como lo exporta
SAP, sin procesarlo. De ahí salen las cuentas con gestión de partidas
abiertas (columna PI) que luego se consultan en FAGLL03.

Diferencias con la grabación: `/n`, sociedades elegidas por el usuario
(se pegan desde el portapapeles, como en la grabación, borrando antes la
selección) y archivo en `salida/` como `Y_FI_GRL_004_AAAAMMDD_HHMMSS.xlsx`.

No usa fecha clave ni disposición: la grabación exporta la lista con la
disposición por defecto del usuario.

Cumple el contrato de los módulos de flujo que usa la GUI:
`validar_configuracion()`, `get_sap_session()` y `descargar(...)`.

REQUISITOS
==========
Windows con SAP GUI abierto, sesión iniciada y scripting habilitado.

USO
===
    python src/y_fi_grl_004.py [SOCIEDAD ...]

    python src/y_fi_grl_004.py              # todas las sociedades
    python src/y_fi_grl_004.py ISA XM       # solo ISA y XM
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from pathlib import Path

from comun import (
    SOCIEDADES,
    abrir_transaccion,
    configurar_logging,
    crear_avisador,
    ejecutar,
    ejecutar_reporte,
    exportar_hoja_calculo,
    get_sap_session,
    nombre_con_timestamp,
    pegar_seleccion_multiple,
    terminar_exportacion,
    validar_sociedades,
)
from paths import SALIDA_DIR

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

TRANSACCION = "Y_FI_GRL_004"
PREFIJO_SALIDA = "Y_FI_GRL_004"  # salida: Y_FI_GRL_004_AAAAMMDD_HHMMSS.xlsx

# IDs de Y_FI_GRL_004.vbs.
ID_CAMPO_PLAN_CUENTAS = "wnd[0]/usr/ctxtSD_KTOPL-LOW"
ID_BTN_SOCIEDADES = "wnd[0]/usr/btn%_SD_BUKRS_%_APP_%-VALU_PUSH"

TODOS_LOS_PLANES = "*"
# El export de ejemplo de todas las sociedades pesa ~5,7 MB (42 mil filas).
TIMEOUT_ARCHIVO_SEG = 180.0


# ---------------------------------------------------------------------------
# VALIDACIONES
# ---------------------------------------------------------------------------


def validar_configuracion() -> None:
    """No hay nada que configurar: este reporte no usa disposición. Existe
    para cumplir el contrato de los módulos de flujo."""
    return None


# ---------------------------------------------------------------------------
# PASOS: una función por paso; la sesión siempre es el 1.er argumento
# ---------------------------------------------------------------------------


def seleccionar_planes_de_cuentas(session) -> None:
    """Todos los planes de cuentas (`*`, como la grabación)."""

    def _escribir() -> None:
        session.findById(ID_CAMPO_PLAN_CUENTAS).text = TODOS_LOS_PLANES

    ejecutar("Seleccionar todos los planes de cuentas", _escribir)


def seleccionar_sociedades(session, sociedades: Iterable[str]) -> None:
    """La grabación pega sin borrar antes; aquí se borra igual (mismo
    diálogo que FBL1N/FBL5N) por si el campo trae una sociedad por defecto."""
    pegar_seleccion_multiple(session, ID_BTN_SOCIEDADES, sociedades)


# ---------------------------------------------------------------------------
# ORQUESTADOR
# ---------------------------------------------------------------------------


def descargar(
    session,
    sociedades: Iterable[str],
    carpeta_destino: Path = SALIDA_DIR,
    progreso: Callable[[str], None] | None = None,
) -> tuple[str, str]:
    """Descarga Y_FI_GRL_004 y devuelve `(carpeta, nombre_archivo)`.

    Aborta en el primer error. Todo se valida antes de tocar SAP.
    `progreso(texto)` recibe el paso en curso.
    """
    socs = validar_sociedades(sociedades)
    validar_configuracion()

    carpeta = Path(carpeta_destino)
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = nombre_con_timestamp(PREFIJO_SALIDA)
    avisar = crear_avisador(progreso)

    avisar(f"Y_FI_GRL_004: {len(socs)} sociedad(es)")
    avisar("Paso 1 de 5: abriendo Y_FI_GRL_004…")
    abrir_transaccion(session, TRANSACCION)
    avisar("Paso 2 de 5: seleccionando planes de cuentas y sociedades…")
    seleccionar_planes_de_cuentas(session)
    seleccionar_sociedades(session, socs)
    avisar("Paso 3 de 5: ejecutando el reporte (puede tardar varios minutos)…")
    ejecutar_reporte(session)
    avisar("Paso 4 de 5: exportando a Excel…")
    archivo = exportar_hoja_calculo(session, carpeta, nombre)
    avisar("Paso 5 de 5: esperando a que SAP termine de guardar…")
    terminar_exportacion(session, archivo, TIMEOUT_ARCHIVO_SEG)
    avisar(f"Y_FI_GRL_004 listo: {archivo}")
    return str(carpeta), nombre


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """0 = OK · 1 = error (validación o SAP) · 2 = uso incorrecto."""
    argv = argv if argv is not None else sys.argv[1:]
    if any(arg.startswith("-") for arg in argv):
        print("Uso: python src/y_fi_grl_004.py [SOCIEDAD ...]", file=sys.stderr)
        return 2
    sociedades = argv or list(SOCIEDADES)
    configurar_logging()
    try:
        validar_sociedades(sociedades)
        session = get_sap_session()
        carpeta, nombre = descargar(session, sociedades)
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {Path(carpeta) / nombre}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
