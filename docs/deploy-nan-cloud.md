# Deploying to NaN Cloud

NaN Cloud builds a Docker image per **app** from a GitHub repository and serves
it behind a public HTTPS domain inside a Space. Two consequences shape this
deployment:

- **One container per app and one internal port per app.** NaN Cloud does not
  inject a `PORT` variable: the port you type in the form is the port your
  container must be listening on.
- **There is no managed database.** The API needs an external PostgreSQL.

So the deployment is three pieces: one external Postgres and two apps.

```mermaid
flowchart LR
    USER["Browser"] --> WEB["App: radar-web<br/>frontend/Dockerfile<br/>nginx :80"]
    WEB -->|"VITE_API_URL<br/>baked at build time"| API["App: radar-api<br/>backend/Dockerfile<br/>uvicorn :8000 or :3080"]
    API -->|"DATABASE_URL"| PG[("External Postgres<br/>Neon · Supabase · …")]
    API --> VOL[("Persistent volume<br/>mounted at the storage path")]
    API --> LLM["NaN Builders API"]
```

**Why two apps and not one.** Serving the SPA from the API container would force
every backend route under an `/api` prefix, because the SPA and the API share
paths (`/perfil`, `/licitaciones/{id}`). That would touch every test and the
typed client for no functional gain. Two apps keep the architecture identical to
`docker compose`; only the host changes.

---

## Step 0 — Create the external database

Any managed PostgreSQL works. Neon and Supabase both have a free tier and hand
out a URL that already contains the SSL requirement.

1. Create the project and the database (name it `radar`).
2. Copy the connection string. It looks like:

   ```
   postgresql://radar:secret@ep-cool-name-123456.eu-central-1.aws.neon.tech/radar?sslmode=require
   ```

3. Keep it for step 2. **Do not edit it.** The API normalises the scheme to
   `postgresql+asyncpg://` and translates `sslmode=` to `ssl=` for asyncpg, so the
   string the provider gives you is exactly what you paste.

Migrations run automatically when the API container starts
(`alembic upgrade head`), so there is no manual schema step.

## Step 1 — App `radar-api`

In `cloud.nan.builders/apps/new`:

| Field               | Value                                                                                 |
| ------------------- | ------------------------------------------------------------------------------------- |
| Space               | the Space you want (`prod · basic` is enough: 2 vCPU, 4 GiB RAM, 20 GiB disk, 5 pods) |
| GitHub installation | your user                                                                             |
| Repository          | `aam9063/Radar-de-Pliegos`                                                            |
| App name            | `radar-api`                                                                           |
| Branch / tag        | `main`                                                                                |
| Dockerfile path     | `backend/Dockerfile`                                                                  |
| **Build context**   | **`backend`**                                                                         |
| Expose over HTTP    | checked                                                                               |
| Container port      | `8000`, or `3080` if you prefer the value already in the form                         |

> **The build context is the field that silently breaks the build.** The API
> Dockerfile copies `pyproject.toml`, `app/`, `migrations/` from the context root.
> With the default context `.` those files are not there and the build fails on
> the first `COPY`. Set it to `backend`.

**Port rule.** The number in the form and the port inside the container must be
the same. The image runs `uvicorn … --port ${PORT:-8000}`:

- Type `8000` in the form and add no `PORT` variable, **or**
- Type `3080` in the form and add `PORT=3080` to the environment.

Do not mix them: a mismatch is the most common `502` on this platform.

**Advanced options.**

- **Replicas: 1.** The PDFs live on a local volume; more replicas would each
  serve a different view of the disk.
- **Persistent storage: on.** The platform mounts the volume at **`/data`**, so
  `STORAGE_DIR` must be `/data`. Without the volume, every deploy or restart
  loses the uploaded PDFs.

**Environment variables** (runtime):

