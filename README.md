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
| Deudores | FBL5N | Partidas abiertas de clientes | ⏳ Esperando grabación |
| Maestro de cuentas | Y_FI_GRL_004 | Plan de cuentas; identifica las cuentas con gestión de partidas abiertas | ⏳ Esperando grabación |
| Partidas de mayor | FAGLL03 | Partidas abiertas de esas cuentas de mayor | ⏳ Esperando grabación |

### Acreedores (FBL1N)

1. Marca las sociedades (por defecto, las 28) y elige la fecha clave (por
   defecto, hoy).
2. Pulsa **Descargar FBL1N** y confirma. La app usa el portapapeles para
   pasarle las sociedades a SAP, así que reemplaza lo que tengas copiado.
3. No uses SAP mientras corre. Al terminar, el archivo queda en
   `salida/FBL1N_AAAAMMDD_HHMMSS.xlsx`.

También se puede correr desde la terminal:

```bash
python src/fbl1n.py 28.10.2026            # todas las sociedades
python src/fbl1n.py 28.10.2026 ISA XM     # solo ISA y XM
```

Códigos de salida: 0 = OK, 1 = error (datos o SAP), 2 = uso incorrecto.

## Requisitos

- **Para usar la app:** Windows, SAP GUI for Windows con scripting
  habilitado en el cliente y en el servidor, y la sesión de SAP iniciada.
- **Para desarrollar:** Python 3.11 o superior **con Tk**. En macOS sirve
  el Python de python.org, o el de Homebrew con `python-tk` para esa
  versión.

## Quick start (desarrollo)

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python src/main.py
```

En Windows, `.venv\Scripts\python` en lugar de `.venv/bin/python`.

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
| `test_comun.py` | 52 | Validaciones, logging, conexión a SAP, COM, portapapeles, selección múltiple, calendario, disposición por nombre, exportar, archivos |
| `test_main.py` | 38 | Ventana, menú 2×2, navegación, vista y handler de Acreedores, footer, errores, splash |
| `test_fbl1n.py` | 20 | Cada paso de FBL1N, orden del flujo completo, validaciones, CLI |
| `test_branding.py` | 17 | `RoundedButton` (estilos, estado, `invoke`, reconfiguración) y logo |
| `test_paths.py` | 7 | Rutas en modo dev y empaquetado |

## Estructura

```
partidas-abiertas-py/
├── src/
│   ├── main.py        # GUI: menú, vistas, handlers, arranque
│   ├── comun.py       # catálogo, logging, conexión SAP, pasos y archivos compartidos
│   ├── fbl1n.py       # flujo FBL1N (acreedores)
│   ├── branding.py    # paleta, logo, RoundedButton
│   └── paths.py       # rutas dev/empaquetado
├── tests/             # un test_<modulo>.py por módulo + helpers.py
├── resources/
│   ├── logo.png       # se empaqueta
│   └── grabaciones/   # grabaciones .vbs de SAP (referencia, NO se empaquetan)
├── docs/
│   └── fichas-flujos.md
├── salida/            # RUNTIME (ignorada): exports de SAP y logs/
├── pyproject.toml     # metadatos + configuración de ruff
├── requirements.txt / requirements-dev.txt
├── CLAUDE.md
└── LICENSE
```

## Licencia

Propietaria. © El Hub de ISA. Todos los derechos reservados. Ver
[`LICENSE`](LICENSE).
