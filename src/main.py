"""main.py — GUI de Partidas Abiertas (Tkinter).

Una sola ventana. El menú principal muestra una card por cada transacción
del proceso, en el orden en que se usan:

1. Acreedores (FBL1N) y 2. Deudores (FBL5N): partidas abiertas por sociedad.
3. Maestro de cuentas (Y_FI_GRL_004): identifica las cuentas con gestión
   de partidas abiertas.
4. Partidas de mayor (FAGLL03): partidas abiertas de esas cuentas.

Cada opción entrega el archivo original que exporta SAP en `salida/`.

Cada card abre su vista en la misma ventana (frame switching, nunca
`Toplevel`); "← Atrás" destruye la vista y vuelve a mostrar el menú.

USO
===
    python src/main.py
"""

from __future__ import annotations

import threading
import tkinter as tk
import traceback
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox
from typing import NamedTuple

from tkcalendar import DateEntry

import branding
from comun import (
    SOCIEDADES,
    TITULAR,
    TITULO_APP,
    com_apartment,
    configurar_logging,
    log,
    logger,
    validar_fecha_clave,
    validar_sociedades,
)

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

# El layout está calculado en píxeles para este tamaño (ventana fija).
TAMANO_VENTANA = "620x605"
# Todas las cards del menú miden lo mismo aunque sus textos tengan
# distinto largo (pack_propagate(False)).
_CARD_W, _CARD_H = 250, 170
# Casillas de sociedades por fila en las vistas (28 sociedades → 4 filas).
_COLUMNAS_SOCIEDADES = 7


class Opcion(NamedTuple):
    """Una opción del menú principal y su vista."""

    clave: str  # identificador interno (clave en `frame_menu.botones`)
    titulo: str  # título de la card y de la vista
    transaccion: str  # transacción de SAP (y nombre de su grabación .vbs)
    descripcion: str  # texto de la card
    subtitulo: str  # subtítulo de la vista
    estilo: str  # estilo del botón de la card (ver branding._BUTTON_STYLES)


# En el orden del proceso: el maestro de cuentas (3) alimenta a FAGLL03 (4).
OPCIONES: tuple[Opcion, ...] = (
    Opcion(
        clave="acreedores",
        titulo="Acreedores",
        transaccion="FBL1N",
        descripcion="Descarga las partidas abiertas\nde proveedores por sociedad.",
        subtitulo="Partidas abiertas de acreedores (FBL1N)",
        estilo="primary",
    ),
    Opcion(
        clave="deudores",
        titulo="Deudores",
        transaccion="FBL5N",
        descripcion="Descarga las partidas abiertas\nde clientes por sociedad.",
        subtitulo="Partidas abiertas de deudores (FBL5N)",
        estilo="primary",
    ),
    Opcion(
        clave="maestro_cuentas",
        titulo="Maestro de cuentas",
        transaccion="Y_FI_GRL_004",
        descripcion="Lista el plan de cuentas e identifica\nlas cuentas con partidas abiertas.",
        subtitulo="Plan de cuentas por sociedad (Y_FI_GRL_004)",
        estilo="acento",
    ),
    Opcion(
        clave="partidas_mayor",
        titulo="Partidas de mayor",
        transaccion="FAGLL03",
        descripcion="Descarga las partidas abiertas\nde las cuentas de mayor.",
        subtitulo="Partidas abiertas de cuentas de mayor (FAGLL03)",
        estilo="ok",
    ),
)


# ---------------------------------------------------------------------------
# ERRORES Y ARRANQUE
# ---------------------------------------------------------------------------


def _show_unexpected_error(title: str, exc: BaseException) -> None:
    """Red de seguridad para errores que ningún `except` específico
    capturó: el traceback va al log y el usuario lo ve en pantalla (con
    doble clic no hay consola)."""
    tb_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("%s: %s", title, exc, exc_info=(type(exc), exc, exc.__traceback__))
    messagebox.showerror(
        title, f"{type(exc).__name__}: {exc}\n\n--- Detalle técnico ---\n{tb_text}"
    )


