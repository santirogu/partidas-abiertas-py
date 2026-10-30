"""Tests de src/y_fi_grl_004.py: pasos, orquestador y CLI del maestro de cuentas."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers

import comun
import y_fi_grl_004


class PasosTest(unittest.TestCase):
    """Cada paso reproduce exactamente los IDs de Y_FI_GRL_004.vbs."""

    def test_seleccionar_planes_de_cuentas_writes_asterisk(self) -> None:
        session = helpers.MockSession()
        y_fi_grl_004.seleccionar_planes_de_cuentas(session)
        self.assertEqual(session.actions, [("wnd[0]/usr/ctxtSD_KTOPL-LOW", "text=", "*")])

    def test_seleccionar_sociedades_pastes_into_sd_bukrs(self) -> None:
        session = helpers.MockSession()
        clip = helpers.fake_win32clipboard()
        with patch.dict(sys.modules, {"win32clipboard": clip}):
            y_fi_grl_004.seleccionar_sociedades(session, ["ISA", "XM"])
        self.assertEqual(clip.contenido[0], "ISA\r\nXM")
        self.assertEqual(
            session.actions,
            [
                ("wnd[0]/usr/btn%_SD_BUKRS_%_APP_%-VALU_PUSH", "press"),
                ("wnd[1]/tbar[0]/btn[16]", "press"),
                ("wnd[1]/tbar[0]/btn[24]", "press"),
                ("wnd[1]/tbar[0]/btn[8]", "press"),
            ],
        )

    def test_needs_no_configuration(self) -> None:
        self.assertIsNone(y_fi_grl_004.validar_configuracion())


class DescargarTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.carpeta = Path(self._tmp.name) / "salida"
        self.session = helpers.MockSession()
        self.session.simular_lista_tras_ejecutar(y_fi_grl_004.ID_CAMPO_PLAN_CUENTAS)
        self._patches = [
            patch.dict(sys.modules, {"win32clipboard": helpers.fake_win32clipboard()}),
            patch("comun.esperar_archivo_listo", return_value=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def test_runs_steps_in_recording_order(self) -> None:
        y_fi_grl_004.descargar(self.session, ["ISA"], self.carpeta)
        orden = [
            ("wnd[0]/tbar[0]/okcd", "text=", "/nY_FI_GRL_004"),
            ("wnd[0]/usr/ctxtSD_KTOPL-LOW", "text=", "*"),
            ("wnd[0]/usr/btn%_SD_BUKRS_%_APP_%-VALU_PUSH", "press"),
            ("wnd[0]/tbar[1]/btn[8]", "press"),
            ("wnd[0]/mbar/menu[0]/menu[3]/menu[1]", "select"),
            ("wnd[1]/tbar[0]/btn[0]", "press"),
            ("wnd[0]/tbar[0]/okcd", "text=", "/n"),
        ]
        indices = [self.session.actions.index(a) for a in orden]
        self.assertEqual(indices, sorted(indices))

    def test_uses_neither_key_date_nor_layout(self) -> None:
        y_fi_grl_004.descargar(self.session, ["ISA"], self.carpeta)
        ids = {a[0] for a in self.session.actions}
        self.assertNotIn(comun.ID_CALENDARIO, ids)
        self.assertNotIn(comun.ID_BTN_DISPOSICION, ids)

    def test_saves_with_transaction_prefix(self) -> None:
        carpeta, nombre = y_fi_grl_004.descargar(self.session, ["ISA"], self.carpeta)
        self.assertEqual(carpeta, str(self.carpeta))
        self.assertRegex(nombre, r"^Y_FI_GRL_004_\d{8}_\d{6}\.xlsx$")
        self.assertIn(("wnd[1]/usr/ctxtDY_PATH", "text=", str(self.carpeta)), self.session.actions)

    def test_invalid_company_does_not_touch_sap(self) -> None:
        with self.assertRaises(ValueError):
            y_fi_grl_004.descargar(self.session, ["ZZZ"], self.carpeta)
        self.assertEqual(self.session.actions, [])

    def test_no_items_stops_after_execute(self) -> None:
        """REGRESIÓN 2026-10-29: FBL5N solo con AM no tenía partidas; SAP se
        quedó en la pantalla de selección y la app siguió hasta fallar al
        buscar la lista de disposiciones ("control could not be found")."""
        session = helpers.MockSession()  # sin simular la lista de resultados
        session.mostrar("wnd[0]/sbar", "No se seleccionaron partidas")
        with self.assertRaises(comun.SinResultadosError) as ctx:
            y_fi_grl_004.descargar(session, ["AM"], self.carpeta)
        self.assertIn("AM", str(ctx.exception))
        self.assertIn("No se seleccionaron partidas", str(ctx.exception))
        ids = [accion[0] for accion in session.actions]
        self.assertNotIn(comun.ID_BTN_DISPOSICION, ids)
        self.assertNotIn(comun.ID_MENU_EXPORTAR, ids)
        self.assertEqual(
            session.actions[-2:],
            [("wnd[0]/tbar[0]/okcd", "text=", "/n"), ("wnd[0]", "sendVKey", 0)],
        )


class MainEntryPointTest(unittest.TestCase):
    def _main(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with (
            redirect_stdout(out),
            redirect_stderr(err),
            patch("y_fi_grl_004.configurar_logging"),
        ):
            codigo = y_fi_grl_004.main(argv)
        return codigo, out.getvalue(), err.getvalue()

    def test_option_flags_are_usage_errors(self) -> None:
        codigo, _, err = self._main(["--help"])
        self.assertEqual(codigo, 2)
        self.assertIn("Uso:", err)

    def test_invalid_company_returns_1(self) -> None:
        codigo, _, err = self._main(["ZZZ"])
        self.assertEqual(codigo, 1)
        self.assertIn("ZZZ", err)

    def test_defaults_to_all_companies(self) -> None:
        descargar = MagicMock(return_value=("C:/salida", "Y_FI_GRL_004_x.xlsx"))
        with (
            patch("y_fi_grl_004.get_sap_session", return_value="sesion"),
            patch("y_fi_grl_004.descargar", descargar),
        ):
            codigo, out, _ = self._main([])
        self.assertEqual(codigo, 0)
        self.assertIn("OK:", out)
        self.assertEqual(descargar.call_args[0][1], list(comun.SOCIEDADES))


if __name__ == "__main__":
    unittest.main()
