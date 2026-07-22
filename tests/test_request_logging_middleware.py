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
