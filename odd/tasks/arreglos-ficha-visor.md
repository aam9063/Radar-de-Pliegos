# Arreglos del visor de PDF y del formato de la ficha

> Owner: Albert · Rama: `fix/ficha-y-visor` · Origen: reporte de bugs del 2026-11-13 · Estado: en curso

## Specs

- **S1 · El PDF no se descarga.** "Cuando adjunto un pdf de un pliego y le doy a extraer se me descarga el pdf a parte de subirse, luego cuando pincho sobre ese archivo se me vuelve a descargar y cuadno entro a la vista del archivo cada vez que me muevo de pagina se me vuelve a descargar". El endpoint debe servir el PDF `inline` y el visor no debe volver a pedir el fichero al cambiar de página.
- **S2 · El visor se ve.** "en la vista del archivo en el cuadro ese de ver poagina a pagina no se ve nada": el recuadro del visor muestra el PDF en la página indicada.
- **S3 · La ficha aparece sin pulsar nada.** "Y le tengo que dar al boton de volver a extrar para que me muestre los datos del pdf": al entrar en una licitación con documentos y sin ficha, la extracción arranca sola una vez y la ficha aparece al terminar.
- **S4 · Formato legible de los datos.** "y luego el formato de los datos me parece horrible" (capturas del 2026-11-13): criterios de adjudicación como lista con nombre, tipo y ponderación; penalidades, solvencias y clasificación como listas o etiquetas, no como una cadena unida por "·"; plazo de ejecución como "3 meses"; evidencias en su propia línea, sin duplicados y sin desbordar la fila.

## Tasks

- [x] **T1** Backend: servir el PDF `inline` + test del header — cubre S1 — commit: `6d3dc75`
- [x] **T2** Visor: no re-pedir el PDF al cambiar de página — cubre S1, S2 — commit: `84a2c18`
- [x] **T3** Extracción automática única cuando no hay ficha — cubre S3 — commit: `84a2c18`
- [x] **T4** Render estructurado de la ficha y de las evidencias — cubre S4 — commit: `977312e`

## Evidencias de verificación

- Backend: `uv run pytest` → 222 passed; `ruff check`, `ruff format --check`, `mypy --strict app` limpios.
- Frontend: `pnpm vitest run` → 24 passed; `pnpm lint`, `pnpm typecheck`, `pnpm build` limpios.
- Funcional: contenedores `api` y `web` reconstruidos; `curl -D -` sobre el PDF restaurado devuelve `content-disposition: inline; filename="EXP4.pdf"`.
- Riesgo detectado fuera de alcance (no se toca): la suite de integración del backend apunta al Postgres de `docker compose` y vacía el esquema, así que correr `uv run pytest` borra las licitaciones locales.

## Log

- **L1** (2026-11-13, Albert): "Si bastantes bugs.Cuando adjunto un pdf de un pliego y le doy a extraer se me descarga el pdf a parte de subirse, luego cuando pincho sobre ese archivo se me vuelve a descargar y cuadno entro a la vista del archivo cada vez que me muevo de pagina se me vuelve a descargar, y a parte en la  vista del archivo en el cuadro ese de ver poagina a pagina no se ve nada. Y le tengo que dar al boton de volver a extrar para que me muestre los datos del pdf, y luego el formato de los datos me parece horrible. Te voy a adjuntar captura para que lo veas: C:\Users\alber\AppData\Local\Temp\orca-paste-1794562633488-b90de46b-e0f9-4ff6-9d36-fa227c9b81f6.png C:\Users\alber\AppData\Local\Temp\orca-paste-1794562651467-71efc6ca-1fa3-4d1c-a4a5-c8d283ee62fe.png"
- **L2** (2026-11-13, diagnóstico con evidencia): `curl -D -` sobre `/documentos/169/pdf` devuelve `content-disposition: attachment; filename="EXP4.pdf"` porque `FileResponse` recibe `filename=` sin `content_disposition_type` (`backend/app/api/documentos.py:74`). El `iframe` del visor se remonta por `key={id}-{pagina}` en cada cambio de página (`frontend/src/features/licitaciones/LicitacionDetailPage.tsx:243`). `NuevaLicitacionPage.tsx:37-44` sube documentos y navega, pero nunca llama a `extraerFicha` ni invalida `['ficha']`. `formatValor` aplana arrays y objetos con `' · '` (`frontend/src/features/licitaciones/ficha.ts:85,93`), y el esquema real es estructurado: `criterios_adjudicacion: list[CriterioAdjudicacion]`, `penalidades: list[str]`, `plazo_ejecucion: {"valor","unidad"}`, `clasificacion_exigida: [{"grupo","subgrupo","categoria"}]`.
- **L3** (2026-11-13): T1–T4 cerradas con TDD. RED/GREEN observados en cada una: `test_fetch_pdf_is_served_inline_for_the_embedded_viewer` (attachment → inline), dos tests de identidad del `iframe` (remontaba → nodo estable), tres tests de extracción automática (no se llamaba a `extraerFicha` → una llamada única con 404 + documentos), y siete tests de `describirValor`/`evidenciasUnicas` más tres de render. Checks: backend 222 tests, ruff, format, mypy --strict verdes; frontend 24 tests, lint, typecheck y build verdes. Verificación funcional: `content-disposition: inline; filename="EXP4.pdf"` servido por el contenedor reconstruido.
