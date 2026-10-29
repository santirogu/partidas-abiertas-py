# Fichas de los flujos (Fase 0)

Especificación de los 4 flujos a partir de las grabaciones de
`resources/grabaciones/` y de las notas de la reunión
(`Partidas abiertas.docx`, en la carpeta de red
`//192.168.68.116/Compartida`). Es la base de la Fase 3: cada flujo se
implementa cuando su grabación nueva esté disponible.

> Las grabaciones `.vbs` vienen en UTF-16LE. Para leerlas:
> `iconv -f UTF-16LE -t UTF-8 resources/grabaciones/FBL1N.vbs`

## El proceso

1. **FBL1N y FBL5N**: partidas abiertas de acreedores y deudores por
   sociedad.
2. **Y_FI_GRL_004** (maestro del plan de cuentas): se toman las cuentas
   con `X` en la columna **PI** (gestión de partidas abiertas), excluyendo
   el plan de cuentas consolidado **001** (incluye todas las cuentas y
   hace la extracción muy pesada). Si una cuenta compartida tiene PI en el
   plan de cuentas, aplica a todas las sociedades que la usan.
3. **FAGLL03**: con esas cuentas se consultan las partidas abiertas de
   mayor, sin revisar el balance primero.
4. **Antigüedad**: cada partida se clasifica por antigüedad con un
   semáforo (rojo para más de un año, intermedio alrededor de 3 meses,
   verde para ~1 mes). La reunión no fijó un umbral definitivo.

Según las notas, primero se prueba el rendimiento de la consulta en
pantalla; el procesamiento en segundo plano queda como alternativa porque
su salida viene con peor formato.

## Problemas comunes a las 4 grabaciones

| # | Problema | Consecuencia | Solución |
|---|---|---|---|
| 1 | La transacción se abre sin `/n` (`okcd = "fbl1n"`) | Falla si el usuario está dentro de otra transacción | `comun.abrir_transaccion` usa `/n` ✅ |
| 2 | La disposición se elige por **número de fila** en el diálogo (378, 168, 473) | Si alguien crea o borra una disposición, se elige otra sin aviso | Escribir el nombre en el campo **Disposición** de la pantalla de selección (requiere regrabar) |
| 3 | No se graba la carpeta ni el nombre del archivo exportado | El archivo queda donde SAP tenga por defecto | Escribir `DY_PATH` y `DY_FILENAME` en el diálogo de guardado (requiere regrabar) |
| 4 | Se usa `*` en todas las sociedades | Extracciones lentas | Permitir elegir sociedades (pendiente de decisión) |
| 5 | Salen con un número fijo de F3 | Uno de más saca de la transacción | La siguiente transacción arranca con `/n`; no hace falta volver |

## FBL1N — Partidas abiertas de acreedores

| Paso | Grabación | Qué hace |
|---|---|---|
| 1 | `wnd[0]/tbar[0]/okcd = "fbl1n"` + Enter | Abre la transacción |
| 2 | `wnd[0]/usr/ctxtKD_LIFNR-LOW = "*"` | Todos los acreedores |
| 3 | `wnd[0]/usr/ctxtKD_BUKRS-LOW = "*"` | Todas las sociedades |
| 4 | `wnd[0]/tbar[1]/btn[8]` | Ejecutar (partidas abiertas a la fecha clave por defecto: hoy) |
| 5 | `wnd[0]/tbar[1]/btn[33]` + fila **378** del diálogo de disposiciones | Elige la disposición |
| 6 | `wnd[0]/mbar/menu[0]/menu[3]/menu[1]` | Exportar la lista |
| 7 | `wnd[1]` F4 → `wnd[2]/usr/ctxtDY_PATH` F4 → `wnd[3]/tbar[0]/btn[0]` → `wnd[2]/tbar[0]/btn[0]` → `wnd[1]/tbar[0]/btn[11]` | Elige la carpeta navegando y guarda |
| 8 | `wnd[0]/tbar[0]/btn[3]` | Atrás |

## FBL5N — Partidas abiertas de deudores

