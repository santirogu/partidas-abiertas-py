"""Piezas compartidas por la GUI y los módulos de flujo.

En `activos-propios-py`, `_log`, `_ejecutar` y `get_sap_session` estaban
copiados en cada flujo, y el título de la ventana vivía en dos constantes
distintas (eso rompió el minimizado antes de las capturas). Aquí viven una
sola vez:

- Identidad de la app (`TITULO_APP`, `TITULAR`).
- Catálogo de sociedades y validación de las entradas comunes.
- Logging a consola y a `salida/logs/app.log`.
- `ejecutar()`: traduce los errores COM (suelen venir vacíos) a mensajes
  que dicen qué paso falló.
- Conexión a SAP GUI Scripting, apartamento COM por thread y portapapeles.
- Pasos de SAP que comparten los flujos (selección múltiple, calendario,
  disposición, exportar a Excel).
- Utilidades de archivos (Excel bloqueado, guardado seguro, esperar a
  que SAP termine de escribir, nombres con timestamp).

Nunca importa `main` ni ningún módulo de flujo.
"""

from __future__ import annotations

import contextlib
import logging
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from paths import LOGS_DIR

# ---------------------------------------------------------------------------
# IDENTIDAD DE LA APP
# ---------------------------------------------------------------------------

# Única fuente del título de la ventana. Si algún flujo necesita buscar la
# ventana de la app (p. ej. para minimizarla), usa ESTA constante.
TITULO_APP = "Partidas Abiertas"
TITULAR = "El Hub de ISA"


# ---------------------------------------------------------------------------
# CATÁLOGOS Y VALIDACIONES
# ---------------------------------------------------------------------------

# Lista oficial de sociedades (confirmada el 2026-10-28; coincide con las
# 28 que salen en el export de ejemplo de FBL1N). En orden alfabético.
SOCIEDADES: tuple[str, ...] = (
    "AM", "ARAU", "BOSQ", "CABA", "CEYT", "CTMP", "HUBD",
    "INCO", "INNO", "INTE", "ISA", "ISAP", "ISAV", "ITCH",
    "ITCO", "LAGO", "MAIP", "PDI", "REP", "REPD", "RIOS",
    "RLOA", "RORB", "RPAE", "TELE", "TELP", "TRAN", "XM",
)  # fmt: skip

# Formato en que el usuario escribe y lee las fechas (el de SAP en ISA).
FORMATO_FECHA_USUARIO = "%d.%m.%Y"


def validar_sociedades(sociedades: Iterable[str]) -> list[str]:
    """Normaliza (strip/upper) y valida contra `SOCIEDADES`.

    Devuelve las sociedades sin duplicados y en el orden del catálogo, o
    lanza `ValueError` si no hay ninguna o alguna no existe.
    """
    elegidas = {s.strip().upper() for s in sociedades if s and s.strip()}
    if not elegidas:
        raise ValueError("Selecciona al menos una sociedad.")
    invalidas = sorted(elegidas - set(SOCIEDADES))
    if invalidas:
        raise ValueError(
            f"Sociedad no válida: {', '.join(invalidas)}. Las válidas son: {', '.join(SOCIEDADES)}."
        )
    return [s for s in SOCIEDADES if s in elegidas]


