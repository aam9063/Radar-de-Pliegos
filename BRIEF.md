# BRIEF · Radar de Pliegos

> Proyecto de aprendizaje inspirado en el módulo de licitaciones de **Miranda AI** (Crata AI).
> Autor y dueño del producto: Albert. Fecha del brief: 11 nov 2026.
> Objetivo personal: entender en primera persona el problema que resuelve Miranda antes de la entrevista con el CTO de Crata (lunes 16 nov, 15:00).

---

## 0. Cómo usar este brief con ODD (instrucciones para el agente)

1. Este documento es la **especificación de producto**. Léelo entero antes de explorar el código.
2. El trabajo es **sustancial** según ODD: tiene varios pasos de implementación y progreso que merece la pena recuperar. Antes de la primera escritura de código crea el feature document `odd/tasks/radar-pliegos-mvp.md` y su espejo en Engram (`odd/radar-pliegos-mvp/tasks`).
3. El feature document **cita este brief literalmente** en su sección de objetivo y problema. Los handoffs a subagentes apuntan al feature document, nunca lo parafrasean.
4. Cada tarea del checklist lleva un **ID estable** (`RP-01`, `RP-02`...) y enlaza los criterios de aceptación (`AC-xx`) que cubre.
5. TDD y RDD están **activados** según `AGENTS.md`. Cada tarea cierra con un work-unit commit en su rama `feat/*` y la evidencia en el feature document.
6. Si algo de este brief es ambiguo y cambia la siguiente acción, haz **una** pregunta concreta a Albert. No amplíes el alcance por tu cuenta: los hallazgos no autorizan scope nuevo.

---

## 1. Introducción

**Radar de Pliegos** es una aplicación web que recibe los documentos de una licitación pública de obra (pliego de cláusulas administrativas, pliego de prescripciones técnicas y anexos, en PDF), extrae los datos que importan para decidir si presentarse y emite una recomendación **GO / NO-GO / REVISAR** frente al perfil de una constructora.

Cada dato extraído va acompañado de su **evidencia**: documento, página y cita literal. El usuario no tiene que leer 120 páginas; verifica una ficha de una pantalla y salta a la página exacta cuando duda.

Principio de diseño, igual que Miranda: **la IA prepara, la persona decide**. El LLM lee y extrae; las reglas de decisión y cualquier cálculo viven en código determinista y testeado.

## 2. El problema

- Una constructora mediana revisa decenas de licitaciones al mes en la Plataforma de Contratación del Sector Público.
- Cada licitación son 2 a 6 PDFs y entre 50 y 200 páginas. Los datos críticos están repartidos: el presupuesto en un sitio, la clasificación exigida en otro, las penalidades en un anexo.
- Leer y resumir un pliego lleva entre 1 y 4 horas de un técnico cualificado.
- Un dato mal leído sale caro: presentarse sin la clasificación exigida supone exclusión; descartar una licitación buena por no tener tiempo de leerla es dinero perdido.
- Las herramientas genéricas (pegar el PDF en un chat) no citan la página, inventan datos cuando no los encuentran y no aplican los criterios de la empresa.

## 3. Para quién

| Persona | Qué necesita | Cómo usa Radar |
| --- | --- | --- |
| **Técnico de licitaciones / jefe de estudios** (usuario principal) | Saber en minutos si una licitación encaja y dónde están los datos | Sube los PDFs, revisa la ficha, comprueba las citas dudosas |
| **Gerente o director de producción** (secundario) | Decidir presentarse o no con información fiable | Lee la recomendación y sus razones |

## 4. Objetivo y métrica de éxito

- En **menos de 2 minutos** por licitación, una ficha estructurada donde cada dato no nulo tiene documento, página y cita verificable.
- Una recomendación GO / NO-GO / REVISAR con razones trazables a evidencias.
- Una **evaluación honesta**: precisión por campo medida sobre 5 pliegos reales anotados a mano. Esa cifra, sea la que sea, es lo que Albert contará en la entrevista.

## 5. Alcance (scopes)

### Fase 1 · MVP (obligatorio)

**S1 · Licitaciones y subida de documentos**
- Crear una licitación y subirle de 1 a N PDFs, cada uno con un tipo: `PCAP`, `PPT`, `ANEXO`, `OTRO`.
- Guardar el PDF original y sus metadatos.

