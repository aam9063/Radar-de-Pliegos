# syntax=docker/dockerfile:1

FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code and migrations
COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations

EXPOSE 8000

# Apply database migrations before serving the API. Hosts (Render) inject the
# port to bind; local docker compose keeps working through the 8000 default.
CMD ["sh", "-c", "uv run alembic upgrade head && exec uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
