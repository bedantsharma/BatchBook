"""
Tests for services/auth_service.py — get_current_user_id.

Uses a generated EC P-256 key pair to sign tokens locally. The JWKS fetch
(_get_public_key) is mocked so no network calls are made.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from services.auth_service import get_current_user_id

# Generate a throw-away EC P-256 key pair once for the whole test module.
_private_key = ec.generate_private_key(ec.SECP256R1())
_public_key = _private_key.public_key()


def _make_token(user_id, *, exp_offset: int = 3600, audience: str = "authenticated") -> str:
    payload = {
        "sub": str(user_id),
        "aud": audience,
        "exp": int(time.time()) + exp_offset,
    }
    return jwt.encode(payload, _private_key, algorithm="ES256")


@pytest.fixture
def mock_supabase():
    """Unused by the implementation but kept — signature still accepts it."""
    return MagicMock()


@pytest.fixture(autouse=True)
def patch_get_public_key():
    """Replace the JWKS network fetch with the in-process test public key."""
    with patch(
        "services.auth_service._get_public_key",
        new=AsyncMock(return_value=_public_key),
    ):
        yield


# ---------------------------------------------------------------------------
# 1. Valid token — returns correct UUID
# ---------------------------------------------------------------------------


async def test_valid_token_returns_correct_uuid(mock_supabase):
    user_id = uuid4()
    token = _make_token(user_id)

    result = await get_current_user_id(mock_supabase, f"Bearer {token}")

    assert result == user_id
    assert isinstance(result, UUID)


# ---------------------------------------------------------------------------
# 2. Expired token — raises 401
# ---------------------------------------------------------------------------


async def test_expired_token_raises_401(mock_supabase):
    token = _make_token(uuid4(), exp_offset=-100)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(mock_supabase, f"Bearer {token}")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


# ---------------------------------------------------------------------------
# 3. Tampered signature — raises 401
# ---------------------------------------------------------------------------


async def test_tampered_signature_raises_401(mock_supabase):
    token = _make_token(uuid4())
    header, body_part, sig = token.split(".")
    corrupted_sig = sig[:-4] + ("XXXX" if sig[-4:] != "XXXX" else "YYYY")
    tampered = f"{header}.{body_part}.{corrupted_sig}"

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(mock_supabase, f"Bearer {tampered}")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


# ---------------------------------------------------------------------------
# 4. Malformed Bearer — raises 401
# ---------------------------------------------------------------------------


async def test_malformed_bearer_raises_401(mock_supabase):
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(mock_supabase, "not-a-bearer-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


# ---------------------------------------------------------------------------
# 5. JWKS fetch failure — raises 503
# ---------------------------------------------------------------------------


async def test_jwks_fetch_failure_raises_503(mock_supabase):
    import httpx

    with patch(
        "services.auth_service._get_public_key",
        new=AsyncMock(side_effect=httpx.ConnectError("unreachable")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(mock_supabase, "Bearer anything")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Auth service unavailable"
