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
