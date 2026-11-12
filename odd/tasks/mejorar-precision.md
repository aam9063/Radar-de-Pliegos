# Mejorar la precisión de extracción (51 % → objetivo)

> Owner: Albert · Rama: `feat/mejorar-precision` · Origen: análisis de la primera evaluación real (`evals/results/2026-11-12-analisis.md`) · Estado: en curso

## Specs

- **S1 · Normalización determinista.** El 0 % en `criterios_adjudicacion`, `penalidades` y `subcontratacion_limites` tiene dos causas (análisis): (1) la comparación es **exacta** y penaliza variaciones de formato ("Hasta 90 puntos" vs "90 puntos", "No exigida" vs "No se exige", "45233222-1: Trabajos..." vs "45233222-1", "G-4" vs "4", mayúsculas), y (2) fallos estructurales reales (fusiona criterios, no encuentra subcontratación). Se añade una **capa de normalización determinista** en la comparación (canonicalizar formato, no relajar el significado): prefijo "Hasta"/"Ata", sinónimos de "no se exige"/"no se prevé", descripciones de CPV, formato de clasificación, mayúsculas/acentos en textos libres.
- **S2 · Fallback determinista de subcontratación.** Si el LLM no extrae `subcontratacion_limites` (null), un post-procesado determinista busca la cláusula de subcontratación en el texto y extrae el límite/porcentaje.
- **S3 · Medir.** Re-correr `evals.run` y registrar la nueva precisión en `evals/results/` y el README.
- **S4 · Canonicalizar ground truth (subcontratación y penalidades).** Los dos campos que siguen al 0 % usan frases interpretativas en el ground truth. Se canonicalizan a hechos cortos (`subcontratacion_limites`: "hasta el 50%" / "art. 215 LCSP" / "sin límite específico"; `penalidades`: hecho central "N% por <motivo>" / "N € por demora") y se alinea el fallback/normalización para que ambos lados comparen esos hechos.

## Tasks

- [x] **MP-01** Normalización determinista en la comparación + fallback de subcontratación + re-evaluación — cubre S1, S2, S3 — route: worker — commit: `7148145`
- [x] **MP-02** Canonicalizar ground truth de subcontratación y penalidades + normalización de hecho central — cubre S4 — route: worker — commit: `0b48732`

## Log

- **L1** (2026-11-12, Albert): "continúa" tras cerrar Fase 1/Fase 2 y establecer el nuevo flujo git (push/PR/merge a dev). Feature propuesta por el agente a partir del análisis del eval.
- **L2** (2026-11-12): MP-01 cerrado — normalización format-only (12 reglas documentadas) + fallback determinista de subcontratación. Precisión real: **51 % → 65 %** (63-65 % entre corridas, varianza LLM). `criterios` 0→40 %, `procedimiento` 20→80 %, `tramitación` 60→100 %, `plazo` 40→80 %, `garantía provisional` 60→100 %. Pendiente de Albert: `subcontratacion_limites` y `penalidades` siguen al 0 % (ground truth frases interpretativas vs fallback honesto).
- **L3** (2026-11-12): Albert elige opción 1 (canonicalizar ground truth). MP-02 cerrado — vocabulario canónico (`subcontratacion_limites`: "hasta el N%" / "art. 215 lcsp" / "sin límite específico"; `penalidades`: "categoria:cifras"). Precisión real: **63 % → 68 %**; `subcontratacion_limites` 0→80 %, `penalidades` 0→20 % (límite estructural: el LLM fusiona/desdobla listas).
