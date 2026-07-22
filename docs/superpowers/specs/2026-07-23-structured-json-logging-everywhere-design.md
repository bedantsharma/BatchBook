# Structured JSON Logging Everywhere + Grafana Cloud Body-Format Fix

Date: 2026-07-23

> **Amendment (post-implementation review):** every `url=str(request.url)` in this
> document (Decisions, Section 2, Section 4) describes the *originally planned* shape —
> full path + query string. Task-review found this duplicates the query string
> unredacted next to the already-redacted `query_params` field in the same log line, a
> real redaction bypass. The shipped code instead builds `url` as
> `f"{request.url.scheme}://{request.url.netloc}{request.url.path}"` — scheme + host +
> path, deliberately **without** the query string, which stays exclusively in the
> (redacted) `query_params` field. See commit `32ea8a1` on
> `feature/structured-json-logging-everywhere`.

## Problem

`docs/superpowers/specs/2026-07-08-structured-logging-otel-design.md` shipped structured
JSON logging, trace/span correlation, and a redacted request/response body capture
middleware — but gated the entire thing behind `telemetry.OTEL_ENABLED`
(`bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"))`). That gate causes two problems
discovered in this session:

1. **Local dev never sees any of it.** `OTEL_EXPORTER_OTLP_ENDPOINT` is only set in
   production (Render), so local/Docker dev logs are still the original plain-text
   line (`method path → status (time)`), and the request/response interceptor's body,
   query-param, and URL capture never executes — it's dead code outside of prod.
2. **Production JSON is broken.** With `OTEL_EXPORTER_OTLP_ENDPOINT` now configured on
   Render, logs reach Grafana Cloud (Loki) correctly, but the log line body is not
   JSON. Querying `{service_name="batchbook-backend-production"}` directly against the
   `grafanacloud-logs` Loki datasource shows lines like:

   ```
   2026-07-22 18:11:20.109 | INFO     | app:log_and_handle_exceptions:124 - request completed
   ```

   with `trace_id`, `span_id`, `extra_method`, `extra_path`, `extra_status_code`, etc.
   correctly present as **structured metadata** (confirmed via
   `list_loki_label_names`/`query_loki_logs` against the live datasource), but the body
   text itself is loguru's default pre-rendered format string, not JSON.

## Root cause (verified against loguru source, not guessed)

`telemetry.py`'s `configure_logging()` adds `otel_handler` (an
`opentelemetry.sdk._logs.LoggingHandler`, which is a `logging.Handler`) as a loguru
sink without a `"format"` key. Per
`loguru/_logger.py:822` → `loguru/_simple_sinks.py:30-52` (`StandardSink.write`):

```python
def write(self, message):
    raw_record = message.record
    message = str(message)   # renders using the sink's format, default if unset
    record = logging.getLogger().makeRecord(
        raw_record["name"], raw_record["level"].no, raw_record["file"].path,
        raw_record["line"], message, (), ...,
        raw_record["function"], {"extra": raw_record["extra"]},
    )
    self._handler.handle(record)
```

