# Fichas de los flujos

Especificación de los 4 flujos a partir de las grabaciones de
`resources/grabaciones/` y de las notas de la reunión
(`Partidas abiertas.docx`, en la carpeta de red
`//192.168.68.116/Compartida`).

> Las grabaciones `.vbs` vienen en UTF-16LE. Para leerlas:
> `iconv -f UTF-16LE -t UTF-8 resources/grabaciones/FBL1N.vbs`

## Alcance (decidido el 2026-10-28)

- Cada opción **descarga el archivo original de SAP** a `salida/` y nada
  más: no hay procesamiento del Excel.
- El **semáforo de antigüedad queda fuera del alcance** (lo hace otra
  persona del equipo).
- Sociedades: la lista oficial son las 28 de `comun.SOCIEDADES`. El
  usuario puede elegir todas o algunas.
- Fecha clave: la elige el usuario; por defecto, hoy.

## El proceso (según la reunión)

1. **FBL1N y FBL5N**: partidas abiertas de acreedores y deudores.
2. **Y_FI_GRL_004** (maestro del plan de cuentas): las cuentas con `X` en
   la columna **PI** (gestión de partidas abiertas), sin el plan de
   cuentas consolidado **001**.
3. **FAGLL03**: partidas abiertas de esas cuentas de mayor.

## Problemas comunes de las grabaciones

| # | Problema | Solución en la app |
|---|---|---|
| 1 | La transacción se abre sin `/n` | `comun.abrir_transaccion` usa `/n` ✅ |
| 2 | La disposición se elige por **número de fila** | `comun.elegir_disposicion` la busca por nombre en la columna `VARIANT` ✅ (`/PARTABIERTA` en FBL1N, FBL5N y FAGLL03) |
| 3 | No se graba el nombre del archivo exportado | `comun.exportar_hoja_calculo` escribe `DY_PATH` y `DY_FILENAME` ✅ |
| 4 | Salen con un número fijo de F3 | `comun.volver_al_inicio` usa `/n` ✅ |

## FBL1N — Partidas abiertas de acreedores ✅ implementado

Grabación del 2026-10-28 (`FBL1N.vbs`, con el usuario de Windows
reemplazado por `USUARIO`). Módulo: `src/fbl1n.py`.

| Paso | Grabación | En la app |
|---|---|---|
| 1 | `okcd = "fbl1n"` + Enter | `abrir_transaccion` con `/nFBL1N` |
| 2 | `btn%_KD_LIFNR_%_APP_%-VALU_PUSH` → `…SLOW_I[1,0] = "*"` → `wnd[1]/tbar[0]/btn[8]` | `seleccionar_acreedores`: todos los acreedores |
| 3 | `btn%_KD_BUKRS_%_APP_%-VALU_PUSH` → `btn[16]` (borrar) → `btn[24]` (pegar del portapapeles) → `btn[8]` | `seleccionar_sociedades`: la app copia las sociedades elegidas al portapapeles |
| 4 | `ctxtPA_STIDA` + F4 → `wnd[1]/usr/cntlCONTAINER/shellcont/shell.selectionInterval = "AAAAMMDD,AAAAMMDD"` | `fijar_fecha_clave`: mismo calendario (no depende del formato de fecha del usuario) |
| 5 | `chkX_NORM = true`, `chkX_SHBV = true` | `marcar_clases_de_partida` |
| 6 | `wnd[0]/tbar[1]/btn[8]` | `ejecutar_reporte` |
| 7 | `btn[33]` → ordenar por `VARIANT` → fila **182** | `elegir_disposicion(fbl1n.DISPOSICION)` por nombre |
| 8 | `menu[0]/menu[3]/menu[1]` → `wnd[1]/usr/ctxtDY_PATH` → `wnd[1]/tbar[0]/btn[0]` | `exportar_hoja_calculo`: carpeta `salida/` y nombre `FBL1N_AAAAMMDD_HHMMSS.xlsx` |
| 9 | `btn[3]` ×2 | `volver_al_inicio` (`/n`) |

**Disposición:** `/PARTABIERTA` (`fbl1n.DISPOSICION`, confirmada el
2026-10-28).

**A verificar en la primera prueba en Windows:**

- `wnd[1]/usr/ctxtDY_FILENAME` no está en `FBL1N.vbs`; se usa porque
  `activos-propios-py` lo usa en producción en este mismo SAP.
- En el equipo de la grabación no apareció la ventana de formato de hoja
  de cálculo. Si aparece en otro equipo, la app la acepta con
  `wnd[1]/tbar[0]/btn[0]`.

**Export de ejemplo** (`EXPORT_20261028_223644_FBL1N.XLSX`, 2,6 MB): una
hoja, 23 columnas, 24.366 partidas de las 28 sociedades más 74 filas de
subtotales y totales. La columna "Ejercicio" aparece dos veces (la
segunda casi vacía; pendiente saber qué campo es). Como la app entrega el
archivo tal cual, nada de esto afecta al flujo.

## FBL5N — Partidas abiertas de deudores ✅ implementado

Grabación del 2026-10-28 (`FBL5N.vbs`). Módulo: `src/fbl5n.py`. Es la
**misma secuencia que FBL1N** con los campos de deudor:

