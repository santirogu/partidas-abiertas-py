"""Tests de src/branding.py: logo y `RoundedButton`.

`RoundedButton` pinta un botón con esquinas redondeadas sobre un
`tk.Canvas` y espeja la API mínima de `tk.Button` que usa el proyecto.
"""

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: F401  (agrega src/ al sys.path)

import branding


class _TkTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()


class RoundedButtonConstructorTest(_TkTestCase):
    def test_stores_text_command_and_initial_state(self) -> None:
        btn = branding.RoundedButton(self.root, text="Click", command=lambda: None)
        self.assertEqual(btn.cget("text"), "Click")
        self.assertEqual(btn.cget("state"), "normal")
        self.assertIsNotNone(btn.cget("command"))

    def test_unknown_style_raises(self) -> None:
        with self.assertRaises(ValueError):
            branding.RoundedButton(self.root, text="X", style="inexistente")

    def test_inherits_from_tk_canvas(self) -> None:
        """Heredar de Canvas le da pack/grid/place y bindings, y permite
        que los handlers acepten tanto `tk.Button` (tests) como
        `RoundedButton` (producción)."""
        btn = branding.RoundedButton(self.root, text="X")
        self.assertIsInstance(btn, tk.Canvas)

    def test_inherits_parent_background(self) -> None:
        frame = tk.Frame(self.root, bg="#123456")
        btn = branding.RoundedButton(frame, text="X")
        self.assertEqual(str(btn.cget("bg")).lower(), "#123456")


class RoundedButtonStylesTest(_TkTestCase):
    def _fill(self, style: str) -> str:
        btn = branding.RoundedButton(self.root, text="X", style=style)
        return btn.itemcget(btn._bg_item, "fill").lower()

    def test_each_style_uses_its_palette_color(self) -> None:
        esperado = {
            "primary": branding.COLOR_PRIMARIO,
            "tertiary": branding.COLOR_FONDO,
            "acento": branding.COLOR_ACENTO,
            "ok": branding.COLOR_OK,
        }
        for style, color in esperado.items():
            with self.subTest(style=style):
                self.assertEqual(self._fill(style), color.lower())

    def test_primary_and_tertiary_are_distinct(self) -> None:
        self.assertNotEqual(self._fill("primary"), self._fill("tertiary"))


class RoundedButtonStateTest(_TkTestCase):
    def test_disabled_state_via_config(self) -> None:
        btn = branding.RoundedButton(self.root, text="X")
        btn.config(state="disabled")
        self.assertEqual(btn.cget("state"), "disabled")

    def test_getitem_returns_overridden_state(self) -> None:
        """REGRESIÓN (heredada de activos-propios-py): `tk.Misc.__getitem__`
        es alias directo de `cget`, así que sin override `btn["state"]`
        devolvería el estado del Canvas (siempre "normal")."""
        btn = branding.RoundedButton(self.root, text="X")
        btn.config(state="disabled")
        self.assertEqual(str(btn["state"]), "disabled")
        btn.config(state="normal")
        self.assertEqual(str(btn["state"]), "normal")

    def test_setitem_routes_through_config(self) -> None:
        btn = branding.RoundedButton(self.root, text="X")
        btn["state"] = "disabled"
        self.assertEqual(btn.cget("state"), "disabled")

    def test_disabled_ignores_mouse_release(self) -> None:
        llamadas = []
        btn = branding.RoundedButton(self.root, text="X", command=lambda: llamadas.append(1))
        btn.config(state="disabled")
        btn._on_release(None)
        self.assertEqual(llamadas, [])


class RoundedButtonInvokeTest(_TkTestCase):
    def test_invoke_runs_command(self) -> None:
        llamadas = []
        btn = branding.RoundedButton(self.root, text="X", command=lambda: llamadas.append("ok"))
        btn.invoke()
        self.assertEqual(llamadas, ["ok"])

    def test_invoke_when_disabled_is_noop(self) -> None:
        llamadas = []
        btn = branding.RoundedButton(self.root, text="X", command=lambda: llamadas.append("ok"))
        btn.config(state="disabled")
        btn.invoke()
        self.assertEqual(llamadas, [])

    def test_invoke_with_no_command_is_safe(self) -> None:
        branding.RoundedButton(self.root, text="X").invoke()


class RoundedButtonReconfigureTest(_TkTestCase):
    def test_can_update_text_after_construction(self) -> None:
        btn = branding.RoundedButton(self.root, text="Antes")
        btn.config(text="Después")
        self.assertEqual(btn.cget("text"), "Después")

    def test_can_update_command_after_construction(self) -> None:
        """Los handlers se cablean con `btn.config(command=...)` después de
        crear el botón, para que el command pueda referenciarlo."""
        marca = []
        btn = branding.RoundedButton(self.root, text="X")
        btn.config(command=lambda: marca.append("v2"))
        btn.invoke()
        self.assertEqual(marca, ["v2"])


class CargarLogoTest(_TkTestCase):
    def test_returns_none_when_file_missing(self) -> None:
        with patch.object(branding, "LOGO_PATH", Path("/no/existe/logo.png")):
            self.assertIsNone(branding.cargar_logo())

    def test_scales_logo_to_requested_height(self) -> None:
        logo = branding.cargar_logo(altura_px=40)
        self.assertIsNotNone(logo)
        self.assertEqual(logo.height(), 40)


if __name__ == "__main__":
    unittest.main()
