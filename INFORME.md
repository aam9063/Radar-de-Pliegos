# Informe final — Radar de Pliegos

> Proyecto de aprendizaje: extraer datos fiables de pliegos de contratación pública de obra y emitir una recomendación GO / NO-GO / REVISAR contra el perfil de una constructora. La IA prepara, la persona decide.

---

## 1. Qué se quería implementar

Según `BRIEF.md`:

- **Fase 1 (MVP)**: subir PDFs de una licitación (PCAP/PPT/ANEXO), extraer texto por página (PyMuPDF), extraer 20 campos con el LLM (`PliegoFicha`, cada campo con valor + evidencia + confianza), verificar cada cita de forma determinista, fusionar documentos por prioridad de fuentes, aplicar un motor de decisión **determinista** GO/NO-GO/REVISAR contra el perfil de empresa, un frontend (lista/alta/detalle con visor PDF/perfil) y una evaluación honesta sobre 5 pliegos reales.
- **Fase 2 (opcional)**: planificador mínimo — el LLM propone actividades, el código calcula el camino crítico (CPM) y se muestra un Gantt.

Restricciones clave: la IA **nunca decide ni calcula**; reglas y cálculos viven en código determinista y testeado. Sin OCR, sin scraping, sin frameworks de agentes pesados, todo local con Docker.

## 2. Qué se ha hecho (tarea a tarea)

| Tarea | Qué se implementó |
| --- | --- |
| **RP-01** Esqueleto | Monorepo `backend/` + `frontend/`, FastAPI con `/health`, React 19 + Vite + Tailwind, `docker-compose.yml` (db/api/web con healthchecks), CI de GitHub Actions, `evals.yml`. |
| **RP-02** Modelos + subida | Modelos async de SQLAlchemy (`licitacion`, `documento`, `pagina`) + migración Alembic; endpoints `POST/GET /licitaciones` y `POST /licitaciones/{id}/documentos` (multipart + `tipo`); extracción de texto por página con PyMuPDF (`sin_texto=true` sin OCR). |
| **RP-03** LLMClient | Puerto `LLMClient` (Protocol puro en `domain/`) + `NanLLMClient` (openai SDK, `json_schema` sin tools, semáforo 5, backoff+jitter ante 429/5xx) + `FakeLLMClient` determinista para tests. |
| **RP-04** PliegoFicha | Esquema Pydantic v2 (`CampoExtraido[T]`, `Evidencia`, 20 campos), extractor con marcadores `[[DOC:<tipo>|P:<n>]]`, reintento único ante JSON inválido → 502 sin ficha a medias. |
| **RP-05** Verificación + fusión | Extracción **por documento** (refactor desde single-call), fusión determinista con prioridad `PCAP > ANEXO > PPT > OTRO` + avisos de conflicto, verificación de citas (normalización + `rapidfuzz` ≥ 0,9) → `verificado=false`. |
| **RP-06** Motor de decisión | Perfil de empresa + motor **puro** (6 reglas, NO-GO > REVISAR, razones con evidencia) + resumen LLM (solo redacta, no decide). |
| **RP-07** Frontend | 4 vistas (lista con recomendación, alta con drag-and-drop, detalle ficha+visor+decisión, perfil) siguiendo los 3 mockups de Albert; clic en evidencia → visor salta a `#page=N`; `GET /documentos/{id}/pdf` + CORS. |
| **RP-08** Evaluación | Runner `python -m evals.run` + comparación determinista (tolerancia 0,1 % en económicos, listas sin orden) + informe markdown + esquema de ground truth. |
| **RP-09** README + cierre | README, revisión 4R del slice, borrador de PR. |
| **RP-10** Planificador CPM | `calcular_cpm` puro (networkx, fechas tempranas/tardías, holguras, ruta crítica) + propuesta de actividades desde el PPT + Gantt/CSV. |
| **MP-01..MP-03** Mejora precisión | Normalización determinista de la comparación, canonicalización del ground truth, regla solvencia-vs-clasificación (51 % → **71 %**). |

