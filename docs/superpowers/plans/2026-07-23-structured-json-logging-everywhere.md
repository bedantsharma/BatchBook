# Structured JSON Logging Everywhere + Grafana Body-Format Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Amendment (post-implementation review):** Task 2's `url=str(request.url)` (both the
> code block and the test named `test_middleware_logs_full_url_with_query_params`) was
> the originally planned shape — full path + query string. Task review found this
> duplicates the query string unredacted next to the already-redacted `query_params`
> field. The shipped code builds `url` as
> `f"{request.url.scheme}://{request.url.netloc}{request.url.path}"` instead (no query
> string), and the test was replaced with `test_middleware_logs_url_without_query_string`
> in fix commit `32ea8a1`. Task 1's body-read-before-`try:` shape was also amended in
> the same fix — see `.superpowers/sdd/task-2-report.md`'s "Fix for review findings"
> section for the full record.

**Goal:** Make structured JSON logging (with trace/span correlation) and the redacted request/response interceptor middleware run unconditionally in every environment, and fix the Grafana Cloud (Loki) log body so it's the clean message text instead of loguru's pre-rendered default format string — completing the work scoped in `docs/superpowers/specs/2026-07-23-structured-json-logging-everywhere-design.md`.

**Architecture:** `telemetry.py`'s `configure_logging()` splits into an always-run JSON-stdout part and an `OTEL_ENABLED`-gated OTLP-shipping part; `setup_telemetry()` calls `configure_logging()` before its `OTEL_ENABLED` early-return instead of after. `app.py`'s `log_and_handle_exceptions` middleware drops all `if OTEL_ENABLED:` branching so body/query/path-param capture (already correct and tested) runs for every request everywhere, and gains a new `url` field. `request_logging.py`'s redaction/truncation logic is untouched.

**Tech Stack:** `loguru` (already installed), `opentelemetry-sdk._logs` (already installed, import-verified in the prior spec's plan) — no new dependencies.

## Global Constraints

- Package manager is `uv` — use `uv add` / `uv run`, never bare `pip`/`python`.
- Ruff line length 100, Python 3.14 target — new/changed code must pass `uv run ruff check`.
- Full `uv run pytest` must pass after each task.
- OTLP shipping to Grafana Cloud stays gated behind `OTEL_ENABLED` (`bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))`) — only the stdout JSON format and the middleware's capture behavior become unconditional. `setup_telemetry()`'s tracer/meter/FastAPI instrumentation stays gated exactly as today.
- Headers are never logged — no denylist, no allowlist, not touched by this plan at all.
- `request_logging.py` (`REDACTED_FIELDS`, `MAX_LOGGED_BYTES`, `redact()`, `capture_and_redact()`) is not modified.

---

### Task 1: Make JSON stdout logging unconditional in `telemetry.py`

**Files:**
- Modify: `telemetry.py:25-109` (`setup_telemetry`, `configure_logging`)
- Test: Create `tests/test_json_logging.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: no new public interface — `configure_logging()`'s signature (`() -> None`) is unchanged; only its internal behavior and its caller (`setup_telemetry`) change.

- [ ] **Step 1: Write the failing test**

Create `tests/test_json_logging.py`:

```python
"""
Confirms loguru is configured to print structured JSON to stdout in every
environment, not just when OTEL_EXPORTER_OTLP_ENDPOINT (and therefore
telemetry.OTEL_ENABLED) is set. conftest.py's `from app import app` triggers
app.py's module-level `setup_telemetry(app)` call before any test runs, which
must call `configure_logging()` regardless of OTEL_ENABLED.
"""

import json

from loguru import logger


def test_logger_emits_json_to_stdout_even_when_otel_disabled(capsys):
    logger.bind(custom_field="hello").info("a test log line")

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().splitlines() if line]
    assert lines, "expected at least one line printed to stdout"

    payload = json.loads(lines[-1])
    assert payload["message"] == "a test log line"
    assert payload["level"] == "INFO"
    assert payload["custom_field"] == "hello"
    assert payload["trace_id"] == ""
    assert payload["span_id"] == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `RAZORPAY_KEY_ID=rzp_test_placeholder uv run pytest tests/test_json_logging.py -v`

Expected: FAIL on `assert lines` (nothing captured on stdout) — today, `setup_telemetry()` returns early when `OTEL_ENABLED` is `False` (always true in tests, since `tests/conftest.py` never sets `OTEL_EXPORTER_OTLP_ENDPOINT`), so `configure_logging()` never runs and loguru keeps its default sink, which writes to stderr, not stdout, and isn't JSON.

