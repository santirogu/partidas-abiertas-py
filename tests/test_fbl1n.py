"""Tests de src/fbl1n.py: pasos, orquestador y CLI de FBL1N."""

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
import fbl1n

DISPOSICION = "/PARTABIERTAS"


class ValidarDisposicionTest(unittest.TestCase):
    def test_pending_layout_raises(self) -> None:
        with patch.object(fbl1n, "DISPOSICION", None), self.assertRaises(ValueError) as ctx:
            fbl1n.validar_disposicion()
        self.assertIn("disposición", str(ctx.exception))

    def test_returns_configured_layout(self) -> None:
        with patch.object(fbl1n, "DISPOSICION", f" {DISPOSICION} "):
            self.assertEqual(fbl1n.validar_disposicion(), DISPOSICION)


class PasosTest(unittest.TestCase):
    """Cada paso reproduce exactamente los IDs de FBL1N.vbs."""

    def test_seleccionar_acreedores_writes_asterisk(self) -> None:
        session = helpers.MockSession()
        fbl1n.seleccionar_acreedores(session)
        self.assertEqual(
            session.actions,
            [
                ("wnd[0]/usr/btn%_KD_LIFNR_%_APP_%-VALU_PUSH", "press"),
                (comun.ID_SELMULT_PRIMER_VALOR, "text=", "*"),
                ("wnd[1]/tbar[0]/btn[8]", "press"),
            ],
        )

    def test_seleccionar_sociedades_pastes_from_clipboard(self) -> None:
        session = helpers.MockSession()
        clip = helpers.fake_win32clipboard()
        with patch.dict(sys.modules, {"win32clipboard": clip}):
            fbl1n.seleccionar_sociedades(session, ["ISA", "XM"])
        self.assertEqual(clip.contenido[0], "ISA\r\nXM")
        self.assertEqual(
            session.actions[0], ("wnd[0]/usr/btn%_KD_BUKRS_%_APP_%-VALU_PUSH", "press")
        )

    def test_fijar_fecha_clave_uses_pa_stida_calendar(self) -> None:
        session = helpers.MockSession()
        fbl1n.fijar_fecha_clave(session, date(2026, 10, 28))
        self.assertEqual(session.actions[0], ("wnd[0]/usr/ctxtPA_STIDA", "setFocus"))
        self.assertEqual(
            session.actions[-1], (comun.ID_CALENDARIO, "selectionInterval=", "20261028,20261028")
        )

    def test_marcar_clases_de_partida(self) -> None:
        session = helpers.MockSession()
        fbl1n.marcar_clases_de_partida(session)
        self.assertEqual(
            session.actions,
            [
                ("wnd[0]/usr/chkX_NORM", "selected=", True),
                ("wnd[0]/usr/chkX_SHBV", "selected=", True),
            ],
        )