**S2 · Extracción de texto por página**
- Extraer el texto de cada página con PyMuPDF conservando número de página.
- Guardar `documento → páginas` en Postgres.
- Una página sin texto (PDF escaneado) se marca `sin_texto = true`. No se hace OCR.

**S3 · Extracción estructurada con LLM**
- Esquema Pydantic `PliegoFicha` con estos campos:
  - Identificación: `expediente`, `objeto`, `organo_contratacion`, `cpv`, `procedimiento` (abierto, abierto simplificado, restringido, negociado...), `tramitacion` (ordinaria, urgente).
  - Económicos: `presupuesto_base_sin_iva`, `presupuesto_base_con_iva`, `valor_estimado`, `revision_precios` (sí/no + fórmula si aparece).
  - Plazos: `plazo_ejecucion` (valor + unidad), `fecha_limite_presentacion`.
  - Requisitos: `clasificacion_exigida` (lista de grupo, subgrupo y categoría), `solvencia_economica`, `solvencia_tecnica`.
  - Adjudicación: `criterios_adjudicacion` (lista de nombre, tipo `automatico | juicio_valor` y ponderación en puntos o %).
  - Riesgos: `penalidades` (lista), `garantia_provisional`, `garantia_definitiva`, `subcontratacion_limites`.
- Cada campo es un `CampoExtraido[T]` con: `valor: T | None`, `evidencia: list[Evidencia]` (documento, página, cita literal de 30 palabras como máximo) y `confianza: alta | media | baja`.
- Regla de oro: **si el dato no aparece, `valor = None` y sin evidencia**. Nunca se inventa ni se deduce.
- Llamada a la API de NaN Builders con el modelo `deepseek-v4-flash` y `response_format` `json_schema` en `/chat/completions` **sin tools** (con tools ese modo no está soportado). El texto se envía con marcadores de página: `[[DOC:PCAP|P:12]]`.
- Si el JSON no valida contra Pydantic: **un** reintento enviando el error de validación. Si vuelve a fallar: error 502 claro y nada guardado a medias.
- Cuando hay varios documentos, prioridad de fuentes en caso de conflicto: `PCAP > ANEXO > PPT > OTRO`. El conflicto se registra como aviso en la ficha.

**S4 · Verificación de evidencias (determinista)**
- Para cada evidencia, el código comprueba que la cita aparece en el texto de esa página (coincidencia normalizada: minúsculas, espacios, acentos; tolerancia fuzzy ≥ 0,9).
- Si no aparece, el campo queda `verificado = false` y la interfaz lo muestra como "sin verificar".

**S5 · Perfil de empresa**
- Un único perfil editable: clasificaciones que posee (grupo, subgrupo, categoría), volumen anual de negocio medio, provincias donde trabaja, tipos de obra, rango de presupuesto de interés y días mínimos para preparar una oferta.

**S6 · Motor de decisión GO / NO-GO / REVISAR (código, no LLM)**
- Reglas puras y testeadas, por ejemplo:
  - Falta una clasificación exigida → `NO-GO`.
  - Solvencia económica exigida mayor que el volumen de negocio → `NO-GO`.
  - Días hasta la fecha límite menores que el mínimo del perfil → `NO-GO`.
  - Presupuesto fuera de rango → `REVISAR`.
  - Algún campo crítico nulo o sin verificar → `REVISAR`.
  - Todo lo demás → `GO`.
- Cada razón enlaza a la evidencia del campo que la provoca.
- El LLM solo redacta, a partir de las razones ya calculadas, un resumen de 3 a 5 frases para el gerente. No decide nada.

**S7 · Frontend**
- Lista de licitaciones con estado (pendiente, procesando, lista, error) y recomendación.
- Alta de licitación y subida de PDFs con arrastrar y soltar.
- Vista de detalle: ficha a la izquierda, visor PDF a la derecha. Al pulsar una evidencia, el visor salta a esa página.
- Panel de decisión con las razones y el resumen.
- Pantalla de perfil de empresa.

