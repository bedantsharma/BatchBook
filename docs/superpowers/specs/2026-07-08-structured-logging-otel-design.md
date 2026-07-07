# Structured JSON Logging + Grafana Cloud (Loki) Shipping

Date: 2026-07-08

## Problem

`docs/superpowers/plans/2026-07-08-otel-grafana-cloud.md` wired traces and metrics from
the FastAPI backend to Grafana Cloud, gated behind `OTEL_ENABLED` (set when
`OTEL_EXPORTER_OTLP_ENDPOINT` is configured). That plan's Task 6 (local smoke test)
confirmed traces and metrics land correctly.

The third leg of observability — logs — is still loguru's default colored-text sink,
disconnected from the trace/span that produced each line, and not shipped anywhere.
This spec adds structured JSON logging with trace/span correlation, ships logs to
Grafana Cloud (Loki) via OTLP, and — per the follow-up ask — captures request/response
bodies, query params, and path params so a slow or failing request's full context is
visible without reproducing it locally.

Handling request/response bodies means potentially logging passwords, OTP tokens,
Razorpay secrets, and WhatsApp API tokens to a third-party cloud service. Verified
against the actual DTOs (`routes/requests/otp_verify_request.py`,
`update_razorpay_credentials_request.py`, `set_razorpay_webhook_secret_request.py`,
`refresh_token_request.py`) that this risk is real, not hypothetical — those fields
exist today. Redaction is not optional in this design.

## Decisions

- **Ship logs to Grafana Cloud (Loki) via OTLP**, not just JSON-on-stdout. Reuses the
  same `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_EXPORTER_OTLP_HEADERS` credentials already
  configured — no new env vars. This is what enables pivoting from a slow span in Tempo
  to its correlated log lines in Loki inside the Grafana UI, which was the original
  motivation (matching the trace↔log correlation the user was used to in SigNoz).
- **JSON format + log shipping is gated behind `OTEL_ENABLED`**, same as
  `setup_telemetry()`/`instrument_engine()` in `telemetry.py`. Local dev without
  Grafana credentials keeps today's human-readable colored console output and pays zero
  extra cost (no body buffering, no redaction, no JSON serialization).
- **`logger.configure(patcher=..., handlers=[...])`, not `.patch()` + `.add()`
  separately.** loguru's `.patch()` returns a new bound logger instance; the 15 files
  that already did `from loguru import logger` at import time hold a reference to the
  unpatched singleton and would silently never see injected trace context.
  `logger.configure()` mutates the shared core, so it affects every existing call site
  process-wide with zero per-file changes.
- **51 of 52 existing `logger.info(...)`/`logger.error(...)` call sites are untouched.**
  Only the one request-completion line in `app.py`'s `log_and_handle_exceptions`
  middleware gets restructured into bound fields (`method`, `path`, `status_code`,
  `duration_ms`) instead of one f-string — it's the single line that fires on every
  request, so it's the only one worth the refactor. Everything else keeps its free-text
  message; the JSON envelope and trace context wrap around it automatically via the
  patcher, no code change needed at those call sites.
- **No headers are logged**, not even redacted. The ask was body/query/path params;
  skipping headers entirely removes the `Authorization`/cookie leak vector by scope
  instead of by remembering to redact it correctly.
- **Redaction is a denylist by exact field name** (case-insensitive), applied
  recursively through any nesting depth of the parsed JSON body. Ordinary PII (phone,
  email, student name) is deliberately **not** redacted — it's core business data
  needed for debugging, and redacting it wasn't asked for. `razorpay_key_id` is
  deliberately **not** redacted — it's a public identifier, not a secret.
