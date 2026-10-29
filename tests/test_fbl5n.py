"""Tests de src/fbl5n.py: pasos, orquestador y CLI de FBL5N."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers

import comun
import fbl5n

DISPOSICION = "/PARTABIERTA"


class ValidarConfiguracionTest(unittest.TestCase):
    def test_uses_same_layout_as_fbl1n(self) -> None:
        """El equipo usuario confirmó que FBL5N usa la misma disposición
        que FBL1N."""
        self.assertEqual(fbl5n.validar_configuracion(), "/PARTABIERTA")

    def test_pending_layout_raises(self) -> None:
        with patch.object(fbl5n, "DISPOSICION", None), self.assertRaises(ValueError) as ctx:
            fbl5n.validar_configuracion()
        self.assertIn("FBL5N", str(ctx.exception))

    def test_returns_configured_layout(self) -> None:
        with patch.object(fbl5n, "DISPOSICION", DISPOSICION):
            self.assertEqual(fbl5n.validar_configuracion(), DISPOSICION)


class PasosTest(unittest.TestCase):
    """Cada paso reproduce exactamente los IDs de FBL5N.vbs."""

    def test_seleccionar_deudores_writes_asterisk(self) -> None:
        session = helpers.MockSession()
        fbl5n.seleccionar_deudores(session)
        self.assertEqual(
            session.actions,
            [
                ("wnd[0]/usr/btn%_DD_KUNNR_%_APP_%-VALU_PUSH", "press"),
                (comun.ID_SELMULT_PRIMER_VALOR, "text=", "*"),
                ("wnd[1]/tbar[0]/btn[8]", "press"),
            ],
        )

    def test_seleccionar_sociedades_uses_dd_bukrs(self) -> None:
        session = helpers.MockSession()
        with patch.dict(sys.modules, {"win32clipboard": helpers.fake_win32clipboard()}):
            fbl5n.seleccionar_sociedades(session, ["XM"])
        self.assertEqual(
            session.actions[0], ("wnd[0]/usr/btn%_DD_BUKRS_%_APP_%-VALU_PUSH", "press")
        )

    def test_fijar_fecha_clave_uses_pa_stida_calendar(self) -> None:
        session = helpers.MockSession()
        fbl5n.fijar_fecha_clave(session, date(2026, 10, 28))
        self.assertEqual(session.actions[0], ("wnd[0]/usr/ctxtPA_STIDA", "setFocus"))

    def test_marcar_clases_de_partida(self) -> None:
        session = helpers.MockSession()
        fbl5n.marcar_clases_de_partida(session)
        self.assertEqual(
            session.actions,
            [
                ("wnd[0]/usr/chkX_NORM", "selected=", True),
                ("wnd[0]/usr/chkX_SHBV", "selected=", True),
            ],
        )


class DescargarTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._tmp.name) / "salida"
        self.session = helpers.MockSession()
        self.session.configurar_grilla(
            comun.ID_GRILLA_DISPOSICIONES, comun.COLUMNA_NOMBRE_DISPOSICION, ["/X", DISPOSICION]
        )
        self.clip = helpers.fake_win32clipboard()
        self._patches = [
            patch.object(fbl5n, "DISPOSICION", DISPOSICION),
            patch.dict(sys.modules, {"win32clipboard": self.clip}),
            patch("comun.esperar_archivo_listo", return_value=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def test_runs_steps_in_recording_order(self) -> None:
        fbl5n.descargar(self.session, ["ISA", "XM"], date(2026, 10, 28), self.carpeta)
        orden = [
            ("wnd[0]/tbar[0]/okcd", "text=", "/nFBL5N"),
            ("wnd[0]/usr/btn%_DD_KUNNR_%_APP_%-VALU_PUSH", "press"),
            ("wnd[0]/usr/btn%_DD_BUKRS_%_APP_%-VALU_PUSH", "press"),
            (comun.ID_CALENDARIO, "selectionInterval=", "20261028,20261028"),
            ("wnd[0]/usr/chkX_SHBV", "selected=", True),
            ("wnd[0]/tbar[1]/btn[8]", "press"),
            (comun.ID_GRILLA_DISPOSICIONES, "currentCellRow=", 1),
            ("wnd[0]/mbar/menu[0]/menu[3]/menu[1]", "select"),
            ("wnd[1]/tbar[0]/btn[0]", "press"),
            ("wnd[0]/tbar[0]/okcd", "text=", "/n"),
        ]
        indices = [self.session.actions.index(a) for a in orden]
        self.assertEqual(indices, sorted(indices))
        self.assertEqual(self.clip.contenido[0], "ISA\r\nXM")

    def test_saves_with_fbl5n_prefix(self) -> None:
        carpeta, nombre = fbl5n.descargar(self.session, ["ISA"], "28.10.2026", self.carpeta)
        self.assertEqual(carpeta, str(self.carpeta))
        self.assertRegex(nombre, r"^FBL5N_\d{8}_\d{6}\.xlsx$")
        self.assertIn(("wnd[1]/usr/ctxtDY_FILENAME", "text=", nombre), self.session.actions)

    def test_validation_errors_do_not_touch_sap(self) -> None:
        with patch.object(fbl5n, "DISPOSICION", None), self.assertRaises(ValueError):
            fbl5n.descargar(self.session, ["ISA"], date(2026, 10, 28), self.carpeta)
        with self.assertRaises(ValueError):
            fbl5n.descargar(self.session, ["ISA"], "28/10/2026", self.carpeta)
        self.assertEqual(self.session.actions, [])


class MainEntryPointTest(unittest.TestCase):
    def _main(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch("fbl5n.configurar_logging"):
            codigo = fbl5n.main(argv)
        return codigo, out.getvalue(), err.getvalue()

    def test_no_arguments_is_usage_error(self) -> None:
        self.assertEqual(self._main([])[0], 2)

    def test_pending_layout_returns_1(self) -> None:
        with patch.object(fbl5n, "DISPOSICION", None):
            codigo, _, err = self._main(["28.10.2026"])
        self.assertEqual(codigo, 1)
        self.assertIn("disposición", err)

    def test_happy_path_defaults_to_all_companies(self) -> None:
        descargar = MagicMock(return_value=("C:/salida", "FBL5N_x.xlsx"))
        with (
            patch.object(fbl5n, "DISPOSICION", DISPOSICION),
            patch("fbl5n.get_sap_session", return_value="sesion"),
            patch("fbl5n.descargar", descargar),
        ):
            codigo, out, _ = self._main(["28.10.2026"])
        self.assertEqual(codigo, 0)
        self.assertIn("FBL5N_x.xlsx", out)
        self.assertEqual(descargar.call_args[0][1], list(comun.SOCIEDADES))


if __name__ == "__main__":
    unittest.main()
