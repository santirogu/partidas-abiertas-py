"""Tests de src/comun.py: logging, conexión SAP, COM y archivos."""

import io
import logging
import sys
import tempfile
import types
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers

import comun


class ConfigurarLoggingTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        comun.cerrar_logging()
        # El handler de consola escribe en este buffer y no ensucia la
        # salida de la suite.
        self._stdout = patch.object(sys, "stdout", io.StringIO())
        self._stdout.start()

    def tearDown(self) -> None:
        comun.cerrar_logging()
        self._stdout.stop()
        self._tmp.cleanup()

    def _handlers_propios(self) -> list[logging.Handler]:
        return [h for h in comun.logger.handlers if getattr(h, comun._MARCA_HANDLER, False)]

    def test_writes_messages_to_log_file(self) -> None:
        archivo = comun.configurar_logging(self.tmp / "logs")
        comun.log("mensaje de prueba")
        for h in self._handlers_propios():
            h.flush()
        self.assertEqual(archivo, self.tmp / "logs" / comun.LOG_ARCHIVO_NOMBRE)
        self.assertIn("mensaje de prueba", archivo.read_text(encoding="utf-8"))

    def test_is_idempotent(self) -> None:
        primero = comun.configurar_logging(self.tmp)
        cantidad = len(self._handlers_propios())
        segundo = comun.configurar_logging(self.tmp)
        self.assertEqual(primero, segundo)
        self.assertEqual(len(self._handlers_propios()), cantidad)

    def test_skips_console_handler_when_stdout_is_none(self) -> None:
        """REGRESIÓN preventiva: el `.exe` sin consola tiene `sys.stdout =
        None`; un `StreamHandler(None)` fallaría en cada mensaje."""
        with patch.object(sys, "stdout", None):
            comun.configurar_logging(self.tmp)
        tipos = [type(h) for h in self._handlers_propios()]
        self.assertNotIn(logging.StreamHandler, tipos)
        self.assertEqual(len(tipos), 1)

    def test_returns_none_when_folder_cannot_be_created(self) -> None:
        with patch.object(Path, "mkdir", side_effect=PermissionError("sin permiso")):
            self.assertIsNone(comun.configurar_logging(self.tmp / "logs"))
        comun.log("la app sigue funcionando")

    def test_cerrar_logging_removes_only_own_handlers(self) -> None:
        ajeno = logging.NullHandler()
        comun.logger.addHandler(ajeno)
        try:
            comun.configurar_logging(self.tmp)
            comun.cerrar_logging()
            self.assertEqual(self._handlers_propios(), [])
            self.assertIn(ajeno, comun.logger.handlers)
        finally:
            comun.logger.removeHandler(ajeno)


class EjecutarTest(unittest.TestCase):
    def test_returns_function_result(self) -> None:
        self.assertEqual(comun.ejecutar("sumar", lambda a, b: a + b, 2, b=3), 5)

    def test_wraps_errors_with_step_description(self) -> None:
        """Los errores COM suelen venir vacíos: el mensaje debe decir qué
        paso falló y conservar la causa original."""

        def falla() -> None:
            raise OSError("")

        with self.assertRaises(RuntimeError) as ctx:
            comun.ejecutar("Presionar Ejecutar", falla)
        self.assertIn("Falló: Presionar Ejecutar", str(ctx.exception))
        self.assertIsInstance(ctx.exception.__cause__, OSError)


class GetSapSessionTest(unittest.TestCase):
    def _fake_win32com(self, get_object: MagicMock) -> dict:
        cliente = types.ModuleType("win32com.client")
        cliente.GetObject = get_object
        paquete = types.ModuleType("win32com")
        paquete.client = cliente
        return {"win32com": paquete, "win32com.client": cliente}

    def _engine(self, conexiones: int, sesiones: int) -> tuple[MagicMock, MagicMock]:
        session = MagicMock(name="session")
        connection = MagicMock()
        connection.Children.Count = sesiones
        connection.Children.return_value = session
        application = MagicMock()
        application.Children.Count = conexiones
        application.Children.return_value = connection
        sap_gui = MagicMock()
        sap_gui.GetScriptingEngine = application
        return MagicMock(return_value=sap_gui), session

    def test_raises_when_pywin32_missing(self) -> None:
        with patch.dict(sys.modules, {"win32com": None, "win32com.client": None}):
            with self.assertRaises(RuntimeError) as ctx:
                comun.get_sap_session()
        self.assertIn("pywin32", str(ctx.exception))

    def test_raises_when_sap_gui_not_running(self) -> None:
        get_object = MagicMock(side_effect=OSError("Operación no disponible"))
        with patch.dict(sys.modules, self._fake_win32com(get_object)):
            with self.assertRaises(RuntimeError) as ctx:
                comun.get_sap_session()
        self.assertIn("No se pudo conectar a SAP GUI", str(ctx.exception))

    def test_raises_when_no_connections(self) -> None:
        get_object, _ = self._engine(conexiones=0, sesiones=0)
        with patch.dict(sys.modules, self._fake_win32com(get_object)):
            with self.assertRaises(RuntimeError) as ctx:
                comun.get_sap_session()
        self.assertIn("no hay conexiones", str(ctx.exception))

    def test_raises_when_no_sessions(self) -> None:
        get_object, _ = self._engine(conexiones=1, sesiones=0)
        with patch.dict(sys.modules, self._fake_win32com(get_object)):
            with self.assertRaises(RuntimeError) as ctx:
                comun.get_sap_session()
        self.assertIn("Inicia sesión en SAP", str(ctx.exception))

    def test_returns_first_session_of_first_connection(self) -> None:
        get_object, session = self._engine(conexiones=1, sesiones=2)
        with patch.dict(sys.modules, self._fake_win32com(get_object)):
            self.assertIs(comun.get_sap_session(), session)
        get_object.assert_called_once_with("SAPGUI")


