# Partidas Abiertas

App de escritorio para Windows que automatiza la descarga de partidas
abiertas desde SAP. Se conecta a la sesión de SAP GUI que el usuario ya
tiene abierta (nunca pide ni guarda credenciales) y deja el archivo
original que exporta SAP en la carpeta `salida/`, junto al ejecutable.

> **Borrador.** Este README se completa en la Fase 5. Estado de cada
> opción en [`docs/fichas-flujos.md`](docs/fichas-flujos.md).

## Opciones del menú

| Card | Transacción | Qué hace | Estado |
|---|---|---|---|
| Acreedores | FBL1N | Partidas abiertas de proveedores | ✅ Lista para probar en Windows |
| Deudores | FBL5N | Partidas abiertas de clientes | ✅ Lista para probar en Windows |
| Maestro de cuentas | Y_FI_GRL_004 | Plan de cuentas; identifica las cuentas con gestión de partidas abiertas | ✅ Lista para probar en Windows |
| Partidas de mayor | FAGLL03 | Partidas abiertas de las cuentas con gestión de partidas abiertas (las toma del maestro) | ✅ Lista para probar en Windows |

### Cómo se usa una opción

1. Marca las sociedades (por defecto, todas las de tu lista). En
   Acreedores, Deudores y Partidas de mayor elige también la fecha clave
   (por defecto, hoy).
2. Pulsa **Descargar …** y confirma. La app usa el portapapeles para
   pasarle las listas a SAP, así que reemplaza lo que tengas copiado.
3. No uses SAP mientras corre. Al terminar, el archivo queda en `salida/`
   con el nombre de la transacción y la hora, p. ej.
   `salida/FBL1N_20261028_153000.xlsx`.

Si SAP no encuentra partidas para lo que elegiste (p. ej. una sociedad
sin partidas de deudores a esa fecha), la app muestra un **aviso "Sin
partidas"** con el mensaje de SAP y no genera archivo. No es un error:
prueba con otras sociedades u otra fecha clave.

**Partidas de mayor necesita el maestro:** las cuentas que consulta son
las que tienen `X` en la columna PI del Maestro de cuentas más reciente de
`salida/`. Descarga primero el Maestro de cuentas; la vista de Partidas de
mayor muestra qué archivo va a usar.

### Cambiar la lista de sociedades

La lista **no está en el código**: se administra desde la app, en
**"Editar sociedades"** (arriba a la derecha del menú) o en **"Editar
lista"** (junto a "Todas / Ninguna" en cada descarga).

- **Agregar:** escribe el código (de 1 a 4 letras o números) y, si
  quieres, el nombre, y pulsa **Agregar**.
- **Modificar:** toca la sociedad en la lista, cambia el código o el nombre
  y pulsa **Guardar cambios**.
- **Quitar:** toca la sociedad y pulsa **Quitar** (pide confirmación).
- **Restaurar lista inicial:** vuelve a las 24 sociedades de partida.

Cada cambio se guarda al instante en `configuracion/sociedades.json`,
junto al `.exe`: cada analista tiene su propia lista y la conserva al
actualizar la app. La primera vez se crea con la lista inicial
(`resources/sociedades_iniciales.json`).

También se puede correr cada opción desde la terminal (sin sociedades,
usa todas las de la lista):

```bash
python src/fbl1n.py 28.10.2026            # FBL1N, todas las sociedades
python src/fbl5n.py 28.10.2026 ISA XM     # FBL5N, solo ISA y XM
python src/y_fi_grl_004.py                # maestro de cuentas, todas
python src/fagll03.py 28.10.2026          # FAGLL03 (usa el último maestro)
```

Códigos de salida: 0 = OK, 1 = error (datos o SAP), 2 = uso incorrecto.

## Requisitos

- **Para usar la app:** Windows, SAP GUI for Windows con scripting
  habilitado en el cliente y en el servidor, y la sesión de SAP iniciada.
- **Para desarrollar:** Python 3.11 o superior **con Tk**. En macOS sirve
  el Python de python.org, o el de Homebrew con `python-tk` para esa
  versión.