def validar_fecha_clave(valor: date | str) -> date:
    """Acepta un `date` o un texto `dd.mm.aaaa`; lanza `ValueError` si no."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = (valor or "").strip()
    try:
        return datetime.strptime(texto, FORMATO_FECHA_USUARIO).date()
    except ValueError as exc:
        raise ValueError(f"Fecha clave inválida: '{texto}'. Usa el formato dd.mm.aaaa.") from exc


def validar_disposicion(nombre: str | None, transaccion: str) -> str:
    """Devuelve el nombre de la disposición o lanza `ValueError` si el flujo
    aún no la tiene configurada (sin ella el export sale con otras columnas)."""
    if not nombre or not nombre.strip():
        raise ValueError(
            f"Todavía no está configurada la disposición de {transaccion} "
            f"({transaccion.lower()}.DISPOSICION). Sin ella el archivo saldría "
            "con otras columnas."
        )
    return nombre.strip()


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

LOGGER_NOMBRE = "partidas_abiertas"
LOG_ARCHIVO_NOMBRE = "app.log"
LOG_MAX_BYTES = 1_000_000
LOG_BACKUPS = 3

logger = logging.getLogger(LOGGER_NOMBRE)
# Sin configurar (tests, uso como librería) los mensajes no se pierden con
# un warning de "No handlers": simplemente se descartan.
logger.addHandler(logging.NullHandler())

# Marca para reconocer los handlers que agrega `configurar_logging` y poder
# quitarlos sin tocar los de terceros.
_MARCA_HANDLER = "_partidas_abiertas"


def configurar_logging(carpeta_logs: Path = LOGS_DIR) -> Path | None:
    """Envía los logs a la consola y a `carpeta_logs/app.log` (rotativo).

    Es idempotente: si ya se configuró, no duplica handlers.

    Returns:
        La ruta del archivo de log, o `None` si no se pudo crear la carpeta
        (la app sigue funcionando solo con consola).

    El `.exe` se construye sin consola y ahí `sys.stdout` es `None`: el
    handler de consola solo se agrega si existe, porque un
    `StreamHandler(None)` cae a `sys.stderr` (también `None`) y falla en
    cada mensaje.
    """
    if any(getattr(h, _MARCA_HANDLER, False) for h in logger.handlers):
        archivos = [
            Path(h.baseFilename) for h in logger.handlers if isinstance(h, RotatingFileHandler)
        ]
        return archivos[0] if archivos else None

    logger.setLevel(logging.INFO)

    if sys.stdout is not None:
        consola = logging.StreamHandler(sys.stdout)
        consola.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
        setattr(consola, _MARCA_HANDLER, True)
        logger.addHandler(consola)

    try:
        carpeta_logs.mkdir(parents=True, exist_ok=True)
        archivo = carpeta_logs / LOG_ARCHIVO_NOMBRE
        handler_archivo = RotatingFileHandler(
            archivo, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("No se pudo crear el log en %s: %s", carpeta_logs, exc)
        return None

    handler_archivo.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s")
    )
    setattr(handler_archivo, _MARCA_HANDLER, True)
    logger.addHandler(handler_archivo)
    return archivo


def cerrar_logging() -> None:
    """Quita y cierra los handlers de `configurar_logging`.

    En Windows un archivo de log abierto no se puede borrar; los tests lo
    llaman antes de limpiar su carpeta temporal.
    """
    for handler in list(logger.handlers):
        if getattr(handler, _MARCA_HANDLER, False):
            logger.removeHandler(handler)
            handler.close()


def log(mensaje: str) -> None:
    """Registra un mensaje informativo (consola + archivo, si están)."""
    logger.info(mensaje)


def crear_avisador(progreso: Callable[[str], None] | None) -> Callable[[str], None]:
    """Devuelve una función que registra cada texto en el log y, si hay
    `progreso`, se lo pasa (la GUI lo muestra en el label de estado).

    Un fallo de `progreso` (p. ej. la ventana ya se cerró) nunca detiene el
    flujo de SAP.
    """

    def avisar(texto: str) -> None:
        log(texto)
        if progreso is not None:
            try:
                progreso(texto)
            except Exception as exc:
                log(f"progreso falló (ignorado): {exc!r}")

    return avisar


def ejecutar(descripcion: str, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Loguea la operación y ejecuta `fn(*args, **kwargs)`.

    Si falla, re-lanza un `RuntimeError` que dice qué se intentaba hacer:
    las excepciones COM de SAP suelen venir con la descripción vacía.
    """
    log(f"  → {descripcion}")
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        raise RuntimeError(f"Falló: {descripcion}\nDetalle técnico SAP: {exc!r}") from exc


# ---------------------------------------------------------------------------
# CONEXIÓN A SAP
# ---------------------------------------------------------------------------


def get_sap_session():
    """Devuelve la primera sesión de la primera conexión de SAP GUI.

    La app nunca inicia sesión: usa la que el usuario ya tiene abierta.

    Raises:
        RuntimeError: con un mensaje accionable si falta pywin32, SAP GUI
            no está abierto o sin scripting, o no hay conexión o sesión.
    """
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Falta la dependencia pywin32 (solo Windows). Instálala con: pip install pywin32"
        ) from exc

    try:
        sap_gui_auto = win32com.client.GetObject("SAPGUI")
        application = sap_gui_auto.GetScriptingEngine
    except Exception as exc:
        raise RuntimeError(
            "No se pudo conectar a SAP GUI. Verifica:\n"
            "  - SAP GUI for Windows está abierto y con sesión iniciada.\n"
            "  - SAP GUI Scripting está habilitado en las opciones del cliente.\n"
            "  - sapgui/user_scripting = TRUE en el servidor SAP."
        ) from exc

    if application.Children.Count == 0:
        raise RuntimeError("SAP GUI está abierto pero no hay conexiones activas.")
    connection = application.Children(0)
    if connection.Children.Count == 0:
        raise RuntimeError("No hay sesiones activas. Inicia sesión en SAP y vuelve a intentarlo.")
    return connection.Children(0)


