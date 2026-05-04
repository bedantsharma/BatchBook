"""
Tests for routes/owner_route.py — all 4 HTTP endpoints.

Symbols under test (from GitNexus):
  Function:routes/owner_route.py:send_otp
  Function:routes/owner_route.py:verify_otp
  Function:routes/owner_route.py:get_owner
  Function:routes/owner_route.py:update_owner

Supabase and OwnerService are mocked so no real network calls are made.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from clients.supabase_client import get_supabase_client
from models.owner_base import OwnerSchema
from services.owner_service import OwnerService, get_owner_service


def _mock_supabase():
    sb = MagicMock()
    sb.auth = MagicMock()
    return sb


def _make_owner_schema(teacher_id=None):
    owner = MagicMock(spec=OwnerSchema)
    owner.id = 1
    owner.teacher_id = teacher_id or uuid4()
    owner.phone_number = "9876543210"
    owner.name = "Sharma Sir"
    owner.email = "sharma@example.com"
    owner.institute_name = "Sharma Classes"
    owner.city = "Delhi"
    owner.created_at = datetime(2026, 1, 1)
    return owner


@pytest.fixture(autouse=True)
def override_supabase(client):
    sb = _mock_supabase()
    from app import app
    app.dependency_overrides[get_supabase_client] = lambda: sb
    yield sb
    # conftest.client fixture already calls app.dependency_overrides.clear()


# --- POST /owner/generate_otp ---

async def test_generate_otp_calls_supabase(client, override_supabase):
    override_supabase.auth.sign_in_with_otp = AsyncMock(return_value={"message_id": "abc"})

    response = await client.post("/owner/generate_otp", json={"phone": "9876543210"})

    assert response.status_code == 200
    override_supabase.auth.sign_in_with_otp.assert_called_once_with({"phone": "+919876543210"})


async def test_generate_otp_returns_500_on_supabase_error(client, override_supabase):
    override_supabase.auth.sign_in_with_otp = AsyncMock(side_effect=Exception("Supabase down"))

    response = await client.post("/owner/generate_otp", json={"phone": "9876543210"})

    assert response.status_code == 500


async def test_generate_otp_rejects_invalid_phone(client):
    response = await client.post("/owner/generate_otp", json={"phone": "12345"})
    assert response.status_code == 422


# --- POST /owner/verify_otp ---

async def test_verify_otp_returns_token_on_success(client):
    teacher_id = uuid4()
    mock_service = MagicMock(spec=OwnerService)
    mock_service.verify_otp = AsyncMock(return_value=("tok_abc_1234567890", "authenticated", teacher_id))

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: mock_service

    response = await client.post("/owner/verify_otp", json={
        "phone": "9876543210",
        "token": "123456",
        "name": "Sharma Sir",
    })

    assert response.status_code == 200
    body = response.json()
    assert body["auth_token"] == "tok_abc_1234567890"
    assert body["aud"] == "authenticated"
    assert body["teacher_id"] == str(teacher_id)


async def test_verify_otp_returns_401_on_value_error(client):
    mock_service = MagicMock(spec=OwnerService)
    mock_service.verify_otp = AsyncMock(side_effect=ValueError("OTP verification failed"))

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: mock_service

    response = await client.post("/owner/verify_otp", json={
        "phone": "9876543210",
        "token": "000000",
    })

    assert response.status_code == 401
    assert "OTP verification failed" in response.json()["detail"]


# --- GET /owner/me ---

async def test_get_owner_me_returns_profile(client):
    teacher_id = uuid4()
    owner = _make_owner_schema(teacher_id=teacher_id)

    mock_service = MagicMock(spec=OwnerService)
    mock_service.get_current_teacher_id = AsyncMock(return_value=teacher_id)
    mock_service.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: mock_service

    response = await client.get("/owner/me", headers={"Authorization": "Bearer sometoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["phone_number"] == "9876543210"
    assert body["name"] == "Sharma Sir"


async def test_get_owner_me_returns_404_when_not_found(client):
    teacher_id = uuid4()
    mock_service = MagicMock(spec=OwnerService)
    mock_service.get_current_teacher_id = AsyncMock(return_value=teacher_id)
    mock_service.get_owner_by_teacher_id = AsyncMock(return_value=None)

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: mock_service

    response = await client.get("/owner/me", headers={"Authorization": "Bearer sometoken"})

    assert response.status_code == 404


async def test_get_owner_me_returns_401_without_auth(client):
    mock_service = MagicMock(spec=OwnerService)
    mock_service.get_current_teacher_id = AsyncMock(side_effect=Exception("bad token"))

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: mock_service

    response = await client.get("/owner/me", headers={"Authorization": "Bearer badtoken"})

    assert response.status_code == 401


# --- PATCH /owner/update ---

async def test_update_owner_returns_updated_profile(client):
    teacher_id = uuid4()
    updated_owner = _make_owner_schema(teacher_id=teacher_id)
    updated_owner.city = "Mumbai"

    mock_service = MagicMock(spec=OwnerService)
    mock_service.get_current_teacher_id = AsyncMock(return_value=teacher_id)
    mock_service.update_owner = AsyncMock(return_value=updated_owner)

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: mock_service

    response = await client.patch(
        "/owner/update",
        json={"city": "Mumbai"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 200
    assert response.json()["city"] == "Mumbai"


async def test_update_owner_returns_404_when_owner_not_found(client):
    teacher_id = uuid4()
    mock_service = MagicMock(spec=OwnerService)
    mock_service.get_current_teacher_id = AsyncMock(return_value=teacher_id)
    mock_service.update_owner = AsyncMock(return_value=None)

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: mock_service

    response = await client.patch(
        "/owner/update",
        json={"city": "Mumbai"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404
