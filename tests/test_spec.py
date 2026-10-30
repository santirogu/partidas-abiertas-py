"""Tests de PartidasAbiertas.spec: que el .exe empaquete lo que la app usa.

Un error en el spec no se nota al desarrollar: el .exe arranca y falla
recién al pulsar una opción. Estos tests leen el spec (sin ejecutarlo) y lo
comparan con el código.
"""

import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: F401  (agrega src/ al sys.path)

import branding
import comun
import main
import paths
import sociedades

SPEC = paths.PROJECT_ROOT / "PartidasAbiertas.spec"


def _constantes_del_spec() -> dict:
    """Asignaciones simples del spec (`NOMBRE = <literal>`)."""
    arbol = ast.parse(SPEC.read_text(encoding="utf-8"))
    constantes = {}
    for nodo in arbol.body:
        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
            destino = nodo.targets[0]
            if isinstance(destino, ast.Name):
                try:
                    constantes[destino.id] = ast.literal_eval(nodo.value)
                except ValueError:
                    pass  # no es un literal (p. ej. Analysis(...)); no interesa
    return constantes


class SpecTest(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = _constantes_del_spec()

    def test_every_flow_module_is_bundled(self) -> None:
        """REGRESIÓN preventiva: los flujos se importan con importlib y
        PyInstaller no los detecta; si falta uno, su opción falla en el .exe."""
        self.assertEqual(
            sorted(self.spec["MODULOS_DE_FLUJO"]), sorted(o.modulo for o in main.OPCIONES)
        )

    def test_bundles_the_resources_the_app_reads(self) -> None:
        empaquetados = {origen for origen, _ in self.spec["DATOS"]}
        for recurso in (branding.LOGO_PATH, sociedades.INICIALES_PATH):
            with self.subTest(recurso=recurso.name):
                relativo = recurso.relative_to(paths.PROJECT_ROOT).as_posix()
                self.assertIn(relativo, empaquetados)

    def test_bundled_files_exist_and_land_in_resources(self) -> None:
        for origen, destino in self.spec["DATOS"]:
            with self.subTest(origen=origen):
                self.assertTrue((paths.PROJECT_ROOT / origen).exists())
                self.assertEqual(destino, "resources")

    def test_recordings_and_examples_are_not_bundled(self) -> None:
        for origen, _ in self.spec["DATOS"]:
            self.assertNotIn("grabaciones", origen)
            self.assertNotIn("ejemplos", origen)

    def test_names_and_colors_match_the_code(self) -> None:
        self.assertEqual(self.spec["TITULO_APP"], comun.TITULO_APP)
        self.assertEqual(self.spec["COLOR_PRIMARIO"], branding.COLOR_PRIMARIO)
        self.assertEqual(self.spec["NOMBRE_EXE"], "PartidasAbiertas")

    def test_no_upx_compression(self) -> None:
        """UPX hace más probable que el antivirus corporativo marque el .exe."""
        self.assertIn("upx=False", SPEC.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
