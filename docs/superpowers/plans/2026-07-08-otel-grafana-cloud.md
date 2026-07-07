# OpenTelemetry + Grafana Cloud Ingest Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Several tasks require the human operator (Grafana Cloud console clicks, Render dashboard env vars) — these are marked **[USER ACTION]** and cannot be delegated to a subagent.

**Goal:** Instrument the FastAPI backend with OpenTelemetry (traces + metrics) and export directly to Grafana Cloud via OTLP/HTTP, so API endpoint latency/error-rate/throughput can be inspected in aggregate ("why is this endpoint slow at scale") in Grafana, with the ability to jump into an individual trace for root cause.

**Architecture:** No collector, no sidecar container. The FastAPI process holds an OTel SDK `TracerProvider` + `MeterProvider` in-process and pushes OTLP/HTTP batches straight to Grafana Cloud's managed OTLP gateway. This fits Render's one-container-per-service model and the local Docker dev stack without adding a new service. Instrumentation is entirely opt-in at runtime: if `OTEL_EXPORTER_OTLP_ENDPOINT` isn't set, `telemetry.py` no-ops, so local dev without credentials and the pytest suite (which never sets that var) are completely unaffected.

**Tech Stack:** `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-sqlalchemy`, `opentelemetry-instrumentation-httpx`. Backend: Grafana Cloud (free tier — 10k metric series / 50GB logs / 50GB traces, 14-day retention).

## Global Constraints

- Package manager is `uv` — use `uv add` / `uv run`, never bare `pip`/`python`.
- Zero impact on the existing 261+ test suite (`tests/conftest.py` never sets `OTEL_EXPORTER_OTLP_ENDPOINT`, so telemetry code must no-op in that path).
- No new container/service — must run inside the existing single `backend` container on Render and in `docker-compose.dev.yml`/`docker-compose.prod.yml` (both already use `env_file: .env`, so no compose file edits are needed for env var plumbing).
- Ruff line length 100, Python 3.14 target — new code must pass `uv run ruff check`.

---

### Task 0: Create the Grafana Cloud stack and generate OTLP credentials **[USER ACTION]**

No code in this task — this produces the three secrets later tasks need.

- [ ] **Step 1: Sign up / log in to Grafana Cloud**

Go to `https://grafana.com/auth/sign-up/create-user` (or sign in if you already have an account) and create a free-tier org. This provisions a default stack (Tempo for traces, Mimir/Prometheus for metrics, Loki for logs) at no cost.

- [ ] **Step 2: Open the OTLP connection page**

In the Grafana Cloud Portal, open your stack, then go to **Connections → Add new connection → OpenTelemetry (OTLP)** (or the "OpenTelemetry" tile on the stack's overview page → **Configure**).

- [ ] **Step 3: Generate credentials**

Click **Generate now**. Grafana creates a scoped API token and shows you three ready-to-copy lines:

```
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64 instanceID:token>
```

Copy all three — do not compute the Basic Auth header by hand, this flow already base64-encodes and percent-encodes it correctly.

- [ ] **Step 4: Save the values somewhere safe**

Paste them into a scratch note for now (e.g. your password manager). Task 5 puts them in `.env` locally and Task 8 puts them in the Render dashboard. Do not commit them to git.

---

### Task 1: Add OpenTelemetry dependencies

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` (generated)

- [ ] **Step 1: Install the packages**

```bash
cd /Users/bedantsharma/PycharmProjects/BatchBook
uv add opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp-proto-http \
  opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-sqlalchemy \
  opentelemetry-instrumentation-httpx
```

- [ ] **Step 2: Verify the install**

```bash
uv run python -c "import opentelemetry.sdk, opentelemetry.instrumentation.fastapi; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add OpenTelemetry SDK and instrumentation packages"
```

---

### Task 2: Create the telemetry bootstrap module

**Files:**
- Create: `telemetry.py`

**Interfaces:**
- Produces: `OTEL_ENABLED: bool`, `setup_telemetry(app: FastAPI) -> None`, `instrument_engine(engine: AsyncEngine) -> None` — both functions consumed by Task 3 (`app.py`) and Task 4 (`db/session.py`).

- [ ] **Step 1: Write `telemetry.py`**

```python
"""OpenTelemetry bootstrap for traces + metrics, exported via OTLP/HTTP to Grafana Cloud.

Entirely opt-in: every function here no-ops unless OTEL_EXPORTER_OTLP_ENDPOINT is set,
so local dev without credentials and the pytest suite are unaffected.
"""

import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

OTEL_ENABLED = bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))


