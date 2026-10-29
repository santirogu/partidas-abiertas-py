"""Tests de src/main.py: ventana, menú, vistas y utilidades de la GUI."""

import importlib
import inspect
import sys
import tempfile
import tkinter as tk
import types
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers

import branding
import comun
import fbl1n
import fbl5n
import main
import paths


class _TkTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()


def _textos_de_labels(frame: tk.Misc) -> list[str]:
    return [str(w.cget("text")) for w in frame.winfo_children() if isinstance(w, tk.Label)]


class OpcionesTest(unittest.TestCase):
    def test_options_follow_process_order(self) -> None:
        """El maestro de cuentas (Y_FI_GRL_004) alimenta a FAGLL03, así que
        el menú las muestra en el orden del proceso."""
        self.assertEqual(
            [o.transaccion for o in main.OPCIONES],
            ["FBL1N", "FBL5N", "Y_FI_GRL_004", "FAGLL03"],
        )

    def test_each_option_has_its_recording(self) -> None:
        carpeta = paths.PROJECT_ROOT / "resources" / "grabaciones"
        for opcion in main.OPCIONES:
            with self.subTest(transaccion=opcion.transaccion):
                self.assertTrue((carpeta / f"{opcion.transaccion}.vbs").exists())

    def test_each_option_has_a_view_and_a_valid_style(self) -> None:
        self.assertEqual(set(main.VISTAS), {o.clave for o in main.OPCIONES})
        for opcion in main.OPCIONES:
            with self.subTest(clave=opcion.clave):
                self.assertIn(opcion.estilo, branding._BUTTON_STYLES)

    def test_modules_follow_the_flow_contract(self) -> None:
        """La GUI llama a cualquier flujo de la misma forma: si un módulo
        no cumple el contrato, el error saldría recién al usar el botón."""
        self.assertEqual(
            [o.modulo for o in main.OPCIONES], ["fbl1n", "fbl5n", "y_fi_grl_004", "fagll03"]
        )
        for opcion in main.OPCIONES:
            with self.subTest(modulo=opcion.modulo):
                flujo = importlib.import_module(opcion.modulo)
                self.assertEqual(flujo.TRANSACCION, opcion.transaccion)
                for nombre in ("validar_configuracion", "get_sap_session", "descargar"):
                    self.assertTrue(callable(getattr(flujo, nombre)), nombre)
                parametros = inspect.signature(flujo.descargar).parameters
                self.assertIn("progreso", parametros)
                self.assertEqual("fecha_clave" in parametros, opcion.usa_fecha_clave)

    def test_required_options_exist_and_come_before(self) -> None:
        """FAGLL03 necesita el maestro: la opción requerida debe existir y
        aparecer antes en el menú (el orden del proceso)."""
        claves = [o.clave for o in main.OPCIONES]
        for opcion in main.OPCIONES:
            if opcion.requiere:
                with self.subTest(clave=opcion.clave):
                    self.assertIn(opcion.requiere, claves)
                    self.assertLess(claves.index(opcion.requiere), claves.index(opcion.clave))
        self.assertEqual(main._opcion("partidas_mayor").requiere, "maestro_cuentas")


class CrearAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = main.crear_app()
        self.root.withdraw()

    def tearDown(self) -> None:
        self.root.destroy()

    def test_window_title_matches_titulo_app(self) -> None:
        """REGRESIÓN heredada (bug #5 de activos-propios-py): el título de
        la ventana y la constante con que se busca la ventana divergieron.
        Aquí ambos salen de `comun.TITULO_APP`."""
        self.assertEqual(self.root.title(), comun.TITULO_APP)

    def test_window_is_not_resizable(self) -> None:
        self.assertEqual(tuple(bool(v) for v in self.root.resizable()), (False, False))

    def test_menu_is_packed_with_one_button_per_option(self) -> None:
        self.assertEqual(self.root.frame_menu.winfo_manager(), "pack")
        self.assertEqual(set(self.root.frame_menu.botones), {o.clave for o in main.OPCIONES})

    def test_installs_exception_handler(self) -> None:
        self.assertEqual(self.root.report_callback_exception.__name__, "handler")

    def test_keeps_logo_reference_on_root(self) -> None:
        self.assertIsNotNone(self.root._logo_ref)


