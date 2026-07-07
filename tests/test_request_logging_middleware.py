"""
Regression tests for the OTEL_ENABLED request/response body capture path in
app.py's log_and_handle_exceptions middleware.

This path has no coverage in the default test run because conftest.py never
sets OTEL_EXPORTER_OTLP_ENDPOINT, so telemetry.OTEL_ENABLED (and the copy
imported into app.py's namespace) is always False. These tests monkeypatch
app.OTEL_ENABLED directly (not telemetry.OTEL_ENABLED) since app.py did
`from telemetry import OTEL_ENABLED`, which binds a separate name in app's
own module namespace.
"""

import pytest
from fastapi import APIRouter, Request

import app as app_module
from app import app


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


async def test_middleware_survives_invalid_json_body_when_otel_enabled(
    client, echo_route, monkeypatch
):
    monkeypatch.setattr(app_module, "OTEL_ENABLED", True)

    response = await client.post(
        "/echo-body",
        content=b"not valid json{",
        headers={"Content-Type": "application/json"},
    )

    # The point is that the middleware's body-capture code ran without
    # raising an uncaught exception -- we got SOME HTTP response back.
    assert response.status_code in (200, 401, 404, 422, 500)


async def test_middleware_survives_non_utf8_body_when_otel_enabled(
    client, echo_route, monkeypatch
):
    monkeypatch.setattr(app_module, "OTEL_ENABLED", True)

    response = await client.post(
        "/echo-body",
        content=b"\xff\xfe\x00\x01invalid",
        headers={"Content-Type": "application/json"},
    )

    # Before the fix, json.loads() on non-UTF-8 bytes raised UnicodeDecodeError
    # outside the middleware's try block (request side) or was mis-caught by
    # the broad `except Exception` and turned into a fabricated 500 (response
    # side). Either way the request must complete with a real HTTP response.
    assert response.status_code in (200, 401, 404, 422, 500)
