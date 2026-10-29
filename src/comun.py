"""Piezas compartidas por la GUI y los módulos de flujo.

En `activos-propios-py`, `_log`, `_ejecutar` y `get_sap_session` estaban
copiados en cada flujo, y el título de la ventana vivía en dos constantes
distintas (eso rompió el minimizado antes de las capturas). Aquí viven una
sola vez:

- Identidad de la app (`TITULO_APP`, `TITULAR`).
- Logging a consola y a `salida/logs/app.log`.
- `ejecutar()`: traduce los errores COM (suelen venir vacíos) a mensajes
  que dicen qué paso falló.
- Conexión a SAP GUI Scripting y apartamento COM por thread.
- Pasos de SAP que comparten los 4 flujos.
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
from collections.abc import Callable, Iterator
from datetime import datetime
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


# ---------------------------------------------------------------------------
# PASOS DE SAP COMPARTIDOS
# ---------------------------------------------------------------------------

# IDs tomados de las grabaciones de resources/grabaciones/ (comunes a las 4).
ID_VENTANA_PRINCIPAL = "wnd[0]"
ID_CAMPO_COMANDO = "wnd[0]/tbar[0]/okcd"
VKEY_ENTER = 0


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
