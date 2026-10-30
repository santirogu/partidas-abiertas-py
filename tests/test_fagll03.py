"""Tests de src/fagll03.py: cuentas del maestro, pasos, orquestador y CLI."""

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
import fagll03
import sociedades

ENCABEZADO_MAESTRO = ["Cta.mayor", "Texto breve", "PI", "Cla", "Soc."]


def _crear_maestro(carpeta: Path, nombre: str = "Y_FI_GRL_004_20261028_225628.xlsx") -> Path:
    """Maestro mínimo con las columnas reales del export de Y_FI_GRL_004."""
    return helpers.crear_libro(
        carpeta / nombre,
        {
            "Sheet1": [
                ENCABEZADO_MAESTRO,
                ["1001010100", "Caja", None, "001", "ISA"],
                ["1317210105", "Clientes", "X", "001", "ISA"],
                ["1317210105", "Clientes", "X", "001", "TRAN"],  # misma cuenta, otra sociedad
                ["2424067700", "Proveedores", "X", "001", "TRAN"],
                ["2810050500", "Anticipos", "X", "001", "AM"],
                ["2999999999", "Sin sociedad", "X", "001", None],
            ]
        },
    )


class LeerCuentasPartidasAbiertasTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.maestro = _crear_maestro(self.tmp)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_only_accounts_with_pi_for_selected_companies(self) -> None:
        cuentas = fagll03.leer_cuentas_partidas_abiertas(self.maestro, ["ISA", "TRAN"])
        self.assertEqual(cuentas, ["1317210105", "2424067700"])

    def test_filters_by_company(self) -> None:
        """La gestión de partidas abiertas se define por sociedad: una
        cuenta con PI = X solo en TRAN no entra si se elige solo ISA."""
        self.assertEqual(
            fagll03.leer_cuentas_partidas_abiertas(self.maestro, ["ISA"]), ["1317210105"]
        )

    def test_no_accounts_for_companies_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            fagll03.leer_cuentas_partidas_abiertas(self.maestro, ["RIOS"])
        self.assertIn("PI = X", str(ctx.exception))

    def test_missing_columns_raise_clear_error(self) -> None:
        otro = helpers.crear_libro(
            self.tmp / "otro.xlsx", {"Sheet1": [["Cuenta", "Sociedad"], ["1", "ISA"]]}
        )
        with self.assertRaises(ValueError) as ctx:
            fagll03.leer_cuentas_partidas_abiertas(otro, ["ISA"])
        self.assertIn("Cta.mayor", str(ctx.exception))
        self.assertIn("PI", str(ctx.exception))


class BuscarMaestroTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_picks_the_most_recent_master(self) -> None:
        _crear_maestro(self.tmp, "Y_FI_GRL_004_20261027_090000.xlsx")
        reciente = _crear_maestro(self.tmp, "Y_FI_GRL_004_20261028_225628.xlsx")
        _crear_maestro(self.tmp, "FBL1N_20261029_080000.xlsx")
        self.assertEqual(fagll03.buscar_ultimo_maestro(self.tmp), reciente)

    def test_missing_master_raises_with_instructions(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            fagll03.validar_maestro(self.tmp)
        self.assertIn("Maestro de cuentas", str(ctx.exception))

    def test_configuration_requires_master(self) -> None:
        with (
            patch("fagll03.validar_maestro", side_effect=ValueError("sin maestro")),
            self.assertRaises(ValueError),
        ):
            fagll03.validar_configuracion()

    def test_configuration_uses_partabierta(self) -> None:
        with patch("fagll03.validar_maestro"):
            self.assertEqual(fagll03.validar_configuracion(), "/PARTABIERTA")


class PasosTest(unittest.TestCase):
    """Cada paso reproduce exactamente los IDs de FAGLL03.vbs."""

    def test_seleccionar_cuentas_pastes_into_sd_saknr(self) -> None:
        session = helpers.MockSession()
        clip = helpers.fake_win32clipboard()
        with patch.dict(sys.modules, {"win32clipboard": clip}):
            fagll03.seleccionar_cuentas(session, ["1317210105", "2424067700"])
        self.assertEqual(clip.contenido[0], "1317210105\r\n2424067700")
        self.assertEqual(
            session.actions,
            [
                ("wnd[0]/usr/btn%_SD_SAKNR_%_APP_%-VALU_PUSH", "press"),
                ("wnd[1]/tbar[0]/btn[16]", "press"),
                ("wnd[1]/tbar[0]/btn[24]", "press"),
                ("wnd[1]/tbar[0]/btn[8]", "press"),
            ],
        )

    def test_seleccionar_sociedades_pastes_into_sd_bukrs(self) -> None:
        session = helpers.MockSession()
        with patch.dict(sys.modules, {"win32clipboard": helpers.fake_win32clipboard()}):
            fagll03.seleccionar_sociedades(session, ["ISA"])
        self.assertEqual(
            session.actions[0], ("wnd[0]/usr/btn%_SD_BUKRS_%_APP_%-VALU_PUSH", "press")
        )

    def test_fijar_fecha_clave_uses_pa_stida_calendar(self) -> None:
        session = helpers.MockSession()
        fagll03.fijar_fecha_clave(session, date(2026, 10, 28))
        self.assertEqual(session.actions[0], ("wnd[0]/usr/ctxtPA_STIDA", "setFocus"))


class DescargarTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.maestro = _crear_maestro(self.tmp)
        self.carpeta = self.tmp / "salida"
        self.session = helpers.MockSession()
        self.session.simular_lista_tras_ejecutar(fagll03.ID_CAMPO_FECHA_CLAVE)
        self.session.configurar_grilla(
            comun.ID_GRILLA_DISPOSICIONES, comun.COLUMNA_NOMBRE_DISPOSICION, ["/X", "/PARTABIERTA"]
        )
        self.clip = helpers.fake_win32clipboard()
        self.pegados: list[str] = []
        original = self.clip.SetClipboardText

        def registrar(texto: str, formato: int) -> None:
            self.pegados.append(texto)
            original(texto, formato)

        self.clip.SetClipboardText = registrar
        self._patches = [
            patch.dict(sys.modules, {"win32clipboard": self.clip}),
            patch("comun.esperar_archivo_listo", return_value=True),
        ]
        for p in self._patches:
            p.start()

    def tearDown(self) -> None:
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    def _descargar(self, sociedades=("ISA", "TRAN")) -> tuple[str, str]:
        return fagll03.descargar(
            self.session,
            list(sociedades),
            date(2026, 10, 28),
            self.carpeta,
            archivo_maestro=self.maestro,
        )

    def test_runs_steps_in_recording_order(self) -> None:
        self._descargar()
        orden = [
            ("wnd[0]/tbar[0]/okcd", "text=", "/nFAGLL03"),
            ("wnd[0]/usr/btn%_SD_SAKNR_%_APP_%-VALU_PUSH", "press"),
            ("wnd[0]/usr/btn%_SD_BUKRS_%_APP_%-VALU_PUSH", "press"),
            (comun.ID_CALENDARIO, "selectionInterval=", "20261028,20261028"),
            ("wnd[0]/tbar[1]/btn[8]", "press"),
            (comun.ID_GRILLA_DISPOSICIONES, "currentCellRow=", 1),
            ("wnd[0]/mbar/menu[0]/menu[3]/menu[1]", "select"),
            ("wnd[1]/tbar[0]/btn[0]", "press"),
            ("wnd[0]/tbar[0]/okcd", "text=", "/n"),
        ]
        indices = [self.session.actions.index(a) for a in orden]
        self.assertEqual(indices, sorted(indices))

    def test_pastes_master_accounts_then_companies(self) -> None:
        """Dos listas por el portapapeles, en el orden de la grabación."""
        self._descargar()
        self.assertEqual(self.pegados, ["1317210105\r\n2424067700", "ISA\r\nTRAN"])

    def test_saves_with_fagll03_prefix(self) -> None:
        carpeta, nombre = self._descargar()
        self.assertEqual(carpeta, str(self.carpeta))
        self.assertRegex(nombre, r"^FAGLL03_\d{8}_\d{6}\.xlsx$")
        self.assertIn(("wnd[1]/usr/ctxtDY_FILENAME", "text=", nombre), self.session.actions)

    def test_uses_latest_master_in_salida_by_default(self) -> None:
        with patch("fagll03.validar_maestro", return_value=self.maestro) as validar:
            fagll03.descargar(self.session, ["AM"], date(2026, 10, 28), self.carpeta)
        validar.assert_called_once()
        self.assertEqual(self.pegados[0], "2810050500")

    def test_master_problems_do_not_touch_sap(self) -> None:
        with self.assertRaises(ValueError):
            self._descargar(sociedades=["RIOS"])  # sin cuentas PI = X
        with (
            patch("fagll03.validar_maestro", side_effect=ValueError("sin maestro")),
            self.assertRaises(ValueError),
        ):
            fagll03.descargar(self.session, ["ISA"], date(2026, 10, 28), self.carpeta)
        self.assertEqual(self.session.actions, [])

    def test_no_items_stops_after_execute(self) -> None:
        """REGRESIÓN 2026-10-29: FBL5N solo con AM no tenía partidas; SAP se
        quedó en la pantalla de selección y la app siguió hasta fallar al
        buscar la lista de disposiciones ("control could not be found")."""
        session = helpers.MockSession()  # sin simular la lista de resultados
        session.mostrar("wnd[0]/sbar", "No se seleccionaron partidas")
        with self.assertRaises(comun.SinResultadosError) as ctx:
            fagll03.descargar(
                session, ["ISA"], date(2026, 10, 29), self.carpeta, archivo_maestro=self.maestro
            )
        self.assertIn("ISA", str(ctx.exception))
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
        with redirect_stdout(out), redirect_stderr(err), patch("fagll03.configurar_logging"):
            codigo = fagll03.main(argv)
        return codigo, out.getvalue(), err.getvalue()

    def test_no_arguments_is_usage_error(self) -> None:
        self.assertEqual(self._main([])[0], 2)

    def test_missing_master_returns_1(self) -> None:
        with patch(
            "fagll03.validar_maestro", side_effect=ValueError("Primero descarga el Maestro")
        ):
            codigo, _, err = self._main(["28.10.2026"])
        self.assertEqual(codigo, 1)
        self.assertIn("Maestro", err)

    def test_happy_path_defaults_to_all_companies(self) -> None:
        descargar = MagicMock(return_value=("C:/salida", "FAGLL03_x.xlsx"))
        with (
            patch("fagll03.validar_maestro"),
            patch("fagll03.get_sap_session", return_value="sesion"),
            patch("fagll03.descargar", descargar),
        ):
            codigo, out, _ = self._main(["28.10.2026"])
        self.assertEqual(codigo, 0)
        self.assertIn("FAGLL03_x.xlsx", out)
        self.assertEqual(descargar.call_args[0][1], sociedades.codigos())


if __name__ == "__main__":
    unittest.main()
