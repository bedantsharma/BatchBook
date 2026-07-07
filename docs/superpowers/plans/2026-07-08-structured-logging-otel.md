# Structured JSON Logging + Grafana Cloud (Loki) Shipping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement Tasks 1-3 (pure code, each independently testable). Task 4 (local smoke test) requires live Docker interaction and the user's own Grafana Cloud UI access — handle it directly in the orchestrating session, not via subagent dispatch.

**Goal:** Reconfigure loguru to emit structured JSON with trace/span correlation, ship logs to Grafana Cloud (Loki) via OTLP, and log redacted request/response bodies + query/path params — completing the traces+metrics+logs triad from `docs/superpowers/specs/2026-07-08-structured-logging-otel-design.md`.

**Architecture:** `telemetry.py` gains `configure_logging()`, called from the existing `setup_telemetry(app)`. It uses `logger.configure(patcher=..., handlers=[...])` — not `.patch()` — to mutate loguru's shared core so all 15 existing files using `from loguru import logger` get trace-context injection with zero per-file changes. A new `request_logging.py` holds pure, unit-tested redaction logic. `app.py`'s existing request-logging middleware calls into it to capture/redact/log request+response bodies. Everything is gated behind the existing `telemetry.OTEL_ENABLED` flag — local dev without Grafana credentials and the full pytest suite are entirely unaffected.

**Tech Stack:** `opentelemetry-sdk._logs` (`LoggerProvider`, `LoggingHandler`), `opentelemetry.sdk._logs.export.BatchLogRecordProcessor`, `opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter` — all already installed (`opentelemetry-sdk==1.43.0`, `opentelemetry-exporter-otlp-proto-http==1.43.0`) and import-verified:

```bash
uv run python -c "
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
print('ok - all imports resolved')
"
```
Already run — printed `ok - all imports resolved`. No new dependencies needed for this plan.

## Global Constraints

- Package manager is `uv` — use `uv add` / `uv run`, never bare `pip`/`python`.
- Zero impact on the existing pytest suite — `tests/conftest.py` never sets `OTEL_EXPORTER_OTLP_ENDPOINT`, so `OTEL_ENABLED` is `False` in every test run; all new logging behavior must no-op in that path.
- Redaction denylist (case-insensitive, exact key match, applied recursively): `token`, `refresh_token`, `access_token`, `password`, `otp`, `secret`, `razorpay_key_secret`, `razorpay_webhook_secret`, `client_secret`, `api_key`, `admin_backfill_secret`, `meta_whatsapp_token`. `razorpay_key_id` and ordinary PII (phone/email/name) are explicitly NOT redacted.
- No HTTP headers are ever logged (not even redacted) — out of scope by design, removes the `Authorization`/cookie leak vector entirely.
- Logged bodies/query params/path params truncate at 4096 bytes (`MAX_LOGGED_BYTES`), stored as a JSON-serialized string field, never nested JSON, so the outer log line is always valid.
- Ruff line length 100, Python 3.14 target — new code must pass `uv run ruff check`.

---

### Task 1: Create `request_logging.py` with redaction logic

**Files:**
- Create: `request_logging.py`
- Test: `tests/test_request_logging.py`