| Paso | Grabación | En la app |
|---|---|---|
| 1 | `okcd = "fbl5n"` + Enter | `abrir_transaccion` con `/nFBL5N` |
| 2 | `btn%_DD_KUNNR_%_APP_%-VALU_PUSH` → `…SLOW_I[1,0] = "*"` → `btn[8]` | `seleccionar_deudores` |
| 3 | `btn%_DD_BUKRS_%_APP_%-VALU_PUSH` → `btn[16]` → `btn[24]` → `btn[8]` | `seleccionar_sociedades` (portapapeles) |
| 4 | `ctxtPA_STIDA` + F4 → calendario `selectionInterval` | `fijar_fecha_clave` |
| 5 | `chkX_NORM = true`, `chkX_SHBV = true` | `marcar_clases_de_partida` |
| 6 | `btn[8]` | `ejecutar_reporte` |
| 7 | `btn[33]` → fila **169** | `elegir_disposicion(fbl5n.DISPOSICION)` por nombre |
| 8 | `menu[0]/menu[3]/menu[1]` → `DY_PATH` → `btn[0]` | `exportar_hoja_calculo` → `FBL5N_AAAAMMDD_HHMMSS.xlsx` |

**Disposición:** `/PARTABIERTA`, la misma que FBL1N (`fbl5n.DISPOSICION`,
confirmada el 2026-10-28).

**Export de ejemplo** (`EXPORT_20261028_224456_FBL5N.XLSX`, 3,7 MB): una
hoja, 27 columnas (distintas de las de FBL1N: trae vencimiento neto y
demora), 28.538 partidas de 23 sociedades más 7 filas de totales.

## Y_FI_GRL_004 — Maestro del plan de cuentas ✅ implementado

Grabación del 2026-10-28 (en la carpeta de red se llama
`EXPORT_20261028_225628_Y_FI_GRL_004.vbs`). Módulo: `src/y_fi_grl_004.py`.
No usa fecha clave ni disposición.

| Paso | Grabación | En la app |
|---|---|---|
| 1 | `okcd = "Y_FI_GRL_004"` + Enter | `abrir_transaccion` con `/nY_FI_GRL_004` |
| 2 | `ctxtSD_KTOPL-LOW = "*"` | `seleccionar_planes_de_cuentas` |
| 3 | `btn%_SD_BUKRS_%_APP_%-VALU_PUSH` → `btn[24]` → `btn[8]` | `seleccionar_sociedades`; la app además borra antes (`btn[16]`, mismo diálogo que FBL1N/FBL5N) |
| 4 | `btn[8]` | `ejecutar_reporte` |
| 5 | `menu[0]/menu[3]/menu[1]` → `DY_PATH` → `btn[0]` | `exportar_hoja_calculo` → `Y_FI_GRL_004_AAAAMMDD_HHMMSS.xlsx` |

**Export de ejemplo** (`EXPORT_20261028_225628_Y_FI_GRL_004.XLSX`,
5,7 MB): una hoja, 41 columnas, 42.158 cuentas de 28 sociedades, sin
subtotales. La columna **PI** (gestión de partidas abiertas) tiene `X` en
30.097 filas.

**Notas:**

- Al no elegir disposición, las columnas salen con la disposición por
  defecto de cada usuario. Si otro usuario tiene otra por defecto, su
  archivo puede traer otras columnas.
- La reunión propuso excluir el plan de cuentas consolidado **001** para
  aligerar la extracción; la grabación usa `*` y la app hace lo mismo.

## FAGLL03 — Partidas abiertas de cuentas de mayor ✅ implementado

Grabación del 2026-10-28 (en la carpeta de red se llama
`EXPORT_20261028_232304_FAGLL03.vbs`). Módulo: `src/fagll03.py`.

| Paso | Grabación | En la app |
|---|---|---|
| 1 | `okcd = "FAGLL03"` + Enter | `abrir_transaccion` con `/nFAGLL03` |
| 2 | `btn%_SD_SAKNR_%_APP_%-VALU_PUSH` → `btn[16]` → `btn[24]` → `btn[8]` | `seleccionar_cuentas`: la app copia las cuentas del maestro al portapapeles |
| 3 | `btn%_SD_BUKRS_%_APP_%-VALU_PUSH` → `btn[16]` → `btn[24]` → `btn[8]` | `seleccionar_sociedades` (portapapeles) |
| 4 | `ctxtPA_STIDA` + F4 → calendario `selectionInterval` | `fijar_fecha_clave` |
| 5 | `btn[8]` | `ejecutar_reporte` |
| 6 | `btn[33]` → fila **473** | `elegir_disposicion(fagll03.DISPOSICION)` por nombre |
| 7 | `menu[0]/menu[3]/menu[1]` → `DY_PATH` → `btn[0]` | `exportar_hoja_calculo` → `FAGLL03_AAAAMMDD_HHMMSS.xlsx` |

**Disposición:** `/PARTABIERTA`, la misma que FBL1N y FBL5N (confirmada el
2026-10-28).

**De dónde salen las cuentas.** La grabación pega una lista de cuentas
desde el portapapeles. La app la arma con el export del **maestro más
reciente** de `salida/` (`Y_FI_GRL_004_*.xlsx`): las filas con `X` en la
columna **PI** y una de las sociedades elegidas (la gestión de partidas
abiertas se define por sociedad). Se lee antes de tocar SAP. Por eso:

- La vista muestra qué maestro va a usar y deshabilita el botón si no hay
  ninguno.
- Con las 28 sociedades salen **15.466 cuentas** (≈ 4 s de lectura y
  166 KB en el portapapeles); con una sola sociedad, unas 5.700.
- Supuesto validado con los ejemplos: las 383 cuentas con partidas en el
  export de FAGLL03 tienen todas PI = X en el maestro.

**Export de ejemplo** (`EXPORT_20261028_232304_FAGLL03.XLSX`, 34 MB): una
hoja, 33 columnas, 238.724 partidas de 383 cuentas y 27 sociedades, más 10
filas de totales.

**A verificar en la primera prueba en Windows:** que SAP acepte pegar
~15 mil cuentas en la selección múltiple. Si falla con todas las
sociedades, la alternativa es descargar por grupos de sociedades.