class ComApartmentTest(unittest.TestCase):
    def test_is_noop_without_pythoncom(self) -> None:
        with patch.dict(sys.modules, {"pythoncom": None}):
            with comun.com_apartment():
                pass

    def test_initializes_and_releases_com(self) -> None:
        pythoncom = MagicMock()
        with patch.dict(sys.modules, {"pythoncom": pythoncom}):
            with comun.com_apartment():
                pythoncom.CoInitialize.assert_called_once()
                pythoncom.CoUninitialize.assert_not_called()
        pythoncom.CoUninitialize.assert_called_once()

    def test_releases_com_even_when_body_fails(self) -> None:
        pythoncom = MagicMock()
        with patch.dict(sys.modules, {"pythoncom": pythoncom}):
            with self.assertRaises(ValueError), comun.com_apartment():
                raise ValueError("falla el flujo")
        pythoncom.CoUninitialize.assert_called_once()

    def test_release_failure_does_not_hide_result(self) -> None:
        pythoncom = MagicMock()
        pythoncom.CoUninitialize.side_effect = OSError("ya liberado")
        with patch.dict(sys.modules, {"pythoncom": pythoncom}):
            with comun.com_apartment():
                pass


class AbrirTransaccionTest(unittest.TestCase):
    def test_maximizes_and_opens_with_n_prefix(self) -> None:
        """Las grabaciones escriben "fbl1n" sin `/n`; la app siempre usa
        `/n` para arrancar limpia desde cualquier pantalla."""
        session = helpers.MockSession()
        comun.abrir_transaccion(session, " fbl1n ")
        self.assertEqual(
            session.actions,
            [
                ("wnd[0]", "maximize"),
                ("wnd[0]/tbar[0]/okcd", "text=", "/nFBL1N"),
                ("wnd[0]", "sendVKey", 0),
            ],
        )

    def test_empty_code_raises(self) -> None:
        with self.assertRaises(ValueError):
            comun.abrir_transaccion(helpers.MockSession(), "  ")


class NombreConTimestampTest(unittest.TestCase):
    def test_builds_prefix_and_timestamp(self) -> None:
        ahora = datetime(2026, 10, 28, 15, 30, 5)
        self.assertEqual(
            comun.nombre_con_timestamp("FBL1N", ahora=ahora), "FBL1N_20261028_153005.xlsx"
        )

    def test_accepts_extension_with_dot(self) -> None:
        ahora = datetime(2026, 1, 2, 3, 4, 5)
        self.assertEqual(
            comun.nombre_con_timestamp("Log", ".txt", ahora=ahora), "Log_20260102_030405.txt"
        )


class ArchivosTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_missing_file_is_not_locked(self) -> None:
        self.assertFalse(comun.archivo_esta_bloqueado(self.tmp / "no_existe.xlsx"))

    def test_free_file_is_not_locked(self) -> None:
        archivo = helpers.crear_libro(self.tmp / "libre.xlsx", {"Hoja": [["A"]]})
        self.assertFalse(comun.archivo_esta_bloqueado(archivo))

    def test_file_open_elsewhere_is_locked(self) -> None:
        archivo = helpers.crear_libro(self.tmp / "abierto.xlsx", {"Hoja": [["A"]]})
        with patch("builtins.open", side_effect=PermissionError("en uso")):
            self.assertTrue(comun.archivo_esta_bloqueado(archivo))

    def test_guardar_workbook_seguro_saves(self) -> None:
        wb = openpyxl.Workbook()
        wb.active["A1"] = "ok"
        destino = self.tmp / "guardado.xlsx"
        comun.guardar_workbook_seguro(wb, destino)
        self.assertEqual(openpyxl.load_workbook(destino).active["A1"].value, "ok")

    def test_guardar_workbook_seguro_explains_excel_lock(self) -> None:
        wb = MagicMock()
        wb.save.side_effect = PermissionError(13, "Permission denied")
        with self.assertRaises(PermissionError) as ctx:
            comun.guardar_workbook_seguro(wb, self.tmp / "bloqueado.xlsx")
        self.assertIn("Ciérralo", str(ctx.exception))

    def test_esperar_archivo_listo_when_size_is_stable(self) -> None:
        archivo = self.tmp / "export.xlsx"
        archivo.write_bytes(b"datos")
        self.assertTrue(comun.esperar_archivo_listo(archivo, timeout_seg=1, poll_seg=0.01))

    def test_esperar_archivo_listo_times_out_when_missing(self) -> None:
        archivo = self.tmp / "nunca.xlsx"
        self.assertFalse(comun.esperar_archivo_listo(archivo, timeout_seg=0.05, poll_seg=0.01))


if __name__ == "__main__":
    unittest.main()
