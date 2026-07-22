"""OpenTelemetry bootstrap for traces + metrics, exported via OTLP/HTTP to Grafana Cloud.

Entirely opt-in: every function here no-ops unless OTEL_EXPORTER_OTLP_ENDPOINT is set,
so local dev without credentials and the pytest suite are unaffected.
"""

import json
import os

from loguru import logger
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


def instrument_engine(engine) -> None:
    """Attach DB span attribution to a SQLAlchemy async engine."""
    if not OTEL_ENABLED:
        return
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
