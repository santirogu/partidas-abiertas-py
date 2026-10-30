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
| 3. Flujos | 🟡 Los 4 implementados (FBL1N, FBL5N y FAGLL03 con `/PARTABIERTA`; Y_FI_GRL_004 sin disposición). Primera prueba real de FBL5N el 2026-10-29: la selección funcionó; falló sin partidas (corregido, ver decisiones). Falta una descarga completa en Windows |
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
  main.py      GUI: OPCIONES (con modulo/usa_fecha_clave/requiere), VISTAS,
               _crear_vista_descarga, _descargar_handler, construir_menu,
               crear_app, main
  comun.py     TITULO_APP, TITULAR, validar_* (sociedades contra la lista del usuario), logging,
               crear_avisador, ejecutar, get_sap_session, com_apartment,
               copiar_al_portapapeles, pasos de SAP compartidos
               (abrir_transaccion, selección múltiple, calendario,
               elegir_disposicion, exportar_hoja_calculo, volver_al_inicio,
               terminar_exportacion), buscar_ultimo_export, utilidades de archivos
  fbl1n.py     flujo FBL1N (acreedores)        ┐ contrato de módulo de flujo:
  fbl5n.py     flujo FBL5N (deudores)          │ TRANSACCION, validar_configuracion(),
  y_fi_grl_004.py  maestro de cuentas          │ get_sap_session(), descargar(...), main()
  fagll03.py   partidas de mayor               ┘ + leer_cuentas_partidas_abiertas (maestro)
  branding.py  paleta COLOR_*, cargar_logo, RoundedButton
  sociedades.py  lista de sociedades del usuario: cargar/codigos/guardar,
               agregar/modificar/quitar (puras), restaurar_iniciales
  paths.py     PROJECT_ROOT, SALIDA_DIR, LOGS_DIR, CONFIG_DIR, bundled_resource_path
tests/
  helpers.py   agrega src/ al sys.path; MockSession, SyncFakeThread, crear_libro
  test_<modulo>.py
resources/
  logo.png         se empaqueta
  sociedades_iniciales.json  lista inicial (24, de Sociedades.xlsx), se empaqueta
  grabaciones/     .vbs en UTF-16LE, solo referencia (no se empaquetan)
  ejemplos/        exports reales de SAP (ignorada por git)
configuracion/     runtime (ignorada): sociedades.json, la lista del usuario
salida/            runtime (ignorada): exports de SAP, logs/app.log
```

No hay `entrada/`: los datos salen de SAP. Lo único que el usuario
administra es la lista de sociedades, desde la pantalla «Sociedades».

## Comandos

```bash
.venv/bin/python src/main.py
.venv/bin/python -m unittest discover tests -v       # 256 tests
.venv/bin/python src/fbl1n.py 28.10.2026 [ISA XM]    # CLI (solo Windows con SAP)
.venv/bin/python src/fbl5n.py 28.10.2026 [ISA XM]
.venv/bin/python src/y_fi_grl_004.py [ISA XM]
.venv/bin/python src/fagll03.py 28.10.2026 [ISA XM]  # usa el último maestro de salida/
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
- **Contrato de los módulos de flujo.** La GUI no conoce cada flujo: una
  sola vista (`_crear_vista_descarga`) y un solo handler
  (`_descargar_handler`) importan `Opcion.modulo` y llaman
  `validar_configuracion()`, `get_sap_session()` y
  `descargar(session, sociedades, [fecha_clave=], progreso=)`.
  `test_connected_modules_follow_the_flow_contract` lo verifica.
  FBL1N y FBL5N comparten secuencia pero son módulos separados para poder
  ajustar cada uno si su pantalla de SAP cambia.
- **Y_FI_GRL_004 borra la selección antes de pegar** aunque su grabación
  no lo haga: es el mismo diálogo de selección múltiple de FBL1N/FBL5N, y
  así no se cuela una sociedad por defecto.
- **Y_FI_GRL_004 no elige disposición** (la grabación tampoco): sale con
  la disposición por defecto de cada usuario.
- **FAGLL03 toma las cuentas del maestro.** La grabación pega una lista de
  cuentas desde el portapapeles; la app la arma con el
  `Y_FI_GRL_004_*.xlsx` más reciente de `salida/`: filas con `PI = X` y
  sociedad entre las elegidas (la gestión de partidas abiertas es por
  sociedad). Se lee antes de tocar SAP. Validado con los ejemplos: las 383
  cuentas con partidas en FAGLL03 tienen PI = X en el maestro. Con las 28
  sociedades son ~15.466 cuentas: falta confirmar en Windows que SAP
  acepte pegar tantas.
- **Sociedades administradas por el usuario** (`sociedades.py` + vista
  `abrir_sociedades`). Pedido del 2026-10-29: la lista cambia y no debe
  estar en el código. El usuario eligió una pantalla en la app (no un
  Excel editable) y guardar junto al `.exe`. Se guarda en
  `configuracion/sociedades.json` con escritura atómica (temporal +
  `os.replace`); la primera vez se copia `resources/sociedades_iniciales.json`
  y nunca se sobrescribe. Cada acción se guarda al instante. Las vistas de
  descarga leen la lista al abrirse y al volver de «Sociedades»
  (`SelectorSociedades.recargar`); con más de 6 filas de casillas usan
  barra de desplazamiento porque la ventana es fija. **Fase 4:** el `.spec`
  debe empaquetar `resources/sociedades_iniciales.json`.
- **Los tests no tocan `configuracion/` real:** `tests/helpers.py` apunta
  `sociedades.ARCHIVO` a una carpeta temporal al importarse;
  `helpers.sociedades_temporales()` da a cada test una lista propia.
- **Verificar el resultado después de Ejecutar** (`verificar_resultado`).
  Incidente del 2026-10-29: FBL5N solo con AM no tenía partidas; SAP se
  quedó en la pantalla de selección, la app pulsó "Seleccionar
  disposición" (SAP: "Seleccione una función válida") y falló con el
  error 619 al buscar la lista. Ahora, si un campo de la pantalla de
  selección (`PA_STIDA`; `SD_KTOPL-LOW` en Y_FI_GRL_004) sigue en
  pantalla, se lanza `SinResultadosError` con el mensaje de la barra de
  estado (`wnd[0]/sbar`), SAP vuelve al inicio y la GUI lo muestra como
  **aviso**, no como error. En la prueba quedó validado con SAP real:
  deudor `*`, sociedades por portapapeles, fecha clave por calendario y CME.
- **Errores con la pantalla de SAP** (`diagnostico_sap`). Cualquier falla
  dentro de los pasos de SAP agrega al mensaje y al log la ventana activa
  y la barra de estado, para diagnosticar sin captura de pantalla.
- **`Opcion.requiere`** declara qué opción debe descargarse antes. La
  vista muestra el archivo que usará y deshabilita el botón si falta; se
  evalúa al abrir la vista (sin polling).
- **`helpers` tiene su propia sección en isort** (`pyproject.toml`): es
  quien agrega `src/` al `sys.path`, así que debe importarse antes que
  cualquier módulo del proyecto.
- **`crear_app()` separado de `main()`** para probar la ventana sin entrar
  al `mainloop`.