## 3. Errores cometidos, cómo se identificaron y cómo se arreglaron

| Error | Cómo se identificó | Solución |
| --- | --- | --- |
| `db` no arrancaba en Docker (exit 1) | Logs del contenedor: "PostgreSQL data in /var/lib/postgresql/data" | Postgres 18 monta los datos en `/var/lib/postgresql` (no `/data`) |
| Falta `python-multipart` (FastAPI multipart) | Bloqueo del worker en preflight | `uv add python-multipart` |
| Revisión nativa excedió presupuesto (`lens_context_budget_exceeded`) | 46 ficheros / 4759 líneas (los lockfiles dominan) | Partir en commits revisables; revisar nativo solo el de alto riesgo |
| `pnpm/action-setup` sin versión ("No pnpm version") | Log de GitHub Actions | La acción busca `packageManager` en la **raíz**; fijé `version: 11.4.0` |
| `Event loop is closed` al correr el eval en Windows | Traceback del SDK (ProactorEventLoop + cierre TLS de `httpx2/httpcore2/anyio`) | `WindowsSelectorEventLoopPolicy` + un único `asyncio.run` para los 5 pliegos |
| e2e de la PR fallaba (frontend se quedaba en `/licitaciones/nueva`) | El test esperaba navegar al detalle y no lo hacía | La imagen de `api` **no aplicaba migraciones**: DB vacía → `POST /licitaciones` 500. Se añadió `alembic upgrade head` al `CMD` del Dockerfile |
| `astral-sh/setup-uv@v10` no resuelve | Anotación del CI | No existe el tag major `v10`; se fijó la versión completa `v10.3.3` |
| Regla "verbatim" de listas **empeoró** `penalidades` (20→0 %) | Re-corrida del eval (la métrica lo midió) | Se descartó; se conservó solo la regla solvencia-vs-clasificación |
| `qwen3.6` peor que `deepseek-v4-flash` | Prueba A/B con el mismo eval | Se mantuvo `deepseek-v4-flash` (71 % vs 66 %, y 98,8 % vs 82,1 % de citas verificadas) |
| Warnings de Node 20 / ubuntu-latest en CI | Anotaciones de GitHub | Bump de acciones a últimas majors + runner `ubuntu-24.04` |
| `# type: ignore` en networkx | mypy `--strict` | Documentado con motivo (networkx no trae `py.typed`); pendiente opcional: `types-networkx` |

Además, decisiones de anotación resueltas con Albert: la clasificación "no exigida" (VE < 500 k€) se anota `null`, y el ground truth de subcontratación/penalidades se canonicalizó a hechos cortos.

## 4. Tests: qué tipos hay y por qué esos y no otros

**Principio**: cada comportamiento determinista tiene un test; todo lo que depende del LLM se prueba con `FakeLLMClient`; la API real solo se usa en la evaluación manual.

| Tipo | Herramienta | Qué cubre | Por qué |
| --- | --- | --- | --- |
| **Unitario backend** | `pytest` | Funciones puras de `domain/` (motor de decisión, CPM, fusión, verificación de citas, comparación/normalización del eval) y adaptadores (NaN con semáforo/backoff, fake) | Son deterministas y sin I/O → entrada fija ⇒ salida fija. Rápidos y sin red. |
| **Integración backend** | `pytest` + `httpx` (`ASGITransport`) + Postgres real | Endpoints API + persistencia (subida de PDF, extracción, decisión, perfil, CPM, servir PDF) | `httpx` levanta la app sin servidor; la DB real (con `alembic upgrade head` en `conftest`) pilla errores de schema/FK/transacciones que un mock no vería. |
| **Componente frontend** | Vitest + Testing Library | Render de vistas y comportamientos de UI (clic en evidencia → visor `#page=N`, contadores de ficha, Gantt) | `jsdom` simula el DOM sin navegador: rápido, determinista, accesible por rol/texto. |
| **e2e** | Playwright | Flujo real de usuario contra `docker compose` (crear licitación, subir PDF, llegar al detalle) | Único test que ejercita navegador + nginx + API + DB juntos; corre solo en PR para no ralentizar cada push. |
| **Evaluación** | `evals.run` (manual) | Precisión real del LLM sobre 5 pliegos anotados | No se puede "testear" la calidad del modelo sin llamarlo; por eso es manual, gasta cuota y no corre en CI. |

