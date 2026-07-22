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
