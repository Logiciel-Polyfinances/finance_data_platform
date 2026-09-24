# --- Stage 1: build the React/Vite frontend ---------------------------------
# Kept separate so the final image doesn't need Node at all -- only the
# built static output (frontend/dist) is copied over below.
FROM node:20-slim AS frontend-build

# Optionally bake an API key into the build so a stack can ship a
# pre-authenticated UI (the local compose passes local-dev-key). No arg -> empty
# -> nothing baked in, so prod builds stay keyless.
ARG VITE_API_KEY=""
ENV VITE_API_KEY=$VITE_API_KEY

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

# --- Stage 2: the actual API image -------------------------------------------
FROM python:3.12-slim

# uv provides the resolver + installer; the pinned binary is copied straight
# from Astral's image so we don't pip-install it.
COPY --from=ghcr.io/astral-sh/uv:0.10.9 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Install dependencies first (cached layer, independent of the app source) from
# the locked versions only -- --no-dev drops pytest/ruff/etc, --frozen fails if
# the lock is out of sync with pyproject.toml.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY alembic.ini .
COPY alembic ./alembic
COPY src ./src
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# Now install the project itself into the same venv.
RUN uv sync --frozen --no-dev

# Put the venv on PATH so alembic/uvicorn resolve without `uv run`.
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# Migrations run on every container start instead of being a manual step
# someone has to remember before deploying -- alembic upgrade head is a
# no-op if the schema is already current.
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
