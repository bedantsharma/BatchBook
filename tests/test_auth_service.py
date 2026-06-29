"""
Tests for services/auth_service.py — get_current_user_id.

Symbols under test (from GitNexus):
  Function:services/auth_service.py:get_current_user_id
  Called by: StudentService.get_current_user_id, OwnerService.get_current_teacher_id

Local JWT verification (HS256 + audience="authenticated") is tested; no Supabase
network calls are made. The supabase parameter is present in the signature but unused.
"""

import time
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException

from services.auth_service import get_current_user_id

TEST_SECRET = "test-jwt-secret-for-unit-tests-ok"


def _make_token(
    user_id, *, secret=TEST_SECRET, exp_offset: int = 3600, audience: str = "authenticated"
) -> str:
    """Build a signed HS256 JWT suitable for passing to get_current_user_id."""
    payload = {
        "sub": str(user_id),
        "aud": audience,
        "exp": int(time.time()) + exp_offset,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture
def mock_supabase():
    """Unused by the new implementation but kept — signature still accepts it."""
    return MagicMock()


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.supabase_jwt_secret = TEST_SECRET
    return settings


# ---------------------------------------------------------------------------
# 1. Valid token — returns correct UUID
# ---------------------------------------------------------------------------


async def test_valid_token_returns_correct_uuid(mock_supabase, mock_settings):
    user_id = uuid4()
    token = _make_token(user_id)

    with patch("services.auth_service.get_settings", return_value=mock_settings):
        result = await get_current_user_id(mock_supabase, f"Bearer {token}")

    assert result == user_id
    assert isinstance(result, UUID)


# ---------------------------------------------------------------------------
# 2. Expired token — raises 401
# ---------------------------------------------------------------------------


async def test_expired_token_raises_401(mock_supabase, mock_settings):
    user_id = uuid4()
    token = _make_token(user_id, exp_offset=-100)  # expired 100 s ago

    with patch("services.auth_service.get_settings", return_value=mock_settings):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(mock_supabase, f"Bearer {token}")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


# ---------------------------------------------------------------------------
# 3. Tampered signature — raises 401
# ---------------------------------------------------------------------------


async def test_tampered_signature_raises_401(mock_supabase, mock_settings):
    user_id = uuid4()
    token = _make_token(user_id)

    # Corrupt the signature segment (last dot-separated part)
    header, body_part, sig = token.split(".")
    corrupted_sig = sig[:-4] + ("XXXX" if sig[-4:] != "XXXX" else "YYYY")
    tampered_token = f"{header}.{body_part}.{corrupted_sig}"

    with patch("services.auth_service.get_settings", return_value=mock_settings):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(mock_supabase, f"Bearer {tampered_token}")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


# ---------------------------------------------------------------------------
# 4. Missing / malformed Bearer prefix — raises 401
# ---------------------------------------------------------------------------


async def test_malformed_bearer_raises_401(mock_supabase, mock_settings):
    """A non-JWT string without the Bearer prefix should be rejected."""
    with patch("services.auth_service.get_settings", return_value=mock_settings):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(mock_supabase, "not-a-bearer-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"
