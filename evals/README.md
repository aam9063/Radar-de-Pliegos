# Evaluación de extracción (S8 / RP-08)

Este directorio contiene los **datos** de la evaluación: pliegos reales, su
anotación manual (ground truth) y los informes generados. El **código** del
runner vive en `backend/evals/`.

```
evals/
├── pliegos/            # PDFs reales (1..N por licitación, no versionados en el repo)
├── ground_truth/       # anotación manual: <expediente>.json (los que empiezan por '_' se ignoran)
└── results/            # informes generados: <fecha>.md
```

## Cómo ejecutar la evaluación

```bash
cd backend && uv run python -m evals.run
```

Requiere `NAN_API_KEY` (variable de entorno o `backend/.env`): la evaluación
usa la **API real de NaN** y gasta cuota, por eso no corre en el CI normal
(solo manualmente o vía `.github/workflows/evals.yml` con `workflow_dispatch`).

Directorio de datos, en orden de prioridad:

1. `--data-dir <ruta>` (argumento CLI).
2. Variable de entorno `EVALS_DIR`.
3. Por defecto: `evals/` en la raíz del repositorio (el caso de `cd backend && uv run python -m evals.run`).

Salida: `evals/results/<fecha>.md` (si ya existe el del día, se genera
`<fecha>-HHMM.md` para no sobrescribir). Código de salida: `0` si todo fue
correcto, `1` si algún pliego falló (el fallo queda registrado en el informe)
o si falta configuración.

## Formato del ground truth

Un fichero JSON por pliego, `evals/ground_truth/<expediente>.json`. Mira la
plantilla `evals/ground_truth/_ejemplo.json` para el formato completo. Reglas:

- `expediente`: identificador del pliego (debe coincidir con el nombre del
  fichero).
- `documentos`: lista de PDFs del pliego con su tipo (`PCAP`, `ANEXO`, `PPT`,
  `OTRO`). Cada `archivo` es un nombre de fichero dentro de `evals/pliegos/`.
- `campos`: valor esperado por campo, usando los nombres de `PliegoFicha`
  (los 20 campos: `expediente`, `objeto`, `organo_contratacion`, `cpv`,
  `procedimiento`, `tramitacion`, `presupuesto_base_sin_iva`,
  `presupuesto_base_con_iva`, `valor_estimado`, `revision_precios`,
  `plazo_ejecucion`, `fecha_limite_presentacion`, `clasificacion_exigida`,
  `solvencia_economica`, `solvencia_tecnica`, `criterios_adjudicacion`,
  `penalidades`, `garantia_provisional`, `garantia_definitiva`,
  `subcontratacion_limites`).
  - Valor directo: `"objeto": "texto esperado"`.
  - Con nota (opcional): `"objeto": {"valor": "texto", "nota": "página 3"}`.
  - Un campo **no anotado** se espera **ausente** (null) en la ficha: si el
    extractor lo rellena, cuenta como fallo (dato inventado).
  - Campos compuestos: `plazo_ejecucion` → `{"valor": "12", "unidad": "meses"}`;
    `revision_precios` → `{"aplica": true, "formula": "..."}`;
    `clasificacion_exigida` → lista de `{grupo, subgrupo, categoria}`;
    `criterios_adjudicacion` → lista de `{nombre, tipo, ponderacion}` con
    `tipo` = `automatico` o `juicio_valor`.

## Qué mide el informe

- **Precisión global**: valores correctos / total de comparaciones (20 campos
  por pliego). Ambos nulos cuenta como correcto; los campos económicos
  toleran una diferencia relativa del 0,1 %; las listas se comparan sin
  tener en cuenta el orden.
- **Precisión por campo**: correctos / total por campo entre todos los pliegos.
- **% de evidencias verificadas**: porcentaje de campos extraídos (no nulos)
  cuya evidencia pasa la verificación determinista de citas (S4).
- **3 fallos más frecuentes**: campos con más comparaciones fallidas.
