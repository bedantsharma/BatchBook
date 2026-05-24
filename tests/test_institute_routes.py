"""
Tests for the institute endpoints added to routes/owner_route.py.

Endpoints under test:
  POST /owner/institute  — create institute (once per owner)
  GET  /owner/institute  — get owner's institute

All external calls (Supabase, DB) are mocked.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from clients.supabase_client import get_supabase_client
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service


# ─── helpers ──────────────────────────────────────────────────────────────────


def _mock_supabase():
    sb = MagicMock()
    sb.auth = MagicMock()
    return sb


def _make_owner(teacher_id=None) -> OwnerSchema:
    owner = MagicMock(spec=OwnerSchema)
    owner.id = 1
    owner.teacher_id = teacher_id or uuid4()
    owner.phone_number = "9876543210"
    owner.name = "Sharma Sir"
    owner.email = "sharma@example.com"
    owner.institute_name = None
    owner.city = None
    owner.created_at = datetime(2026, 1, 1)
    return owner


def _make_institute(owner_id: int = 1) -> InstituteSchema:
    inst = MagicMock(spec=InstituteSchema)
    inst.id = 10
    inst.owner_id = owner_id
    inst.name = "Sharma Classes"
    inst.city = "Gurugram"
    inst.created_at = datetime(2026, 5, 1)
    return inst


# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def override_supabase(client):
    sb = _mock_supabase()
    from app import app

    app.dependency_overrides[get_supabase_client] = lambda: sb
    yield sb


def _setup_owner_service(client, teacher_id, owner=None, update_result=None):
    """Wire an OwnerService mock that returns teacher_id and optionally an owner object."""
    mock_svc = MagicMock(spec=OwnerService)
    mock_svc.get_current_teacher_id = AsyncMock(return_value=teacher_id)
    mock_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)
    if update_result is not None:
        mock_svc.update_owner = AsyncMock(return_value=update_result)
    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_svc
    return mock_svc


def _setup_institute_service(client, existing=None, created=None, updated=None):
    """Wire an InstituteService mock."""
    mock_svc = MagicMock(spec=InstituteService)
    mock_svc.get_institute_by_owner_id = AsyncMock(return_value=existing)
    if created is not None:
        mock_svc.create_institute = AsyncMock(return_value=created)
    if updated is not None:
        mock_svc.update_institute = AsyncMock(return_value=updated)
    from app import app

    app.dependency_overrides[get_institute_service] = lambda: mock_svc
    return mock_svc


# ─── POST /owner/institute ────────────────────────────────────────────────────


async def test_create_institute_returns_201_on_success(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)
    institute = _make_institute(owner_id=owner.id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service(client, existing=None, created=institute)

    response = await client.post(
        "/owner/institute",
        json={"name": "Sharma Classes", "city": "Gurugram"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Sharma Classes"
    assert body["city"] == "Gurugram"
    assert body["owner_id"] == owner.id


async def test_create_institute_returns_409_when_already_exists(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)
    existing_institute = _make_institute(owner_id=owner.id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service(client, existing=existing_institute)

    response = await client.post(
        "/owner/institute",
        json={"name": "Duplicate Classes", "city": "Delhi"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


async def test_create_institute_returns_404_when_owner_not_found(client):
    teacher_id = uuid4()
    _setup_owner_service(client, teacher_id, owner=None)
    _setup_institute_service(client, existing=None)

    response = await client.post(
        "/owner/institute",
        json={"name": "Some Classes", "city": "Noida"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404
    assert "Owner" in response.json()["detail"]


async def test_create_institute_returns_401_without_auth(client):
    mock_svc = MagicMock(spec=OwnerService)
    mock_svc.get_current_teacher_id = AsyncMock(side_effect=Exception("bad token"))
    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_svc

    response = await client.post(
        "/owner/institute",
        json={"name": "Some Classes", "city": "Noida"},
        headers={"Authorization": "Bearer badtoken"},
    )

    assert response.status_code == 401


async def test_create_institute_rejects_empty_name(client):
    teacher_id = uuid4()
    _setup_owner_service(client, teacher_id, owner=_make_owner(teacher_id))
    _setup_institute_service(client, existing=None)

    response = await client.post(
        "/owner/institute",
        json={"name": "", "city": "Delhi"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 422


async def test_create_institute_rejects_missing_city(client):
    teacher_id = uuid4()
    _setup_owner_service(client, teacher_id, owner=_make_owner(teacher_id))
    _setup_institute_service(client, existing=None)

    response = await client.post(
        "/owner/institute",
        json={"name": "Some Classes"},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 422


# ─── GET /owner/institute ─────────────────────────────────────────────────────


async def test_get_institute_returns_200_with_data(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)
    institute = _make_institute(owner_id=owner.id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service(client, existing=institute)

    response = await client.get(
        "/owner/institute",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Sharma Classes"
    assert body["city"] == "Gurugram"
    assert body["id"] == 10


async def test_get_institute_returns_404_when_no_institute(client):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id)

    _setup_owner_service(client, teacher_id, owner=owner)
    _setup_institute_service(client, existing=None)

    response = await client.get(
        "/owner/institute",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404
    assert "No institute found" in response.json()["detail"]


async def test_get_institute_returns_404_when_owner_not_found(client):
    teacher_id = uuid4()
    _setup_owner_service(client, teacher_id, owner=None)
    _setup_institute_service(client, existing=None)

    response = await client.get(
        "/owner/institute",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404
    assert "Owner" in response.json()["detail"]


async def test_get_institute_returns_401_without_auth(client):
    mock_svc = MagicMock(spec=OwnerService)
    mock_svc.get_current_teacher_id = AsyncMock(side_effect=Exception("bad token"))
    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_svc

    response = await client.get(
        "/owner/institute",
        headers={"Authorization": "Bearer badtoken"},
    )

    assert response.status_code == 401
