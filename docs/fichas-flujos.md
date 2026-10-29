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
| 2 | La disposición se elige por **número de fila** | `comun.elegir_disposicion` la busca por nombre en la columna `VARIANT` ✅ (falta el nombre de cada una) |
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

**Pendiente:** el nombre de la disposición (`fbl1n.DISPOSICION`). Sin él,
la app avisa y no se conecta a SAP.

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

## FBL5N — Partidas abiertas de deudores ⏳ esperando grabación nueva

Grabación vieja: `wnd[0]/usr/chkX_NORM` y `chkX_SHBV` marcados,
`ctxtDD_KUNNR-LOW = "*"`, `ctxtDD_BUKRS-LOW = "*"`, disposición por fila
(**168**), exportar y confirmar con `wnd[1]/tbar[0]/btn[0]`.

## Y_FI_GRL_004 — Maestro del plan de cuentas ⏳ esperando grabación nueva

Grabación vieja: `ctxtSD_KTOPL-LOW = "*"`, `ctxtSD_BUKRS-LOW = "*"`,
ejecutar, exportar sin elegir disposición.

## FAGLL03 — Partidas abiertas de cuentas de mayor ⏳ esperando grabación nueva

Grabación vieja: las cuentas se cargan **desde el portapapeles** en la
selección múltiple de `SD_SAKNR` (`btn[24]` → `btn[8]`), todas las
sociedades (`ctxtSD_BUKRS-LOW = ""`), disposición por fila (**473**).
La lista de cuentas sale del maestro (paso 2 del proceso).

## Cómo regrabar las que faltan

- Entrar con `/n` + transacción.
- Escribir la sociedad y la fecha clave, aunque sean los valores de siempre.
- Tener a mano el **nombre** de la disposición (columna "Disposición" del
  diálogo "Seleccionar disposición").
- En el diálogo de guardado, escribir la carpeta y el nombre del archivo.