@contextlib.contextmanager
def com_apartment() -> Iterator[None]:
    """Inicializa el apartamento COM del thread actual y lo libera al salir.

    Obligatorio en todo worker que hable con SAP: sin `CoInitialize()`,
    `GetObject("SAPGUI")` falla en threads secundarios con un error
    genérico aunque SAP esté abierto. No hace nada si no hay `pythoncom`
    (macOS/Linux).
    """
    try:
        import pythoncom  # type: ignore[import-not-found]
    except ImportError:
        yield
        return

    hilo = threading.get_ident()
    pythoncom.CoInitialize()
    log(f"COM inicializado (thread={hilo})")
    try:
        yield
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception as exc:
            # Best-effort: un fallo al liberar no debe tapar el resultado
            # (o el error) del flujo que corrió dentro.
            log(f"CoUninitialize falló (ignorado): {exc!r}")


# Reintentos para abrir el portapapeles: Windows lo bloquea mientras otro
# programa (p. ej. un gestor de portapapeles) lo está leyendo.
PORTAPAPELES_REINTENTOS = 5
PORTAPAPELES_ESPERA_SEG = 0.2


def copiar_al_portapapeles(texto: str) -> None:
    """Deja `texto` en el portapapeles de Windows (reemplaza lo que hubiera).

    SAP carga las listas de la selección múltiple desde el portapapeles
    ("Cargar desde portapapeles"), así que es la forma de pasarle muchos
    valores sin escribirlos fila por fila.
    """
    try:
        import win32clipboard  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "Falta la dependencia pywin32 (solo Windows). Instálala con: pip install pywin32"
        ) from exc

    for intento in range(1, PORTAPAPELES_REINTENTOS + 1):
        try:
            win32clipboard.OpenClipboard()
            break
        except Exception as exc:
            if intento == PORTAPAPELES_REINTENTOS:
                raise RuntimeError(
                    "No se pudo usar el portapapeles: otro programa lo tiene ocupado. "
                    "Cierra los programas que lo estén usando y vuelve a intentarlo."
                ) from exc
            time.sleep(PORTAPAPELES_ESPERA_SEG)
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(texto, win32clipboard.CF_UNICODETEXT)
    finally:
        win32clipboard.CloseClipboard()


# ---------------------------------------------------------------------------
# PASOS DE SAP COMPARTIDOS
# ---------------------------------------------------------------------------

# IDs tomados de las grabaciones de resources/grabaciones/. Los que salen
# de un solo script lo indican.
ID_VENTANA_PRINCIPAL = "wnd[0]"
ID_VENTANA_DIALOGO = "wnd[1]"
ID_CAMPO_COMANDO = "wnd[0]/tbar[0]/okcd"
ID_BTN_EJECUTAR = "wnd[0]/tbar[1]/btn[8]"
VKEY_ENTER = 0
VKEY_F4 = 4

# Ventana de selección múltiple (FBL1N.vbs: acreedores y sociedades).
ID_SELMULT_PRIMER_VALOR = (
    "wnd[1]/usr/tabsTAB_STRIP/tabpSIVA/ssubSCREEN_HEADER:SAPLALDB:3010"
    "/tblSAPLALDBSINGLE/ctxtRSCSEL_255-SLOW_I[1,0]"
)
ID_SELMULT_BORRAR_TODO = "wnd[1]/tbar[0]/btn[16]"
ID_SELMULT_PEGAR = "wnd[1]/tbar[0]/btn[24]"
ID_SELMULT_ACEPTAR = "wnd[1]/tbar[0]/btn[8]"

# Calendario que abre F4 sobre un campo de fecha (FBL1N.vbs: fecha clave).
ID_CALENDARIO = "wnd[1]/usr/cntlCONTAINER/shellcont/shell"

