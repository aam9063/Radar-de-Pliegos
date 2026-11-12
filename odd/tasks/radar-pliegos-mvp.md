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
- [x] **RP-02** Modelos, migraciones y subida de PDFs con extracción por página — cubre AC-02 — route: worker (`gentle-ai-worker`) — commit: `bca0430` `9bb18eb`
- [x] **RP-03** Puerto `LLMClient`, adaptador NaN y cliente falso con límites — cubre AC-10 — route: worker (`gentle-ai-worker`) — commit: `de0f588` `5e6c31a`
- [x] **RP-04** Esquema `PliegoFicha` y extracción con reintento — cubre AC-03, AC-04 — route: worker (`gentle-ai-worker`) — commit: `6f0cec4`
- [x] **RP-05** Verificación de evidencias y fusión con prioridad de fuentes — cubre AC-05, AC-07 — route: worker (`gentle-ai-worker`) — commit: `e81ade1`
- [x] **RP-06** Perfil de empresa y motor de decisión — cubre AC-06 — route: worker (`gentle-ai-worker`) — commit: `4790acc`
- [x] **RP-07** Frontend: lista, subida, ficha + visor, decisión, perfil — cubre AC-09 — route: worker (`gentle-ai-worker`) — commit: `96b09d6` `f00e2ea`
- [x] **RP-08** Evaluación con 5 pliegos e informe — cubre AC-08 — route: worker (`gentle-ai-worker`) — commit: `65447e8`
- [x] **RP-09** README y cierre de la Fase 1 — cubre AC-12 — route: inline — commit: `180959b`
- [x] **RP-10** (Fase 2) Planificador CPM + Gantt — cubre AC-13 — route: worker (`gentle-ai-worker`) — commit: `4d0e045` `073b27f`

## TDD / RDD configuration

- **TDD: on.** Fuente: `AGENTS.md` §4. Runners: backend `uv run pytest` (desde `/backend`); frontend unit/componentes `pnpm vitest run`; e2e `pnpm playwright test`. Ciclo RED → GREEN → REFACTOR con salidas anotadas por tarea.
- **RDD: on (global).** `gentle-ai review mode status` → `receipt-driven development: on (decided by global)`. Después de cada work-unit commit: `gentle-ai review assess --cwd <repo> --base-ref <último límite> --committed-only --json`. Regla del repo: al cerrar la feature se revisa siempre el slice completo (4R) aunque todos los assess salgan `passive`.

## Verification evidence

| Tarea | RED | GREEN | Lint/tipos/tests | Commit | RDD assess |
| --- | --- | --- | --- | --- | --- |
| RP-01 | `ModuleNotFoundError: No module named 'app.main'` (test_health) | `1 passed` | backend `ruff check`/`format`/`mypy --strict` OK · `pytest` 1 passed · frontend `eslint`/`tsc --noEmit`/`vitest`/`build`/`prettier` OK · `docker compose config` OK · `docker compose build` OK | `75b1a80` `483762b` `5e3bbdc` | infra (`5e3bbdc`) high → native review **approved** |
| RP-02 | `ModuleNotFoundError: No module named 'app.db.session'` (collection) | `10 passed` | backend `ruff check`/`format`/`mypy --strict` OK · `pytest` 10 passed (6 integración + 3 extracción + 1 health) · `alembic check` OK | `bca0430` `9bb18eb` | medium → slice close |
| RP-03 | `ModuleNotFoundError: No module named 'app.adapters.fake_llm_client'` (collection) | `28 passed` | backend `ruff check`/`format`/`mypy --strict` OK · `pytest` 28 passed (18 nuevas + 10 previas) | `de0f588` `5e6c31a` | medium → slice close |
| RP-04 | `ModuleNotFoundError: No module named 'app.domain.pliego_ficha'` (collection) | `51 passed` | backend `ruff check`/`format`/`mypy --strict` OK · `pytest` 51 passed (23 nuevas + 28 previas) · `alembic check` OK | `6f0cec4` | medium → slice close |
| RP-05 | `ModuleNotFoundError: No module named 'app.domain.fusion_ficha'` (collection) | `73 passed` | backend `ruff check`/`format`/`mypy --strict` OK · `pytest` 73 passed (22 nuevas + 51 previas) | `e81ade1` | medium → slice close |
| RP-06 | `ModuleNotFoundError: No module named 'app.domain.motor_decision'` (collection) | `103 passed` | backend `ruff check`/`format`/`mypy --strict` OK · `pytest` 103 passed (30 nuevas + 73 previas) · `alembic check` OK | `4790acc` | medium → slice close |
| RP-07 | backend `assert 404 == 200` (PDF endpoint) / frontend `Failed to resolve import ../../lib/api` | backend `109 passed` · frontend `vitest 5` + `playwright 3` | backend `ruff`/`mypy` OK · frontend `eslint`/`tsc`/`vitest`/`build` OK · e2e OK | `96b09d6` `f00e2ea` | medium → slice close |
| RP-08 | `ModuleNotFoundError: No module named 'evals.comparacion'` (collection) | `153 passed` | backend `ruff`/`format`/`mypy --strict` OK · `pytest` 153 passed (44 nuevas + 109 previas) · `python -m evals.run` exit 1 (sin NAN_API_KEY, esperado) | `65447e8` | medium → slice close |
| RP-09 | n/a (docs) | n/a | README creado; arranque verificado en RP-01 (`docker compose up -d` → `/health` 200) | `180959b` | slice-close 4R (abajo) |
| RP-10 | `ModuleNotFoundError: No module named 'app.domain.planificacion'` (collection) | `186 passed` | backend `ruff`/`format`/`mypy --strict` OK · `pytest` 186 passed (33 nuevas) · frontend `eslint`/`tsc`/`vitest 10`/`build` OK | `4d0e045` `073b27f` | native review **approved** (reliability + resilience) |