def setup_telemetry(app) -> None:
    """Instrument the FastAPI app and start exporting traces + metrics via OTLP."""
    if not OTEL_ENABLED:
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "batchbook-backend"),
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()


def instrument_engine(engine) -> None:
    """Attach DB span attribution to a SQLAlchemy async engine."""
    if not OTEL_ENABLED:
        return
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
```

- [ ] **Step 2: Verify it imports cleanly and is disabled by default**

```bash
uv run python -c "import telemetry; print(telemetry.OTEL_ENABLED)"
```

Expected: `False` (no `OTEL_EXPORTER_OTLP_ENDPOINT` set in your shell)

- [ ] **Step 3: Lint**

```bash
uv run ruff check telemetry.py
```

Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add telemetry.py
git commit -m "feat: add OpenTelemetry bootstrap module (opt-in via OTEL_EXPORTER_OTLP_ENDPOINT)"
```

---

### Task 3: Wire telemetry into the FastAPI app

**Files:**
- Modify: `app.py:1-56`

**Interfaces:**
- Consumes: `telemetry.setup_telemetry(app: FastAPI) -> None` from Task 2.

- [ ] **Step 1: Import and call `setup_telemetry`**

In `app.py`, add the import alongside the other local imports:

```python
from scheduler import shutdown_scheduler, start_scheduler
from telemetry import setup_telemetry
```

Then call it immediately after the `FastAPI(...)` constructor, before `app.state.limiter = limiter`:

```python
app = FastAPI(
    title="Batch Book",
    description="Clean, well-documented API for batch book application 🚀",
    version="1.0.0",
    contact={
        "name": "Bedant Sharma",
        "email": "bedant.sharma.dev@gmail.com",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

setup_telemetry(app)

app.state.limiter = limiter
```

- [ ] **Step 2: Run the full test suite to confirm zero regression**

```bash
uv run pytest -v
```