- [ ] **Step 3: Modify `telemetry.py`**

Replace the current `setup_telemetry` and `configure_logging` functions (lines 25-109) with:

```python
def setup_telemetry(app) -> None:
    """Instrument the FastAPI app and start exporting traces + metrics via OTLP."""
    configure_logging()

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


def configure_logging() -> None:
    """Reconfigure loguru: JSON stdout always; ship to Grafana Cloud (Loki) via
    OTLP only when OTEL_ENABLED.

    Mutates the shared loguru core via configure(), so every existing
    `from loguru import logger` call site across the codebase is affected —
    no per-file changes needed.
    """

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

    handlers = [{"sink": json_sink, "level": "INFO"}]

    if OTEL_ENABLED:
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

        # Explicit format is required: without it, loguru's StandardSink
        # pre-renders its own default text format ("{time} | {level} | ... -
        # {message}") into the message it hands to any logging.Handler sink,
        # and that becomes the OTel LogRecord body shipped to Loki. This is
        # what caused Grafana Cloud log lines to not be JSON even with the
        # OTLP pipeline correctly wired — verified live against the
        # grafanacloud-logs Loki datasource in this session.
        handlers.append({"sink": otel_handler, "level": "INFO", "format": "{message}"})

    logger.configure(patcher=inject_trace_context, handlers=handlers)
```

`instrument_engine()` (currently lines 112-117) is unchanged — leave it exactly as-is below this.

- [ ] **Step 4: Run test to verify it passes**

Run: `RAZORPAY_KEY_ID=rzp_test_placeholder uv run pytest tests/test_json_logging.py -v`

Expected: PASS

- [ ] **Step 5: Run the full test suite**

Run: `RAZORPAY_KEY_ID=rzp_test_placeholder uv run pytest -q --deselect tests/test_fee_reminder_live.py::test_generate_payment_link_and_send_fee_reminder`

Expected: all tests pass. Test output will now be noisier (a JSON line prints to stdout for every request any test makes, since `configure_logging()` now runs unconditionally at `app` import time) — that's expected, not a failure.

- [ ] **Step 6: Lint**