# Diálogo "Seleccionar disposición" (FBL1N.vbs; también en FBL5N y FAGLL03).
ID_BTN_DISPOSICION = "wnd[0]/tbar[1]/btn[33]"
ID_GRILLA_DISPOSICIONES = (
    "wnd[1]/usr/ssubD0500_SUBSCREEN:SAPLSLVC_DIALOG:0501/cntlG51_CONTAINER/shellcont/shell"
)
COLUMNA_NOMBRE_DISPOSICION = "VARIANT"

# Exportar la lista a hoja de cálculo y diálogo de guardado.
ID_MENU_EXPORTAR = "wnd[0]/mbar/menu[0]/menu[3]/menu[1]"
ID_GUARDAR_CARPETA = "wnd[1]/usr/ctxtDY_PATH"
# No está en FBL1N.vbs, pero activos-propios-py lo usa en producción en
# este mismo SAP (extraer_activos_creados.CAMPO_DY_FILENAME).
ID_GUARDAR_NOMBRE = "wnd[1]/usr/ctxtDY_FILENAME"
ID_GUARDAR_GENERAR = "wnd[1]/tbar[0]/btn[0]"
# Ventana "Seleccionar formato de hoja de cálculo": en el equipo donde se
# grabó FBL1N no aparece (el formato quedó fijo), pero en otros sí puede.
# Las grabaciones viejas de FBL5N/FAGLL03 la aceptan con este botón.
ID_FORMATO_CONTINUAR = "wnd[1]/tbar[0]/btn[0]"


def existe_control(session, id_control: str) -> bool:
    """True si el control existe en pantalla (`findById` sin lanzar error)."""
    try:
        return session.findById(id_control, False) is not None
    except Exception:
        return False


def cargar_valor_unico(session, id_boton: str, valor: str) -> None:
    """Abre la selección múltiple de un campo y escribe `valor` en la
    primera fila de "Seleccionar valores individuales"."""
    ejecutar("Abrir la selección múltiple", lambda: session.findById(id_boton).press())

    def _escribir() -> None:
        session.findById(ID_SELMULT_PRIMER_VALOR).text = valor

    ejecutar(f"Escribir '{valor}' en la selección múltiple", _escribir)
    ejecutar("Aceptar la selección múltiple", lambda: session.findById(ID_SELMULT_ACEPTAR).press())


def pegar_seleccion_multiple(session, id_boton: str, valores: Iterable[str]) -> None:
    """Carga `valores` en la selección múltiple de un campo vía portapapeles.

    Borra primero toda la selección: el campo puede traer un valor por
    defecto del usuario (p. ej. su sociedad) que se sumaría a la lista.
    """
    lista = list(valores)
    copiar_al_portapapeles("\r\n".join(lista))
    log(f"  → {len(lista)} valor(es) copiados al portapapeles")
    ejecutar("Abrir la selección múltiple", lambda: session.findById(id_boton).press())
    ejecutar(
        "Borrar la selección anterior", lambda: session.findById(ID_SELMULT_BORRAR_TODO).press()
    )
    ejecutar("Cargar desde el portapapeles", lambda: session.findById(ID_SELMULT_PEGAR).press())
    ejecutar("Aceptar la selección múltiple", lambda: session.findById(ID_SELMULT_ACEPTAR).press())


def elegir_fecha_en_calendario(session, id_campo: str, fecha: date) -> None:
    """Abre el calendario (F4) del campo y elige `fecha`.

    Se usa el calendario y no se escribe el texto porque `selectionInterval`
    va en `AAAAMMDD`, sin depender del formato de fecha que cada usuario
    tenga configurado en SAP.
    """
    ejecutar("Ubicar el campo de fecha", lambda: session.findById(id_campo).setFocus())
    ejecutar(
        "Abrir el calendario (F4)",
        lambda: session.findById(ID_VENTANA_PRINCIPAL).sendVKey(VKEY_F4),
    )
    intervalo = f"{fecha:%Y%m%d},{fecha:%Y%m%d}"

    def _elegir() -> None:
        session.findById(ID_CALENDARIO).selectionInterval = intervalo

    ejecutar(f"Elegir {fecha:%d.%m.%Y} en el calendario", _elegir)


def ejecutar_reporte(session) -> None:
    """Pulsa Ejecutar (F8). Con muchos datos puede tardar varios minutos."""
    ejecutar("Ejecutar el reporte", lambda: session.findById(ID_BTN_EJECUTAR).press())