def _install_tk_exception_handler(root: tk.Tk) -> None:
    """Reemplaza el handler de Tkinter (que solo imprime a stderr) por uno
    que registra el error y lo muestra en un diálogo. Sin esto, un error en
    un callback es invisible para quien abre la app con doble clic."""

    def handler(exc_type, exc_value, tb) -> None:
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, tb))
        logger.error("Error no manejado en un callback de Tk", exc_info=(exc_type, exc_value, tb))
        messagebox.showerror(
            "Error inesperado",
            f"{exc_type.__name__}: {exc_value}\n\n--- Detalle técnico ---\n{tb_text}",
        )

    root.report_callback_exception = handler


def _cerrar_splash() -> None:
    """Cierra el splash de PyInstaller si la app corre empaquetada.

    `pyi_splash` solo existe cuando el `.spec` incluye un `Splash(...)` y
    la app corre como `.exe`; en dev (y en macOS, donde no hay splash) el
    import falla y no hay nada que cerrar.
    """
    try:
        import pyi_splash  # type: ignore[import-not-found]
    except ImportError:
        return
    try:
        if pyi_splash.is_alive():
            pyi_splash.close()
    except Exception as exc:
        # Un fallo del splash nunca debe impedir que la app arranque.
        log(f"No se pudo cerrar el splash (ignorado): {exc!r}")


# ---------------------------------------------------------------------------
# PIEZAS VISUALES
# ---------------------------------------------------------------------------


def _crear_footer_copyright(parent: tk.Misc) -> tk.Label:
    """Footer con el copyright del año actual.

    Se empaqueta UNA vez sobre `root` con `side="bottom"` y ANTES que
    cualquier vista: así reclama la franja inferior y sigue visible en
    todas las vistas, que se montan encima con `fill="both", expand=True`.
    """
    footer = tk.Label(
        parent,
        text=f"© {datetime.now().year} {TITULAR} · Todos los derechos reservados",
        font=("Helvetica", 8),
        fg=branding.COLOR_GRIS_CLARO,
        bg=branding.COLOR_FONDO,
    )
    footer.pack(side="bottom", pady=(0, 6))
    return footer


def _crear_card_visual(
    parent: tk.Misc,
    *,
    titulo: str,
    etiqueta: str | None,
    descripcion: str,
    btn_texto: str,
    btn_style: str,
    command: Callable[[], object] | None = None,
    disabled: bool = False,
    width: int | None = None,
    height: int | None = None,
) -> tuple[tk.Frame, branding.RoundedButton]:
    """Card del menú principal: título, etiqueta (la transacción),
    descripción y botón, con borde plano de 1 px.

    Con `width` y `height` la card se fuerza a ese tamaño exacto. No se
    empaqueta: quien llama decide el layout.

    Returns:
        `(card, boton)`; el botón se expone para tests y para cambiar su
        estado después.
    """
    card = tk.Frame(
        parent,
        bg=branding.COLOR_BLANCO,
        highlightthickness=1,
        highlightbackground=branding.COLOR_GRIS_BORDE,
        bd=0,
    )
    if width is not None and height is not None:
        card.configure(width=width, height=height)
        card.pack_propagate(False)

    tk.Label(
        card,
        text=titulo,
        font=("Helvetica", 12, "bold"),
        fg=branding.COLOR_PRIMARIO,
        bg=branding.COLOR_BLANCO,
    ).pack(pady=(14, 0), padx=12)

    if etiqueta:
        tk.Label(
            card,
            text=etiqueta,
            font=("Helvetica", 9, "bold"),
            fg=branding.COLOR_ACENTO,
            bg=branding.COLOR_BLANCO,
        ).pack(pady=(2, 6), padx=12)

    tk.Label(
        card,
        text=descripcion,
        font=("Helvetica", 9),
        fg=branding.COLOR_GRIS,
        bg=branding.COLOR_BLANCO,
        justify="center",
    ).pack(pady=(0, 12), padx=12)

    boton = branding.RoundedButton(
        card,
        text=btn_texto,
        style=btn_style,
        padx=12,
        pady=6,
        width=170,
        font=("Helvetica", 10, "bold"),
        command=command,
    )
    if disabled:
        boton.config(state="disabled")
    boton.pack(pady=(0, 14), padx=12)

    return card, boton


