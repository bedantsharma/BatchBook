# BatchBook

A vertical SaaS for India's small coaching institutes (tuition centers, 30–300 students). Owners manage students, batches, fees, and attendance. Students/parents see schedule, attendance, and fee status.

Backend: FastAPI + SQLAlchemy (async) + PostgreSQL (Supabase). Frontend: React 19 + Vite, in the `batchbookui/` git submodule.

## Getting Started

```bash
# Clone with the frontend submodule
git clone --recurse-submodules git@github.com:bedantsharma/BatchBook.git
cd BatchBook

# If already cloned without --recurse-submodules:
git submodule update --init
```

Create `.env` in the repo root (not committed):

```
PROJECT_NAME=BatchBook
DATABASE_URL=postgresql+asyncpg://[user]:[password]@[host]/postgres
SUPABASE_URL=https://[project-id].supabase.co
SUPABASE_KEY=sb_publishable_[key]
RAZORPAY_KEY_ID=rzp_test_xxxxx
RAZORPAY_KEY_SECRET=xxxxxxxx
META_WHATSAPP_TOKEN=xxxxxxxx
META_WHATSAPP_PHONE_NUMBER_ID=xxxxxxxx
WABA_ID=xxxxxxxx
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-xxx.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20xxxxxxxx
OTEL_SERVICE_NAME=batchbook-backend
ENVIRONMENT=development
```

Telemetry is opt-in — the backend only exports traces/metrics if `OTEL_EXPORTER_OTLP_ENDPOINT` is set. See [`telemetry.py`](./telemetry.py).

Create `batchbookui/.env`:

```
VITE_SUPABASE_URL=https://[project-id].supabase.co
VITE_SUPABASE_ANON_KEY=eyJhbGci...
```

## Running Locally

**Docker (preferred):**

```bash
make dev          # frontend + backend, hot-reload, foreground
make dev-d        # same, detached
make prod         # production build (nginx + 2 uvicorn workers)
make down         # stop everything
make logs         # tail all logs
make help         # list all targets
```

- Dev: frontend `http://localhost:5173`, backend `http://localhost:8000/docs`
- Prod: frontend `http://localhost:80`, backend `http://localhost:8000`

**Without Docker:**

```bash
# Backend
uv run uvicorn app:app --reload --port 8000

# Frontend
cd batchbookui && npm run dev
```

## Database Migrations (Alembic)

Migrations are managed with Alembic autogenerate. Always run from the repo root.

```bash
# After changing a model in models/
uv run alembic revision --autogenerate -m "describe your change"
uv run alembic upgrade head
```

`models/__init__.py` imports every model so Alembic's autogenerate can see them — add new models there too. Never hand-edit files under `alembic/versions/`.

In the local Docker prod stack (`make prod`), a one-shot `alembic-check` container blocks the backend from starting if the DB isn't at head (bypass with `make prod BYPASS_UPDATE=1`). This guard does **not** run when deployed on Render — see Deployment below.

## Testing

```bash
uv run pytest -v        # 261+ tests — models, routes, services
```

Test DB is in-memory SQLite (`aiosqlite`), injected via dependency override in `tests/conftest.py`.

E2E (Playwright specs exist in `batchbookui/`, not yet run in CI):

```bash
npx playwright test
```

## Tooling

- **Package manager:** `uv` — use `uv add <pkg>` / `uv run <cmd>`, not `pip`/`python` directly
- **Linter/formatter:** `ruff` (line length 100, Python 3.14 target, auto-fix on)
- **Test runner:** `pytest` (async mode `auto`)
- **Python version:** 3.14 (`.python-version`)

## Deployment

- **Frontend:** Vercel, auto-deploys from the `batchbookui` repo on push. Live at `batchbook.in`. The design system lives in `batchbookui/batchbook-design-system`.
- **Backend:** Render.com, Docker web service built from the root `Dockerfile` (`prod` stage).
- **Domain:** `batchbook.in` (Namecheap) — `api.batchbook.in` → Render, `batchbook.in`/`www` → Vercel.
- **Database:** Supabase Postgres (no separate DB hosting cost).

Render builds a single Dockerfile, not `docker-compose.prod.yml` (that file is only for self-hosted Docker stacks). Things that differ from local Docker when deploying to Render:

1. **Port** — set env var `PORT=8000` in Render's dashboard to match the hardcoded `uvicorn --port 8000` in the Dockerfile.
2. **Migrations aren't auto-checked** — Render doesn't run the `alembic-check` compose service. Run `uv run alembic upgrade head` against the prod `DATABASE_URL` manually before/after a deploy that changes the schema.
3. **Env vars must be set individually** in the Render dashboard — Render doesn't read `.env` files: `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `META_WHATSAPP_TOKEN`, `META_WHATSAPP_PHONE_NUMBER_ID`, `WABA_ID`, `PROJECT_NAME`, `PORT`.
4. **CORS** — production origins must be added to `allow_origins` in `app.py` before the first deploy to avoid a redeploy just for CORS.

Full deployment checklist and current project status: see [`BATCHBOOK_ROADMAP_V2.md`](./BATCHBOOK_ROADMAP_V2.md).

## Repo Structure

```
app.py              FastAPI entry point — CORS, routers, Supabase lifespan
config.py            Pydantic Settings, reads .env
models/              SQLAlchemy ORM tables
DTO/                 Pydantic request/response schemas
repositories/        DB query layer
services/            Business logic
routes/              FastAPI routers
alembic/versions/    Migration history (autogenerated, do not hand-edit)
tests/               Pytest suite
batchbookui/         Frontend, git submodule (separate repo)
```

See `CLAUDE.md` for the full architecture reference, including data models, API endpoint tables, auth flow, and Docker file map.