**Por qué no otros enfoques:**

- **No se testea el LLM real en CI** (coste, no-determinismo y `AGENTS.md` lo prohíbe): se usa `FakeLLMClient` con respuestas/errores programados (éxito, JSON inválido, 429, 5xx).
- **La comparación del eval es exacta, no semántica**: un "juez" semántico tendría que ser otro LLM, lo cual sería circular. Por eso normalizamos formato de forma determinista y lo documentamos.
- **No se hace unit-test de los modelos SQLAlchemy** (son declarativos): los cubre la integración contra Postgres real.
- **TDD**: cada regla primero se escribió el test (RED observado), luego el mínimo código (GREEN), luego refactor con la suite en verde. Las salidas RED/GREEN quedaron anotadas en el feature document.

## 5. Resultados de la evaluación (lo más importante para la entrevista)

| Métrica | Valor |
| --- | --- |
| **Precisión global** | **71 %** (baseline 51 %) |
| Evidencias verificadas | 98,8 % |

- **Lo que el LLM clava (100 %)**: expediente, presupuestos, valor estimado, revisión de precios, fecha límite, garantía provisional, tramitación — datos "de portada".
- **Donde falla**: campos **estructurales** (listas de criterios, penalidades, solvencias) — el modelo fusiona/desdobla listas o reformula, aunque las citas que devuelve están casi siempre en la página (98,8 %).
- **Modelo**: `deepseek-v4-flash` supera a `qwen3.6` en precisión (71 % vs 66 %) y en citas verificadas (98,8 % vs 82,1 %), y es ~4× más rápido.

**Lección de diseño (la tesis del proyecto)**: la IA prepara, pero la confianza viene del **código determinista** — la verificación de citas (fuzzy ≥ 0,9) y las reglas de decisión/CPM no fallan nunca; el LLM solo extrae y redacta.

## 6. Por qué se hizo así y no de otra forma (decisiones justificadas)

- **`domain/` puro, sin FastAPI/SQLAlchemy/SDK**: las reglas de negocio (motor, fusión, verificación, CPM, comparación) son funciones puras testeables e independientes de la infraestructura. Es lo que hace el sistema "de fiar".
- **Puerto `LLMClient` con dos implementaciones**: permite testear todo sin la API real y cambiar de proveedor/modelo sin tocar el resto.
- **Extracción documento a documento + fusión determinista** (en vez de una sola llamada con todo el pliego): así los conflictos entre PCAP/PPT se resuelven por regla, no por el LLM (AC-07).
- **Comparación exacta + normalización de formato** (no un juez semántico): honestidad y reproducibilidad; normalizamos solo formato, nunca significado.
- **Regla solvencia-vs-clasificación** y no "verbatim": medido por el eval, "verbatim" empeoraba; nos quedamos con lo que la métrica demostró mejor.
- **Sin persistir la planificación/CPM**: se calcula on-demand (Fase 2 mínima); si se usara en producción habría que cachear.
- **`alembic upgrade head` en el arranque del contenedor**: la DB siempre está migrada, también en CI/e2e.

## 7. Conclusión

Radar de Pliegos cumple el brief completo (Fase 1 + Fase 2) con una evaluación **honesta**: 71 % de precisión sobre 5 pliegos reales, con el 98,8 % de las citas verificadas. El aprendizaje central es empírico: **extraer números es fácil para el LLM; reconstruir listas complejas repartidas en cláusulas no lo es** — y por eso el producto no confía en el LLM para decidir: verifica cada cita y deja que el código determinista calcule la recomendación.
