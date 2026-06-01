"""
Tests for the request logging + global exception handling middleware in app.py.
"""

from unittest.mock import patch

import pytest
from fastapi import APIRouter

from app import app


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
    with patch("app.logger") as mock_logger:
        await client.get("/crash")
        error_calls = [str(c) for c in mock_logger.error.call_args_list]
        assert any("RuntimeError" in c for c in error_calls)
        assert any("crash" in c for c in error_calls)


async def test_middleware_logs_successful_request(client):
    with patch("app.logger") as mock_logger:
        response = await client.get("/docs")
        assert response.status_code == 200
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("GET" in c and "/docs" in c and "200" in c for c in info_calls)


async def test_middleware_logs_404_as_404_not_500(client):
    with patch("app.logger") as mock_logger:
        response = await client.get("/nonexistent-route-xyz")
        assert response.status_code == 404
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("404" in c for c in info_calls)
        assert not any("500" in c for c in info_calls)