class ConstruirMenuTest(_TkTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root._logo_ref = None
        self.frame_menu = main.construir_menu(self.root)
        self.frame_menu.pack(fill="both", expand=True)

    def test_shows_app_title(self) -> None:
        self.assertIn(comun.TITULO_APP, _textos_de_labels(self.frame_menu))

    def test_cards_are_laid_out_in_two_by_two_grid(self) -> None:
        cuadricula = next(w for w in self.frame_menu.winfo_children() if isinstance(w, tk.Frame))
        posiciones = sorted(
            (int(c.grid_info()["row"]), int(c.grid_info()["column"]))
            for c in cuadricula.winfo_children()
        )
        self.assertEqual(posiciones, [(0, 0), (0, 1), (1, 0), (1, 1)])

    def test_each_card_button_opens_its_view(self) -> None:
        for opcion in main.OPCIONES:
            with self.subTest(clave=opcion.clave):
                self.frame_menu.botones[opcion.clave].invoke()
                vistas = [
                    w for w in self.root.winfo_children() if getattr(w, "opcion", None) == opcion
                ]
                self.assertEqual(len(vistas), 1)
                self.assertEqual(self.frame_menu.winfo_manager(), "")
                vistas[0].btn_atras.invoke()


class VistasTest(_TkTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root._logo_ref = None
        self.parent = tk.Frame(self.root)
        self.parent.pack(fill="both", expand=True)

    def test_view_hides_parent_and_shows_title(self) -> None:
        for clave, abrir in main.VISTAS.items():
            with self.subTest(clave=clave):
                frame = abrir(self.root, self.parent)
                try:
                    self.assertEqual(self.parent.winfo_manager(), "")
                    self.assertEqual(frame.opcion.clave, clave)
                    self.assertIn(frame.opcion.titulo, _textos_de_labels(frame))
                    self.assertIn(frame.opcion.subtitulo, _textos_de_labels(frame))
                finally:
                    frame.btn_atras.invoke()

    def test_back_button_destroys_view_and_restores_parent(self) -> None:
        for clave, abrir in main.VISTAS.items():
            with self.subTest(clave=clave):
                frame = abrir(self.root, self.parent)
                self.assertIsInstance(frame.btn_atras, branding.RoundedButton)
                frame.btn_atras.invoke()
                self.assertFalse(frame.winfo_exists())
                self.assertEqual(self.parent.winfo_manager(), "pack")


class CardVisualTest(_TkTestCase):
    def test_fixed_size_card_does_not_propagate(self) -> None:
        card, _ = main._crear_card_visual(
            self.root,
            titulo="T",
            etiqueta="FBL1N",
            descripcion="D",
            btn_texto="B",
            btn_style="primary",
            width=200,
            height=150,
        )
        self.assertFalse(card.pack_propagate())
        self.assertIn("FBL1N", _textos_de_labels(card))

    def test_disabled_card_button_starts_disabled(self) -> None:
        _, boton = main._crear_card_visual(
            self.root,
            titulo="T",
            etiqueta=None,
            descripcion="D",
            btn_texto="B",
            btn_style="primary",
            disabled=True,
        )
        self.assertEqual(boton.cget("state"), "disabled")


class FooterCopyrightTest(_TkTestCase):
    def test_label_includes_current_year_and_owner(self) -> None:
        footer = main._crear_footer_copyright(self.root)
        texto = footer.cget("text")
        self.assertIn(f"© {datetime.now().year}", texto)
        self.assertIn(comun.TITULAR, texto)

    def test_packed_at_bottom(self) -> None:
        footer = main._crear_footer_copyright(self.root)
        self.assertEqual(footer.pack_info()["side"], "bottom")


class InstallTkExceptionHandlerTest(_TkTestCase):
    def test_handler_logs_and_shows_dialog(self) -> None:
        main._install_tk_exception_handler(self.root)
        try:
            raise ValueError("error en callback")
        except ValueError:
            info = sys.exc_info()
        with (
            patch("main.messagebox.showerror") as mock_err,
            self.assertLogs(comun.logger, level="ERROR"),
        ):
            self.root.report_callback_exception(*info)
        titulo, mensaje = mock_err.call_args[0][:2]
        self.assertEqual(titulo, "Error inesperado")
        self.assertIn("ValueError", mensaje)
        self.assertIn("error en callback", mensaje)


class ShowUnexpectedErrorTest(unittest.TestCase):
    def test_shows_type_message_and_traceback(self) -> None:
        try:
            raise KeyError("columna")
        except KeyError as exc:
            error = exc
        with (
            patch("main.messagebox.showerror") as mock_err,
            self.assertLogs(comun.logger, level="ERROR") as logs,
        ):
            main._show_unexpected_error("Error en el flujo", error)
        titulo, mensaje = mock_err.call_args[0][:2]
        self.assertEqual(titulo, "Error en el flujo")
        self.assertIn("KeyError", mensaje)
        self.assertIn("Detalle técnico", mensaje)
        self.assertIn("Error en el flujo", logs.output[0])


class CerrarSplashTest(unittest.TestCase):
    def test_noop_when_pyi_splash_absent(self) -> None:
        with patch.dict(sys.modules, {"pyi_splash": None}):
            main._cerrar_splash()

    def test_closes_splash_when_alive(self) -> None:
        splash = types.SimpleNamespace(is_alive=MagicMock(return_value=True), close=MagicMock())
        with patch.dict(sys.modules, {"pyi_splash": splash}):
            main._cerrar_splash()
        splash.close.assert_called_once()

    def test_does_not_close_when_not_alive(self) -> None:
        splash = types.SimpleNamespace(is_alive=MagicMock(return_value=False), close=MagicMock())
        with patch.dict(sys.modules, {"pyi_splash": splash}):
            main._cerrar_splash()
        splash.close.assert_not_called()

    def test_splash_failure_does_not_break_startup(self) -> None:
        splash = types.SimpleNamespace(
            is_alive=MagicMock(return_value=True), close=MagicMock(side_effect=RuntimeError("x"))
        )
        with patch.dict(sys.modules, {"pyi_splash": splash}):
            main._cerrar_splash()


class VistaDescargaTest(_TkTestCase):
    """Vistas de descarga de las 4 opciones."""

    def setUp(self) -> None:
        super().setUp()
        self.root._logo_ref = None
        self.parent = tk.Frame(self.root)
        self.parent.pack(fill="both", expand=True)
        self._tmp = tempfile.TemporaryDirectory()
        self.salida = Path(self._tmp.name)
        self._salida = patch("main.SALIDA_DIR", self.salida)
        self._salida.start()

    def tearDown(self) -> None:
        self._salida.stop()
        self._tmp.cleanup()
        super().tearDown()

    def _abrir(self, clave: str) -> tk.Frame:
        frame = main.VISTAS[clave](self.root, self.parent)
        return frame

    def test_all_companies_checked_by_default(self) -> None:
        for clave in main.VISTAS:
            with self.subTest(clave=clave):
                frame = self._abrir(clave)
                self.assertEqual(list(frame.vars_sociedades), list(comun.SOCIEDADES))
                self.assertTrue(all(v.get() for v in frame.vars_sociedades.values()))
                frame.btn_atras.invoke()

    def test_none_and_all_buttons_toggle_every_company(self) -> None:
        frame = self._abrir("deudores")
        frame.btn_ninguna.invoke()
        self.assertFalse(any(v.get() for v in frame.vars_sociedades.values()))
        frame.btn_todas.invoke()
        self.assertTrue(all(v.get() for v in frame.vars_sociedades.values()))

    def test_button_names_the_transaction(self) -> None:
        for clave, transaccion in (("acreedores", "FBL1N"), ("maestro_cuentas", "Y_FI_GRL_004")):
            with self.subTest(clave=clave):
                frame = self._abrir(clave)
                self.assertEqual(frame.btn_descargar.cget("text"), f"Descargar {transaccion}")
                frame.btn_atras.invoke()

    def test_key_date_only_where_the_flow_uses_it(self) -> None:
        for clave, usa_fecha in (
            ("acreedores", True),
            ("deudores", True),
            ("maestro_cuentas", False),
            ("partidas_mayor", True),
        ):
            with self.subTest(clave=clave):
                frame = self._abrir(clave)
                self.assertEqual(frame.entry_fecha is not None, usa_fecha)
                frame.btn_atras.invoke()

    def test_key_date_defaults_to_today(self) -> None:
        self.assertEqual(self._abrir("acreedores").entry_fecha.get_date(), date.today())

    def test_key_date_entry_does_not_validate_on_key(self) -> None:
        """REGRESIÓN heredada de activos-propios-py: `validate="key"` en un
        DateEntry rompe la selección desde el calendario."""
        frame = self._abrir("acreedores")
        self.assertNotIn(str(frame.entry_fecha.cget("validate")), ("key", "all"))

    def test_download_button_passes_option_companies_and_date(self) -> None:
        frame = self._abrir("deudores")
        frame.btn_ninguna.invoke()
        frame.vars_sociedades["ISA"].set(True)
        frame.vars_sociedades["XM"].set(True)
        frame.entry_fecha.set_date(date(2026, 9, 30))
        with patch("main._descargar_handler") as handler:
            frame.btn_descargar.invoke()
        args = handler.call_args[0]
        self.assertEqual(args[1].clave, "deudores")
        self.assertEqual(args[2], ["ISA", "XM"])
        self.assertEqual(args[3], date(2026, 9, 30))
        self.assertIs(args[5], frame.btn_descargar)
        self.assertIs(args[6], frame.btn_atras)

    def test_download_without_key_date_passes_none(self) -> None:
        frame = self._abrir("maestro_cuentas")
        with patch("main._descargar_handler") as handler:
            frame.btn_descargar.invoke()
        self.assertIsNone(handler.call_args[0][3])

    def test_only_fagll03_shows_a_required_file(self) -> None:
        for clave in ("acreedores", "deudores", "maestro_cuentas"):
            with self.subTest(clave=clave):
                frame = self._abrir(clave)
                self.assertIsNone(frame.lbl_requisito)
                frame.btn_atras.invoke()

    def test_fagll03_without_master_disables_download(self) -> None:
        frame = self._abrir("partidas_mayor")
        self.assertEqual(frame.btn_descargar.cget("state"), "disabled")
        self.assertIn("Falta el maestro de cuentas", frame.lbl_requisito.cget("text"))

    def test_fagll03_names_the_latest_master(self) -> None:
        for nombre in ("Y_FI_GRL_004_20261027_090000.xlsx", "Y_FI_GRL_004_20261028_225628.xlsx"):
            (self.salida / nombre).write_bytes(b"x")
        frame = self._abrir("partidas_mayor")
        self.assertEqual(frame.btn_descargar.cget("state"), "normal")
        self.assertIn("Y_FI_GRL_004_20261028_225628.xlsx", frame.lbl_requisito.cget("text"))


class DescargarHandlerTest(_TkTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root.after = lambda delay, fn, *args: fn(*args)  # UI síncrona
        self.status_var = tk.StringVar(master=self.root)
        self.button = tk.Button(self.root)
        self.btn_atras = tk.Button(self.root)
        self._disposicion = patch.object(fbl1n, "DISPOSICION", "/PARTABIERTA")
        self._disposicion.start()

    def tearDown(self) -> None:
        self._disposicion.stop()
        super().tearDown()

    def _llamar(self, clave="acreedores", sociedades=("ISA",), fecha=date(2026, 10, 28)) -> None:
        main._descargar_handler(
            self.root,
            main._opcion(clave),
            list(sociedades),
            fecha,
            self.status_var,
            self.button,
            self.btn_atras,
        )

    def _sync_thread(self):
        return patch(
            "main.threading.Thread",
            side_effect=lambda target=None, **kw: helpers.SyncFakeThread(target),
        )

    def test_cancel_does_not_start_thread(self) -> None:
        with (
            patch("main.messagebox.askyesno", return_value=False),
            patch("main.threading.Thread") as mock_thread,
        ):
            self._llamar()
        mock_thread.assert_not_called()

    def test_no_company_shows_error_without_confirming(self) -> None:
        with (
            patch("main.messagebox.showerror") as mock_err,
            patch("main.messagebox.askyesno") as mock_ask,
        ):
            self._llamar(sociedades=[])
        mock_ask.assert_not_called()
        self.assertEqual(mock_err.call_args[0][0], "Datos inválidos")

    def test_pending_layout_shows_error(self) -> None:
        """Si un flujo no tiene disposición configurada, la app avisa sin
        tocar SAP."""
        with (
            patch.object(fbl5n, "DISPOSICION", None),
            patch("main.messagebox.showerror") as mock_err,
            patch("main.messagebox.askyesno") as mock_ask,
        ):
            self._llamar(clave="deudores")
        mock_ask.assert_not_called()
        self.assertIn("FBL5N", mock_err.call_args[0][1])

    def test_missing_master_shows_error_for_fagll03(self) -> None:
        with (
            patch("fagll03.validar_maestro", side_effect=ValueError("Primero descarga el Maestro")),
            patch("main.messagebox.showerror") as mock_err,
            patch("main.messagebox.askyesno") as mock_ask,
        ):
            self._llamar(clave="partidas_mayor")
        mock_ask.assert_not_called()
        self.assertIn("Maestro", mock_err.call_args[0][1])

    def test_confirmation_warns_about_clipboard_and_summarizes_companies(self) -> None:
        with patch("main.messagebox.askyesno", return_value=False) as mock_ask:
            self._llamar(sociedades=comun.SOCIEDADES)
        titulo, mensaje = mock_ask.call_args[0][:2]
        self.assertEqual(titulo, "Confirmar descarga de FBL1N")
        self.assertIn("portapapeles", mensaje)
        self.assertIn("todas las sociedades (28)", mensaje)
        self.assertIn("28.10.2026", mensaje)

    def test_confirmation_without_key_date(self) -> None:
        with patch("main.messagebox.askyesno", return_value=False) as mock_ask:
            self._llamar(clave="maestro_cuentas", fecha=None)
        self.assertNotIn("fecha clave", mock_ask.call_args[0][1])

    def test_disables_buttons_before_starting_thread(self) -> None:
        estados = {}

        class _HiloQueMira:
            def __init__(hilo, target=None, **kw) -> None:
                pass

            def start(hilo) -> None:
                estados["accion"] = str(self.button["state"])
                estados["atras"] = str(self.btn_atras["state"])

        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.threading.Thread", _HiloQueMira),
        ):
            self._llamar()
        self.assertEqual(estados, {"accion": "disabled", "atras": "disabled"})

    def test_happy_path_downloads_and_reenables(self) -> None:
        mocks = {
            "get_sap_session": MagicMock(return_value="sesion"),
            "descargar": MagicMock(return_value=("C:/app/salida", "FBL1N_x.xlsx")),
        }
        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.messagebox.showinfo") as mock_info,
            self._sync_thread(),
            patch.multiple("fbl1n", **mocks),
        ):
            self._llamar(sociedades=["xm", "ISA"])
        mocks["descargar"].assert_called_once_with(
            "sesion", ["ISA", "XM"], progreso=ANY, fecha_clave=date(2026, 10, 28)
        )
        self.assertIn("FBL1N_x.xlsx", mock_info.call_args[0][1])
        self.assertEqual(str(self.button["state"]), "normal")
        self.assertEqual(str(self.btn_atras["state"]), "normal")
        self.assertEqual(self.status_var.get(), "")

    def test_flow_without_key_date_is_called_without_it(self) -> None:
        mocks = {
            "get_sap_session": MagicMock(return_value="sesion"),
            "descargar": MagicMock(return_value=("C:/salida", "Y_FI_GRL_004_x.xlsx")),
        }
        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.messagebox.showinfo"),
            self._sync_thread(),
            patch.multiple("y_fi_grl_004", **mocks),
        ):
            self._llamar(clave="maestro_cuentas", fecha=None)
        mocks["descargar"].assert_called_once_with("sesion", ["ISA"], progreso=ANY)

    def test_flow_error_shows_message_and_reenables(self) -> None:
        mocks = {
            "get_sap_session": MagicMock(return_value="sesion"),
            "descargar": MagicMock(side_effect=RuntimeError("Falló: Ejecutar el reporte")),
        }
        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.messagebox.showerror") as mock_err,
            self._sync_thread(),
            patch.multiple("fbl1n", **mocks),
            self.assertLogs(comun.logger, level="ERROR"),
        ):
            self._llamar()
        self.assertEqual(mock_err.call_args[0][0], "Error en la descarga de FBL1N")
        self.assertIn("Ejecutar el reporte", mock_err.call_args[0][1])
        self.assertEqual(str(self.button["state"]), "normal")
        self.assertEqual(str(self.btn_atras["state"]), "normal")

    def test_progress_updates_status_label(self) -> None:
        def descargar(session, socs, progreso, fecha_clave):
            progreso("Paso 4 de 7: ejecutando el reporte…")
            self.assertEqual(self.status_var.get(), "Paso 4 de 7: ejecutando el reporte…")
            return ("C:/salida", "FBL1N_x.xlsx")

        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.messagebox.showinfo"),
            self._sync_thread(),
            patch.multiple("fbl1n", get_sap_session=MagicMock(), descargar=descargar),
        ):
            self._llamar()


class MainTest(unittest.TestCase):
    def test_configures_logging_then_closes_splash_before_mainloop(self) -> None:
        orden = MagicMock()
        root = MagicMock()
        orden.attach_mock(root.mainloop, "mainloop")
        with (
            patch("main.configurar_logging", return_value=None) as mock_logging,
            patch("main.crear_app", return_value=root),
            patch("main._cerrar_splash", orden.cerrar_splash),
        ):
            main.main()
        mock_logging.assert_called_once()
        self.assertEqual(orden.mock_calls, [call.cerrar_splash(), call.mainloop()])


if __name__ == "__main__":
    unittest.main()
