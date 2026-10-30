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

import importlib
import threading
import tkinter as tk
import traceback
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import NamedTuple

from tkcalendar import DateEntry

import branding
import sociedades as catalogo_sociedades
from comun import (
    TITULAR,
    TITULO_APP,
    SinResultadosError,
    buscar_ultimo_export,
    com_apartment,
    configurar_logging,
    log,
    logger,
    validar_fecha_clave,
    validar_sociedades,
)
from paths import SALIDA_DIR

# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

# El layout está calculado en píxeles para este tamaño (ventana fija).
TAMANO_VENTANA = "620x605"
# Todas las cards del menú miden lo mismo aunque sus textos tengan
# distinto largo (pack_propagate(False)).
_CARD_W, _CARD_H = 250, 170
# Casillas de sociedades por fila en las vistas (24 sociedades → 4 filas).
_COLUMNAS_SOCIEDADES = 7
# A partir de aquí las casillas van en un área con barra de desplazamiento,
# para que la vista siga cabiendo en la ventana fija.
_FILAS_SIN_DESPLAZAMIENTO = 6
_ALTO_FILA_CASILLA = 24


class Opcion(NamedTuple):
    """Una opción del menú principal y su vista."""

    clave: str  # identificador interno (clave en `frame_menu.botones`)
    titulo: str  # título de la card y de la vista
    transaccion: str  # transacción de SAP (y nombre de su grabación .vbs)
    descripcion: str  # texto de la card
    subtitulo: str  # subtítulo de la vista
    estilo: str  # estilo del botón de la card (ver branding._BUTTON_STYLES)
    # Módulo de flujo que hace la descarga. Debe cumplir el contrato:
    # validar_configuracion(), get_sap_session() y
    # descargar(session, sociedades, [fecha_clave=...], progreso=...).
    modulo: str
    usa_fecha_clave: bool = False  # si la vista pide fecha clave
    # Clave de la opción cuyo export necesita esta (FAGLL03 toma las cuentas
    # del maestro). La vista muestra qué archivo usará.
    requiere: str | None = None


