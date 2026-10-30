"""Tests de src/sociedades.py: validación, operaciones y archivo de la lista."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import helpers  # noqa: F401  (agrega src/ al sys.path y aísla la lista)

import sociedades
from sociedades import Sociedad


def _lista(*codigos: str) -> list[Sociedad]:
    return [Sociedad(c) for c in codigos]


class NormalizarTest(unittest.TestCase):
    def test_code_is_uppercased_and_trimmed(self) -> None:
        self.assertEqual(sociedades.normalizar_codigo("  isa "), "ISA")

    def test_invalid_codes_raise(self) -> None:
        for codigo in ("", "   ", "ISAPX", "IS A", "IS-A", "ñ"):
            with self.subTest(codigo=codigo), self.assertRaises(ValueError):
                sociedades.normalizar_codigo(codigo)

    def test_invalid_code_message_says_the_rule(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            sociedades.normalizar_codigo("IS A")
        self.assertIn("de 1 a 4 letras o números", str(ctx.exception))

    def test_name_collapses_spaces_and_is_optional(self) -> None:
        self.assertEqual(
            sociedades.normalizar_nombre("  Interconexión   Eléctrica "), "Interconexión Eléctrica"
        )
        self.assertEqual(sociedades.normalizar_nombre(""), "")

    def test_name_too_long_raises(self) -> None:
        with self.assertRaises(ValueError):
            sociedades.normalizar_nombre("x" * (sociedades.LARGO_MAXIMO_NOMBRE + 1))


class OperacionesTest(unittest.TestCase):
    def test_agregar_keeps_alphabetical_order(self) -> None:
        resultado = sociedades.agregar(_lista("AM", "XM"), "isa", " Interconexión ")
        self.assertEqual(
            resultado, [Sociedad("AM"), Sociedad("ISA", "Interconexión"), Sociedad("XM")]
        )

    def test_agregar_duplicate_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            sociedades.agregar(_lista("ISA"), "isa")
        self.assertIn("ya está en la lista", str(ctx.exception))

    def test_agregar_does_not_change_original(self) -> None:
        original = _lista("AM")
        sociedades.agregar(original, "ISA")
        self.assertEqual(original, _lista("AM"))

    def test_modificar_name(self) -> None:
        resultado = sociedades.modificar(_lista("AM", "ISA"), "ISA", "ISA", "Interconexión")
        self.assertEqual(resultado[1], Sociedad("ISA", "Interconexión"))

    def test_modificar_code_reorders(self) -> None:
        resultado = sociedades.modificar(_lista("AM", "ISA"), "AM", "ZZ")
        self.assertEqual([s.codigo for s in resultado], ["ISA", "ZZ"])

    def test_modificar_to_existing_code_raises(self) -> None:
        with self.assertRaises(ValueError):
            sociedades.modificar(_lista("AM", "ISA"), "AM", "isa")

    def test_modificar_missing_raises(self) -> None:
        with self.assertRaises(ValueError):
            sociedades.modificar(_lista("AM"), "ISA", "ISA")

    def test_quitar(self) -> None:
        self.assertEqual(sociedades.quitar(_lista("AM", "ISA"), "AM"), _lista("ISA"))

    def test_quitar_last_one_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            sociedades.quitar(_lista("ISA"), "ISA")
        self.assertIn("al menos una", str(ctx.exception))

    def test_quitar_missing_raises(self) -> None:
        with self.assertRaises(ValueError):
            sociedades.quitar(_lista("AM"), "ISA")


class ListaInicialTest(unittest.TestCase):
    def test_initial_list_comes_from_sociedades_xlsx(self) -> None:
        """Lista entregada el 2026-10-29 (Sociedades.xlsx): 24 sociedades;
        salen INNO, REP, TELE, TELP y XM, y entra INVI."""
        codigos = [s.codigo for s in sociedades._leer(sociedades.INICIALES_PATH)]
        self.assertEqual(len(codigos), 24)
        self.assertEqual(codigos, sorted(codigos))
        self.assertIn("INVI", codigos)
        for fuera in ("INNO", "REP", "TELE", "TELP", "XM"):
            self.assertNotIn(fuera, codigos)


class ArchivoTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.archivo = Path(self._tmp.name) / "configuracion" / "sociedades.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_first_load_creates_file_with_initial_list(self) -> None:
        ruta, creado = sociedades.asegurar_archivo(self.archivo)
        self.assertTrue(creado)
        self.assertEqual(ruta, self.archivo)
        self.assertEqual(len(sociedades.codigos(self.archivo)), 24)

    def test_never_overwrites_the_user_file(self) -> None:
        sociedades.guardar(_lista("ZZ"), self.archivo)
        _, creado = sociedades.asegurar_archivo(self.archivo)
        self.assertFalse(creado)
        self.assertEqual(sociedades.codigos(self.archivo), ["ZZ"])

    def test_save_and_load_round_trip_with_names(self) -> None:
        lista = [Sociedad("ISA", "Interconexión Eléctrica"), Sociedad("AM")]
        sociedades.guardar(lista, self.archivo)
        self.assertEqual(
            sociedades.cargar(self.archivo),
            [Sociedad("AM"), Sociedad("ISA", "Interconexión Eléctrica")],
        )
        datos = json.loads(self.archivo.read_text(encoding="utf-8"))
        self.assertEqual(datos["version"], sociedades.VERSION_FORMATO)

    def test_save_leaves_no_temporary_files(self) -> None:
        sociedades.guardar(_lista("AM"), self.archivo)
        sociedades.guardar(_lista("AM", "ISA"), self.archivo)
        self.assertEqual([p.name for p in self.archivo.parent.iterdir()], ["sociedades.json"])

    def test_failed_save_keeps_previous_file(self) -> None:
        """Se escribe un temporal y luego se reemplaza: si la escritura
        falla, el archivo anterior queda intacto."""
        sociedades.guardar(_lista("AM"), self.archivo)
        with (
            patch("sociedades.json.dump", side_effect=OSError("disco lleno")),
            self.assertRaises(OSError),
        ):
            sociedades.guardar(_lista("AM", "ISA"), self.archivo)
        self.assertEqual(sociedades.codigos(self.archivo), ["AM"])
        self.assertEqual(len(list(self.archivo.parent.iterdir())), 1)

    def test_empty_list_cannot_be_saved(self) -> None:
        with self.assertRaises(ValueError):
            sociedades.guardar([], self.archivo)

    def test_damaged_file_explains_how_to_fix(self) -> None:
        self.archivo.parent.mkdir(parents=True)
        for contenido in ("{no es json", '{"otra": []}', '{"sociedades": [{"codigo": "IS A"}]}'):
            with self.subTest(contenido=contenido):
                self.archivo.write_text(contenido, encoding="utf-8")
                with self.assertRaises(ValueError) as ctx:
                    sociedades.cargar(self.archivo)
                self.assertIn("Restaurar lista inicial", str(ctx.exception))

    def test_duplicates_in_file_raise(self) -> None:
        self.archivo.parent.mkdir(parents=True)
        self.archivo.write_text(
            '{"sociedades": [{"codigo": "ISA"}, {"codigo": "isa"}]}', encoding="utf-8"
        )
        with self.assertRaises(ValueError) as ctx:
            sociedades.cargar(self.archivo)
        self.assertIn("repetida", str(ctx.exception))

    def test_restore_brings_back_initial_list(self) -> None:
        sociedades.guardar(_lista("ZZ"), self.archivo)
        restaurada = sociedades.restaurar_iniciales(self.archivo)
        self.assertEqual(len(restaurada), 24)
        self.assertEqual(sociedades.codigos(self.archivo), [s.codigo for s in restaurada])

    def test_missing_initial_list_raises(self) -> None:
        with (
            patch.object(sociedades, "INICIALES_PATH", Path("/no/existe.json")),
            self.assertRaises(ValueError) as ctx,
        ):
            sociedades.asegurar_archivo(self.archivo)
        self.assertIn("lista inicial", str(ctx.exception))

    def test_default_file_lives_in_configuracion(self) -> None:
        """Junto al `.exe` (decisión del 2026-10-29): cada analista tiene la
        suya y no depende de la red."""
        import paths

        self.assertEqual(paths.CONFIG_DIR.name, "configuracion")
        self.assertEqual(paths.CONFIG_DIR.parent, paths.PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()
