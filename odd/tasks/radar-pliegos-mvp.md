# Radar de Pliegos — MVP (Fase 1) + planificador CPM (Fase 2 opcional)

> Owner: Albert · Rama: `feat/radar-pliegos-mvp` · Origen: `BRIEF.md` (2026-11-11) · Estado: en curso

## Specs

Fuente de verdad: `BRIEF.md`. Se cita literalmente. Cada `S#` enlaza los criterios de aceptación (`AC-xx`) que cubre.

- **S1 · Licitaciones y subida de documentos.** "Crear una licitación y subirle de 1 a N PDFs, cada uno con un tipo: `PCAP`, `PPT`, `ANEXO`, `OTRO`. Guardar el PDF original y sus metadatos."
- **S2 · Extracción de texto por página.** "Extraer el texto de cada página con PyMuPDF conservando número de página. Guardar `documento → páginas` en Postgres. Una página sin texto (PDF escaneado) se marca `sin_texto = true`. No se hace OCR."
- **S3 · Extracción estructurada con LLM.** Esquema Pydantic `PliegoFicha` (identificación, económicos, plazos, requisitos, adjudicación, riesgos). "Cada campo es un `CampoExtraido[T]` con: `valor: T | None`, `evidencia: list[Evidencia]` (documento, página, cita literal de 30 palabras como máximo) y `confianza: alta | media | baja`." Regla de oro: "si el dato no aparece, `valor = None` y sin evidencia. Nunca se inventa ni se deduce." Llamada a NaN (`deepseek-v4-flash`, `json_schema`, `/chat/completions` **sin tools**), texto con marcadores `[[DOC:PCAP|P:12]]`, un reintento ante JSON inválido y si vuelve a fallar "error 502 claro y nada guardado a medias". Prioridad de fuentes en conflicto: `PCAP > ANEXO > PPT > OTRO`.
- **S4 · Verificación de evidencias (determinista).** "Para cada evidencia, el código comprueba que la cita aparece en el texto de esa página (coincidencia normalizada: minúsculas, espacios, acentos; tolerancia fuzzy ≥ 0,9). Si no aparece, el campo queda `verificado = false`."
- **S5 · Perfil de empresa.** "Un único perfil editable: clasificaciones que posee (grupo, subgrupo, categoría), volumen anual de negocio medio, provincias donde trabaja, tipos de obra, rango de presupuesto de interés y días mínimos para preparar una oferta."
- **S6 · Motor de decisión GO / NO-GO / REVISAR (código, no LLM).** Reglas puras y testeadas (clasificación faltante → NO-GO; solvencia > volumen → NO-GO; días < mínimo → NO-GO; presupuesto fuera de rango → REVISAR; campo crítico nulo/sin verificar → REVISAR; resto → GO). "Cada razón enlaza a la evidencia del campo que la provoca." El LLM solo redacta un resumen de 3 a 5 frases a partir de las razones ya calculadas. "No decide nada."
- **S7 · Frontend.** Lista con estado y recomendación; alta y subida con drag-and-drop; detalle (ficha izq. + visor PDF der., la evidencia salta a su página); panel de decisión; pantalla de perfil.
- **S8 · Evaluación.** `evals/` con 5 licitaciones reales de obra + `evals/ground_truth/<expediente>.json`; `uv run python -m evals.run` genera `evals/results/<fecha>.md` (precisión por campo, global, % evidencias verificadas, 3 fallos más frecuentes). "La evaluación usa la API real y no corre en el CI por defecto."
- **S9 · Fase 2 (opcional).** Planificador mínimo: actividades propuestas por el LLM (con evidencia), CPM con `networkx`, Gantt sencillo + export CSV.

### Criterios de aceptación (resumen de mapeo)

| ID | Criterio | AC |
| --- | --- | --- |
| RP-01 | Esqueleto monorepo, Docker Compose, `/health`, CI mínimo | AC-01, AC-11 |
| RP-02 | Modelos, migraciones, subida PDFs + extracción por página | AC-02 |
| RP-03 | Puerto `LLMClient`, adaptador NaN, cliente falso con límites | AC-10 |
| RP-04 | Esquema `PliegoFicha` + extracción con reintento | AC-03, AC-04 |
| RP-05 | Verificación de evidencias + fusión con prioridad de fuentes | AC-05, AC-07 |
| RP-06 | Perfil de empresa + motor de decisión | AC-06 |
| RP-07 | Frontend: lista, subida, ficha + visor, decisión, perfil | AC-09 |
| RP-08 | Evaluación con 5 pliegos + informe | AC-08 |
| RP-09 | README + cierre Fase 1 | AC-12 |
| RP-10 | (Fase 2) Planificador CPM + Gantt | AC-13 |

## Tasks