**S8 · Evaluación**
- Carpeta `evals/` con 5 licitaciones reales de obra descargadas a mano de la Plataforma de Contratación del Sector Público y `evals/ground_truth/<expediente>.json` anotado por Albert.
- Comando `uv run python -m evals.run` que extrae, compara con el ground truth y genera `evals/results/<fecha>.md` con: precisión por campo, precisión global, % de evidencias verificadas y los 3 fallos más frecuentes.
- La evaluación usa la API real y **no** corre en el CI por defecto (solo con `workflow_dispatch` y el secreto `NAN_API_KEY`).

### Fase 2 · Extensión (solo si la Fase 1 está cerrada y en verde)

**S9 · Planificador mínimo**
- A partir del PPT, el LLM propone una lista de actividades (nombre, duración estimada en días, predecesoras) con evidencia.
- El código calcula el método del camino crítico con `networkx`: fechas tempranas y tardías, holguras y ruta crítica.
- Vista Gantt sencilla con la ruta crítica resaltada y exportación CSV.
- La idea a demostrar es la misma: el LLM propone, el código calcula.

## 6. Lo que NO queremos (non-goals)

- Scraping o descarga automática desde la Plataforma de Contratación. Los PDFs se suben a mano.
- OCR de PDFs escaneados.
- Autenticación, multiusuario o multiempresa.
- Redacción de la memoria técnica, cálculo de presupuestos o lectura de ficheros BC3.
- Que el LLM tome la decisión GO / NO-GO o haga cualquier cálculo numérico.
- Frameworks de agentes pesados (LangChain, LangGraph, CrewAI). SDK `openai` apuntando a NaN + Pydantic es suficiente.
- Fine-tuning, bases de datos vectoriales externas o embeddings (no hacen falta en este proyecto).
- Licitaciones de servicios o suministros. Solo obras.
- Despliegue en la nube. Todo corre en local con Docker.
- Llamadas reales a la API de IA en los tests del CI.
- Pulido visual más allá de un diseño limpio y usable.

## 7. Restricciones

- Stack, Git, TDD, RDD y CI según `AGENTS.md`.
- Límites de NaN Builders: 60 peticiones por minuto y 7 concurrentes por clave. El cliente usa un semáforo de 5 y backoff exponencial ante 429.
- Contexto de 1M tokens: un pliego completo cabe en una llamada; aun así, se envía documento a documento y se fusionan resultados.
- Tiempo disponible: noches del 11 y 12 de noviembre (el 13 al 15 hay hackathon). La Fase 1 debe poder cerrarse en unas 6 horas de trabajo con agentes. Si no cabe, se recorta S7 a lo mínimo, nunca S4, S6 ni S8.

## 8. Modelo de datos (orientativo)

- `licitacion(id, nombre, creada_en, estado)`
- `documento(id, licitacion_id, tipo, nombre_fichero, ruta, num_paginas)`
- `pagina(id, documento_id, numero, texto, sin_texto)`
- `ficha(id, licitacion_id, datos jsonb, modelo, creada_en, avisos jsonb)`
- `perfil_empresa(id, datos jsonb)`
- `decision(id, licitacion_id, resultado, razones jsonb, resumen, creada_en)`