class DescargarFbl1nTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._tmp.name) / "salida"
        self.session = helpers.MockSession()
        self.session.configurar_grilla(
            comun.ID_GRILLA_DISPOSICIONES,
            comun.COLUMNA_NOMBRE_DISPOSICION,
            ["/OTRA", DISPOSICION, "/ZZZ"],
        )
        self.clip = helpers.fake_win32clipboard()
        self._patches = [
            patch.object(fbl1n, "DISPOSICION", DISPOSICION),
            patch.dict(sys.modules, {"win32clipboard": self.clip}),
            patch("fbl1n.esperar_archivo_listo", return_value=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def _indice(self, accion: tuple) -> int:
        return self.session.actions.index(accion)

    def test_runs_steps_in_recording_order(self) -> None:
        fbl1n.descargar_fbl1n(self.session, ["ISA", "XM"], date(2026, 10, 28), self.carpeta)
        orden = [
            ("wnd[0]/tbar[0]/okcd", "text=", "/nFBL1N"),
            ("wnd[0]/usr/btn%_KD_LIFNR_%_APP_%-VALU_PUSH", "press"),
            ("wnd[0]/usr/btn%_KD_BUKRS_%_APP_%-VALU_PUSH", "press"),
            (comun.ID_CALENDARIO, "selectionInterval=", "20261028,20261028"),
            ("wnd[0]/usr/chkX_SHBV", "selected=", True),
            ("wnd[0]/tbar[1]/btn[8]", "press"),
            ("wnd[0]/tbar[1]/btn[33]", "press"),
            (comun.ID_GRILLA_DISPOSICIONES, "clickCurrentCell"),
            ("wnd[0]/mbar/menu[0]/menu[3]/menu[1]", "select"),
            ("wnd[1]/tbar[0]/btn[0]", "press"),
        ]
        indices = [self._indice(a) for a in orden]
        self.assertEqual(indices, sorted(indices))
        self.assertEqual(self.clip.contenido[0], "ISA\r\nXM")

    def test_saves_in_destination_with_timestamped_name(self) -> None:
        carpeta, nombre = fbl1n.descargar_fbl1n(
            self.session, ["ISA"], date(2026, 10, 28), self.carpeta
        )
        self.assertEqual(carpeta, str(self.carpeta))
        self.assertRegex(nombre, r"^FBL1N_\d{8}_\d{6}\.xlsx$")
        self.assertIn(("wnd[1]/usr/ctxtDY_PATH", "text=", str(self.carpeta)), self.session.actions)
        self.assertIn(("wnd[1]/usr/ctxtDY_FILENAME", "text=", nombre), self.session.actions)
        self.assertTrue(self.carpeta.is_dir())

    def test_selects_layout_by_name(self) -> None:
        fbl1n.descargar_fbl1n(self.session, ["ISA"], date(2026, 10, 28), self.carpeta)
        self.assertIn((comun.ID_GRILLA_DISPOSICIONES, "currentCellRow=", 1), self.session.actions)

    def test_returns_to_initial_screen_at_the_end(self) -> None:
        fbl1n.descargar_fbl1n(self.session, ["ISA"], date(2026, 10, 28), self.carpeta)
        self.assertEqual(
            self.session.actions[-2:],
            [("wnd[0]/tbar[0]/okcd", "text=", "/n"), ("wnd[0]", "sendVKey", 0)],
        )

    def test_validation_errors_do_not_touch_sap(self) -> None:
        casos = {
            "sociedad": (["ZZZ"], date(2026, 10, 28)),
            "fecha": (["ISA"], "2026-10-28"),
        }
        for nombre, (sociedades, fecha) in casos.items():
            with self.subTest(caso=nombre), self.assertRaises(ValueError):
                fbl1n.descargar_fbl1n(self.session, sociedades, fecha, self.carpeta)
        self.assertEqual(self.session.actions, [])

    def test_pending_layout_does_not_touch_sap(self) -> None:
        with patch.object(fbl1n, "DISPOSICION", None), self.assertRaises(ValueError):
            fbl1n.descargar_fbl1n(self.session, ["ISA"], date(2026, 10, 28), self.carpeta)
        self.assertEqual(self.session.actions, [])

    def test_raises_when_file_never_appears(self) -> None:
        with (
            patch("fbl1n.esperar_archivo_listo", return_value=False),
            self.assertRaises(RuntimeError) as ctx,
        ):
            fbl1n.descargar_fbl1n(self.session, ["ISA"], date(2026, 10, 28), self.carpeta)
        self.assertIn("no terminó de guardar", str(ctx.exception))

    def test_reports_progress_and_ignores_callback_errors(self) -> None:
        mensajes = []

        def progreso(texto: str) -> None:
            mensajes.append(texto)
            raise RuntimeError("la GUI se cerró")

        fbl1n.descargar_fbl1n(
            self.session, ["ISA"], date(2026, 10, 28), self.carpeta, progreso=progreso
        )
        self.assertTrue(any("Paso 4 de 7" in m for m in mensajes))
        self.assertTrue(mensajes[-1].startswith("FBL1N listo"))


class MainEntryPointTest(unittest.TestCase):
    def _main(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch("fbl1n.configurar_logging"):
            codigo = fbl1n.main(argv)
        return codigo, out.getvalue(), err.getvalue()

    def test_no_arguments_is_usage_error(self) -> None:
        codigo, _, err = self._main([])
        self.assertEqual(codigo, 2)
        self.assertIn("Uso:", err)

    def test_invalid_date_returns_1(self) -> None:
        with patch.object(fbl1n, "DISPOSICION", DISPOSICION):
            codigo, _, err = self._main(["2026-10-28"])
        self.assertEqual(codigo, 1)
        self.assertIn("Fecha clave inválida", err)

    def test_sap_error_returns_1(self) -> None:
        with (
            patch.object(fbl1n, "DISPOSICION", DISPOSICION),
            patch("fbl1n.get_sap_session", side_effect=RuntimeError("SAP cerrado")),
        ):
            codigo, _, err = self._main(["28.10.2026"])
        self.assertEqual(codigo, 1)
        self.assertIn("SAP cerrado", err)

    def test_defaults_to_all_companies(self) -> None:
        descargar = MagicMock(return_value=("C:/salida", "FBL1N_x.xlsx"))
        with (
            patch.object(fbl1n, "DISPOSICION", DISPOSICION),
            patch("fbl1n.get_sap_session", return_value="sesion"),
            patch("fbl1n.descargar_fbl1n", descargar),
        ):
            codigo, out, _ = self._main(["28.10.2026"])
        self.assertEqual(codigo, 0)
        self.assertIn("OK:", out)
        self.assertEqual(descargar.call_args[0][1], list(comun.SOCIEDADES))

    def test_passes_given_companies(self) -> None:
        descargar = MagicMock(return_value=("C:/salida", "FBL1N_x.xlsx"))
        with (
            patch.object(fbl1n, "DISPOSICION", DISPOSICION),
            patch("fbl1n.get_sap_session", return_value="sesion"),
            patch("fbl1n.descargar_fbl1n", descargar),
        ):
            codigo, _, _ = self._main(["28.10.2026", "isa", "XM"])
        self.assertEqual(codigo, 0)
        self.assertEqual(descargar.call_args[0][1], ["isa", "XM"])


if __name__ == "__main__":
    unittest.main()
