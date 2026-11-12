# Radar de Pliegos

Aplicación web que recibe los PDFs de una licitación pública de obra (PCAP, PPT y anexos), extrae los datos que importan para decidir si presentarse y emite una recomendación **GO / NO-GO / REVISAR** contra el perfil de una constructora. Cada dato va con su evidencia (documento, página y cita literal verificada).

Principio de diseño: **la IA prepara, la persona decide**. El LLM lee y extrae; las reglas de decisión y todos los cálculos viven en código determinista y testeado.

## Arranque (5 comandos o menos)

```bash
git clone <repo>
cd Radar-de-Pliegos
cp .env.example .env        # rellena NAN_API_KEY
docker compose up -d        # db + api + web con healthchecks
```

- Web: http://localhost:5173
- API: http://localhost:8000 (`GET /health` → 200)

## Stack

- **Backend** (`backend/`): Python 3.14 + FastAPI + SQLAlchemy 2 (async) + Alembic + PostgreSQL 18 (pgvector) + PyMuPDF. Calidad: ruff, mypy `--strict`, pytest.
- **Frontend** (`frontend/`): React 19 + TypeScript strict + Vite + pnpm + Tailwind CSS + TanStack Query + React Router. Tests: Vitest + Playwright.
- **IA**: NaN Builders (`deepseek-v4-flash`) vía un puerto `LLMClient` (`NanLLMClient` real y `FakeLLMClient` para tests). Ningún test llama a la API real.

## Desarrollo

```bash
# Backend
cd backend && uv sync
uv run alembic upgrade head
uv run pytest
uv run ruff check . && uv run mypy --strict app

# Frontend
cd frontend && pnpm install
pnpm dev
pnpm lint && pnpm typecheck && pnpm vitest run && pnpm build
```

## Evaluación

```bash
cd backend && uv run python -m evals.run
```

Usa la API real (`NAN_API_KEY`) y compara contra los pliegos anotados en `evals/ground_truth/`. Genera el informe en `evals/results/`.

**Última precisión global: 51 %** (5 pliegos reales, 2026-11-12; evidencias verificadas 97,7 %). Detalle y análisis en `evals/results/`.

## Cómo funciona

1. **Subida**: subís los PDFs indicando el tipo (`PCAP`, `PPT`, `ANEXO`, `OTRO`).
2. **Texto por página**: PyMuPDF extrae el texto de cada página (sin OCR; las páginas escaneadas se marcan `sin_texto`).
3. **Extracción**: el LLM rellena la ficha `PliegoFicha` documento a documento, con cita y página por dato.
4. **Verificación**: el código comprueba cada cita contra el texto (fuzzy ≥ 0,9) y marca lo no verificado.
5. **Fusión**: si hay conflicto entre documentos, gana `PCAP > ANEXO > PPT > OTRO` (con aviso).
6. **Decisión**: reglas deterministas contra el perfil de empresa → GO / NO-GO / REVISAR. El LLM solo redacta el resumen.