def _crear_panel_card(parent: tk.Misc) -> tk.Frame:
    """Contenedor blanco con borde de 1 px para el contenido de una vista
    (mismo lenguaje visual que las cards del menú)."""
    panel = tk.Frame(
        parent,
        bg=branding.COLOR_BLANCO,
        highlightthickness=1,
        highlightbackground=branding.COLOR_GRIS_BORDE,
        bd=0,
    )
    panel.pack(pady=(4, 8), padx=20)
    return panel


def _crear_header_form(
    root: tk.Tk,
    frame: tk.Frame,
    parent_frame: tk.Frame,
    titulo: str,
    subtitulo: str | None = None,
) -> branding.RoundedButton:
    """Encabezado de toda vista: "← Atrás", logo, título y subtítulo.

    Devuelve el botón Atrás (ya cableado: destruye `frame` y vuelve a
    mostrar `parent_frame`) para que los handlers lo deshabiliten mientras
    corre un flujo.
    """
    btn_atras = branding.RoundedButton(
        frame, text="← Atrás", style="tertiary", font=("Helvetica", 9), padx=8, pady=2
    )
    btn_atras.pack(anchor="w", padx=10, pady=(10, 0))

    def volver() -> None:
        frame.destroy()
        parent_frame.pack(fill="both", expand=True)

    btn_atras.config(command=volver)

    if getattr(root, "_logo_ref", None) is not None:
        tk.Label(frame, image=root._logo_ref, bg=branding.COLOR_FONDO).pack(pady=(4, 6))

    tk.Label(
        frame,
        text=titulo,
        font=("Helvetica", 14, "bold"),
        fg=branding.COLOR_PRIMARIO,
        bg=branding.COLOR_FONDO,
    ).pack(pady=(4, 4))

    if subtitulo is not None:
        tk.Label(
            frame,
            text=subtitulo,
            font=("Helvetica", 10),
            fg=branding.COLOR_GRIS,
            bg=branding.COLOR_FONDO,
        ).pack(pady=(0, 12))

    return btn_atras


def _crear_selector_sociedades(
    parent: tk.Misc,
) -> tuple[dict[str, tk.BooleanVar], branding.RoundedButton, branding.RoundedButton]:
    """Casillas con las sociedades del catálogo (todas marcadas) y los
    botones "Todas" / "Ninguna".

    Returns:
        `(variables, btn_todas, btn_ninguna)`; `variables` va de sociedad a
        su `BooleanVar`.
    """
    variables = {s: tk.BooleanVar(master=parent, value=True) for s in SOCIEDADES}

    def marcar(valor: bool) -> None:
        for var in variables.values():
            var.set(valor)

    cabecera = tk.Frame(parent, bg=branding.COLOR_BLANCO)
    cabecera.pack(fill="x", padx=16, pady=(14, 4))
    tk.Label(
        cabecera,
        text="Sociedades",
        font=("Helvetica", 10, "bold"),
        fg=branding.COLOR_PRIMARIO,
        bg=branding.COLOR_BLANCO,
    ).pack(side="left")
    btn_ninguna = branding.RoundedButton(
        cabecera, text="Ninguna", style="tertiary", padx=6, pady=1, command=lambda: marcar(False)
    )
    btn_ninguna.pack(side="right")
    btn_todas = branding.RoundedButton(
        cabecera, text="Todas", style="tertiary", padx=6, pady=1, command=lambda: marcar(True)
    )
    btn_todas.pack(side="right")

    casillas = tk.Frame(parent, bg=branding.COLOR_BLANCO)
    casillas.pack(padx=16)
    for indice, sociedad in enumerate(SOCIEDADES):
        tk.Checkbutton(
            casillas,
            text=sociedad,
            variable=variables[sociedad],
            font=("Helvetica", 9),
            fg=branding.COLOR_GRIS,
            bg=branding.COLOR_BLANCO,
            activebackground=branding.COLOR_BLANCO,
            highlightthickness=0,
            anchor="w",
            width=6,
        ).grid(
            row=indice // _COLUMNAS_SOCIEDADES,
            column=indice % _COLUMNAS_SOCIEDADES,
            sticky="w",
            padx=2,
        )
    return variables, btn_todas, btn_ninguna