## Progress / Next step

- [x] Feature document creado + espejo Engram.
- [x] Bootstrap git: `main` (17d09a5), `dev`, `feat/radar-pliegos-mvp`.
- [x] RP-01 cerrado: código + verificaciones + 3 commits (`75b1a80`, `483762b`, `5e3bbdc`) + RDD nativo aprobado.
- [x] AC-01 verificado end-to-end (`docker compose up -d` → db/api/web healthy, `/health` 200). Fix mount pg18 `72779c3` + template de entorno commiteado `0ecd0b0`. Assess del fix: medium → slice close.
- [x] RP-02 cerrado: modelos + migración + subida + extracción por página (worker `gentle-ai-worker`), 10 tests, assess medium.
- [x] RP-03 cerrado: puerto `LLMClient` + `NanLLMClient` (semáforo 5 + backoff/jitter) + `FakeLLMClient`, 28 tests, assess medium.
- [x] RP-04 cerrado: `PliegoFicha` (20 campos `CampoExtraido[T]`) + extractor con marcadores y reintento único + modelo `ficha`, 51 tests, assess medium.
- [x] RP-05 cerrado: extracción por documento + fusión determinista (prioridad PCAP>ANEXO>PPT>OTRO + avisos de conflicto) + verificación fuzzy de citas (≥0,9 → `verificado`), 73 tests, assess medium.
- [x] RP-06 cerrado: perfil de empresa + motor de decisión puro (6 reglas, NO-GO>REVISAR, razones con evidencia) + resumen LLM, 103 tests, assess medium.
- [x] RP-07 cerrado: frontend completo según los 3 mockups (lista/nueva/detalle/perfil) + `GET /documentos/{id}/pdf` + `GET /licitaciones/{id}/documentos` + CORS, 109 backend + 5 vitest + 3 e2e, assess medium.
- [x] RP-08 cerrado: runner `python -m evals.run` + comparación determinista + informe markdown + esquema ground truth, 153 tests, assess medium. Falta la parte manual: 5 pliegos reales + anotaciones de Albert.
- [x] RP-09 cerrado: README + revisión 4R del slice + borrador de PR. **Fase 1 cerrada** (AC-01..AC-12; AC-08 real pendiente de los 5 pliegos de Albert).
- [x] RP-10 cerrado: planificador CPM determinista (`networkx`) + propuesta de actividades desde el PPT + Gantt/CSV. **Fase 2 cerrada** (AC-13).

### Hallazgos RDD (no bloqueantes, follow-up)