**Interfaces:**
- Produces: `REDACTED_FIELDS: set[str]`, `MAX_LOGGED_BYTES: int`, `redact(value) -> Any`, `capture_and_redact(data) -> str` — consumed by Task 3 (`app.py`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_request_logging.py
import json

from request_logging import MAX_LOGGED_BYTES, capture_and_redact, redact


def test_redact_replaces_top_level_secret_field():
    assert redact({"token": "abc123", "phone": "9876543210"}) == {
        "token": "[REDACTED]",
        "phone": "9876543210",
    }


def test_redact_replaces_nested_secret_field():
    data = {
        "credentials": {
            "razorpay_key_secret": "sk_live_xxx",
            "razorpay_key_id": "rzp_live_yyy",
        }
    }
    assert redact(data) == {
        "credentials": {
            "razorpay_key_secret": "[REDACTED]",
            "razorpay_key_id": "rzp_live_yyy",
        }
    }


def test_redact_handles_lists_of_dicts():
    data = [{"otp": "1234"}, {"otp": "5678", "name": "Asha"}]
    assert redact(data) == [{"otp": "[REDACTED]"}, {"otp": "[REDACTED]", "name": "Asha"}]


def test_redact_is_case_insensitive_on_field_name():
    assert redact({"Token": "abc", "Password": "xyz"}) == {
        "Token": "[REDACTED]",
        "Password": "[REDACTED]",
    }


def test_redact_passes_through_non_dict_non_list_values():
    assert redact("just a string") == "just a string"
    assert redact(42) == 42
    assert redact(None) is None


def test_capture_and_redact_returns_valid_json_with_redaction_applied():
    result = capture_and_redact({"token": "secret", "student_id": 42})
    parsed = json.loads(result)
    assert parsed == {"token": "[REDACTED]", "student_id": 42}


def test_capture_and_redact_truncates_large_payloads():
    big_list = [{"student_id": i, "name": f"Student {i}"} for i in range(500)]
    result = capture_and_redact(big_list)
    assert len(result) <= MAX_LOGGED_BYTES + 100
    assert "truncated" in result


def test_capture_and_redact_does_not_truncate_small_payloads():
    result = capture_and_redact({"student_id": 1})
    assert "truncated" not in result
    assert json.loads(result) == {"student_id": 1}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_request_logging.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'request_logging'`

- [ ] **Step 3: Write the implementation**

```python
# request_logging.py
"""Request/response body capture with secret redaction for structured request logging."""

import json

REDACTED_FIELDS = {
    "token",
    "refresh_token",
    "access_token",
    "password",
    "otp",
    "secret",
    "razorpay_key_secret",
    "razorpay_webhook_secret",
    "client_secret",
    "api_key",
    "admin_backfill_secret",
    "meta_whatsapp_token",
}

MAX_LOGGED_BYTES = 4096


def redact(value):
    """Recursively replace any dict value whose key is in REDACTED_FIELDS."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if k.lower() in REDACTED_FIELDS else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def capture_and_redact(data) -> str:
    """Redact, JSON-serialize, and truncate to MAX_LOGGED_BYTES for log output."""
    redacted = redact(data)
    serialized = json.dumps(redacted, default=str)
    if len(serialized) > MAX_LOGGED_BYTES:
        total = len(serialized)
        serialized = serialized[:MAX_LOGGED_BYTES] + f"...[truncated, {total} bytes total]"
    return serialized
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_request_logging.py -v
```

Expected: 8 passed

- [ ] **Step 5: Lint**

```bash
uv run ruff check request_logging.py tests/test_request_logging.py
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add request_logging.py tests/test_request_logging.py
git commit -m "feat: add request/response body redaction for structured logging"
```

---

### Task 2: Extend `telemetry.py` with `configure_logging()`

**Files:**
- Modify: `telemetry.py`

**Interfaces:**
- Consumes: nothing new (uses `OTEL_ENABLED`, `trace` already present in the file).
- Produces: `configure_logging() -> None`, called internally by `setup_telemetry(app)` — not consumed elsewhere.

- [ ] **Step 1: Add the two new imports**

At the top of `telemetry.py`, add to the existing import block:

```python
import json
import os

from loguru import logger
from opentelemetry import metrics, trace
```

(`import json` and `from loguru import logger` are the two new lines; `import os` and `from opentelemetry import metrics, trace` already exist — keep them as-is, shown here only for placement context.)

- [ ] **Step 2: Add `configure_logging()`**

Add this function to `telemetry.py`, after `setup_telemetry` and before `instrument_engine`:

```python
def configure_logging() -> None:
    """Reconfigure loguru: JSON stdout + ship to Grafana Cloud (Loki) via OTLP.

    Mutates the shared loguru core via configure(), so every existing
    `from loguru import logger` call site across the codebase is affected —
    no per-file changes needed. No-ops unless OTEL_ENABLED.
    """
    if not OTEL_ENABLED:
        return

    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    resource = Resource.create(
        {
            "service.name": os.getenv("OTEL_SERVICE_NAME", "batchbook-backend"),
            "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        }
    )

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    otel_handler = LoggingHandler(logger_provider=logger_provider)

    def inject_trace_context(record):
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            record["extra"]["trace_id"] = format(ctx.trace_id, "032x")
            record["extra"]["span_id"] = format(ctx.span_id, "016x")
        else:
            record["extra"]["trace_id"] = ""
            record["extra"]["span_id"] = ""

    def json_sink(message):
        record = message.record
        payload = {
            "timestamp": record["time"].isoformat(),
            "level": record["level"].name,
            "message": record["message"],
            "module": record["module"],
            "function": record["function"],
            "line": record["line"],
            **record["extra"],
        }
        print(json.dumps(payload, default=str))

    logger.configure(
        patcher=inject_trace_context,
        handlers=[
            {"sink": json_sink, "level": "INFO"},
            {"sink": otel_handler, "level": "INFO"},
        ],
    )
```

- [ ] **Step 3: Call it from `setup_telemetry`**

At the end of `setup_telemetry(app)` (after the existing `HTTPXClientInstrumentor().instrument()` line), add:

```python
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

    configure_logging()
```

- [ ] **Step 4: Verify the module still imports cleanly with OTel disabled**

```bash
uv run python -c "import telemetry; print(telemetry.OTEL_ENABLED)"
```

Expected: `False` (no `OTEL_EXPORTER_OTLP_ENDPOINT` in your shell env)

- [ ] **Step 5: Run the full test suite**

```bash
RAZORPAY_KEY_ID=rzp_test_placeholder uv run pytest -q --deselect tests/test_fee_reminder_live.py::test_generate_payment_link_and_send_fee_reminder
```

Expected: all tests pass, same count as before this task (`configure_logging` no-ops since `OTEL_ENABLED` is `False` in the test env)

- [ ] **Step 6: Lint**

```bash
uv run ruff check telemetry.py
```

Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add telemetry.py
git commit -m "feat: ship structured logs to Grafana Cloud (Loki) with trace/span correlation"
```

---

### Task 3: Wire body/query/path param capture into `app.py`'s middleware

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `request_logging.capture_and_redact(data) -> str` (Task 1), `telemetry.OTEL_ENABLED: bool` (Task 2, already exists as a module attribute in `telemetry.py`).

- [ ] **Step 1: Add new imports**

In `app.py`, add `import json` near the top (it's not currently imported), and add these import lines alongside the existing ones:

```python
import json
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.concurrency import iterate_in_threadpool
from supabase._async.client import create_client

from clients import supabase_client
from config import get_settings
from rate_limiter import limiter
from request_logging import capture_and_redact
from routes.admin_route import router as admin_router
```

(Only `import json` and `from starlette.concurrency import iterate_in_threadpool` and `from request_logging import capture_and_redact` are new — the rest of the block is shown for exact placement; leave every other existing import line as-is.)

Also change the existing telemetry import line from:

```python
from telemetry import setup_telemetry
```

to:

```python
from telemetry import OTEL_ENABLED, setup_telemetry
```

- [ ] **Step 2: Replace `log_and_handle_exceptions`**

Replace the entire existing middleware function with:

```python
@app.middleware("http")
async def log_and_handle_exceptions(request: Request, call_next):
    """Log every request with method, path, status, and elapsed time.

    When OTEL_ENABLED, also captures redacted request/response bodies and
    query/path params as structured fields. Also catches any unhandled
    exception that escapes a route handler so the client always receives a
    well-formed 500 JSON body instead of a raw traceback or an empty response.
    """
    start = time.perf_counter()

    request_body_log = None
    if OTEL_ENABLED:
        raw_body = await request.body()
        if raw_body and "application/json" in request.headers.get("content-type", ""):
            try:
                request_body_log = capture_and_redact(json.loads(raw_body))
            except json.JSONDecodeError:
                request_body_log = None

    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        if OTEL_ENABLED:
            response_body_log = None
            if "application/json" in response.headers.get("content-type", ""):
                chunks = [chunk async for chunk in response.body_iterator]
                response.body_iterator = iterate_in_threadpool(iter(chunks))
                raw_response = b"".join(chunks)
                try:
                    response_body_log = capture_and_redact(json.loads(raw_response))
                except json.JSONDecodeError:
                    response_body_log = None

            logger.bind(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(elapsed * 1000, 2),
                query_params=capture_and_redact(dict(request.query_params)),
                path_params=capture_and_redact(dict(request.path_params)),
                request_body=request_body_log,
                response_body=response_body_log,
            ).info("request completed")
        else:
            logger.info(
                f"{request.method} {request.url.path} → {response.status_code} ({elapsed:.3f}s)"
            )
        return response
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.error(
            f"Unhandled exception on {request.method} {request.url.path}: {exc!r}"
        )
        logger.info(f"{request.method} {request.url.path} → 500 ({elapsed:.3f}s)")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
```

- [ ] **Step 3: Run the full test suite**

```bash
RAZORPAY_KEY_ID=rzp_test_placeholder uv run pytest -q --deselect tests/test_fee_reminder_live.py::test_generate_payment_link_and_send_fee_reminder
```

Expected: all tests pass (middleware behavior is identical to before when `OTEL_ENABLED` is `False`, which it always is in tests)

- [ ] **Step 4: Lint**

```bash
uv run ruff check app.py
```

Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: log redacted request/response bodies and query/path params"
```

---

### Task 4: Local smoke test against Grafana Cloud **[ORCHESTRATOR + USER ACTION]**

Not delegated to a subagent — requires live Docker interaction on the host and the user's own Grafana Cloud UI access.

- [ ] **Step 1: Rebuild and restart the backend**

```bash
make backend
```

- [ ] **Step 2: Generate traffic including a request with a sensitive field**

```bash
curl -s -X POST http://localhost:8000/owner/institute/razorpay-credentials \
  -H "Content-Type: application/json" \
  -d '{"razorpay_key_id": "rzp_test_abc", "razorpay_key_secret": "should_not_appear_in_logs"}'
```

(Expect a 401/403 — no auth token sent — that's fine, we only care that the request was logged.)

```bash
curl -s http://localhost:8000/docs > /dev/null
```

- [ ] **Step 3: Check `docker logs` for JSON lines with redaction applied**

```bash
docker logs batchbook-dev-backend-1 --tail 20 | grep "request completed"
```

Expected: JSON lines containing `"trace_id"`, `"span_id"`, and — critically — `"razorpay_key_secret\":\"[REDACTED]\"` (or an equivalent redacted marker inside the `request_body` string field), never the literal `should_not_appear_in_logs`.

- [ ] **Step 4: Confirm the raw secret never appears in the logs**

```bash
docker logs batchbook-dev-backend-1 2>&1 | grep -c "should_not_appear_in_logs" || echo "0 (good — not found)"
```

Expected: `0` — if this is nonzero, stop and treat it as a bug, not something to explain away.

- [ ] **Step 5: Verify in Grafana Cloud** (user checks their own account)

Explore → Loki data source → query `{service_name="batchbook-backend"}`. Confirm:
- Log lines appear with `trace_id`/`span_id` populated
- Clicking a trace in Tempo (from earlier smoke testing) offers a correlated-logs link into these Loki entries
- The redacted request body shows `[REDACTED]` in place of the real secret, never the raw value

- [ ] **Step 6: Confirm no regressions in the deployed dev stack**

```bash
docker ps --filter "name=batchbook-dev-backend"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs
```

Expected: container `Up`, health check `200`