def elegir_disposicion(session, nombre: str) -> None:
    """Abre "Seleccionar disposición" y elige la de nombre `nombre`.

    Las grabaciones la eligen por número de fila, y esa fila cambia en
    cuanto alguien crea o borra una disposición. Aquí se recorre la lista
    buscando el nombre en la columna `VARIANT` (la columna por la que
    FBL1N.vbs ordena la lista).
    """
    buscado = nombre.strip().upper()
    if not buscado:
        raise ValueError("Falta el nombre de la disposición.")
    ejecutar(
        "Abrir 'Seleccionar disposición'",
        lambda: session.findById(ID_BTN_DISPOSICION).press(),
    )
    grilla = ejecutar(
        "Ubicar la lista de disposiciones",
        lambda: session.findById(ID_GRILLA_DISPOSICIONES),
    )
    fila, total = ejecutar(
        f"Buscar la disposición {buscado} en la lista",
        lambda: _buscar_fila(grilla, COLUMNA_NOMBRE_DISPOSICION, buscado),
    )
    if fila is None:
        # Best-effort: cerrar el diálogo para no dejar SAP con una ventana
        # modal abierta; el error que importa es el de abajo.
        with contextlib.suppress(Exception):
            session.findById(ID_VENTANA_DIALOGO).close()
        raise RuntimeError(
            f"No se encontró la disposición '{buscado}' entre las {total} disponibles. "
            "Verifica el nombre en SAP (botón 'Seleccionar disposición')."
        )

    def _elegir() -> None:
        grilla.currentCellRow = fila
        grilla.selectedRows = str(fila)
        grilla.clickCurrentCell()

    ejecutar(f"Elegir la disposición {buscado} (fila {fila})", _elegir)


def _buscar_fila(grilla, columna: str, buscado: str) -> tuple[int | None, int]:
    """Devuelve `(fila, total)` de la primera fila cuya `columna` vale
    `buscado` (sin distinguir mayúsculas), o `(None, total)`.

    La grilla de SAP carga las filas a medida que se desplaza: se mueve
    `firstVisibleRow` por bloques antes de leerlas.
    """
    total = int(grilla.RowCount)
    bloque = max(1, int(getattr(grilla, "VisibleRowCount", 0) or 1))
    for fila in range(total):
        if fila % bloque == 0:
            grilla.firstVisibleRow = fila
        valor = str(grilla.GetCellValue(fila, columna) or "")
        if valor.strip().upper() == buscado:
            return fila, total
    return None, total


def exportar_hoja_calculo(session, carpeta: Path, nombre_archivo: str) -> Path:
    """Exporta la lista a `carpeta/nombre_archivo` escribiendo la ruta y el
    nombre directamente en el diálogo de guardado (sin navegar con F4).

    Si antes aparece la ventana de formato, la acepta con el formato que
    tenga preseleccionado.
    """
    ejecutar(
        "Exportar a hoja de cálculo (menú Lista)",
        lambda: session.findById(ID_MENU_EXPORTAR).select(),
    )
    if not existe_control(session, ID_GUARDAR_CARPETA):
        log("  → apareció la ventana de formato; se acepta el formato preseleccionado")
        ejecutar(
            "Aceptar el formato de hoja de cálculo",
            lambda: session.findById(ID_FORMATO_CONTINUAR).press(),
        )
        if not existe_control(session, ID_GUARDAR_CARPETA):
            raise RuntimeError(
                "SAP no mostró la ventana para guardar el archivo después de exportar. "
                "Revisa en SAP qué ventana quedó abierta y avisa para ajustar la app."
            )

    def _escribir_ruta() -> None:
        session.findById(ID_GUARDAR_CARPETA).text = str(carpeta)
        session.findById(ID_GUARDAR_NOMBRE).text = nombre_archivo

    ejecutar(f"Escribir la ruta {carpeta} y el nombre {nombre_archivo}", _escribir_ruta)
    ejecutar("Guardar el archivo", lambda: session.findById(ID_GUARDAR_GENERAR).press())
    return carpeta / nombre_archivo


def volver_al_inicio(session) -> None:
    """Deja SAP en la pantalla inicial (`/n`). Best-effort: si falla, solo
    se registra, porque el archivo ya quedó guardado."""
    try:

        def _ir_al_inicio() -> None:
            session.findById(ID_CAMPO_COMANDO).text = "/n"
            session.findById(ID_VENTANA_PRINCIPAL).sendVKey(VKEY_ENTER)

        ejecutar("Volver a la pantalla inicial de SAP", _ir_al_inicio)
    except Exception as exc:
        log(f"No se pudo volver a la pantalla inicial (ignorado): {exc}")


