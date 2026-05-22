# ─────────────────────────────────────────────────────────────────
#  BatchBook — Backend Dockerfile (multi-stage: dev + prod)
#  Build context: project root (BatchBook/)
# ─────────────────────────────────────────────────────────────────

# ── Shared base ───────────────────────────────────────────────────
FROM python:3.14-slim AS base

# Install uv from the official distroless image (fastest method)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uvx /usr/local/bin/uvx

WORKDIR /app

# Copy dependency manifests first for layer-cache efficiency
COPY pyproject.toml uv.lock ./

# ── Dev stage ─────────────────────────────────────────────────────
FROM base AS dev

# --mount=type=cache keeps the uv download cache on the host between builds.
# Packages that haven't changed are never re-downloaded, even when uv.lock changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Source code is volume-mounted at runtime, not baked in
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app:app", \
     "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Prod stage ────────────────────────────────────────────────────
FROM base AS prod

# Same cache mount — prod deps re-use the same host cache as dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Bake in source code
COPY . .

EXPOSE 8000
# 2 workers; increase to (2 × CPU cores + 1) if on a bigger machine
CMD ["uv", "run", "uvicorn", "app:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
