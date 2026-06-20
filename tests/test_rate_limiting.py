"""
Tests for per-IP rate limiting on OTP endpoints.

Symbols under test:
  Function:rate_limiter.py:limiter
  Function:routes/owner_route.py:send_otp
  Function:routes/owner_route.py:verify_otp
  Function:routes/student_route.py:send_otp
  Function:routes/student_route.py:verify_otp
  Function:routes/parent_route.py:send_otp
  Function:routes/parent_route.py:verify_otp

Rate limiting is disabled globally for tests (RATE_LIMIT_ENABLED=false, see conftest.py)
so the rest of the suite isn't affected by shared in-memory limiter state. This file
flips it on for the duration of each test via `enable_rate_limiting` and resets the
limiter's storage afterward so later tests aren't polluted.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app import app
from clients.supabase_client import get_supabase_client
from rate_limiter import limiter


@pytest.fixture
def enable_rate_limiting():
    limiter.enabled = True
    yield
    limiter.enabled = False
    limiter.reset()


@pytest.fixture(autouse=True)
def override_supabase(client):
    sb = MagicMock()
    sb.auth = MagicMock()
    sb.auth.sign_in_with_otp = AsyncMock(return_value={"message_id": "abc"})
    sb.auth.verify_otp = AsyncMock(side_effect=Exception("not under test"))
    app.dependency_overrides[get_supabase_client] = lambda: sb
    yield sb


@pytest.mark.parametrize("prefix", ["owner", "student", "parent"])
async def test_generate_otp_blocks_after_limit(client, enable_rate_limiting, prefix):
    for _ in range(5):
        response = await client.post(f"/{prefix}/generate_otp", json={"phone": "9876543210"})
        assert response.status_code == 200

    response = await client.post(f"/{prefix}/generate_otp", json={"phone": "9876543210"})
    assert response.status_code == 429


@pytest.mark.parametrize("prefix", ["owner", "student", "parent"])
async def test_verify_otp_blocks_after_limit(client, enable_rate_limiting, prefix):
    payload = {"token": "123456", "phone": "9876543210"}

    for _ in range(10):
        response = await client.post(f"/{prefix}/verify_otp", json=payload)
        assert response.status_code != 429

    response = await client.post(f"/{prefix}/verify_otp", json=payload)
    assert response.status_code == 429


async def test_rate_limit_is_scoped_per_endpoint(client, enable_rate_limiting):
    """Exhausting /owner/generate_otp must not affect /student/generate_otp."""
    for _ in range(5):
        await client.post("/owner/generate_otp", json={"phone": "9876543210"})
    blocked = await client.post("/owner/generate_otp", json={"phone": "9876543210"})
    assert blocked.status_code == 429

    still_open = await client.post("/student/generate_otp", json={"phone": "9876543210"})
    assert still_open.status_code == 200