def terminar_exportacion(session, archivo: Path, timeout_seg: float) -> None:
    """Espera a que SAP termine de escribir `archivo` y deja SAP en la
    pantalla inicial. Lanza `RuntimeError` si el archivo no aparece."""
    if not esperar_archivo_listo(archivo, timeout_seg=timeout_seg):
        raise RuntimeError(
            f"SAP no terminó de guardar {archivo.name} en {archivo.parent} "
            f"después de {timeout_seg:.0f} s. Revisa si quedó abierta alguna "
            "ventana en SAP."
        )
    volver_al_inicio(session)


def abrir_transaccion(session, transaccion: str) -> None:
    """Maximiza la ventana y abre `transaccion` desde cero.

    Las grabaciones escriben el código sin `/n` (p. ej. "fbl1n"), lo que
    falla si el usuario está dentro de otra transacción. Con `/n` siempre
    arranca limpia, desde cualquier pantalla.
    """
    codigo = transaccion.strip().upper()
    if not codigo:
        raise ValueError("Falta el código de la transacción.")
    ejecutar(
        "Maximizar la ventana de SAP", lambda: session.findById(ID_VENTANA_PRINCIPAL).maximize()
    )

    def _escribir_y_enter() -> None:
        session.findById(ID_CAMPO_COMANDO).text = f"/n{codigo}"
        session.findById(ID_VENTANA_PRINCIPAL).sendVKey(VKEY_ENTER)

    ejecutar(f"Abrir la transacción {codigo}", _escribir_y_enter)


# ---------------------------------------------------------------------------
# ARCHIVOS
# ---------------------------------------------------------------------------


def nombre_con_timestamp(
    prefijo: str, extension: str = "xlsx", ahora: datetime | None = None
) -> str:
    """`Prefijo_YYYYMMDD_HHMMSS.ext`, el formato de los archivos intermedios."""
    momento = ahora or datetime.now()
    return f"{prefijo}_{momento:%Y%m%d_%H%M%S}.{extension.lstrip('.')}"


def buscar_ultimo_export(prefijo: str, carpeta: Path) -> Path | None:
    """El `prefijo_AAAAMMDD_HHMMSS.xlsx` más reciente de `carpeta`, o `None`.

    El timestamp del nombre hace que el orden alfabético sea el cronológico.
    """
    if not carpeta.is_dir():
        return None
    archivos = sorted(carpeta.glob(f"{prefijo}_????????_??????.xlsx"))
    return archivos[-1] if archivos else None


def archivo_esta_bloqueado(archivo: Path) -> bool:
    """True si otro proceso (típicamente Excel) tiene el archivo abierto.

    Abre en `r+b`, que en Windows exige un acceso que Excel bloquea. Si el
    archivo no existe, no está bloqueado. Se llama ANTES de un flujo largo
    para no descubrir el problema al final.
    """
    if not archivo.exists():
        return False
    try:
        with open(archivo, "r+b"):
            pass
        return False
    except OSError:
        return True


def guardar_workbook_seguro(wb, archivo: Path) -> None:
    """`wb.save(archivo)`, pero con un mensaje accionable si Excel lo tiene
    abierto (sin esto el usuario ve un `[Errno 13] Permission denied`)."""
    try:
        wb.save(archivo)
    except PermissionError as exc:
        raise PermissionError(
            f"No se pudo guardar {archivo.name}: el archivo está abierto en Excel "
            f"(u otro programa lo está usando). Ciérralo y vuelve a intentarlo.\n\n"
            f"Ruta: {archivo}"
        ) from exc


def esperar_archivo_listo(archivo: Path, timeout_seg: float = 10.0, poll_seg: float = 0.5) -> bool:
    """Espera a que `archivo` exista y su tamaño deje de cambiar.

    SAP cierra el archivo exportado de forma asíncrona (tarda 1–3 s);
    abrirlo antes da archivos truncados o bloqueados. Devuelve False si no
    quedó listo dentro del timeout.
    """
    inicio = time.monotonic()
    tamano_previo = -1
    while time.monotonic() - inicio < timeout_seg:
        if archivo.exists():
            tamano = archivo.stat().st_size
            if tamano > 0 and tamano == tamano_previo:
                return True
            tamano_previo = tamano
        time.sleep(poll_seg)
    return False