| Paso | Grabación | Qué hace |
|---|---|---|
| 1 | `okcd = "fbl5n"` + Enter | Abre la transacción |
| 2 | `wnd[0]/usr/chkX_NORM = true`, `wnd[0]/usr/chkX_SHBV = true` | Partidas normales + operaciones CME |
| 3 | `wnd[0]/usr/ctxtDD_KUNNR-LOW = "*"`, `wnd[0]/usr/ctxtDD_BUKRS-LOW = "*"` | Todos los deudores y sociedades |
| 4 | `btn[8]`, `btn[33]` + fila **168** | Ejecutar y elegir disposición |
| 5 | `menu[0]/menu[3]/menu[1]` → `wnd[1]/tbar[0]/btn[0]` | Exportar y confirmar (ruta y nombre por defecto) |
| 6 | `btn[3]` ×2 | Atrás |

## Y_FI_GRL_004 — Maestro del plan de cuentas

| Paso | Grabación | Qué hace |
|---|---|---|
| 1 | `okcd = "y_fi_grl_004"` + Enter | Abre el reporte |
| 2 | `wnd[0]/usr/ctxtSD_KTOPL-LOW = "*"`, `wnd[0]/usr/ctxtSD_BUKRS-LOW = "*"` | Todos los planes de cuentas y sociedades |
| 3 | `btn[8]` | Ejecutar (sin elegir disposición) |
| 4 | `menu[0]/menu[3]/menu[1]` → `wnd[1]/tbar[0]/btn[0]` | Exportar y confirmar |
| 5 | `btn[3]` ×2 | Atrás |

Post-proceso: filtrar `PI = X` y excluir el plan de cuentas `001` →
lista de cuentas para FAGLL03.

## FAGLL03 — Partidas abiertas de cuentas de mayor

| Paso | Grabación | Qué hace |
|---|---|---|
| 1 | `okcd = "fagll03"` + Enter | Abre la transacción |
| 2 | `wnd[0]/usr/btn%_SD_SAKNR_%_APP_%-VALU_PUSH` | Selección múltiple de cuentas |
| 3 | `wnd[1]/tbar[0]/btn[24]` → `wnd[1]/tbar[0]/btn[8]` | Carga las cuentas **desde el portapapeles** y acepta |
| 4 | `wnd[0]/usr/ctxtSD_BUKRS-LOW = ""` | Todas las sociedades |
| 5 | `btn[8]`, `btn[33]` + fila **473** | Ejecutar y elegir disposición |
| 6 | `menu[0]/menu[3]/menu[1]` → `wnd[1]/tbar[0]/btn[0]` | Exportar y confirmar |
| 7 | `btn[3]` ×2 | Atrás |

La app llenará el portapapeles con las cuentas del maestro antes del
paso 3 (eso reemplaza lo que el usuario tuviera copiado: se avisa en la
confirmación). Post-proceso: antigüedad en días, rango y color del
semáforo.

## Pendiente para la Fase 3

**Regrabar las 4 transacciones** escribiendo en vez de seleccionar:

- entrar con `/n` + transacción;
- escribir la sociedad y la fecha clave, aunque sean los valores de siempre;
- en FBL1N, FBL5N y FAGLL03, escribir el nombre de la disposición en el
  campo **Disposición** de la pantalla de selección;
- en el diálogo de guardado, escribir la carpeta y el nombre del archivo.

**Un export de ejemplo de cada transacción** (en `resources/ejemplos/`,
que no se versiona) para programar el filtro y el semáforo con las
columnas reales.

**Decisiones** (entre paréntesis, la recomendación):

- Sociedades: ¿todas o elegibles? (todas por defecto, con opción de elegir varias)
- Fecha clave: ¿hoy o elegible? (elegible, con hoy por defecto)
- Umbrales del semáforo (verde ≤ 90 días, amarillo 91–365, rojo > 365,
  desde la fecha de documento hasta la fecha clave)
- ¿Semáforo solo en FAGLL03 o también en FBL1N y FBL5N?
- Autoría para el `LICENSE`.
