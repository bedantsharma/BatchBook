"""
Tests for routes/batch_route.py — all 8 HTTP endpoints.

All services and Supabase are mocked so no real network/DB calls are made.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app import app
from clients.supabase_client import get_supabase_client
from models.batch_base import BatchSchema, BatchStatus
from models.batch_teacher_base import BatchTeacherSchema
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from services.batch_service import BatchService, get_batch_service
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_owner(owner_id: int = 1, teacher_id=None):
    o = MagicMock(spec=OwnerSchema)
    o.id = owner_id
    o.teacher_id = teacher_id or uuid4()
    return o


def _make_institute(institute_id: int = 10, owner_id: int = 1):
    i = MagicMock(spec=InstituteSchema)
    i.id = institute_id
    i.owner_id = owner_id
    return i


def _make_batch(
    batch_id: int = 1,
    institute_id: int = 10,
    status: BatchStatus = BatchStatus.ACTIVE,
) -> BatchSchema:
    b = MagicMock(spec=BatchSchema)
    b.id = batch_id
    b.institute_id = institute_id
    b.name = "Class 10 Maths"
    b.subject = "Maths"
    b.grade = "10"
    b.start_time = time(16, 0)
    b.end_time = time(17, 0)
    b.days_of_week = ["MON", "WED", "FRI"]
    b.max_capacity = 30
    b.start_date = date.today()
    b.end_date = date.today() + timedelta(days=365)
    b.status = status
    b.created_at = datetime(2026, 5, 25)
    return b


def _make_batch_teacher(batch_id: int = 1, teacher_id: int = 5) -> BatchTeacherSchema:
    bt = MagicMock(spec=BatchTeacherSchema)
    bt.id = 1
    bt.batch_id = batch_id
    bt.teacher_id = teacher_id
    return bt


def _mock_supabase():
    sb = MagicMock()
    sb.auth = MagicMock()
    return sb


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def override_supabase():
    sb = _mock_supabase()
    app.dependency_overrides[get_supabase_client] = lambda: sb
    yield sb


@pytest.fixture
def owner_user_id():
    return uuid4()


@pytest.fixture
def mock_owner_service(owner_user_id):
    svc = MagicMock(spec=OwnerService)
    svc.get_current_teacher_id = AsyncMock(return_value=owner_user_id)
    owner = _make_owner()
    svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)
    app.dependency_overrides[get_owner_service] = lambda: svc
    yield svc


@pytest.fixture
def mock_institute_service():
    svc = MagicMock(spec=InstituteService)
    institute = _make_institute()
    svc.get_by_owner_id = AsyncMock(return_value=institute)
    app.dependency_overrides[get_institute_service] = lambda: svc
    yield svc


@pytest.fixture
def mock_batch_service():
    svc = MagicMock(spec=BatchService)
    app.dependency_overrides[get_batch_service] = lambda: svc
    yield svc


AUTH_HEADER = {"Authorization": "Bearer valid_token"}


# ─── POST /batch/ — create ─────────────────────────────────────────────────────


async def test_create_batch_returns_201(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    batch = _make_batch()
    mock_batch_service.create_batch = AsyncMock(return_value=batch)

    response = await client.post(
        "/batch/",
        json={
            "name": "Class 10 Maths",
            "subject": "Maths",
            "grade": "10",
            "start_time": "16:00:00",
            "end_time": "17:00:00",
            "days_of_week": ["MON", "WED", "FRI"],
            "max_capacity": 30,
            "end_date": str(date.today() + timedelta(days=365)),
        },
        headers=AUTH_HEADER,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Class 10 Maths"
    assert body["institute_id"] == 10


async def test_create_batch_returns_401_without_auth(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_owner_service.get_current_teacher_id = AsyncMock(side_effect=Exception("bad token"))

    response = await client.post(
        "/batch/",
        json={
            "name": "Test",
            "subject": "Maths",
            "start_time": "16:00:00",
            "end_time": "17:00:00",
            "days_of_week": ["MON"],
            "max_capacity": 10,
            "end_date": str(date.today() + timedelta(days=180)),
        },
        headers={"Authorization": "Bearer bad"},
    )

    assert response.status_code == 401


async def test_create_batch_returns_404_when_no_institute(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_institute_service.get_by_owner_id = AsyncMock(return_value=None)

    response = await client.post(
        "/batch/",
        json={
            "name": "Batch",
            "subject": "Science",
            "start_time": "10:00:00",
            "end_time": "11:00:00",
            "days_of_week": ["SAT"],
            "max_capacity": 20,
            "end_date": str(date.today() + timedelta(days=180)),
        },
        headers=AUTH_HEADER,
    )

    assert response.status_code == 404


async def test_create_batch_rejects_invalid_days(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    response = await client.post(
        "/batch/",
        json={
            "name": "Batch",
            "subject": "Science",
            "start_time": "10:00:00",
            "end_time": "11:00:00",
            "days_of_week": ["MONDAY"],  # invalid
            "max_capacity": 20,
            "end_date": str(date.today() + timedelta(days=180)),
        },
        headers=AUTH_HEADER,
    )

    assert response.status_code == 422


# ─── GET /batch/ — list ────────────────────────────────────────────────────────


async def test_list_batches_returns_all(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    batches = [_make_batch(batch_id=1), _make_batch(batch_id=2)]
    mock_batch_service.list_batches = AsyncMock(return_value=batches)

    response = await client.get("/batch/", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert len(response.json()) == 2


# ─── GET /batch/{id} — get one ─────────────────────────────────────────────────


async def test_get_batch_returns_batch(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    batch = _make_batch()
    mock_batch_service.get_batch = AsyncMock(return_value=batch)

    response = await client.get("/batch/1", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert response.json()["id"] == 1


async def test_get_batch_returns_404(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_batch_service.get_batch = AsyncMock(side_effect=ValueError("Batch not found"))

    response = await client.get("/batch/999", headers=AUTH_HEADER)

    assert response.status_code == 404


# ─── PATCH /batch/{id} — update ───────────────────────────────────────────────


async def test_update_batch_returns_updated(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    updated = _make_batch()
    updated.name = "Advanced Maths"
    mock_batch_service.update_batch = AsyncMock(return_value=updated)

    response = await client.patch(
        "/batch/1", json={"name": "Advanced Maths"}, headers=AUTH_HEADER
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Advanced Maths"


async def test_update_batch_returns_404_for_missing(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_batch_service.update_batch = AsyncMock(side_effect=ValueError("Batch not found"))

    response = await client.patch(
        "/batch/999", json={"name": "X"}, headers=AUTH_HEADER
    )

    assert response.status_code == 404


# ─── DELETE /batch/{id} — delete ──────────────────────────────────────────────


async def test_delete_batch_returns_204(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_batch_service.delete_batch = AsyncMock()

    response = await client.delete("/batch/1", headers=AUTH_HEADER)

    assert response.status_code == 204


async def test_delete_batch_returns_404_when_not_found(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_batch_service.delete_batch = AsyncMock(side_effect=ValueError("Batch not found"))

    response = await client.delete("/batch/999", headers=AUTH_HEADER)

    assert response.status_code == 404


# ─── POST /batch/{id}/assign-teacher ──────────────────────────────────────────


async def test_assign_teacher_returns_201(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    link = _make_batch_teacher()
    mock_batch_service.assign_teacher = AsyncMock(return_value=link)

    response = await client.post(
        "/batch/1/assign-teacher", json={"teacher_id": 5}, headers=AUTH_HEADER
    )

    assert response.status_code == 201
    body = response.json()
    assert body["batch_id"] == 1
    assert body["teacher_id"] == 5


async def test_assign_teacher_returns_409_on_duplicate(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_batch_service.assign_teacher = AsyncMock(
        side_effect=ValueError("Teacher is already assigned to this batch")
    )

    response = await client.post(
        "/batch/1/assign-teacher", json={"teacher_id": 5}, headers=AUTH_HEADER
    )

    assert response.status_code == 409


# ─── DELETE /batch/{id}/teacher/{tid} ─────────────────────────────────────────


async def test_remove_teacher_returns_204(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_batch_service.remove_teacher = AsyncMock()

    response = await client.delete("/batch/1/teacher/5", headers=AUTH_HEADER)

    assert response.status_code == 204


async def test_remove_teacher_returns_404_when_not_assigned(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_batch_service.remove_teacher = AsyncMock(
        side_effect=ValueError("Teacher is not assigned to this batch")
    )

    response = await client.delete("/batch/1/teacher/5", headers=AUTH_HEADER)

    assert response.status_code == 404


# ─── POST /batch/{id}/archive ─────────────────────────────────────────────────


async def test_archive_batch_returns_200(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    archived = _make_batch(status=BatchStatus.ARCHIVED)
    mock_batch_service.try_archive = AsyncMock(return_value=archived)

    response = await client.post("/batch/1/archive", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert response.json()["status"] == "ARCHIVED"


async def test_archive_batch_returns_409_if_unsettled(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_batch_service.try_archive = AsyncMock(
        side_effect=ValueError("Cannot archive batch — there are unsettled fee records.")
    )

    response = await client.post("/batch/1/archive", headers=AUTH_HEADER)

    assert response.status_code == 409


async def test_archive_already_archived_returns_409(
    client, mock_owner_service, mock_institute_service, mock_batch_service
):
    mock_batch_service.try_archive = AsyncMock(
        side_effect=ValueError("Batch is already archived")
    )

    response = await client.post("/batch/1/archive", headers=AUTH_HEADER)

    assert response.status_code == 409