## Quick start (desarrollo)

**Windows** (Git Bash, por ejemplo la terminal de VS Code). En Windows el
entorno virtual guarda los ejecutables en `.venv/Scripts/`, **no** en
`.venv/bin/`:

```bash
py -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python src/main.py
```

Si `py` no existe, usa `python`. En PowerShell o CMD es lo mismo con
barras invertidas: `.venv\Scripts\python`.

**macOS / Linux:**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python src/main.py
```

En el resto de este README los comandos usan `.venv/bin/python`; en
Windows cámbialo por `.venv/Scripts/python`.

## Pruebas y calidad

```bash
.venv/bin/python -m unittest discover tests -v
.venv/bin/ruff check src tests
.venv/bin/ruff format src tests
```

Ninguna prueba necesita SAP, Windows ni una ventana visible: SAP se
reemplaza por `tests/helpers.MockSession`.

| Archivo | Tests | Qué cubre |
|---|---|---|
| `test_comun.py` | 76 | Validaciones, logging, conexión a SAP, COM, portapapeles, selección múltiple, calendario, disposición por nombre, exportar, cierre de la exportación, último export, verificación de resultados, diagnóstico de pantalla, archivos |
| `test_main.py` | 63 | Ventana, menú 2×2, contrato de los módulos de flujo, vistas de descarga (incluido el maestro que necesita FAGLL03), selector de sociedades, pantalla «Sociedades», handler (incluido el aviso de sin partidas), footer, errores, splash |
| `test_sociedades.py` | 27 | Lista inicial, validación de códigos y nombres, agregar/modificar/quitar, guardado seguro, archivo dañado, restaurar |
| `test_fagll03.py` | 20 | Cuentas con PI = X del maestro, búsqueda del último maestro, cada paso de FAGLL03, orden del flujo, CLI |
| `test_fbl1n.py` | 21 | Cada paso de FBL1N, orden del flujo completo, validaciones, CLI |
| `test_branding.py` | 17 | `RoundedButton` (estilos, estado, `invoke`, reconfiguración) y logo |
| `test_fbl5n.py` | 14 | Cada paso de FBL5N, orden del flujo, disposición, CLI |
| `test_y_fi_grl_004.py` | 11 | Cada paso del maestro de cuentas, orden del flujo (sin fecha ni disposición), CLI |
| `test_paths.py` | 7 | Rutas en modo dev y empaquetado |

## Estructura

```
partidas-abiertas-py/
├── src/
│   ├── main.py        # GUI: menú, vistas, handlers, arranque
│   ├── comun.py       # catálogo, logging, conexión SAP, pasos y archivos compartidos
│   ├── fbl1n.py       # flujo FBL1N (acreedores)
│   ├── fbl5n.py       # flujo FBL5N (deudores)
│   ├── y_fi_grl_004.py  # flujo Y_FI_GRL_004 (maestro de cuentas)
│   ├── fagll03.py     # flujo FAGLL03 (partidas de mayor; cuentas del maestro)
│   ├── sociedades.py  # lista de sociedades del usuario (configuracion/sociedades.json)
│   ├── branding.py    # paleta, logo, RoundedButton
│   └── paths.py       # rutas dev/empaquetado
├── tests/             # un test_<modulo>.py por módulo + helpers.py
├── resources/
│   ├── logo.png       # se empaqueta
│   ├── sociedades_iniciales.json  # lista inicial de sociedades, se empaqueta
│   └── grabaciones/   # grabaciones .vbs de SAP (referencia, NO se empaquetan)
├── docs/
│   └── fichas-flujos.md
├── configuracion/     # RUNTIME (ignorada): sociedades.json, la lista del usuario
├── salida/            # RUNTIME (ignorada): exports de SAP y logs/
├── pyproject.toml     # metadatos + configuración de ruff
├── requirements.txt / requirements-dev.txt
├── CLAUDE.md
└── LICENSE
```

## Licencia

Propietaria. © El Hub de ISA. Todos los derechos reservados. Ver
[`LICENSE`](LICENSE).