def _sociedades_marcadas(variables: dict[str, tk.BooleanVar]) -> list[str]:
    return [s for s, var in variables.items() if var.get()]


# ---------------------------------------------------------------------------
# HANDLERS
# ---------------------------------------------------------------------------


def _descargar_fbl1n_handler(
    root: tk.Tk,
    sociedades: list[str],
    fecha_clave: date,
    status_var: tk.StringVar,
    button: tk.Widget,
    btn_atras: tk.Widget,
) -> None:
    """Valida, confirma y descarga FBL1N en un thread (la GUI no se congela).

    Acción y Atrás quedan deshabilitados mientras corre: salir a mitad de
    la descarga dejaría SAP en una pantalla intermedia.
    """
    try:
        import fbl1n
    except ImportError as exc:
        messagebox.showerror("Error de import", f"No se pudo importar fbl1n:\n{exc}")
        return
    try:
        socs = validar_sociedades(sociedades)
        fecha = validar_fecha_clave(fecha_clave)
        fbl1n.validar_disposicion()
    except ValueError as exc:
        messagebox.showerror("Datos inválidos", str(exc))
        return

    if len(socs) == len(SOCIEDADES):
        texto_sociedades = f"todas las sociedades ({len(socs)})"
    else:
        texto_sociedades = f"{len(socs)} sociedad(es): {', '.join(socs)}"
    if not messagebox.askyesno(
        "Confirmar descarga de FBL1N",
        f"Se descargará FBL1N de {texto_sociedades}, con fecha clave {fecha:%d.%m.%Y}.\n\n"
        "La app usa el portapapeles: se reemplazará lo que tengas copiado.\n"
        "Ten SAP abierto y no lo uses mientras corre la descarga.\n\n"
        "¿Continuar?",
    ):
        return

    button.config(state="disabled")
    btn_atras.config(state="disabled")
    status_var.set("Conectando con SAP…")

    def progreso(texto: str) -> None:
        root.after(0, lambda: status_var.set(texto))

    def show_info(title: str, msg: str) -> None:
        root.after(0, lambda: messagebox.showinfo(title, msg))

    def show_error(title: str, msg: str) -> None:
        root.after(0, lambda: messagebox.showerror(title, msg))

    def reenable() -> None:
        def _do() -> None:
            button.config(state="normal")
            btn_atras.config(state="normal")
            status_var.set("")

        root.after(0, _do)

    def worker() -> None:
        with com_apartment():
            try:
                session = fbl1n.get_sap_session()
                carpeta, nombre = fbl1n.descargar_fbl1n(session, socs, fecha, progreso=progreso)
                show_info("Descarga completada", f"Archivo guardado en:\n{Path(carpeta) / nombre}")
            except Exception as exc:
                logger.exception("Falló la descarga de FBL1N")
                show_error("Error en la descarga de FBL1N", str(exc))
            finally:
                reenable()

    threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------------
# VISTAS
# ---------------------------------------------------------------------------


