"""
Tests for routes/parent_route.py — all HTTP endpoints.

Covers:
- POST /parent/generate_otp: delegates to supabase, returns 500 on error, 422 on bad phone
- POST /parent/verify_otp: returns JWT + children on success, 401 on ValueError
- GET /parent/me: returns parent profile + children, 404 if not found, 401 without auth
- POST /parent/refresh: returns new token pair on success, 401 on error
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from clients.supabase_client import get_supabase_client
from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from DTO.student_model import StudentFeesStatus
from services.parent_service import ParentService, get_parent_service


def _mock_supabase():
    sb = MagicMock()
    sb.auth = MagicMock()
    return sb


def _make_parent_schema(user_id=None):
    p = MagicMock(spec=ParentSchema)
    p.id = 1
    p.user_id = user_id or uuid4()
    p.phone_number = "9876543210"
    p.name = "Test Parent"
    p.created_at = datetime(2026, 1, 1)
    return p


def _make_student_schema():
    s = MagicMock(spec=StudentSchema)
    s.id = 10
    s.name = "Test Child"
    s.fees_status = StudentFeesStatus.NOT_PAID
    s.parent_id = 1
    s.institute_id = None
    s.email = "child@test.com"
    return s


@pytest.fixture(autouse=True)
def override_supabase(client):
    sb = _mock_supabase()
    from app import app
    app.dependency_overrides[get_supabase_client] = lambda: sb
    yield sb


# --- POST /parent/generate_otp ---

async def test_generate_otp_calls_supabase(client, override_supabase):
    override_supabase.auth.sign_in_with_otp = AsyncMock(return_value={"message_id": "abc"})

    response = await client.post("/parent/generate_otp", json={"phone": "9876543210"})

    assert response.status_code == 200
    override_supabase.auth.sign_in_with_otp.assert_called_once_with({"phone": "+919876543210"})


async def test_generate_otp_returns_500_on_supabase_error(client, override_supabase):
    override_supabase.auth.sign_in_with_otp = AsyncMock(side_effect=Exception("Supabase down"))

    response = await client.post("/parent/generate_otp", json={"phone": "9876543210"})

    assert response.status_code == 500


async def test_generate_otp_rejects_invalid_phone(client):
    response = await client.post("/parent/generate_otp", json={"phone": "12345"})
    assert response.status_code == 422


# --- POST /parent/verify_otp ---

async def test_verify_otp_returns_token_and_children_on_success(client):
    user_id = uuid4()
    mock_service = MagicMock(spec=ParentService)
    mock_service.verify_otp = AsyncMock(
        return_value=(
            "access_tok_1234567890",
            "refresh_tok_1234567890",
            "authenticated",
            user_id,
            [_make_student_schema()],
        )
    )

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.post("/parent/verify_otp", json={
        "phone": "9876543210",
        "token": "123456",
        "name": "Test Parent",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["auth_token"] == "access_tok_1234567890"
    assert body["refresh_token"] == "refresh_tok_1234567890"
    assert body["aud"] == "authenticated"
    assert body["user_id"] == str(user_id)
    assert len(body["children"]) == 1
    assert body["children"][0]["name"] == "Test Child"


async def test_verify_otp_returns_401_on_value_error(client):
    mock_service = MagicMock(spec=ParentService)
    mock_service.verify_otp = AsyncMock(side_effect=ValueError("OTP verification failed"))

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.post("/parent/verify_otp", json={
        "phone": "9876543210",
        "token": "000000",
    })

    assert response.status_code == 401
    assert "OTP verification failed" in response.json()["detail"]


# --- GET /parent/me ---

async def test_get_parent_me_returns_profile_with_children(client):
    user_id = uuid4()
    parent = _make_parent_schema(user_id=user_id)
    child = _make_student_schema()

    mock_service = MagicMock(spec=ParentService)
    mock_service.get_current_user_id = AsyncMock(return_value=user_id)
    mock_service.get_parent_by_user_id = AsyncMock(return_value=parent)
    mock_service.get_children = AsyncMock(return_value=[child])

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.get("/parent/me", headers={"Authorization": "Bearer sometoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["phone_number"] == "9876543210"
    assert body["name"] == "Test Parent"
    assert len(body["children"]) == 1
    assert body["children"][0]["id"] == 10


async def test_get_parent_me_returns_404_when_not_found(client):
    user_id = uuid4()
    mock_service = MagicMock(spec=ParentService)
    mock_service.get_current_user_id = AsyncMock(return_value=user_id)
    mock_service.get_parent_by_user_id = AsyncMock(return_value=None)

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.get("/parent/me", headers={"Authorization": "Bearer sometoken"})

    assert response.status_code == 404


async def test_get_parent_me_returns_401_without_valid_auth(client):
    mock_service = MagicMock(spec=ParentService)
    mock_service.get_current_user_id = AsyncMock(side_effect=Exception("bad token"))

    from app import app
    app.dependency_overrides[get_parent_service] = lambda: mock_service

    response = await client.get("/parent/me", headers={"Authorization": "Bearer badtoken"})

    assert response.status_code == 401


# --- POST /parent/refresh ---

async def test_refresh_token_returns_new_token_pair(client, override_supabase):
    user_id = uuid4()

    mock_user = MagicMock()
    mock_user.id = str(user_id)
    mock_user.aud = "authenticated"

    mock_session = MagicMock()
    mock_session.access_token = "new_access_tok_1234567890"
    mock_session.refresh_token = "new_refresh_tok_1234567890"

    mock_data = MagicMock()
    mock_data.user = mock_user
    mock_data.session = mock_session

    override_supabase.auth.refresh_session = AsyncMock(return_value=mock_data)

    response = await client.post("/parent/refresh", json={"refresh_token": "old_refresh_tok_1234567890"})

    assert response.status_code == 200
    body = response.json()
    assert body["auth_token"] == "new_access_tok_1234567890"
    assert body["children"] == []


async def test_refresh_token_returns_401_on_failure(client, override_supabase):
    override_supabase.auth.refresh_session = AsyncMock(side_effect=Exception("expired"))

    response = await client.post("/parent/refresh", json={"refresh_token": "bad_tok_1234567890"})

    assert response.status_code == 401
