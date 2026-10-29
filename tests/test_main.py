"""Tests de src/main.py: ventana, menú, vistas y utilidades de la GUI."""

import sys
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

    def test_pending_view_names_its_transaction(self) -> None:
        frame = main.abrir_partidas_mayor(self.root, self.parent)
        try:
            self.assertIn("FAGLL03", frame.lbl_pendiente.cget("text"))
        finally:
            frame.btn_atras.invoke()


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


class AbrirAcreedoresTest(_TkTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root._logo_ref = None
        self.parent = tk.Frame(self.root)
        self.parent.pack(fill="both", expand=True)
        self.frame = main.abrir_acreedores(self.root, self.parent)

    def test_all_companies_checked_by_default(self) -> None:
        self.assertEqual(list(self.frame.vars_sociedades), list(comun.SOCIEDADES))
        self.assertTrue(all(v.get() for v in self.frame.vars_sociedades.values()))

    def test_none_and_all_buttons_toggle_every_company(self) -> None:
        self.frame.btn_ninguna.invoke()
        self.assertFalse(any(v.get() for v in self.frame.vars_sociedades.values()))
        self.frame.btn_todas.invoke()
        self.assertTrue(all(v.get() for v in self.frame.vars_sociedades.values()))

    def test_key_date_defaults_to_today(self) -> None:
        self.assertEqual(self.frame.entry_fecha.get_date(), date.today())

    def test_key_date_entry_does_not_validate_on_key(self) -> None:
        """REGRESIÓN heredada de activos-propios-py: `validate="key"` en un
        DateEntry rompe la selección desde el calendario."""
        self.assertNotIn(str(self.frame.entry_fecha.cget("validate")), ("key", "all"))

    def test_download_button_passes_checked_companies_and_date(self) -> None:
        self.frame.btn_ninguna.invoke()
        self.frame.vars_sociedades["ISA"].set(True)
        self.frame.vars_sociedades["XM"].set(True)
        self.frame.entry_fecha.set_date(date(2026, 9, 30))
        with patch("main._descargar_fbl1n_handler") as handler:
            self.frame.btn_descargar.invoke()
        args = handler.call_args[0]
        self.assertEqual(args[1], ["ISA", "XM"])
        self.assertEqual(args[2], date(2026, 9, 30))
        self.assertIs(args[4], self.frame.btn_descargar)
        self.assertIs(args[5], self.frame.btn_atras)


class DescargarFbl1nHandlerTest(_TkTestCase):
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

    def _llamar(self, sociedades=("ISA",), fecha=date(2026, 10, 28)) -> None:
        main._descargar_fbl1n_handler(
            self.root, list(sociedades), fecha, self.status_var, self.button, self.btn_atras
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
        with (
            patch.object(fbl1n, "DISPOSICION", None),
            patch("main.messagebox.showerror") as mock_err,
            patch("main.messagebox.askyesno") as mock_ask,
        ):
            self._llamar()
        mock_ask.assert_not_called()
        self.assertIn("disposición", mock_err.call_args[0][1])

    def test_confirmation_warns_about_clipboard_and_summarizes_companies(self) -> None:
        with (
            patch("main.messagebox.askyesno", return_value=False) as mock_ask,
        ):
            self._llamar(sociedades=comun.SOCIEDADES)
        mensaje = mock_ask.call_args[0][1]
        self.assertIn("portapapeles", mensaje)
        self.assertIn("todas las sociedades (28)", mensaje)
        self.assertIn("28.10.2026", mensaje)

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
            "descargar_fbl1n": MagicMock(return_value=("C:/app/salida", "FBL1N_x.xlsx")),
        }
        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.messagebox.showinfo") as mock_info,
            self._sync_thread(),
            patch.multiple("fbl1n", **mocks),
        ):
            self._llamar(sociedades=["xm", "ISA"])
        mocks["descargar_fbl1n"].assert_called_once_with(
            "sesion", ["ISA", "XM"], date(2026, 10, 28), progreso=ANY
        )
        self.assertIn("FBL1N_x.xlsx", mock_info.call_args[0][1])
        self.assertEqual(str(self.button["state"]), "normal")
        self.assertEqual(str(self.btn_atras["state"]), "normal")
        self.assertEqual(self.status_var.get(), "")

    def test_flow_error_shows_message_and_reenables(self) -> None:
        mocks = {
            "get_sap_session": MagicMock(return_value="sesion"),
            "descargar_fbl1n": MagicMock(side_effect=RuntimeError("Falló: Ejecutar el reporte")),
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
        def descargar(session, socs, fecha, progreso):
            progreso("Paso 4 de 7: ejecutando el reporte…")
            self.assertEqual(self.status_var.get(), "Paso 4 de 7: ejecutando el reporte…")
            return ("C:/salida", "FBL1N_x.xlsx")

        with (
            patch("main.messagebox.askyesno", return_value=True),
            patch("main.messagebox.showinfo"),
            self._sync_thread(),
            patch.multiple("fbl1n", get_sap_session=MagicMock(), descargar_fbl1n=descargar),
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
