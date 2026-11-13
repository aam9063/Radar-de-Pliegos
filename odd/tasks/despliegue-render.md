# Despliegue en Render

> Owner: Albert · Rama: `feat/despliegue-render` · Estado: en curso

## Specs

- **S1 · Desplegar en Render.** "Quiero desplegarlo. Preparame todo e indicame todos los pasos uno a uno bien explicado. Vamos a desplegarlo en render". El repositorio debe quedar listo para desplegarse en Render sin editar código a mano, con los pasos escritos para que Albert los siga uno a uno.
- **S2 · Tres servicios.** Postgres gestionado, API como servicio Docker y frontend como static site, porque un static site no puede ejecutar el backend y el API necesita proceso.
- **S3 · Configuración por entorno.** El origen del frontend (CORS), la cadena de conexión que entrega Render (`postgresql://…`, no `postgresql+asyncpg://…`), el puerto (`PORT`) y el directorio de PDFs deben venir del entorno, no del código, sin romper el uso local con `docker compose`.
- **S4 · Persistencia de los PDFs.** Los PDFs subidos no pueden desaparecer en cada despliegue: disco persistente montado en el directorio de storage, con su coste explicado.
- **S5 · Cuando algo falle, saber por qué.** El documento de despliegue incluye verificación posterior (health, CORS, subida de un PDF, rutas profundas) y una tabla de problemas típicos con su causa.

## Tasks

- [x] **T1** Settings: CORS desde entorno y normalización de `DATABASE_URL` a `asyncpg` (TDD) — cubre S3 — commit: pendiente
- [x] **T2** Dockerfile del API: escuchar en `$PORT` — cubre S3 — commit: pendiente
- [x] **T3** `render.yaml`: Postgres + API con disco + static site con rewrite SPA — cubre S2, S4 — commit: pendiente
- [x] **T4** `docs/deploy-render.md`: pasos uno a uno, variables, verificación y problemas típicos — cubre S1, S5 — commit: pendiente

## Log

- **L1** (2026-11-13, Albert): "Quiero desplegarlo. Preparame todo e indicame todos los pasos uno a uno bien explicado. Vamos a desplegarlo en render"
- **L2** (2026-11-13, diagnóstico): Render Postgres soporta `pgvector` (PG13+ con `CREATE EXTENSION`) pero el esquema actual no usa tipos `vector`: ninguna migración crea la extensión, así que no es un requisito del despliegue. Los discos persistentes solo existen en servicios de pago; sin disco, los PDFs se pierden en cada reinicio. `app/main.py:12` fija `FRONTEND_ORIGINS` en código (solo localhost), `backend/Dockerfile` fija `--port 8000` y `Settings.database_url` exige el prefijo `postgresql+asyncpg://` mientras Render entrega `postgresql://`.
- **L3** (2026-11-13, implementación): T1–T4 con TDD. Cinco tests nuevos de `Settings` (esquema `postgres://` y `postgresql://` → `postgresql+asyncpg://`, prefijo ya correcto preservado, `sslmode=` traducido a `ssl=` porque asyncpg lo rechaza, orígenes por defecto y lista separada por comas, CORS aplicado a la app). `backend/Dockerfile` usa `${PORT:-8000}`. `render.yaml` con `radar-db` (free), `radar-api` (starter + disco 1 GB en `/app/storage`, healthcheck `/health`) y `radar-web` (static site, `rootDir: frontend`, rewrite `/*` → `/index.html`, caché inmutable para assets y `no-store` para el shell). `docs/deploy-render.md` con los pasos, costes, verificación y tabla de problemas.
- **L4** (2026-11-13, defecto encontrado y corregido): la suite de integración cayó con 39 errores `getaddrinfo failed` por el host `db`. Causa: un `backend/.env` local define `DATABASE_URL` con el nombre del servicio de compose y `get_settings()` se cachea al importar los módulos de la app, pero el conftest fijaba `DATABASE_URL` **después** de esos imports. Corregido moviendo el `setdefault` antes de los imports de `app` (`tests/integration/conftest.py`): la suite pasa a ser determinista frente a un `.env` de desarrollo. Suite completa: 230 tests verdes.
