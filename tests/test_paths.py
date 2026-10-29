"""Tests de src/paths.py: rutas en modo dev y empaquetado."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: F401  (agrega src/ al sys.path)

import paths


class ProjectRootTest(unittest.TestCase):
    def test_dev_mode_returns_repo_root(self) -> None:
        repo = Path(__file__).resolve().parent.parent
        self.assertEqual(paths.project_root(), repo)

    def test_frozen_mode_returns_exe_folder(self) -> None:
        """Empaquetado, la raíz es la carpeta del `.exe`, no `_MEIPASS`:
        ahí es donde el usuario espera encontrar `salida/`."""
        fake_exe = Path("/fake/app/PartidasAbiertas.exe")
        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(sys, "executable", str(fake_exe)),
            patch.object(sys, "_MEIPASS", "/tmp/_MEI123", create=True),
        ):
            self.assertEqual(paths.project_root(), fake_exe.parent.resolve())


class CarpetasDeSalidaTest(unittest.TestCase):
    def test_salida_lives_in_project_root(self) -> None:
        self.assertEqual(paths.SALIDA_DIR, paths.PROJECT_ROOT / "salida")

    def test_logs_live_inside_salida(self) -> None:
        self.assertEqual(paths.LOGS_DIR.parent, paths.SALIDA_DIR)


class BundledResourcePathTest(unittest.TestCase):
    def test_dev_mode_resolves_inside_repo(self) -> None:
        with patch.object(sys, "_MEIPASS", None, create=True):
            ruta = paths.bundled_resource_path("resources/logo.png")
        self.assertEqual(ruta, paths.PROJECT_ROOT / "resources" / "logo.png")

    def test_frozen_mode_resolves_inside_meipass(self) -> None:
        with patch.object(sys, "_MEIPASS", "/fake/_MEIPASS", create=True):
            ruta = paths.bundled_resource_path("resources/logo.png")
        self.assertEqual(ruta, Path("/fake/_MEIPASS") / "resources" / "logo.png")

    def test_logo_exists_in_repo(self) -> None:
        """El logo se versiona en resources/ y el `.spec` lo empaqueta."""
        self.assertTrue(paths.bundled_resource_path("resources/logo.png").exists())


if __name__ == "__main__":
    unittest.main()