Any `logging.Handler` sink added without an explicit `format` gets loguru's default
format (`{time} | {level} | {name}:{function}:{line} - {message}`) baked into the
`msg` that becomes the stdlib `LogRecord`'s body — which is exactly what OTel's
`LoggingHandler` ships as the log record body to Loki. `raw_record["extra"]` (which
carries `trace_id`, `span_id`, `method`, `path`, `status_code`, `duration_ms`, etc. —
everything from `inject_trace_context` and the middleware's `logger.bind(...)`) is
passed through correctly and lands as structured metadata regardless of this bug —
confirmed live in Loki. Only the body text is wrong.

**This does not affect trace/log correlation.** Verified against the live Loki data:
only `service_name`, `deployment_environment`, `service_instance_id` are Loki stream
labels (`list_loki_label_names`); `trace_id`, `span_id`, and every `extra_*` field are
per-line **structured metadata**, filterable via `| trace_id="<id>"` regardless of what
the body text says. Grafana's own "logs for this span" correlation feature queries
structured metadata this way, not the body text.

## Decisions

- **Fix the body format**: add `"format": "{message}"` to the `otel_handler` entry in
  `configure_logging()`'s `handlers=[...]` list. Log body becomes the clean message
  (e.g. `"request completed"`); every structured field keeps flowing as queryable
  metadata, unchanged.
- **JSON stdout becomes unconditional**, decoupled from `OTEL_ENABLED`. Every
  environment (local dev, Docker, prod) prints structured JSON lines to stdout. When no
  OTel span is active (i.e. always, locally, since tracing itself stays gated on
  `OTEL_ENABLED`), `trace_id`/`span_id` print as empty strings — same behavior
  `inject_trace_context` already has today, just no longer skipped locally.
- **OTLP shipping to Grafana Cloud stays gated behind `OTEL_ENABLED`.** Local dev still
  never talks to Grafana Cloud — only the stdout format changes, not what gets shipped
  where.
- **The request/response interceptor middleware becomes unconditional.** Every request,
  in every environment, gets one structured log line capturing: `method`, a new `url`
  field (`str(request.url)` — full path + query string, replacing the need to
  cross-reference `path` and `query_params` separately), `query_params`, `path_params`,
  `request_body`, `response_body`, `status_code`, `duration_ms`. Redaction and the 4KB
  truncation cap (`request_logging.py`, unchanged) apply everywhere now, not just when
  Grafana credentials are configured. The `if OTEL_ENABLED: ... else: <plain text>`
  branch in `app.py`'s `log_and_handle_exceptions` collapses into a single path.
- **Headers are never logged.** Explicitly decided against — `Authorization`/`Cookie`
  leak risk isn't worth it right now. No denylist, no allowlist; headers are simply
  never read by the middleware.
- **`request_logging.py`'s redaction/truncation logic is unchanged** — already correct
  and covered by `tests/test_request_logging.py`.
- **`setup_telemetry()` (tracing + metrics) is unchanged** — still entirely gated on
  `OTEL_EXPORTER_OTLP_ENDPOINT`. This spec only touches logging.

## Section 1 — `telemetry.py`

`configure_logging()` splits into an always-run part (JSON stdout sink) and a part
still gated on `OTEL_ENABLED` (the OTLP log-shipping handler):

```python
def configure_logging() -> None:
    """Reconfigure loguru: JSON stdout always; ship to Grafana Cloud (Loki) via
    OTLP only when OTEL_ENABLED.

    Mutates the shared loguru core via configure(), so every existing
    `from loguru import logger` call site across the codebase is affected —
    no per-file changes needed.
    """
    handlers = [{"sink": json_sink, "level": "INFO"}]

    if OTEL_ENABLED:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

        resource = Resource.create({...})  # unchanged
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
        otel_handler = LoggingHandler(logger_provider=logger_provider)

        # THE FIX: explicit format, so loguru doesn't pre-render its default
        # text format into the OTel LogRecord body.
        handlers.append({"sink": otel_handler, "level": "INFO", "format": "{message}"})

    logger.configure(patcher=inject_trace_context, handlers=handlers)
```

`setup_telemetry(app)` currently calls `configure_logging()` as its last line, after an
early `if not OTEL_ENABLED: return` — so today `configure_logging()` never runs at all
when OTel is disabled. That early return must move to *after* the `configure_logging()`
call, e.g.:

```python
def setup_telemetry(app) -> None:
    configure_logging()  # always runs, even when OTel itself is disabled

    if not OTEL_ENABLED:
        return

    # ... existing tracer/meter/FastAPI instrumentation, unchanged
```

`app.py` keeps making exactly one call (`setup_telemetry(app)`); no new call site is
added there. `inject_trace_context` and `json_sink` are unchanged from the current
implementation (`trace_id`/`span_id` default to `""` when `trace.get_current_span()`
has no valid context — already true today, simply no longer skipped in dev).

## Section 2 — `app.py` middleware

`log_and_handle_exceptions` drops all `if OTEL_ENABLED:` branching. Single path, every
request:

```python
@app.middleware("http")
async def log_and_handle_exceptions(request: Request, call_next):
    start = time.perf_counter()

    request_body_log = None
    request_content_length = request.headers.get("content-length")
    if request_content_length and int(request_content_length) > MAX_LOGGED_BYTES:
        request_body_log = json.dumps(f"[request body too large to capture: {request_content_length} bytes]")
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
                response_body_log = json.dumps(f"[response body too large to capture: {response_content_length} bytes]")
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

`OTEL_ENABLED` import stays in `app.py` only if still needed elsewhere; otherwise
removed from the middleware entirely.

## Section 3 — Test fallout

`tests/test_request_logging_middleware.py` currently monkeypatches `app.OTEL_ENABLED`
to flip capture behavior on/off. Once capture is unconditional, that toggle no longer
exists. Rewrite:

- Drop all `monkeypatch.setattr(app_module, "OTEL_ENABLED", ...)` calls.
- Keep the same assertions (malformed/non-UTF-8 body doesn't crash the middleware,
  sensitive fields get redacted in the bound log record, response body survives
  drain-and-reconstruct) since that behavior is now simply always active.
- `test_middleware_response_body_survives_drain_and_reconstruct`'s two-case structure
  (OTEL_ENABLED False vs True, same assertions) collapses to one case, since there's
  only one path now.

`tests/test_request_logging.py` (pure `request_logging.py` unit tests) is untouched —
nothing about redaction/truncation logic changes.

Full `uv run pytest` must pass after each change.

## Section 4 — Manual verification

1. Local: `make backend`, hit a couple of endpoints, confirm `docker logs
   batchbook-dev-backend-1` now shows structured JSON lines (not the old plain-text
   format), with `trace_id`/`span_id` present as empty strings (no OTel configured
   locally).
2. Confirm a request with a known secret field (e.g. `razorpay_key_secret`) shows
   `"[REDACTED]"` in the local JSON log's `request_body`, not the raw value.
3. Confirm the `url` field shows the full path + query string for a request with query
   params.
4. Production (after deploy): re-query the `grafanacloud-logs` Loki datasource used in
   this session — line body should now read as the plain message (`"request
   completed"`), with `trace_id`/`span_id` still present in structured metadata, and
   `request_body`/`response_body`/`query_params` now populated (they were `None` before
   for the sampled `/docs` GET requests, but should now show real data for JSON
   endpoints).

## Out of scope

- Headers, redacted or otherwise — explicitly rejected in this session due to
  Authorization/Cookie leak risk.
- Any change to `setup_telemetry()` (tracing/metrics setup) or `instrument_engine()`.
- Any change to the redaction denylist, truncation cap, or `request_logging.py` logic.
- Non-JSON response bodies (binary/file downloads) — still out of scope, same reasoning
  as the original spec (none exist in the current route set).