| Variable           | Required                     | Value                                                                                            |
| ------------------ | ---------------------------- | ------------------------------------------------------------------------------------------------ |
| `DATABASE_URL`     | yes                          | the connection string from step 0                                                                |
| `NAN_API_KEY`      | yes                          | your NaN Builders key (`sk-…`)                                                                   |
| `FRONTEND_ORIGINS` | yes                          | the public URL of the `radar-web` app, e.g. `https://radar-web.nan.builders` — no trailing slash |
| `STORAGE_DIR`      | yes                          | `/data` (the platform's volume mount path)                                                       |
| `PORT`             | only if the form says `3080` | `3080`                                                                                           |

Optional, with defaults already correct:

| Variable                   | Default                       |
| -------------------------- | ----------------------------- |
| `NAN_BASE_URL`             | `https://api.nan.builders/v1` |
| `NAN_MAX_CONCURRENCY`      | `5`                           |
| `NAN_MAX_RETRIES`          | `3`                           |
| `NAN_BACKOFF_BASE_SECONDS` | `0.5`                         |
| `EXTRACTION_MODEL`         | `deepseek-v4-flash`           |
| `SUMMARY_MODEL`            | `deepseek-v4-flash`           |

Click **Deploy**. Watch the build; when it finishes, open
`https://<api-domain>/health`. It must answer `{"status":"ok"}`.

## Step 2 — App `radar-web`

Create a second app from the same repository:

| Field             | Value                                       |
| ----------------- | ------------------------------------------- |
| App name          | `radar-web`                                 |
| Branch / tag      | `main`                                      |
| Dockerfile path   | `frontend/Dockerfile`                       |
| **Build context** | **`frontend`**                              |
| Expose over HTTP  | checked                                     |
| Container port    | `80` (the nginx in the image listens on 80) |

**Build variable** — this one is not a runtime variable:

| Variable       | Kind      | Value                                                                                            |
| -------------- | --------- | ------------------------------------------------------------------------------------------------ |
| `VITE_API_URL` | **build** | the public URL of the `radar-api` app, e.g. `https://radar-api.nan.builders` — no trailing slash |

Vite inlines this value into the JavaScript bundle while building, so it must be
present at **build** time. Changing it later requires a rebuilt image, not just a
restart.

No persistent storage and no other variables are needed for this app.

## Step 3 — Close the loop on CORS

The browser calls the API cross-origin, so one value ties the two apps:

1. Copy the public URL of `radar-web`.
2. In `radar-api` → environment, set `FRONTEND_ORIGINS` to that exact URL.
3. Save. If the platform restarts the app, wait for it; changing a runtime
   variable does not require rebuilding the image.

Multiple origins are allowed, comma-separated. Never add a trailing slash: the
browser sends the origin without one, so an extra slash makes every request fail.

## Step 4 — Verify end to end

1. `https://<api-domain>/health` → `{"status":"ok"}`.
2. The site loads with no CORS errors in the browser console.
3. Save the company profile, reload: the values persist (this exercises the
   database).
4. Create a tender, upload a PDF, wait for the ficha (the extraction calls the
   NaN inference API, so `NAN_API_KEY` must have quota).
5. The PDF renders in the viewer; clicking a citation jumps to its page.
6. Reload a deep link such as `/licitaciones/1`: it renders, not 404 (the nginx
   config in the image has the SPA fallback).
7. Redeploy `radar-api`, then open an existing document again: the PDF is still
   there (this proves the volume is mounted at `STORAGE_DIR`).

## Troubleshooting

| Symptom                                                       | Cause and fix                                                                                      |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Build fails on a `COPY` of `pyproject.toml` or `package.json` | Build context is `.`; set it to `backend` (API) or `frontend` (web)                                |
| `502` from the public URL                                     | The form port and the container port differ. Use `8000`/`8000`, or `3080` with `PORT=3080`         |
| Logs show `alembic` errors at boot                            | `DATABASE_URL` is wrong, the database is unreachable, or its SSL mode was edited by hand           |
| `getaddrinfo failed` for a database host                      | The connection string points at an internal or compose host (`db`); use the provider's public host |
| CORS error in the console                                     | `FRONTEND_ORIGINS` does not match the web origin exactly: scheme, no trailing slash                |
| Site loads but every request fails                            | `VITE_API_URL` was empty or wrong when the image was built. Fix the build variable and rebuild     |
| Uploads return 500                                            | The volume is not mounted, or `STORAGE_DIR` differs from the mount path                            |
| PDFs disappear after a deploy                                 | The API app is not marked persistent                                                               |
| Extraction returns 401/429                                    | `NAN_API_KEY` missing, invalid or out of quota                                                     |
| Every route works except a reload                             | The image is not the one with the nginx SPA fallback; rebuild from `main`                          |

## Notes

- Each push to the configured branch triggers a new build while auto-deploy is
  on. Use the same branch for both apps so they never drift apart.
- Branch, Dockerfile, port and resources can be changed from the app's settings
  panel without recreating the app.
- `render.yaml` in this repository is the Render equivalent and stays valid; the
  two platforms are independent.
