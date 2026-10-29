# Partidas Abiertas

App de escritorio para Windows que automatiza la descarga de partidas
abiertas desde SAP y su análisis de antigüedad. Se conecta a la sesión de
SAP GUI que el usuario ya tiene abierta (nunca pide ni guarda
credenciales) y deja todo lo que genera en la carpeta `salida/`, junto al
ejecutable.

> **Borrador.** Este README se completa en la Fase 5. Hoy están listos el
> esqueleto y la interfaz base; las 4 opciones todavía no se conectan a
> SAP (ver [`docs/fichas-flujos.md`](docs/fichas-flujos.md)).

## Opciones del menú

| Card | Transacción | Qué hace |
|---|---|---|
| Acreedores | FBL1N | Partidas abiertas de proveedores por sociedad |
| Deudores | FBL5N | Partidas abiertas de clientes por sociedad |
| Maestro de cuentas | Y_FI_GRL_004 | Plan de cuentas; identifica las cuentas con gestión de partidas abiertas |
| Partidas de mayor | FAGLL03 | Partidas abiertas de esas cuentas y su antigüedad |

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
| `test_main.py` | 25 | Ventana, menú 2×2, navegación a cada vista y de vuelta, footer, manejo de errores, splash |
| `test_comun.py` | 27 | Logging a archivo, `ejecutar`, conexión a SAP, apartamento COM, abrir transacción, utilidades de archivos |
| `test_branding.py` | 17 | `RoundedButton` (estilos, estado, `invoke`, reconfiguración) y logo |
| `test_paths.py` | 7 | Rutas en modo dev y empaquetado |

## Estructura

```
partidas-abiertas-py/
├── src/
│   ├── main.py        # GUI: menú, vistas, arranque
│   ├── comun.py       # identidad, logging, conexión SAP, pasos y archivos compartidos
│   ├── branding.py    # paleta, logo, RoundedButton
│   └── paths.py       # rutas dev/empaquetado
├── tests/             # un test_<modulo>.py por módulo + helpers.py
├── resources/
│   ├── logo.png       # se empaqueta
│   └── grabaciones/   # grabaciones .vbs de SAP (referencia, NO se empaquetan)
├── docs/
│   └── fichas-flujos.md
├── salida/            # RUNTIME (ignorada): exports, Excel procesados y logs/
├── pyproject.toml     # metadatos + configuración de ruff
├── requirements.txt / requirements-dev.txt
├── CLAUDE.md
└── LICENSE
```

## Licencia

Propietaria. © El Hub de ISA. Todos los derechos reservados. Ver
[`LICENSE`](LICENSE).
