# CLAUDE.md — Partidas Abiertas

Memoria del proyecto para Claude Code. **Borrador**: se completa en la
Fase 5. Plantilla de origen: `mega-prompt.md` y `analisis-stack.md`
(basados en `~/Documents/activos-propios-py`).

## Propósito

App de escritorio (Tkinter → `.exe` con PyInstaller) para analistas
contables no técnicos en Windows. Automatiza en SAP GUI Scripting la
descarga de partidas abiertas (FBL1N, FBL5N), del maestro del plan de
cuentas (Y_FI_GRL_004) y de las partidas abiertas de mayor (FAGLL03). Usa
la sesión de SAP que el usuario ya abrió; nunca pide credenciales.

**Alcance:** cada opción entrega el archivo **original** que exporta SAP,
sin procesarlo. El semáforo de antigüedad está **fuera del alcance** (lo
hace otra persona del equipo).

El proceso y el detalle de cada grabación están en
[`docs/fichas-flujos.md`](docs/fichas-flujos.md). Material original en la
carpeta de red `//192.168.68.116/Compartida` (montada en
`/Volumes/Compartida`): `Partidas Abiertas/*.vbs` y
`Partidas abiertas.docx` (notas de la reunión con capturas).

## Estado

| Fase | Estado |
|---|---|
| 0. Fichas de los flujos | ✅ `docs/fichas-flujos.md` |
| 1. Esqueleto | ✅ paths, branding, comun, helpers de tests, pyproject + ruff |
| 2. GUI base | ✅ menú 2×2, 4 vistas pendientes con "← Atrás", footer, errores, splash |
| 3. Flujos | 🟡 FBL1N implementado (falta `fbl1n.DISPOSICION` y probarlo en Windows); FBL5N, Y_FI_GRL_004 y FAGLL03 esperan grabación nueva |
| 4. Empaquetado | — |
| 5. Docs y skills | — |
| 6. Extras (cobertura, CI, lockfile) | — |

## Stack

Python ≥ 3.11 · Tkinter + ttk · `tkcalendar` · `openpyxl` · `Pillow` ·
`pywin32` (solo Windows) · `unittest` · PyInstaller · ruff.

En este Mac el venv usa `/opt/homebrew/bin/python3.14` (Tk 9.0). Los
Python 3.11 y 3.12 de Homebrew **no** traen Tk; el 3.11 de python.org sí
(Tk 8.6).

## Estructura

```
src/
  main.py      GUI: OPCIONES, VISTAS, construir_menu, crear_app, main,
               abrir_acreedores + _descargar_fbl1n_handler
  comun.py     TITULO_APP, TITULAR, SOCIEDADES, validar_*, logging, ejecutar,
               get_sap_session, com_apartment, copiar_al_portapapeles,
               pasos de SAP compartidos (abrir_transaccion, selección
               múltiple, calendario, elegir_disposicion, exportar_hoja_calculo,
               volver_al_inicio), utilidades de archivos
  fbl1n.py     flujo FBL1N: DISPOSICION, pasos, descargar_fbl1n, CLI
  branding.py  paleta COLOR_*, cargar_logo, RoundedButton
  paths.py     PROJECT_ROOT, SALIDA_DIR, LOGS_DIR, bundled_resource_path
tests/
  helpers.py   agrega src/ al sys.path; MockSession, SyncFakeThread, crear_libro
  test_<modulo>.py
resources/
  logo.png         se empaqueta
  grabaciones/     .vbs en UTF-16LE, solo referencia (no se empaquetan)
  ejemplos/        exports reales de SAP (ignorada por git)
salida/            runtime (ignorada): exports, Excel procesados, logs/app.log
```

No hay `entrada/`: los datos salen de SAP, no de un archivo que edite el
usuario.

## Comandos

```bash
.venv/bin/python src/main.py
.venv/bin/python -m unittest discover tests -v       # 132 tests
.venv/bin/python src/fbl1n.py 28.10.2026 [ISA XM]    # CLI (solo Windows con SAP)
.venv/bin/python -m unittest tests.test_comun -v
.venv/bin/ruff check src tests && .venv/bin/ruff format src tests
```

## Convenciones

- Código, docstrings, comentarios, mensajes y docs en **español**; solo
  los nombres de los métodos de test van en inglés.
- `from __future__ import annotations` en todos los módulos de `src/`.
- Separadores `# ----` con títulos en MAYÚSCULAS.
- IDs de SAP siempre como constantes y **solo** si salen de una grabación.
- Cada vista expone sus widgets como atributos del frame
  (`frame.btn_atras`, `frame.opcion`, …) para los tests.
- Cada test de archivo empieza con
  `sys.path.insert(0, str(Path(__file__).resolve().parent))` + `import helpers`.

## Decisiones de diseño no obvias

- **`comun.py` concentra lo compartido.** En el proyecto original `_log`,
  `_ejecutar` y `get_sap_session` estaban copiados en cada flujo.
- **`TITULO_APP` es la única fuente del título.** En el original, el
  título de la ventana y la constante con la que se la buscaba para
  minimizarla divergieron y la app dejó de minimizarse antes de las
  capturas. `test_window_title_matches_titulo_app` lo fija.
- **Logs a `salida/logs/app.log` además de consola.** El `.exe` no tiene
  consola. En ese modo `sys.stdout` es `None`, así que el handler de
  consola solo se agrega si existe (`configurar_logging`).
- **Transacciones con `/n`.** Las grabaciones escriben `fbl1n` sin prefijo,
  lo que falla si el usuario está dentro de otra transacción.
- **Disposición por nombre, no por fila.** Las grabaciones la eligen por
  número de fila del diálogo, que cambia cuando alguien crea o borra una.
  `elegir_disposicion` recorre la columna `VARIANT` (visible en
  FBL1N.vbs) moviendo `firstVisibleRow` por bloques, porque la grilla
  carga las filas a medida que se desplaza.
- **Sociedades por portapapeles.** FBL1N.vbs las pega en la selección
  múltiple (`btn[16]` borrar → `btn[24]` pegar → `btn[8]`). Se borra antes
  porque el campo puede traer la sociedad por defecto del usuario. La
  confirmación avisa que se reemplaza lo copiado.
- **Fecha clave con el calendario (F4 + `selectionInterval`)** en vez de
  escribirla: `AAAAMMDD` no depende del formato de fecha de cada usuario.
- **`DY_FILENAME` sin estar en la grabación.** FBL1N.vbs solo escribe
  `DY_PATH`; `wnd[1]/usr/ctxtDY_FILENAME` lo usa en producción
  `activos-propios-py` en este mismo SAP. Si aparece la ventana de formato
  de hoja de cálculo, se acepta con `wnd[1]/tbar[0]/btn[0]`.
- **Las grabaciones del repo no llevan el usuario de Windows** (el repo es
  público): se reemplaza por `USUARIO` al copiarlas. El original queda en
  la carpeta de red.
- **`helpers` tiene su propia sección en isort** (`pyproject.toml`): es
  quien agrega `src/` al `sys.path`, así que debe importarse antes que
  cualquier módulo del proyecto.
- **`crear_app()` separado de `main()`** para probar la ventana sin entrar
  al `mainloop`.