Run: `uv run ruff check telemetry.py tests/test_json_logging.py`

Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add telemetry.py tests/test_json_logging.py
git commit -m "fix: make JSON stdout logging unconditional and fix Grafana log body format"
```

---

### Task 2: Make the request/response interceptor unconditional in `app.py`

**Files:**
- Modify: `app.py:33` (import), `app.py:68-148` (`log_and_handle_exceptions`)
- Test: Rewrite `tests/test_request_logging_middleware.py`

**Interfaces:**
- Consumes: `request_logging.capture_and_redact(data) -> str`, `request_logging.MAX_LOGGED_BYTES: int` (both already imported in `app.py`, unchanged).
- Produces: no new public interface — `log_and_handle_exceptions` is a middleware, not called directly by other code.

- [ ] **Step 1: Write the failing test for the new `url` field**

This step edits the same test file that Step 5 rewrites wholesale — write this one new test now, confirm it fails, then do the full rewrite (including this test) in Step 5.

Add to the bottom of `tests/test_request_logging_middleware.py` (on top of the current, still-unmodified file):

```python
async def test_middleware_logs_full_url_with_query_params(client):
    """The url field should contain the full path + query string, not just
    the bare path."""
    from loguru import logger

    capture = _LogCapture()
    sink_id = logger.add(capture, level="INFO")
    try:
        await client.get("/public/institute/does-not-exist?foo=bar")
    finally:
        logger.remove(sink_id)

    completed_records = [
        r for r in capture.records if r["message"] == "request completed"
    ]
    assert completed_records, "expected a 'request completed' log record"
    assert "foo=bar" in completed_records[-1]["extra"]["url"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `RAZORPAY_KEY_ID=rzp_test_placeholder uv run pytest tests/test_request_logging_middleware.py::test_middleware_logs_full_url_with_query_params -v`

Expected: FAIL — today this test never even reaches the `url` assertion in a useful way: `OTEL_ENABLED` is `False` in tests and nothing monkeypatches it in this new test, so the middleware takes the plain-text `else` branch and never calls `logger.bind(...)` at all — `completed_records` will be empty and the test fails on `assert completed_records`.

- [ ] **Step 3: Update the import line in `app.py`**

Change line 33 from:

```python
from telemetry import OTEL_ENABLED, setup_telemetry
```

to:

```python
from telemetry import setup_telemetry
```

- [ ] **Step 4: Replace `log_and_handle_exceptions` in `app.py`**

Replace the entire function (currently lines 68-148) with:

```python
@app.middleware("http")
async def log_and_handle_exceptions(request: Request, call_next):
    """Log every request with method, url, status, and elapsed time,
    including redacted request/response bodies and query/path params as
    structured fields. Also catches any unhandled exception that escapes a
    route handler so the client always receives a well-formed 500 JSON body
    instead of a raw traceback or an empty response.
    """
    start = time.perf_counter()

    request_body_log = None
    request_content_length = request.headers.get("content-length")
    if request_content_length and int(request_content_length) > MAX_LOGGED_BYTES:
        request_body_log = json.dumps(
            f"[request body too large to capture: {request_content_length} bytes]"
        )
    else:
        raw_body = await request.body()
        if raw_body and "application/json" in request.headers.get("content-type", ""):
            try:
                request_body_log = capture_and_redact(json.loads(raw_body))
            except (json.JSONDecodeError, UnicodeDecodeError):
                request_body_log = None

    try:
        response = await call_next(request)
        elapsed = time.perf_counter() - start

        response_body_log = None
        if "application/json" in response.headers.get("content-type", ""):
            response_content_length = response.headers.get("content-length")
            if response_content_length and int(response_content_length) > MAX_LOGGED_BYTES:
                response_body_log = json.dumps(
                    f"[response body too large to capture: {response_content_length} bytes]"
                )
            else:
                chunks = [chunk async for chunk in response.body_iterator]
                response.body_iterator = iterate_in_threadpool(iter(chunks))
                raw_response = b"".join(chunks)
                try:
                    response_body_log = capture_and_redact(json.loads(raw_response))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    response_body_log = None

        logger.bind(
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(elapsed * 1000, 2),
            query_params=capture_and_redact(dict(request.query_params)),
            path_params=capture_and_redact(dict(request.path_params)),
            request_body=request_body_log,
            response_body=response_body_log,
        ).info("request completed")
        return response
    except Exception as exc:
        elapsed = time.perf_counter() - start
        logger.bind(
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            status_code=500,
            duration_ms=round(elapsed * 1000, 2),
            query_params=capture_and_redact(dict(request.query_params)),
            path_params=capture_and_redact(dict(request.path_params)),
            request_body=request_body_log,
            exception=repr(exc),
        ).error("request failed")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})
```

- [ ] **Step 5: Rewrite `tests/test_request_logging_middleware.py`**

Replace the entire file with:

```python
"""
Regression tests for app.py's log_and_handle_exceptions middleware, which
unconditionally captures and logs redacted request/response bodies and
query/path params for every request in every environment.
"""

import pytest
from fastapi import APIRouter, Request

from app import app


class _LogCapture:
    """Collects loguru records emitted while this sink is attached."""

    def __init__(self):
        self.records = []

    def __call__(self, message):
        self.records.append(message.record)


@pytest.fixture
def echo_route():
    """Register a temporary POST /echo-body route accepting any body."""
    router = APIRouter()

    @router.post("/echo-body")
    async def echo_body(request: Request):
        return {"ok": True}

    app.include_router(router)
    yield
    app.routes[:] = [
        r for r in app.routes if not (hasattr(r, "path") and r.path == "/echo-body")
    ]


async def test_middleware_survives_invalid_json_body(client, echo_route):
    response = await client.post(
        "/echo-body",
        content=b"not valid json{",
        headers={"Content-Type": "application/json"},
    )

    # The point is that the middleware's body-capture code ran without
    # raising an uncaught exception -- we got SOME HTTP response back.
    assert response.status_code in (200, 401, 404, 422, 500)


async def test_middleware_survives_non_utf8_body(client, echo_route):
    response = await client.post(
        "/echo-body",
        content=b"\xff\xfe\x00\x01invalid",
        headers={"Content-Type": "application/json"},
    )

    # json.loads() on non-UTF-8 bytes raises UnicodeDecodeError; the
    # middleware must catch it (request side) and not mis-report it as a
    # fabricated 500 (response side). Either way the request must complete
    # with a real HTTP response.
    assert response.status_code in (200, 401, 404, 422, 500)


async def test_middleware_redacts_sensitive_fields_in_bound_log_record(client):
    """A real JSON request body flows through the actual middleware +
    logger.bind path (not the isolated request_logging.py unit tests) and
    comes out redacted."""
    from loguru import logger

    capture = _LogCapture()
    sink_id = logger.add(capture, level="INFO")
    try:
        response = await client.post(
            "/owner/generate_otp",
            json={
                "razorpay_key_id": "rzp_test_abc",
                "razorpay_key_secret": "super_secret_marker_value",
            },
        )
        # The middleware captures the body before routing/validation runs,
        # so the eventual status code doesn't matter for this assertion.
        assert response.status_code in (200, 401, 404, 422, 429, 500)
    finally:
        logger.remove(sink_id)

    completed_records = [
        r for r in capture.records if r["message"] == "request completed"
    ]
    assert completed_records, "expected a 'request completed' log record"

    request_body = completed_records[-1]["extra"]["request_body"]
    assert "[REDACTED]" in request_body
    assert "super_secret_marker_value" not in request_body


async def test_middleware_response_body_survives_drain_and_reconstruct(client):
    """Proves the client still receives the correct, unmangled response body
    after the middleware drains response.body_iterator and reconstructs it
    via iterate_in_threadpool."""
    response = await client.get("/public/institute/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "No public site configured for this slug"}


async def test_middleware_logs_full_url_with_query_params(client):
    """The url field should contain the full path + query string, not just
    the bare path."""
    from loguru import logger

    capture = _LogCapture()
    sink_id = logger.add(capture, level="INFO")
    try:
        await client.get("/public/institute/does-not-exist?foo=bar")
    finally:
        logger.remove(sink_id)

    completed_records = [
        r for r in capture.records if r["message"] == "request completed"
    ]
    assert completed_records, "expected a 'request completed' log record"
    assert "foo=bar" in completed_records[-1]["extra"]["url"]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `RAZORPAY_KEY_ID=rzp_test_placeholder uv run pytest tests/test_request_logging_middleware.py -v`

Expected: 6 passed

- [ ] **Step 7: Run the full test suite**

Run: `RAZORPAY_KEY_ID=rzp_test_placeholder uv run pytest -q --deselect tests/test_fee_reminder_live.py::test_generate_payment_link_and_send_fee_reminder`

Expected: all tests pass, same count as before this task plus the one new test.

- [ ] **Step 8: Lint**

Run: `uv run ruff check app.py tests/test_request_logging_middleware.py`

Expected: no errors

- [ ] **Step 9: Commit**

```bash
git add app.py tests/test_request_logging_middleware.py
git commit -m "feat: make request/response body+query+url capture unconditional"
```

---

### Task 3: Local smoke test **[ORCHESTRATOR ACTION — no subagent]**

Requires live Docker interaction; not delegated.

- [ ] **Step 1: Rebuild and restart the backend**

```bash
make backend
```

- [ ] **Step 2: Generate traffic including a request with a sensitive field**

```bash
curl -s http://localhost:8000/docs?foo=bar > /dev/null
curl -s -X POST http://localhost:8000/owner/generate_otp \
  -H "Content-Type: application/json" \
  -d '{"razorpay_key_id": "rzp_test_abc", "razorpay_key_secret": "should_not_appear_in_logs"}'
```

- [ ] **Step 3: Confirm JSON lines with redaction and the new `url` field**

```bash
docker logs batchbook-dev-backend-1 --tail 20 | grep "request completed"
```

Expected: JSON lines (not the old `method path → status (time)` text format) containing `"trace_id":""`, `"span_id":""` (no OTel configured locally), `"url":"http://localhost:8000/docs?foo=bar"` on the first request, and `"razorpay_key_secret\":\"[REDACTED]\"` (or equivalent inside the `request_body` string) on the second — never the literal `should_not_appear_in_logs`.

```bash
docker logs batchbook-dev-backend-1 2>&1 | grep -c "should_not_appear_in_logs" || echo "0 (good — not found)"
```

Expected: `0`.

- [ ] **Step 4: Confirm no regressions in the deployed dev stack**

```bash
docker ps --filter "name=batchbook-dev-backend"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/docs
```

Expected: container `Up`, health check `200`.

- [ ] **Step 5: Note production verification for after deploy**

Not run now — record for post-deploy: re-query the `grafanacloud-logs` Loki datasource (`{service_name="batchbook-backend-production"}`), confirm the log line body now reads as plain message text (`"request completed"`) instead of the old loguru-formatted string, and that `request_body`/`query_params` are populated for real JSON endpoints (they were `None`/`{}` in the pre-fix sample, which only covered `/docs` GETs).