def _crear_vista_pendiente(root: tk.Tk, parent_frame: tk.Frame, opcion: Opcion) -> tk.Frame:
    """Vista con el encabezado estándar y un aviso de que la opción aún no
    está conectada a SAP.

    Cada `abrir_*` la reemplaza por su formulario real en la Fase 3,
    cuando estén las grabaciones nuevas de su transacción.
    """
    parent_frame.pack_forget()
    frame = tk.Frame(root, bg=branding.COLOR_FONDO)
    btn_atras = _crear_header_form(
        root, frame, parent_frame, titulo=opcion.titulo, subtitulo=opcion.subtitulo
    )

    panel = _crear_panel_card(frame)
    lbl_pendiente = tk.Label(
        panel,
        text=(
            "Esta opción todavía no está conectada a SAP.\n"
            f"Se habilita cuando estén las nuevas grabaciones de {opcion.transaccion}."
        ),
        font=("Helvetica", 10),
        fg=branding.COLOR_GRIS,
        bg=branding.COLOR_BLANCO,
        justify="center",
        wraplength=420,
    )
    lbl_pendiente.pack(padx=24, pady=24)

    frame.pack(fill="both", expand=True)
    # Exponer widgets para los tests.
    frame.opcion = opcion
    frame.btn_atras = btn_atras
    frame.lbl_pendiente = lbl_pendiente
    return frame


def _opcion(clave: str) -> Opcion:
    return next(o for o in OPCIONES if o.clave == clave)


def abrir_acreedores(root: tk.Tk, parent_frame: tk.Frame) -> tk.Frame:
    """Vista de FBL1N: sociedades, fecha clave y "Descargar FBL1N".

    Entrega el archivo tal como lo exporta SAP en `salida/`.
    """
    opcion = _opcion("acreedores")
    parent_frame.pack_forget()
    frame = tk.Frame(root, bg=branding.COLOR_FONDO)
    btn_atras = _crear_header_form(
        root, frame, parent_frame, titulo=opcion.titulo, subtitulo=opcion.subtitulo
    )

    panel = _crear_panel_card(frame)
    vars_sociedades, btn_todas, btn_ninguna = _crear_selector_sociedades(panel)

    fila_fecha = tk.Frame(panel, bg=branding.COLOR_BLANCO)
    fila_fecha.pack(pady=(12, 4))
    tk.Label(
        fila_fecha,
        text="Fecha clave",
        font=("Helvetica", 10, "bold"),
        fg=branding.COLOR_PRIMARIO,
        bg=branding.COLOR_BLANCO,
    ).pack(side="left", padx=(0, 8))
    # Sin validate="key": en un DateEntry rompe la selección desde el
    # calendario (bug real en activos-propios-py).
    entry_fecha = DateEntry(fila_fecha, date_pattern="dd.mm.yyyy", locale="es_CO", width=12)
    entry_fecha.pack(side="left")

    status_var = tk.StringVar(master=frame, value="")
    btn_descargar = branding.RoundedButton(
        panel, text="Descargar FBL1N", style="primary", width=220
    )
    btn_descargar.config(
        command=lambda: _descargar_fbl1n_handler(
            root,
            _sociedades_marcadas(vars_sociedades),
            entry_fecha.get_date(),
            status_var,
            btn_descargar,
            btn_atras,
        )
    )
    btn_descargar.pack(pady=(12, 16))

    tk.Label(
        frame,
        textvariable=status_var,
        font=("Helvetica", 10),
        fg=branding.COLOR_PRIMARIO,
        bg=branding.COLOR_FONDO,
        wraplength=480,
    ).pack(pady=(4, 0))

    frame.pack(fill="both", expand=True)
    # Exponer widgets para los tests.
    frame.opcion = opcion
    frame.btn_atras = btn_atras
    frame.vars_sociedades = vars_sociedades
    frame.btn_todas = btn_todas
    frame.btn_ninguna = btn_ninguna
    frame.entry_fecha = entry_fecha
    frame.btn_descargar = btn_descargar
    frame.status_var = status_var
    return frame


def abrir_deudores(root: tk.Tk, parent_frame: tk.Frame) -> tk.Frame:
    """Vista de FBL5N (partidas abiertas de deudores)."""
    return _crear_vista_pendiente(root, parent_frame, _opcion("deudores"))


def abrir_maestro_cuentas(root: tk.Tk, parent_frame: tk.Frame) -> tk.Frame:
    """Vista de Y_FI_GRL_004 (maestro del plan de cuentas)."""
    return _crear_vista_pendiente(root, parent_frame, _opcion("maestro_cuentas"))


