"""Paleta corporativa "Hub de ISA", logo y `RoundedButton`.

Centraliza colores y logo para que todas las vistas se vean igual. La
paleta aproxima los colores del logo (navy + naranja); si se consiguen
los hex exactos de la guía de marca, basta con ajustar las constantes.

Si `resources/logo.png` no existe, `cargar_logo()` devuelve `None` y la
GUI sigue funcionando solo con texto y colores.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from paths import bundled_resource_path

# ---------------------------------------------------------------------------
# PALETA
# ---------------------------------------------------------------------------

# Navy del logo: títulos, botones primarios y acentos sobrios.
COLOR_PRIMARIO = "#1A3A6C"
COLOR_PRIMARIO_HOVER = "#2B5CA8"

# Naranja del swoosh que cruza la "H" del logo. Acento, con moderación.
COLOR_ACENTO = "#F58220"
COLOR_ACENTO_HOVER = "#D96D14"

# Verde de "operación exitosa" (status OK y botón de tercer nivel).
COLOR_OK = "#1A7F37"
COLOR_OK_HOVER = "#15662C"

# Grises de texto secundario y borde de cards (borde plano de 1 px:
# Tk no soporta sombras).
COLOR_GRIS = "#555555"
COLOR_GRIS_CLARO = "#888888"
COLOR_GRIS_BORDE = "#E5E5E5"

COLOR_BLANCO = "#FFFFFF"
COLOR_FONDO = "#FFFFFF"


# ---------------------------------------------------------------------------
# LOGO
# ---------------------------------------------------------------------------

LOGO_PATH = bundled_resource_path("resources/logo.png")
# Alto del logo en la GUI; el ancho se calcula conservando la proporción.
LOGO_ALTURA_PX = 85


def cargar_logo(altura_px: int = LOGO_ALTURA_PX):
    """Carga el logo escalado a `altura_px` de alto.

    Returns:
        Un `ImageTk.PhotoImage` listo para `tk.Label(image=...)`, o `None`
        si falta el archivo, Pillow o Tk.

    IMPORTANTE: quien lo llama DEBE guardar la referencia
    (`root._logo_ref = cargar_logo()`). Tk no retiene el `PhotoImage`: si
    Python lo libera por GC, Tk muestra un cuadro vacío.
    """
    try:
        from PIL import Image, ImageTk
    except ImportError:
        # Pillow sin ImageTk (Python sin Tk): condición esperada en algunos
        # entornos de dev, no amerita log.
        return None

    if not LOGO_PATH.exists():
        return None

    try:
        img = Image.open(LOGO_PATH)
        ratio = altura_px / img.height
        nuevo_ancho = int(img.width * ratio)
        img = img.resize((nuevo_ancho, altura_px), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as exc:
        # El archivo y las librerías están, pero algo falla al cargar o
        # escalar: se loguea para diagnóstico y la GUI sigue sin logo.
        print(
            f"branding.cargar_logo: error cargando {LOGO_PATH.name}: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return None


# ---------------------------------------------------------------------------
# ROUNDEDBUTTON
# ---------------------------------------------------------------------------
#
# En macOS (aqua) `tk.Button` ignora `bg`, y Tk no tiene `border-radius`.
# Esta clase pinta el botón sobre un `tk.Canvas`: un polígono
# `smooth=True` con puntos repetidos en los lados (solo se curvan las
# esquinas) más el texto centrado. Los eventos `<Button-1>`,
# `<ButtonRelease-1>`, `<Enter>` y `<Leave>` imitan a un `tk.Button`.
#
# API espejada de `tk.Button` (solo lo que usa el proyecto):
#   - constructor: text, command, style, radius, padx, pady, font, width,
#     height, wraplength
#   - config(state="normal"|"disabled", text=..., command=...)
#   - cget("text"|"state"|"command"), btn["state"], btn["state"] = ...
#   - invoke()  (click programático, usado en tests)

_BUTTON_STYLES = {
    "primary": dict(
        bg_normal=COLOR_PRIMARIO,
        bg_hover=COLOR_PRIMARIO_HOVER,
        bg_pressed=COLOR_PRIMARIO_HOVER,
        bg_disabled="#B8C3D4",
        fg_normal=COLOR_BLANCO,
        fg_disabled=COLOR_BLANCO,
        font=("Helvetica", 11, "bold"),
        padx=14,
        pady=8,
    ),
    "tertiary": dict(
        bg_normal=COLOR_FONDO,
        bg_hover="#F0F0F0",
        bg_pressed="#E0E0E0",
        bg_disabled=COLOR_FONDO,
        fg_normal=COLOR_GRIS,
        fg_disabled=COLOR_GRIS_CLARO,
        font=("Helvetica", 9),
        padx=10,
        pady=4,
    ),
    "acento": dict(
        bg_normal=COLOR_ACENTO,
        bg_hover=COLOR_ACENTO_HOVER,
        bg_pressed=COLOR_ACENTO_HOVER,
        bg_disabled="#F8C99A",
        fg_normal=COLOR_BLANCO,
        fg_disabled=COLOR_BLANCO,
        font=("Helvetica", 11, "bold"),
        padx=14,
        pady=8,
    ),
    "ok": dict(
        bg_normal=COLOR_OK,
        bg_hover=COLOR_OK_HOVER,
        bg_pressed=COLOR_OK_HOVER,
        bg_disabled="#A8C9B0",
        fg_normal=COLOR_BLANCO,
        fg_disabled=COLOR_BLANCO,
        font=("Helvetica", 11, "bold"),
        padx=14,
        pady=8,
    ),
}


class RoundedButton(tk.Canvas):
    """`tk.Button` con esquinas redondeadas (radio por defecto: 4 px).

    Cualquier opción fuera de la API documentada arriba (p. ej. `relief`,
    `activebackground`) no aplica: el botón se pinta con primitivas de
    Canvas.
    """

    def __init__(
        self,
        parent,
        *,
        text: str = "",
        command=None,
        style: str = "primary",
        radius: int = 4,
        padx: int | None = None,
        pady: int | None = None,
        font=None,
        width: int | None = None,
        height: int | None = None,
        wraplength: int | None = None,
        **canvas_kwargs,
    ) -> None:
        if style not in _BUTTON_STYLES:
            raise ValueError(f"style debe ser uno de {list(_BUTTON_STYLES)!r}, recibí: {style!r}")
        cfg = dict(_BUTTON_STYLES[style])
        if padx is not None:
            cfg["padx"] = padx
        if pady is not None:
            cfg["pady"] = pady
        if font is not None:
            cfg["font"] = font

        self._cfg = cfg
        self._text = text
        self._command = command
        self._radius = radius
        self._wraplength = wraplength
        self._state = "normal"

        # El Canvas hereda el bg del padre para que las esquinas
        # redondeadas se mezclen sin marco visible.
        parent_bg = canvas_kwargs.pop("bg") if "bg" in canvas_kwargs else parent.cget("bg")
        super().__init__(parent, highlightthickness=0, bd=0, bg=parent_bg, **canvas_kwargs)

        self._compute_size_and_draw(width=width, height=height)

        self.bind("<Button-1>", self._on_click)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    # ---- dibujo --------------------------------------------------------

    def _compute_size_and_draw(self, *, width=None, height=None) -> None:
        # Se mide con tkfont.Font y no con el bbox de un item temporal,
        # porque el bbox vale (0, 0, 0, 0) antes del primer layout.
        fnt = tkfont.Font(font=self._cfg["font"])
        text_w = self._wraplength if self._wraplength else fnt.measure(self._text)
        text_h = fnt.metrics("linespace")
        if self._wraplength:
            total_w = fnt.measure(self._text)
            lineas = max(1, -(-total_w // self._wraplength))  # techo
            text_h *= lineas

        w = width if width is not None else int(text_w + 2 * self._cfg["padx"])
        h = height if height is not None else int(text_h + 2 * self._cfg["pady"])
        self.config(width=w, height=h)

        self._bg_item = self._create_rounded_rect(
            1, 1, w - 1, h - 1, self._radius, fill=self._cfg["bg_normal"], outline=""
        )
        text_kwargs = dict(text=self._text, font=self._cfg["font"], fill=self._cfg["fg_normal"])
        if self._wraplength:
            text_kwargs["width"] = self._wraplength
        self._text_item = self.create_text(w / 2, h / 2, **text_kwargs)

    def _create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        # Con `smooth=True` Tk pasa un B-spline por todos los puntos.
        # Repetir cada punto de los lados rectos hace que el spline se
        # "asiente" ahí y solo curve las esquinas.
        points = [
            x1 + r, y1, x1 + r, y1,
            x2 - r, y1, x2 - r, y1,
            x2, y1,
            x2, y1 + r, x2, y1 + r,
            x2, y2 - r, x2, y2 - r,
            x2, y2,
            x2 - r, y2, x2 - r, y2,
            x1 + r, y2, x1 + r, y2,
            x1, y2,
            x1, y2 - r, x1, y2 - r,
            x1, y1 + r, x1, y1 + r,
            x1, y1,
        ]  # fmt: skip
        return self.create_polygon(points, smooth=True, **kwargs)

    # ---- eventos -------------------------------------------------------

    def _on_enter(self, _event) -> None:
        if self._state == "disabled":
            return
        self.itemconfig(self._bg_item, fill=self._cfg["bg_hover"])
        self.config(cursor="hand2")

    def _on_leave(self, _event) -> None:
        if self._state == "disabled":
            return
        self.itemconfig(self._bg_item, fill=self._cfg["bg_normal"])
        self.config(cursor="")

    def _on_click(self, _event) -> None:
        if self._state == "disabled":
            return
        self.itemconfig(self._bg_item, fill=self._cfg["bg_pressed"])

    def _on_release(self, _event) -> None:
        if self._state == "disabled":
            return
        self.itemconfig(self._bg_item, fill=self._cfg["bg_hover"])
        if self._command is not None:
            self._command()

    # ---- API tipo tk.Button --------------------------------------------

    def configure(self, **kwargs):  # alias estándar de Tk
        return self.config(**kwargs)

    def config(self, **kwargs):  # type: ignore[override]
        if "state" in kwargs:
            new_state = str(kwargs.pop("state"))
            self._state = new_state
            if new_state == "disabled":
                self.itemconfig(self._bg_item, fill=self._cfg["bg_disabled"])
                self.itemconfig(self._text_item, fill=self._cfg["fg_disabled"])
                self.config(cursor="")
            else:
                self.itemconfig(self._bg_item, fill=self._cfg["bg_normal"])
                self.itemconfig(self._text_item, fill=self._cfg["fg_normal"])
        if "text" in kwargs:
            self._text = kwargs.pop("text")
            self.itemconfig(self._text_item, text=self._text)
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if kwargs:
            return super().config(**kwargs)
        return None

    def cget(self, option):  # type: ignore[override]
        if option == "text":
            return self._text
        if option == "state":
            return self._state
        if option == "command":
            return self._command
        return super().cget(option)

    def __getitem__(self, key):
        # `tk.Misc.__getitem__` es alias directo de `cget` (no re-despacha),
        # así que sin este override `btn["state"]` devolvería el estado del
        # Canvas (siempre "normal") en vez del nuestro.
        return self.cget(key)

    def __setitem__(self, key, value):
        self.config(**{key: value})

    def invoke(self) -> None:
        """Click programático (espejo de `tk.Button.invoke`). No hace nada
        si el botón está deshabilitado."""
        if self._state != "disabled" and self._command is not None:
            self._command()