- [x] **RP-01** Esqueleto del monorepo, Docker Compose, `/health`, CI mínimo — cubre AC-01, AC-11 — route: inline — commit: `75b1a80` `483762b` `5e3bbdc`
- [ ] **RP-02** Modelos, migraciones y subida de PDFs con extracción por página — cubre AC-02 — route: — commit: —
- [ ] **RP-03** Puerto `LLMClient`, adaptador NaN y cliente falso con límites — cubre AC-10 — route: — commit: —
- [ ] **RP-04** Esquema `PliegoFicha` y extracción con reintento — cubre AC-03, AC-04 — route: — commit: —
- [ ] **RP-05** Verificación de evidencias y fusión con prioridad de fuentes — cubre AC-05, AC-07 — route: — commit: —
- [ ] **RP-06** Perfil de empresa y motor de decisión — cubre AC-06 — route: — commit: —
- [ ] **RP-07** Frontend: lista, subida, ficha + visor, decisión, perfil — cubre AC-09 — route: — commit: —
- [ ] **RP-08** Evaluación con 5 pliegos e informe — cubre AC-08 — route: — commit: —
- [ ] **RP-09** README y cierre de la Fase 1 — cubre AC-12 — route: — commit: —
- [ ] **RP-10** (Fase 2) Planificador CPM + Gantt — cubre AC-13 — route: — commit: —

## TDD / RDD configuration

- **TDD: on.** Fuente: `AGENTS.md` §4. Runners: backend `uv run pytest` (desde `/backend`); frontend unit/componentes `pnpm vitest run`; e2e `pnpm playwright test`. Ciclo RED → GREEN → REFACTOR con salidas anotadas por tarea.
- **RDD: on (global).** `gentle-ai review mode status` → `receipt-driven development: on (decided by global)`. Después de cada work-unit commit: `gentle-ai review assess --cwd <repo> --base-ref <último límite> --committed-only --json`. Regla del repo: al cerrar la feature se revisa siempre el slice completo (4R) aunque todos los assess salgan `passive`.

## Verification evidence

| Tarea | RED | GREEN | Lint/tipos/tests | Commit | RDD assess |
| --- | --- | --- | --- | --- | --- |
| RP-01 | `ModuleNotFoundError: No module named 'app.main'` (test_health) | `1 passed` | backend `ruff check`/`format`/`mypy --strict` OK · `pytest` 1 passed · frontend `eslint`/`tsc --noEmit`/`vitest`/`build`/`prettier` OK · `docker compose config` OK · `docker compose build` OK | `75b1a80` `483762b` `5e3bbdc` | infra (`5e3bbdc`) high → native review **approved** |

## Progress / Next step

- [x] Feature document creado + espejo Engram.
- [x] Bootstrap git: `main` (17d09a5), `dev`, `feat/radar-pliegos-mvp`.
- [x] RP-01 cerrado: código + verificaciones + 3 commits (`75b1a80`, `483762b`, `5e3bbdc`) + RDD nativo aprobado.
- [x] AC-01 verificado end-to-end (`docker compose up -d` → db/api/web healthy, `/health` 200). Fix mount pg18 `72779c3` + template de entorno commiteado `0ecd0b0`. Assess del fix: medium → slice close.
- [ ] RP-02 en curso.

### Hallazgos RDD (no bloqueantes, follow-up)

- `R2-hardcoded-creds` (docker-compose.yml:4): credenciales dev `radar/radar` en compose; aceptable en local, revisar antes de cualquier despliegue.
- `R2-dup-runtime-config` (ci.yml:27) y `R2-implicit-compose` (ci.yml:88): duplicación de `DATABASE_URL` en CI y compose implícito en e2e.
- `R2-monolithic-plan` (odd/tasks:1), `R1-001` (ci.yml:34), `R1-002` (docker-compose.yml:9): informativos.

## Log

- **L1** (2026-11-12, Albert): "Lee el BRIEF.md, entiendelo y empieza a implementar".
- **L2** (2026-11-12, Albert): "espera que se me ha olvidado copiarlo voy" → "ya" (se añadió `AGENTS.md` con el stack/guardarraíles).
- **L3** (2026-11-12): El guard de seguridad de gentle bloquea crear/leer cualquier ruta con `.env` (incluido `.env.example`); lo crea Albert. El resto de RP-01 no depende de ello.
- **L4** (2026-11-12): RP-01 partido en 3 commits revisables porque el candidato completo (46 ficheros / 4759 líneas, con lockfiles) excedió el presupuesto de contexto de la revisión nativa (`lens_context_budget_exceeded`). El commit de infra (`5e3bbdc`, el que contenía la señal de alto riesgo ci.yml) se revisó nativo con 2 lentes (risk + readability) y quedó **approved**; 6 hallazgos no bloqueantes anotados arriba.
- **L5** (2026-11-12): `docker compose up -d` fallaba en `db` (Postgres 18 monta los datos en `/var/lib/postgresql`, no en `/var/lib/postgresql/data`). Fix `72779c3`. Albert creó `.env.example`; lo committeé como `0ecd0b0` (`.env.example` se versiona, solo `.env` se ignora).