def abrir_partidas_mayor(root: tk.Tk, parent_frame: tk.Frame) -> tk.Frame:
    """Vista de FAGLL03 (partidas abiertas de cuentas de mayor)."""
    return _crear_vista_pendiente(root, parent_frame, _opcion("partidas_mayor"))


# Qué vista abre cada card del menú.
VISTAS: dict[str, Callable[[tk.Tk, tk.Frame], tk.Frame]] = {
    "acreedores": abrir_acreedores,
    "deudores": abrir_deudores,
    "maestro_cuentas": abrir_maestro_cuentas,
    "partidas_mayor": abrir_partidas_mayor,
}


# ---------------------------------------------------------------------------
# MENÚ PRINCIPAL Y ARRANQUE
# ---------------------------------------------------------------------------


def construir_menu(root: tk.Tk) -> tk.Frame:
    """Crea el menú principal (logo, título y las 4 cards en 2×2) sin
    empaquetarlo. Expone `frame_menu.botones` (clave → botón) para tests."""
    frame_menu = tk.Frame(root, bg=branding.COLOR_FONDO)

    if getattr(root, "_logo_ref", None) is not None:
        tk.Label(frame_menu, image=root._logo_ref, bg=branding.COLOR_FONDO).pack(pady=(18, 6))

    tk.Label(
        frame_menu,
        text=TITULO_APP,
        font=("Helvetica", 16, "bold"),
        fg=branding.COLOR_PRIMARIO,
        bg=branding.COLOR_FONDO,
    ).pack(pady=(4, 2))
    tk.Label(
        frame_menu,
        text="Descarga y análisis de partidas abiertas desde SAP",
        font=("Helvetica", 10),
        fg=branding.COLOR_GRIS,
        bg=branding.COLOR_FONDO,
    ).pack(pady=(0, 14))

    cuadricula = tk.Frame(frame_menu, bg=branding.COLOR_FONDO)
    cuadricula.pack()

    botones: dict[str, branding.RoundedButton] = {}
    for indice, opcion in enumerate(OPCIONES):
        abrir = VISTAS[opcion.clave]
        card, boton = _crear_card_visual(
            cuadricula,
            titulo=opcion.titulo,
            etiqueta=opcion.transaccion,
            descripcion=opcion.descripcion,
            btn_texto="Abrir  →",
            btn_style=opcion.estilo,
            width=_CARD_W,
            height=_CARD_H,
            command=lambda abrir=abrir: abrir(root, frame_menu),
        )
        card.grid(row=indice // 2, column=indice % 2, padx=8, pady=6)
        botones[opcion.clave] = boton

    frame_menu.botones = botones
    return frame_menu


def crear_app() -> tk.Tk:
    """Crea la ventana con el footer y el menú ya empaquetados.

    Separada de `main()` para poder probarla sin entrar al `mainloop`.
    """
    root = tk.Tk()
    _install_tk_exception_handler(root)
    root.title(TITULO_APP)
    root.geometry(TAMANO_VENTANA)
    root.resizable(False, False)
    root.configure(bg=branding.COLOR_FONDO)

    # El footer va PRIMERO para que quede abajo en todas las vistas.
    _crear_footer_copyright(root)

    # La referencia se guarda en root: si se pierde, el GC libera la imagen
    # y Tk muestra un cuadro vacío. Las vistas la reutilizan.
    root._logo_ref = branding.cargar_logo()

    frame_menu = construir_menu(root)
    frame_menu.pack(fill="both", expand=True)
    root.frame_menu = frame_menu
    return root


def main() -> None:
    archivo_log = configurar_logging()
    log(f"Iniciando {TITULO_APP}" + (f" — log en {archivo_log}" if archivo_log else ""))

    root = crear_app()
    # El splash se cierra justo cuando la ventana está lista para verse.
    root.update_idletasks()
    _cerrar_splash()
    root.mainloop()


if __name__ == "__main__":
    main()