# En el orden del proceso: el maestro de cuentas (3) alimenta a FAGLL03 (4).
OPCIONES: tuple[Opcion, ...] = (
    Opcion(
        clave="acreedores",
        titulo="Acreedores",
        transaccion="FBL1N",
        descripcion="Descarga las partidas abiertas\nde proveedores por sociedad.",
        subtitulo="Partidas abiertas de acreedores (FBL1N)",
        estilo="primary",
        modulo="fbl1n",
        usa_fecha_clave=True,
    ),
    Opcion(
        clave="deudores",
        titulo="Deudores",
        transaccion="FBL5N",
        descripcion="Descarga las partidas abiertas\nde clientes por sociedad.",
        subtitulo="Partidas abiertas de deudores (FBL5N)",
        estilo="primary",
        modulo="fbl5n",
        usa_fecha_clave=True,
    ),
    Opcion(
        clave="maestro_cuentas",
        titulo="Maestro de cuentas",
        transaccion="Y_FI_GRL_004",
        descripcion="Lista el plan de cuentas e identifica\nlas cuentas con partidas abiertas.",
        subtitulo="Plan de cuentas por sociedad (Y_FI_GRL_004)",
        estilo="acento",
        modulo="y_fi_grl_004",
    ),
    Opcion(
        clave="partidas_mayor",
        titulo="Partidas de mayor",
        transaccion="FAGLL03",
        descripcion="Descarga las partidas abiertas\nde las cuentas de mayor.",
        subtitulo="Partidas abiertas de cuentas de mayor (FAGLL03)",
        estilo="ok",
        modulo="fagll03",
        usa_fecha_clave=True,
        requiere="maestro_cuentas",
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
    al_volver: Callable[[], object] | None = None,
) -> branding.RoundedButton:
    """Encabezado de toda vista: "← Atrás", logo, título y subtítulo.

    Devuelve el botón Atrás (ya cableado: destruye `frame` y vuelve a
    mostrar `parent_frame`) para que los handlers lo deshabiliten mientras
    corre un flujo. `al_volver` corre después de volver (p. ej. para que la
    vista de descarga relea la lista de sociedades).
    """
    btn_atras = branding.RoundedButton(
        frame, text="← Atrás", style="tertiary", font=("Helvetica", 9), padx=8, pady=2
    )
    btn_atras.pack(anchor="w", padx=10, pady=(10, 0))

    def volver() -> None:
        frame.destroy()
        parent_frame.pack(fill="both", expand=True)
        if al_volver is not None:
            al_volver()

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


class SelectorSociedades:
    """Casillas con la lista de sociedades del usuario y los botones
    "Todas", "Ninguna" y "Editar lista".

    La lista se lee del archivo al crearse y en cada `recargar()` (p. ej. al
    volver de la vista "Sociedades"). Si el archivo no se puede leer, muestra
    el error en lugar de las casillas y `valido` queda en False.
    """

    def __init__(self, parent: tk.Misc, al_editar: Callable[[], object]) -> None:
        self.variables: dict[str, tk.BooleanVar] = {}
        self.valido = False
        self.con_desplazamiento = False

        cabecera = tk.Frame(parent, bg=branding.COLOR_BLANCO)
        cabecera.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(
            cabecera,
            text="Sociedades",
            font=("Helvetica", 10, "bold"),
            fg=branding.COLOR_PRIMARIO,
            bg=branding.COLOR_BLANCO,
        ).pack(side="left")
        estilo_enlace = dict(style="tertiary", padx=6, pady=1)
        self.btn_ninguna = branding.RoundedButton(
            cabecera, text="Ninguna", command=lambda: self.marcar(False), **estilo_enlace
        )
        self.btn_ninguna.pack(side="right")
        self.btn_todas = branding.RoundedButton(
            cabecera, text="Todas", command=lambda: self.marcar(True), **estilo_enlace
        )
        self.btn_todas.pack(side="right")
        self.btn_editar = branding.RoundedButton(
            cabecera, text="Editar lista", command=al_editar, **estilo_enlace
        )
        self.btn_editar.pack(side="right", padx=(0, 6))

        # Las casillas se redibujan aquí dentro en cada recarga.
        self.zona = tk.Frame(parent, bg=branding.COLOR_BLANCO)
        self.zona.pack(padx=16)
        self.lbl_error = tk.Label(
            parent,
            text="",
            font=("Helvetica", 9),
            fg=branding.COLOR_ACENTO,
            bg=branding.COLOR_BLANCO,
            wraplength=440,
            justify="center",
        )
        self.recargar()

    def recargar(self) -> bool:
        """Relee la lista y redibuja las casillas. Las sociedades que ya
        estaban conservan su marca; las nuevas aparecen marcadas."""
        for hijo in self.zona.winfo_children():
            hijo.destroy()
        self.lbl_error.pack_forget()
        try:
            codigos = catalogo_sociedades.codigos()
        except ValueError as exc:
            self.variables = {}
            self.valido = False
            self.lbl_error.config(text=str(exc))
            self.lbl_error.pack(padx=16, pady=(4, 0))
            return False

        marcas = {codigo: var.get() for codigo, var in self.variables.items()}
        self.variables = {
            codigo: tk.BooleanVar(master=self.zona, value=marcas.get(codigo, True))
            for codigo in codigos
        }
        self._dibujar_casillas(codigos)
        self.valido = True
        return True

    def _dibujar_casillas(self, codigos: list[str]) -> None:
        filas = -(-len(codigos) // _COLUMNAS_SOCIEDADES)  # techo
        self.con_desplazamiento = filas > _FILAS_SIN_DESPLAZAMIENTO
        if self.con_desplazamiento:
            # Con muchas sociedades la vista no cabría en la ventana fija:
            # las casillas van en un área con barra de desplazamiento.
            lienzo = tk.Canvas(
                self.zona,
                bg=branding.COLOR_BLANCO,
                highlightthickness=0,
                height=_FILAS_SIN_DESPLAZAMIENTO * _ALTO_FILA_CASILLA,
            )
            barra = ttk.Scrollbar(self.zona, orient="vertical", command=lienzo.yview)
            contenedor = tk.Frame(lienzo, bg=branding.COLOR_BLANCO)
            lienzo.create_window((0, 0), window=contenedor, anchor="nw")
            lienzo.configure(yscrollcommand=barra.set)

            def ajustar(_evento) -> None:
                lienzo.configure(scrollregion=lienzo.bbox("all"), width=contenedor.winfo_reqwidth())

            contenedor.bind("<Configure>", ajustar)
            lienzo.pack(side="left")
            barra.pack(side="right", fill="y")
        else:
            contenedor = self.zona

        for indice, codigo in enumerate(codigos):
            tk.Checkbutton(
                contenedor,
                text=codigo,
                variable=self.variables[codigo],
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

    def marcar(self, valor: bool) -> None:
        for var in self.variables.values():
            var.set(valor)

    def marcadas(self) -> list[str]:
        return [codigo for codigo, var in self.variables.items() if var.get()]


# ---------------------------------------------------------------------------
# HANDLERS
# ---------------------------------------------------------------------------


def _descargar_handler(
    root: tk.Tk,
    opcion: Opcion,
    sociedades: list[str],
    fecha_clave: date | None,
    status_var: tk.StringVar,
    button: tk.Widget,
    btn_atras: tk.Widget,
) -> None:
    """Valida, confirma y corre la descarga de `opcion` en un thread (la GUI
    no se congela).

    El módulo de flujo se importa aquí y no arriba, para que la GUI arranque
    aunque un flujo tenga un problema. Acción y Atrás quedan deshabilitados
    mientras corre: salir a mitad de la descarga dejaría SAP en una
    pantalla intermedia.
    """
    transaccion = opcion.transaccion
    try:
        flujo = importlib.import_module(opcion.modulo)
    except ImportError as exc:
        messagebox.showerror("Error de import", f"No se pudo importar {opcion.modulo}:\n{exc}")
        return
    try:
        catalogo = catalogo_sociedades.codigos()
        socs = validar_sociedades(sociedades, catalogo)
        fecha = validar_fecha_clave(fecha_clave) if opcion.usa_fecha_clave else None
        flujo.validar_configuracion()
    except ValueError as exc:
        messagebox.showerror("Datos inválidos", str(exc))
        return

    if set(socs) == set(catalogo):
        texto_sociedades = f"todas las sociedades ({len(socs)})"
    else:
        texto_sociedades = f"{len(socs)} sociedad(es): {', '.join(socs)}"
    texto_fecha = f", con fecha clave {fecha:%d.%m.%Y}" if fecha else ""
    if not messagebox.askyesno(
        f"Confirmar descarga de {transaccion}",
        f"Se descargará {transaccion} de {texto_sociedades}{texto_fecha}.\n\n"
        "La app usa el portapapeles: se reemplazará lo que tengas copiado.\n"
        "Ten SAP abierto y no lo uses mientras corre la descarga.\n\n"
        "¿Continuar?",
    ):
        return
    argumentos_fecha = {"fecha_clave": fecha} if opcion.usa_fecha_clave else {}

    button.config(state="disabled")
    btn_atras.config(state="disabled")
    status_var.set("Conectando con SAP…")

    def progreso(texto: str) -> None:
        root.after(0, lambda: status_var.set(texto))

    def show_info(title: str, msg: str) -> None:
        root.after(0, lambda: messagebox.showinfo(title, msg))

    def show_warning(title: str, msg: str) -> None:
        root.after(0, lambda: messagebox.showwarning(title, msg))

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
                session = flujo.get_sap_session()
                carpeta, nombre = flujo.descargar(
                    session, socs, progreso=progreso, **argumentos_fecha
                )
                show_info("Descarga completada", f"Archivo guardado en:\n{Path(carpeta) / nombre}")
            except SinResultadosError as exc:
                # No es una falla: la selección no tiene partidas.
                log(f"{transaccion} sin partidas: {exc}")
                show_warning(f"Sin partidas en {transaccion}", str(exc))
            except Exception as exc:
                logger.exception("Falló la descarga de %s", transaccion)
                show_error(f"Error en la descarga de {transaccion}", str(exc))
            finally:
                reenable()

    threading.Thread(target=worker, daemon=True).start()


# ---------------------------------------------------------------------------
# VISTAS
# ---------------------------------------------------------------------------


def _opcion(clave: str) -> Opcion:
    return next(o for o in OPCIONES if o.clave == clave)


def _crear_vista_descarga(root: tk.Tk, parent_frame: tk.Frame, opcion: Opcion) -> tk.Frame:
    """Vista de una opción conectada a SAP: sociedades, fecha clave (si la
    opción la usa), el archivo previo que necesita (si `opcion.requiere`)
    y "Descargar <transacción>".

    Entrega el archivo tal como lo exporta SAP en `salida/`. Si falta el
    archivo previo, el botón queda deshabilitado y la vista dice qué
    descargar primero; se evalúa al abrir la vista, así que basta con
    volver al menú y entrar de nuevo después de descargarlo. El botón
    también se deshabilita si la lista de sociedades no se puede leer.
    """
    parent_frame.pack_forget()
    frame = tk.Frame(root, bg=branding.COLOR_FONDO)
    btn_atras = _crear_header_form(
        root, frame, parent_frame, titulo=opcion.titulo, subtitulo=opcion.subtitulo
    )

    def actualizar_boton() -> None:
        habilitado = selector.valido and not (opcion.requiere and archivo_previo is None)
        btn_descargar.config(state="normal" if habilitado else "disabled")

    def al_volver_de_sociedades() -> None:
        selector.recargar()
        actualizar_boton()

    panel = _crear_panel_card(frame)
    selector = SelectorSociedades(
        panel,
        al_editar=lambda: abrir_sociedades(root, frame, al_volver=al_volver_de_sociedades),
    )

    entry_fecha = None
    if opcion.usa_fecha_clave:
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

    lbl_requisito = None
    archivo_previo = None
    if opcion.requiere:
        previo = _opcion(opcion.requiere)
        archivo_previo = buscar_ultimo_export(previo.transaccion, SALIDA_DIR)
        if archivo_previo is not None:
            texto = f"Usa el {previo.titulo.lower()} más reciente:\n{archivo_previo.name}"
            color = branding.COLOR_GRIS
        else:
            texto = (
                f"Falta el {previo.titulo.lower()}: descárgalo primero\n"
                f"desde «{previo.titulo}» en el menú."
            )
            color = branding.COLOR_ACENTO
        lbl_requisito = tk.Label(
            panel,
            text=texto,
            font=("Helvetica", 9),
            fg=color,
            bg=branding.COLOR_BLANCO,
            justify="center",
        )
        lbl_requisito.pack(pady=(10, 0))

    status_var = tk.StringVar(master=frame, value="")
    btn_descargar = branding.RoundedButton(
        panel, text=f"Descargar {opcion.transaccion}", style="primary", width=220
    )
    btn_descargar.config(
        command=lambda: _descargar_handler(
            root,
            opcion,
            selector.marcadas(),
            entry_fecha.get_date() if entry_fecha is not None else None,
            status_var,
            btn_descargar,
            btn_atras,
        )
    )
    btn_descargar.pack(pady=(12, 16))
    actualizar_boton()

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
    frame.selector = selector
    frame.entry_fecha = entry_fecha
    frame.btn_descargar = btn_descargar
    frame.status_var = status_var
    frame.lbl_requisito = lbl_requisito
    return frame


def abrir_acreedores(root: tk.Tk, parent_frame: tk.Frame) -> tk.Frame:
    """Vista de FBL1N (partidas abiertas de acreedores)."""
    return _crear_vista_descarga(root, parent_frame, _opcion("acreedores"))


def abrir_deudores(root: tk.Tk, parent_frame: tk.Frame) -> tk.Frame:
    """Vista de FBL5N (partidas abiertas de deudores)."""
    return _crear_vista_descarga(root, parent_frame, _opcion("deudores"))


def abrir_maestro_cuentas(root: tk.Tk, parent_frame: tk.Frame) -> tk.Frame:
    """Vista de Y_FI_GRL_004 (maestro del plan de cuentas; sin fecha clave)."""
    return _crear_vista_descarga(root, parent_frame, _opcion("maestro_cuentas"))


def abrir_partidas_mayor(root: tk.Tk, parent_frame: tk.Frame) -> tk.Frame:
    """Vista de FAGLL03 (partidas abiertas de cuentas de mayor; las cuentas
    salen del maestro más reciente)."""
    return _crear_vista_descarga(root, parent_frame, _opcion("partidas_mayor"))


def abrir_sociedades(
    root: tk.Tk, parent_frame: tk.Frame, al_volver: Callable[[], object] | None = None
) -> tk.Frame:
    """Vista "Sociedades": agregar, modificar, quitar y restaurar la lista
    que usan las descargas.

    Cada acción se guarda al instante en `configuracion/sociedades.json`
    (no hay un "Guardar" general que se pueda olvidar). Se abre desde el
    menú y desde "Editar lista" en cada vista de descarga; `al_volver` deja
    que esa vista relea la lista.
    """
    parent_frame.pack_forget()
    frame = tk.Frame(root, bg=branding.COLOR_FONDO)
    btn_atras = _crear_header_form(
        root,
        frame,
        parent_frame,
        titulo="Sociedades",
        subtitulo="Lista que usan las 4 descargas",
        al_volver=al_volver,
    )
    estado = {"lista": [], "seleccion": None}

    panel = _crear_panel_card(frame)
    cuerpo = tk.Frame(panel, bg=branding.COLOR_BLANCO)
    cuerpo.pack(padx=16, pady=(14, 6))

    # --- Lista ---------------------------------------------------------
    columna_lista = tk.Frame(cuerpo, bg=branding.COLOR_BLANCO)
    columna_lista.pack(side="left", padx=(0, 16))
    marco_lista = tk.Frame(columna_lista, bg=branding.COLOR_BLANCO)
    marco_lista.pack()
    lista = tk.Listbox(
        marco_lista,
        height=10,
        width=26,
        font=("Courier", 10),
        activestyle="none",
        exportselection=False,
        selectbackground=branding.COLOR_PRIMARIO,
        selectforeground=branding.COLOR_BLANCO,
    )
    barra = ttk.Scrollbar(marco_lista, orient="vertical", command=lista.yview)
    lista.configure(yscrollcommand=barra.set)
    lista.pack(side="left")
    barra.pack(side="right", fill="y")
    lbl_total = tk.Label(
        columna_lista,
        text="",
        font=("Helvetica", 9),
        fg=branding.COLOR_GRIS,
        bg=branding.COLOR_BLANCO,
    )
    lbl_total.pack(anchor="w", pady=(4, 0))

    # --- Formulario ----------------------------------------------------
    formulario = tk.Frame(cuerpo, bg=branding.COLOR_BLANCO)
    formulario.pack(side="left", anchor="n")
    for fila, texto in enumerate(("Código", "Nombre")):
        tk.Label(
            formulario,
            text=texto,
            font=("Helvetica", 10, "bold"),
            fg=branding.COLOR_PRIMARIO,
            bg=branding.COLOR_BLANCO,
        ).grid(row=fila, column=0, sticky="w", pady=3)
    entry_codigo = ttk.Entry(formulario, width=8)
    entry_codigo.grid(row=0, column=1, sticky="w", padx=(8, 0), pady=3)
    entry_nombre = ttk.Entry(formulario, width=18)
    entry_nombre.grid(row=1, column=1, sticky="w", padx=(8, 0), pady=3)
    tk.Label(
        formulario,
        text="(opcional)",
        font=("Helvetica", 8),
        fg=branding.COLOR_GRIS_CLARO,
        bg=branding.COLOR_BLANCO,
    ).grid(row=2, column=1, sticky="w", padx=(8, 0))

    botones = tk.Frame(formulario, bg=branding.COLOR_BLANCO)
    botones.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="w")
    btn_agregar = branding.RoundedButton(botones, text="Agregar", style="primary", width=150)
    btn_agregar.pack(pady=(0, 6))
    btn_guardar = branding.RoundedButton(botones, text="Guardar cambios", style="acento", width=150)
    btn_guardar.pack(pady=(0, 6))
    btn_quitar = branding.RoundedButton(botones, text="Quitar", style="tertiary", width=150)
    btn_quitar.pack()

    btn_restaurar = branding.RoundedButton(
        panel, text="Restaurar lista inicial", style="tertiary", font=("Helvetica", 9)
    )
    btn_restaurar.pack(anchor="e", padx=16, pady=(0, 10))

    estado_var = tk.StringVar(master=frame, value="")
    lbl_estado = tk.Label(
        frame,
        textvariable=estado_var,
        font=("Helvetica", 10),
        fg=branding.COLOR_OK,
        bg=branding.COLOR_FONDO,
        wraplength=480,
    )
    lbl_estado.pack(pady=(4, 0))

    # --- Comportamiento --------------------------------------------------

    def limpiar_formulario() -> None:
        estado["seleccion"] = None
        lista.selection_clear(0, "end")
        entry_codigo.delete(0, "end")
        entry_nombre.delete(0, "end")

    def mostrar(lista_nueva, seleccionar: str | None = None) -> None:
        estado["lista"] = lista_nueva
        lista.delete(0, "end")
        for s in lista_nueva:
            lista.insert("end", f"{s.codigo:<5} {s.nombre}".rstrip())
        lbl_total.config(text=f"{len(lista_nueva)} sociedades")
        limpiar_formulario()
        if seleccionar is not None:
            indice = next(i for i, s in enumerate(lista_nueva) if s.codigo == seleccionar)
            lista.selection_set(indice)
            lista.see(indice)
            al_seleccionar()

    def al_seleccionar(_evento=None) -> None:
        indices = lista.curselection()
        if not indices:
            return
        elegida = estado["lista"][indices[0]]
        estado["seleccion"] = elegida.codigo
        entry_codigo.delete(0, "end")
        entry_codigo.insert(0, elegida.codigo)
        entry_nombre.delete(0, "end")
        entry_nombre.insert(0, elegida.nombre)

    def avisar(texto: str, error: bool = False) -> None:
        lbl_estado.config(fg=branding.COLOR_ACENTO if error else branding.COLOR_OK)
        estado_var.set(texto)

    def aplicar(operacion: Callable[[], list], mensaje: str, seleccionar: str | None) -> None:
        """Valida, guarda y muestra; los errores se explican sin cerrar nada."""
        try:
            nueva = operacion()
            catalogo_sociedades.guardar(nueva)
        except ValueError as exc:
            messagebox.showerror("Datos inválidos", str(exc))
            return
        except OSError as exc:
            messagebox.showerror(
                "No se pudo guardar",
                f"No se pudo guardar la lista de sociedades:\n{exc}",
            )
            return
        log(mensaje)
        mostrar(nueva, seleccionar)
        avisar(mensaje)

    def agregar() -> None:
        codigo = entry_codigo.get().strip().upper()
        aplicar(
            lambda: catalogo_sociedades.agregar(estado["lista"], codigo, entry_nombre.get()),
            f"Se agregó {codigo}.",
            codigo,
        )

    def guardar_cambios() -> None:
        actual = estado["seleccion"]
        if actual is None:
            messagebox.showerror(
                "Selecciona una sociedad",
                "Selecciona en la lista la sociedad que quieres modificar.",
            )
            return
        codigo = entry_codigo.get().strip().upper()
        aplicar(
            lambda: catalogo_sociedades.modificar(
                estado["lista"], actual, codigo, entry_nombre.get()
            ),
            f"Se guardaron los cambios de {codigo}.",
            codigo,
        )

    def quitar() -> None:
        actual = estado["seleccion"]
        if actual is None:
            messagebox.showerror(
                "Selecciona una sociedad", "Selecciona en la lista la sociedad que quieres quitar."
            )
            return
        if not messagebox.askyesno(
            "Quitar sociedad",
            f"¿Quitar {actual} de la lista?\n\nYa no aparecerá en las descargas.",
        ):
            return
        aplicar(
            lambda: catalogo_sociedades.quitar(estado["lista"], actual),
            f"Se quitó {actual}.",
            None,
        )

    def restaurar() -> None:
        if not messagebox.askyesno(
            "Restaurar lista inicial",
            "¿Volver a la lista inicial de sociedades?\n\n"
            "Se perderán las sociedades que hayas agregado, modificado o quitado.",
        ):
            return
        try:
            nueva = catalogo_sociedades.restaurar_iniciales()
        except (ValueError, OSError) as exc:
            messagebox.showerror("No se pudo restaurar", str(exc))
            return
        log("Se restauró la lista inicial de sociedades.")
        mostrar(nueva)
        habilitar_edicion(True)
        avisar("Se restauró la lista inicial.")

    def habilitar_edicion(habilitar: bool) -> None:
        for boton in (btn_agregar, btn_guardar, btn_quitar):
            boton.config(state="normal" if habilitar else "disabled")

    lista.bind("<<ListboxSelect>>", al_seleccionar)
    btn_agregar.config(command=agregar)
    btn_guardar.config(command=guardar_cambios)
    btn_quitar.config(command=quitar)
    btn_restaurar.config(command=restaurar)

    try:
        mostrar(catalogo_sociedades.cargar())
    except ValueError as exc:
        # Archivo dañado: solo queda disponible "Restaurar lista inicial".
        habilitar_edicion(False)
        avisar(str(exc), error=True)

    frame.pack(fill="both", expand=True)
    # Exponer widgets para los tests.
    frame.btn_atras = btn_atras
    frame.lista = lista
    frame.entry_codigo = entry_codigo
    frame.entry_nombre = entry_nombre
    frame.btn_agregar = btn_agregar
    frame.btn_guardar = btn_guardar
    frame.btn_quitar = btn_quitar
    frame.btn_restaurar = btn_restaurar
    frame.lbl_total = lbl_total
    frame.estado_var = estado_var
    frame.sociedades = lambda: list(estado["lista"])
    frame.al_seleccionar = al_seleccionar
    return frame


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

    # En la esquina superior derecha con `place`: un botón más debajo de las
    # cards haría que el menú dejara de caber en la ventana fija.
    btn_sociedades = branding.RoundedButton(
        frame_menu,
        text="Editar sociedades",
        style="tertiary",
        font=("Helvetica", 9),
        padx=8,
        pady=2,
        command=lambda: abrir_sociedades(root, frame_menu),
    )
    btn_sociedades.place(relx=1.0, x=-12, y=12, anchor="ne")

    frame_menu.botones = botones
    frame_menu.btn_sociedades = btn_sociedades
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
    try:
        ruta, creado = catalogo_sociedades.asegurar_archivo()
        if creado:
            log(f"Primer arranque: se creó la lista de sociedades en {ruta}")
    except (ValueError, OSError) as exc:
        # No bloquea el arranque: las vistas muestran el problema al abrirse.
        log(f"No se pudo preparar la lista de sociedades: {exc}")

    root = crear_app()
    # El splash se cierra justo cuando la ventana está lista para verse.
    root.update_idletasks()
    _cerrar_splash()
    root.mainloop()


if __name__ == "__main__":
    main()