Expected: all 261+ tests pass (telemetry is disabled in the test env, so this only proves the import/wiring doesn't break app startup).

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: instrument FastAPI app with OpenTelemetry"
```

---

### Task 4: Wire DB span instrumentation into the SQLAlchemy engine

**Files:**
- Modify: `db/session.py:1-27`

**Interfaces:**
- Consumes: `telemetry.instrument_engine(engine: AsyncEngine) -> None` from Task 2.

- [ ] **Step 1: Import and call `instrument_engine` after engine creation**

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import get_settings
from telemetry import instrument_engine

# ... existing _engine_kwargs block unchanged ...

engine = create_async_engine(
    get_settings().database_url,
    **_engine_kwargs,
)
instrument_engine(engine)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)
```

- [ ] **Step 2: Run the full test suite again**

```bash
uv run pytest -v
```

Expected: all tests still pass (tests build their own separate SQLite engine in `conftest.py`, so this only proves `db/session.py` still imports cleanly).

- [ ] **Step 3: Commit**

```bash
git add db/session.py
git commit -m "feat: instrument SQLAlchemy async engine for DB span attribution"
```

---

### Task 5: Document the new env vars

**Files:**
- Modify: `env.example`
- Modify: `README.md` (the `.env` fenced block in "Getting Started")
- Modify: `CLAUDE.md` (the `BatchBook/.env` fenced block under "Environment Variables")

- [ ] **Step 1: Add to `env.example`**

```
OTEL_EXPORTER_OTLP_PROTOCOL=XXXXX
OTEL_EXPORTER_OTLP_ENDPOINT=XXXXX
OTEL_EXPORTER_OTLP_HEADERS=XXXXX
OTEL_SERVICE_NAME=batchbook-backend
ENVIRONMENT=development
```

- [ ] **Step 2: Add the same block to the `.env` example in `README.md`** (inside the existing fenced code block under "Create `.env` in the repo root")

- [ ] **Step 3: Add the same block to `CLAUDE.md`** (inside the existing fenced code block under "## Environment Variables (`BatchBook/.env`)")

- [ ] **Step 4: Commit**

```bash
git add env.example README.md CLAUDE.md
git commit -m "docs: document OpenTelemetry env vars"
```

---

### Task 6: Configure local `.env` and smoke-test against Grafana Cloud **[USER ACTION + verification]**

**Files:**
- Modify: `.env` (gitignored, not committed)

- [ ] **Step 1: Paste the Task 0 credentials into your local `.env`**

Add the same five keys from Task 5's `env.example`, using the real values from Task 0, e.g.:

```
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-<region>.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64 instanceID:token>
OTEL_SERVICE_NAME=batchbook-backend
ENVIRONMENT=development
```

- [ ] **Step 2: Rebuild and start the backend**

```bash
make backend
```

(rebuilds only the backend image so the newly added dependencies are picked up, then restarts the dev stack)

- [ ] **Step 3: Generate some traffic**

```bash
curl http://localhost:8000/docs
curl http://localhost:8000/owner/health  # or any real GET route that exists
```

Hit 5-10 requests so there's enough data to find.

- [ ] **Step 4: Verify traces landed in Grafana Cloud**

In Grafana Cloud → **Explore** → select the **Tempo** data source → search by `service.name = batchbook-backend`. You should see spans for the requests you just made, each with a duration and status.

- [ ] **Step 5: Verify metrics landed in Grafana Cloud**

In Grafana Cloud → **Explore** → select the **Prometheus/Mimir** data source → query `{service_name="batchbook-backend"}` or search the metrics picker for `http_server`. You should see request-duration histogram series.

- [ ] **Step 6: If nothing shows up, check the backend logs**

```bash
make logs-b
```

Common causes: `OTEL_EXPORTER_OTLP_HEADERS` missing the `%20` after `Basic`, or the endpoint URL missing/including `/otlp` incorrectly (use exactly what Grafana generated in Task 0, don't hand-edit it).

---

### Task 7: Configure Render for production **[USER ACTION]**

- [ ] **Step 1: Add the env vars in the Render dashboard**

Render → your backend service → **Environment** → add:

```
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=<same as local>
OTEL_EXPORTER_OTLP_HEADERS=<same as local>
OTEL_SERVICE_NAME=batchbook-backend
ENVIRONMENT=production
```

Using the same Grafana Cloud credentials as local — `deployment.environment` is what distinguishes prod traffic from dev traffic in Grafana, not separate credentials.

- [ ] **Step 2: Deploy**

Trigger a deploy (push to the branch Render tracks, or **Manual Deploy** in the dashboard).

- [ ] **Step 3: Verify**

Hit a couple of real production endpoints, then repeat Task 6 Steps 4-5 in Grafana Cloud, filtering for `deployment.environment = production` to confirm prod traffic is arriving separately from your local dev traffic.

---

### Task 8 (optional follow-up, not required to close this plan): Enable Grafana Application Observability

Once traces are flowing reliably (Task 6/7 verified), turn on Grafana Cloud's **Application Observability** product on your stack (Grafana Cloud Portal → Application Observability → Enable). It auto-builds the Service Inventory / RED-metrics dashboards per endpoint from the traces you're already sending — no additional code changes required. This is a UI toggle, not a code task, so it's left out of the checklist above; do it whenever you're ready to explore the dashboards.