- **Truncate at ~4KB**, storing the (possibly truncated) body as a JSON-serialized
  *string* field in the log envelope, not nested JSON — guarantees the outer log line
  is always valid JSON even when a body gets cut mid-structure. Bounds Grafana Cloud's
  free-tier log volume (50GB) against list-heavy endpoints (e.g. "list all students in
  an institute") dominating usage.
- **New file `request_logging.py`**, not inlined in `app.py`. Holds the redaction
  denylist, `redact()`, and `capture_and_redact()`. Keeps the recursive-redaction logic
  isolated and independently readable/testable rather than bloating the middleware
  function in `app.py`.

## Section 1 — `telemetry.py`: logging setup

New function `configure_logging()`, called from the existing `setup_telemetry(app)` (so
`app.py` keeps making exactly one call). No-ops if `OTEL_ENABLED` is `False`, identical
pattern to `setup_telemetry`/`instrument_engine`.

`telemetry.py` needs two new top-level imports it doesn't currently have: `import json`
and `from loguru import logger` (alongside its existing `import os` and
`from opentelemetry import metrics, trace`).

```python
def configure_logging() -> None:
    """Reconfigure loguru: JSON stdout + ship to Grafana Cloud (Loki) via OTLP.

    Mutates the shared loguru core via configure(), so every existing
    `from loguru import logger` call site across the codebase is affected —
    no per-file changes needed.
    """
    if not OTEL_ENABLED:
        return

    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

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
            **{k: v for k, v in record["extra"].items()},
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

`setup_telemetry(app)` gets one added line at the end: `configure_logging()`.

**Verify before writing this for real** (import paths for the logs API have moved
between OTel SDK versions): `uv run python -c "from opentelemetry.sdk._logs import
LoggerProvider, LoggingHandler; from opentelemetry.sdk._logs.export import
BatchLogRecordProcessor; from opentelemetry.exporter.otlp.proto.http._log_exporter
import OTLPLogExporter; print('ok')"` against the already-installed
`opentelemetry-sdk==1.43.0` / `opentelemetry-exporter-otlp-proto-http==1.43.0`. If the
import paths differ, adjust before proceeding — do not guess.

## Section 2 — `request_logging.py`: redaction + capture

```python
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

## Section 3 — `app.py`: middleware changes

The existing `log_and_handle_exceptions` middleware gains body/query/path param capture,
gated by `telemetry.OTEL_ENABLED` (imported alongside the existing `setup_telemetry`
import):

Also needs two new imports in `app.py`: `import json` (not currently imported there)
and `from starlette.concurrency import iterate_in_threadpool` (needed to reconstruct
the response body iterator after consuming it for logging — see below).

```python
from starlette.concurrency import iterate_in_threadpool

from request_logging import capture_and_redact
from telemetry import OTEL_ENABLED, setup_telemetry


@app.middleware("http")
async def log_and_handle_exceptions(request: Request, call_next):
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

`request.path_params` is empty before `call_next` runs (Starlette resolves it during
routing, which happens *inside* `call_next`) but readable afterward — `request` and the
router share the same `scope` dict by reference, so no separate capture point is needed
for path params.

Consuming `response.body_iterator` to log it empties the iterator; reassigning it via
`iterate_in_threadpool(iter(chunks))` is required or the real response sent to the
client would come back empty.

## Section 4 — Testing

- Full `uv run pytest` suite after each change. `OTEL_ENABLED` is never set in
  `tests/conftest.py`, so none of this should execute during tests — confirms zero
  regression, same pattern as the OTel plan.
- Local smoke test: rebuild backend, generate traffic (reuse the same autocannon
  approach from the OTel plan's Task 6), then verify:
  - `docker logs` shows JSON lines with non-empty `trace_id`/`span_id` for
    request-scoped log lines.
  - A request with a known-sensitive field (e.g. call `/owner/institute` with a body
    containing `razorpay_key_secret`) logs `"[REDACTED]"` in place of the real value —
    check this explicitly, don't assume redaction works from code review alone.
  - Grafana Cloud Explore → Loki shows the same log lines, queryable by
    `service_name="batchbook-backend"`, and clicking a trace in Tempo offers a
    correlated-logs link into Loki.
  - A large list-endpoint response (e.g. list students) shows a truncated
    `response_body` field, not the full payload.

## Out of scope

- Redacting/minimizing ordinary PII (phone, email, name) — explicitly deferred per the
  design discussion; revisit if compliance requirements change.
- Logging headers at all (including auth) — explicitly excluded by scope.
- Non-JSON response bodies (binary/file downloads) — none exist in the current route
  set (verified via grep for `StreamingResponse`/`FileResponse`/binary media types), so
  this isn't handled; the content-type check (`application/json` only) means any future
  binary-response endpoint safely skips body capture rather than crashing on decode.