- `R2-hardcoded-creds` (docker-compose.yml:4): credenciales dev `radar/radar` en compose; aceptable en local, revisar antes de cualquier despliegue.
- `R2-dup-runtime-config` (ci.yml:27) y `R2-implicit-compose` (ci.yml:88): duplicación de `DATABASE_URL` en CI y compose implícito en e2e.
- `R2-monolithic-plan` (odd/tasks:1), `R1-001` (ci.yml:34), `R1-002` (docker-compose.yml:9): informativos.

## Slice review (4R) — cierre Fase 1

Revisión explícita del slice completo (AGENTS.md §5) tras 9 work-units con assess medium (deferidos al cierre).

- **Risk**: sin secretos en el repo (`NAN_API_KEY` solo por env, nunca en logs); path traversal bloqueado en `resolve_pdf_path` (`resolve`+`is_relative_to`); CORS limitado a `localhost:5173`; ORM sin SQL crudo. Pendiente (no bloqueante): credenciales dev `radar/radar` en compose (solo local).
- **Resilience**: semáforo 5 + backoff/jitter ante 429/5xx; extracción con reintento único → 502 sin ficha a medias; healthchecks en compose. Pendiente: `GET /decision` recomputa LLM por fila.
- **Readability**: `domain` (puro) / `services` / `adapters` / `api` / `db` separados; tipado estricto; código en inglés.
- **Reliability**: 153 backend + 5 vitest + 3 e2e; motor, fusión, verificación y comparación deterministas y testeadas. Pendiente: AC-08 real requiere los 5 pliegos anotados.

Open follow-ups (no bloquean, fuera de alcance): auto-extracción al crear (1 línea), resaltar cita en el PDF (PDF.js), decisión persistida en `GET /licitaciones`, revisar "clasificación vacía → NO-GO" tras el eval.

## PR draft

Título: `feat: Radar de Pliegos MVP (Fase 1) — extracción de pliegos y decisión GO/NO-GO/REVISAR`

Resumen: MVP completo — subida de PDFs, texto por página (PyMuPDF), extracción estructurada LLM (`PliegoFicha` con evidencia), verificación determinista de citas y fusión por prioridad de fuentes, perfil de empresa, motor de decisión determinista, frontend React (lista/alta/detalle/perfil) y runner de evaluación.

Criterios cubiertos: AC-01..AC-12 (AC-08 con corrida real pendiente de los 5 pliegos anotados de Albert).

Cómo probarlo: `cp .env.example .env && docker compose up -d` → web en http://localhost:5173.

RDD: commit de infra revisado nativo (**approved**); resto de work-units con assess **medium** → revisados al cierre del slice (4R, arriba).

## Log

