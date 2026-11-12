# Mejorar la precisión de extracción (51 % → objetivo)

> Owner: Albert · Rama: `feat/mejorar-precision` · Origen: análisis de la primera evaluación real (`evals/results/2026-11-12-analisis.md`) · Estado: en curso

## Specs

- **S1 · Normalización determinista.** El 0 % en `criterios_adjudicacion`, `penalidades` y `subcontratacion_limites` tiene dos causas (análisis): (1) la comparación es **exacta** y penaliza variaciones de formato ("Hasta 90 puntos" vs "90 puntos", "No exigida" vs "No se exige", "45233222-1: Trabajos..." vs "45233222-1", "G-4" vs "4", mayúsculas), y (2) fallos estructurales reales (fusiona criterios, no encuentra subcontratación). Se añade una **capa de normalización determinista** en la comparación (canonicalizar formato, no relajar el significado): prefijo "Hasta"/"Ata", sinónimos de "no se exige"/"no se prevé", descripciones de CPV, formato de clasificación, mayúsculas/acentos en textos libres.
- **S2 · Fallback determinista de subcontratación.** Si el LLM no extrae `subcontratacion_limites` (null), un post-procesado determinista busca la cláusula de subcontratación en el texto y extrae el límite/porcentaje.
- **S3 · Medir.** Re-correr `evals.run` y registrar la nueva precisión en `evals/results/` y el README.

## Tasks

- [ ] **MP-01** Normalización determinista en la comparación + fallback de subcontratación + re-evaluación — cubre S1, S2, S3 — route: worker — commit: —

## Log

- **L1** (2026-11-12, Albert): "continúa" tras cerrar Fase 1/Fase 2 y establecer el nuevo flujo git (push/PR/merge a dev). Feature propuesta por el agente a partir del análisis del eval.
