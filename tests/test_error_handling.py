"""
Tests for the request logging + global exception handling middleware in app.py.
"""

import pytest
from fastapi import APIRouter

from app import app


class _LogCapture:
    """Collects loguru records emitted while this sink is attached."""

    def __init__(self):
        self.records = []

    def __call__(self, message):
        self.records.append(message.record)


@pytest.fixture
def crash_route():
    """Register a temporary /crash route that always raises RuntimeError."""
    router = APIRouter()

    @router.get("/crash")
    async def crash():
        raise RuntimeError("boom")

    app.include_router(router)
    yield
    app.routes[:] = [r for r in app.routes if not (hasattr(r, "path") and r.path == "/crash")]


async def test_unhandled_exception_returns_500(client, crash_route):
    response = await client.get("/crash")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


async def test_unhandled_exception_logs_error(client, crash_route):
    from loguru import logger

    capture = _LogCapture()
    sink_id = logger.add(capture, level="INFO")
    try:
        await client.get("/crash")
    finally:
        logger.remove(sink_id)

    failed_records = [r for r in capture.records if r["message"] == "request failed"]
    assert failed_records, "expected a 'request failed' log record"
    assert "RuntimeError" in failed_records[-1]["extra"]["exception"]
    assert "crash" in failed_records[-1]["extra"]["url"]


async def test_middleware_logs_successful_request(client):
    from loguru import logger

    capture = _LogCapture()
    sink_id = logger.add(capture, level="INFO")
    try:
        response = await client.get("/docs")
        assert response.status_code == 200
    finally:
        logger.remove(sink_id)

    completed_records = [r for r in capture.records if r["message"] == "request completed"]
    assert completed_records, "expected a 'request completed' log record"
    record = completed_records[-1]
    assert record["extra"]["method"] == "GET"
    assert "/docs" in record["extra"]["url"]
    assert record["extra"]["status_code"] == 200


async def test_middleware_logs_404_as_404_not_500(client):
    from loguru import logger

    capture = _LogCapture()
    sink_id = logger.add(capture, level="INFO")
    try:
        response = await client.get("/nonexistent-route-xyz")
        assert response.status_code == 404
    finally:
        logger.remove(sink_id)

    completed_records = [r for r in capture.records if r["message"] == "request completed"]
    assert completed_records, "expected a 'request completed' log record"
    assert completed_records[-1]["extra"]["status_code"] == 404