- **L1** (2026-11-12, Albert): "Lee el BRIEF.md, entiendelo y empieza a implementar".
- **L2** (2026-11-12, Albert): "espera que se me ha olvidado copiarlo voy" → "ya" (se añadió `AGENTS.md` con el stack/guardarraíles).
- **L3** (2026-11-12): El guard de seguridad de gentle bloquea crear/leer cualquier ruta con `.env` (incluido `.env.example`); lo crea Albert. El resto de RP-01 no depende de ello.
- **L4** (2026-11-12): RP-01 partido en 3 commits revisables porque el candidato completo (46 ficheros / 4759 líneas, con lockfiles) excedió el presupuesto de contexto de la revisión nativa (`lens_context_budget_exceeded`). El commit de infra (`5e3bbdc`, el que contenía la señal de alto riesgo ci.yml) se revisó nativo con 2 lentes (risk + readability) y quedó **approved**; 6 hallazgos no bloqueantes anotados arriba.
- **L5** (2026-11-12): `docker compose up -d` fallaba en `db` (Postgres 18 monta los datos en `/var/lib/postgresql`, no en `/var/lib/postgresql/data`). Fix `72779c3`. Albert creó `.env.example`; lo committeé como `0ecd0b0` (`.env.example` se versiona, solo `.env` se ignora).
- **L6** (2026-11-12): dependencia `python-multipart` añadida — requerida por FastAPI para el endpoint de subida multipart `POST /licitaciones/{id}/documentos` (BRIEF §9, AC-02).
- **L7** (2026-11-12): RP-03 — puerto `LLMClient` en `domain/` (puro), `NanLLMClient` y `FakeLLMClient` en `adapters/`. Fix `disable_existing_loggers=False` en `migrations/env.py`. `frontend/docs/mock/*.dc.html` (mockups de diseño ajenos) → ignorados en `.gitignore`.
- **L8** (2026-11-12): RP-04 — esquema `PliegoFicha` (20 campos, `CampoExtraido[T]` genérico con regla de oro: no aparece → `None` sin evidencia), extractor single-call con marcadores `[[DOC:<tipo>|P:<n>]]` + reintento único → 502. Pendiente para RP-05: refactor a extracción **por documento** + fusión determinista (AC-07 exige conflictos PCAP>PPT) + verificación de citas. Dependencia `rapidfuzz` para fuzzy ≥0,9 (AC-05).
- **L9** (2026-11-12): RP-05 — refactor a extracción por documento, `fusion_ficha.py` (prioridad + avisos), `verificacion_ficha.py` (normalización + `partial_ratio/100 ≥ 0,9` → `verificado`), `CampoExtraido.verificado`. Umbral fuzzy correcto: `partial_ratio` es 0-100, se divide por 100.
- **L10** (2026-11-12): RP-06 — motor de decisión puro (`motor_decision.py`), perfil de empresa, modelos `perfil_empresa`/`decision`, resumen LLM solo de las razones. Decisiones: presupuesto = `presupuesto_base_sin_iva` (rango inclusivo); solvencia se cuantifica con `maximo_importe_euros` (marcador de divisa, formato ES, None→REVISAR nunca NO-GO); campos críticos = objeto/presupuesto/fecha_limite/clasificacion/solvencia; clasificación vacía → NO-GO (conservador, a revisar en eval).
- **L11** (2026-11-12): RP-07 — frontend siguiendo los 3 mockups (`frontend/docs/mock/*.dc.html`, versionados en `ac2ee33`). Se añadieron 2 endpoints backend habilitadores (aprobados por el parent, requeridos por AC-09): `GET /licitaciones/{id}/documentos` (mapeo tipo→id del visor) y CORS `localhost:5173`. El salto del visor usa iframe `#page=N` (resaltar la cita dentro del PDF necesitaría PDF.js, fuera de scope).
- **L12** (2026-11-12, Albert): el push **no** es automático: al cerrar fase (o cuando haya trabajo listo) le **pregunto** "¿Hago push de `<rama>` a `origin`?" y solo pusheo si dice sí explícito para esa rama. Las PR las abre Albert. Remote: `https://github.com/aam9063/Radar-de-Pliegos.git` (repo vacío, sin ramas aún → el primer push debe establecer `main` y `dev`).
- **L13** (2026-11-12): RP-08 — runner `backend/evals/` (comparación determinista con tolerancia 0,1% en económicos, listas order-insensitive, both-None correcto, alucinación = fallo; informe `evals/results/<fecha>.md` en español). Data dir: `--data-dir` > `EVALS_DIR` > `../evals`. AC-08 manual pendiente: 5 pliegos reales + ground_truth de Albert.
- **L14** (2026-11-12): RP-09 — README (`180959b`) + slice review 4R + borrador de PR. Fase 1 cerrada.
- **L15** (2026-11-12): dependencia `networkx` promovida a directa — requerida para el CPM del planificador (BRIEF §9, AC-13).
- **L16** (2026-11-12): RP-10 — `calcular_cpm` puro en `domain/planificacion.py` (pase adelante/atrás, holgura, ruta crítica determinista), propuesta de actividades desde el PPT con reintento único, endpoints `GET /licitaciones/{id}/planificacion[.csv]`, Gantt con ruta crítica + export CSV. AC-13 (caso resuelto a mano) verde. Follow-up: `# type: ignore[import-untyped]` en networkx (sin py.typed) → añadir `types-networkx` si se quiere limpiar.
- **L17** (2026-11-12): RP-10 revisado nativo (2 lentes: reliability + resilience) → **approved**. 4 hallazgos no bloqueantes (follow-up): `R3-determinism-boundary` (planificacion.py:107-123, sugerencia), `R4-001` (planificacion_extraction.py:89), `R4-002` (api/planificacion.py:103), `R4-003` (PlanificacionGantt.tsx:93).