## 9. API (orientativa)

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/health` | Salud del servicio |
| `POST` | `/licitaciones` | Crear licitación |
| `GET` | `/licitaciones` | Listar |
| `POST` | `/licitaciones/{id}/documentos` | Subir PDF (multipart, campo `tipo`) |
| `POST` | `/licitaciones/{id}/extraer` | Lanzar extracción |
| `GET` | `/licitaciones/{id}/ficha` | Ficha con evidencias |
| `GET` | `/licitaciones/{id}/decision` | Recomendación y razones |
| `GET` | `/documentos/{id}/pdf` | PDF original para el visor |
| `GET`, `PUT` | `/perfil` | Perfil de empresa |

## 10. Criterios de aceptación

Formato: Dado / Cuando / Entonces. Cada uno debe tener al menos un test automatizado salvo que se indique otra cosa.

- **AC-01 · Arranque.** Dado el repo recién clonado con `.env` copiado de `.env.example`, cuando ejecuto `docker compose up -d`, entonces `api`, `web` y `db` quedan sanos y `GET /health` devuelve 200.
- **AC-02 · Subida y páginas.** Dada una licitación, cuando subo un PDF de 3 páginas con una página escaneada, entonces se guardan 3 páginas, la escaneada con `sin_texto = true`, y el texto de las otras es consultable por número de página.
- **AC-03 · Esquema válido.** Dado un pliego, cuando lanzo la extracción, entonces la ficha guardada valida contra `PliegoFicha`. Si el LLM (falso en el test) devuelve JSON inválido dos veces, la API responde 502 y no queda ficha a medias.
- **AC-04 · No inventar.** Dado un pliego de prueba sin penalidades, cuando se extrae, entonces `penalidades.valor` es `None` y no tiene evidencias.
- **AC-05 · Evidencias verificadas.** Dada una evidencia cuya cita no está en la página indicada, cuando se verifica, entonces el campo queda `verificado = false`. En el set de evaluación, al menos el 90% de los campos no nulos quedan verificados.
- **AC-06 · Decisión determinista.** Dada una tabla de al menos 8 casos (clasificación faltante, solvencia insuficiente, plazo corto, presupuesto fuera de rango, campo crítico nulo, caso GO...), cuando evalúo el motor, entonces devuelve el resultado y las razones esperadas, sin llamar al LLM.
- **AC-07 · Prioridad de fuentes.** Dado un presupuesto distinto en PCAP y PPT, cuando se fusionan, entonces gana el del PCAP y la ficha incluye un aviso de conflicto.
- **AC-08 · Evaluación.** Dados los 5 pliegos anotados, cuando ejecuto `uv run python -m evals.run`, entonces se genera el informe en `evals/results/` con precisión por campo y global. Objetivo: global ≥ 80%. Si no se alcanza, el informe explica las 3 causas principales. (Prueba manual, con evidencia en el feature document.)
- **AC-09 · Visor con cita.** Dada una ficha, cuando pulso una evidencia, entonces el visor PDF muestra esa página. (Test de componente con Vitest y un e2e con Playwright.)
- **AC-10 · Límites de la API.** Dado que NaN devuelve 429, cuando el cliente reintenta, entonces aplica backoff y nunca supera 5 peticiones concurrentes. (Test con cliente falso.)
- **AC-11 · CI en verde.** Dado un push a una rama `feat/*`, cuando corre GitHub Actions, entonces pasan lint, tipos, tests de backend y frontend y build, sin usar `NAN_API_KEY`.
- **AC-12 · README.** El README explica cómo arrancar en 5 comandos o menos, cómo ejecutar la evaluación y muestra la última cifra de precisión.
- **AC-13 · Fase 2 (opcional).** Dadas actividades con dependencias conocidas, cuando calculo el CPM, entonces la ruta crítica y las holguras coinciden con un caso resuelto a mano en el test.

## 11. Orden sugerido de tareas (para el checklist del feature document)

| ID | Tarea | Cubre |
| --- | --- | --- |
| RP-01 | Esqueleto del monorepo, Docker Compose, `/health`, CI mínimo | AC-01, AC-11 |
| RP-02 | Modelos, migraciones y subida de PDFs con extracción por página | AC-02 |
| RP-03 | Puerto `LLMClient`, adaptador NaN y cliente falso con límites | AC-10 |
| RP-04 | Esquema `PliegoFicha` y extracción con reintento | AC-03, AC-04 |
| RP-05 | Verificación de evidencias y fusión con prioridad de fuentes | AC-05, AC-07 |
| RP-06 | Perfil de empresa y motor de decisión | AC-06 |
| RP-07 | Frontend: lista, subida, ficha + visor, decisión, perfil | AC-09 |
| RP-08 | Evaluación con 5 pliegos e informe | AC-08 |
| RP-09 | README y cierre de la Fase 1 | AC-12 |
| RP-10 | (Fase 2) Planificador CPM + Gantt | AC-13 |

## 12. Qué quiere aprender Albert con esto

- Cómo de difícil es extraer datos fiables de pliegos reales y dónde falla (tablas, anexos, formatos raros).
- Cómo se diseña la verificación para que el usuario confíe en la IA.
- Por qué separar "el LLM propone" de "el código decide y calcula".
- Qué preguntar a Crata sobre cómo lo resuelven ellos a escala.
