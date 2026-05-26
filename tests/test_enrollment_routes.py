"""
Tests for routes/enrollment_route.py — all HTTP endpoints.

Supabase, OwnerService, InstituteService, EnrollmentService, and the DB
are all mocked so no real network or database calls are made.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from clients.supabase_client import get_supabase_client
from models.batch_base import BatchSchema
from models.enrollment_base import EnrollmentSchema
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from models.student_base import StudentSchema
from services.enrollment_service import EnrollmentService, get_enrollment_service
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_supabase():
    sb = MagicMock()
    sb.auth = MagicMock()
    return sb


def _make_owner(teacher_id=None, owner_id=1):
    o = MagicMock(spec=OwnerSchema)
    o.id = owner_id
    o.teacher_id = teacher_id or uuid4()
    o.name = "Sharma Sir"
    o.phone_number = "9876543210"
    return o


def _make_institute(owner_id=1, institute_id=10):
    i = MagicMock(spec=InstituteSchema)
    i.id = institute_id
    i.owner_id = owner_id
    i.name = "Sharma Classes"
    i.city = "Delhi"
    i.created_at = datetime(2026, 1, 1)
    return i


def _make_batch(batch_id=5, institute_id=10):
    b = MagicMock(spec=BatchSchema)
    b.id = batch_id
    b.institute_id = institute_id
    b.name = "Class 10 Maths"
    b.subject = "Maths"
    return b


def _make_student(student_id=20, institute_id=10):
    s = MagicMock(spec=StudentSchema)
    s.id = student_id
    s.institute_id = institute_id
    s.name = "Rahul Sharma"
    return s


def _make_enrollment(
    enrollment_id=1,
    student_id=20,
    batch_id=5,
    is_active=True,
    due_day=15,
    first_month_amount=None,
):
    e = MagicMock(spec=EnrollmentSchema)
    e.id = enrollment_id
    e.student_id = student_id
    e.batch_id = batch_id
    e.enrolled_at = datetime(2026, 5, 1)
    e.is_active = is_active
    e.due_day = due_day
    e.first_month_amount = first_month_amount
    e.created_at = datetime(2026, 5, 1)
    return e


@pytest.fixture(autouse=True)
def override_supabase(client):
    sb = _mock_supabase()
    from app import app
    app.dependency_overrides[get_supabase_client] = lambda: sb
    yield sb


def _setup_owner_and_institute(owner_teacher_id, owner_id=1, institute_id=10):
    owner = _make_owner(teacher_id=owner_teacher_id, owner_id=owner_id)
    institute = _make_institute(owner_id=owner_id, institute_id=institute_id)

    mock_owner_svc = MagicMock(spec=OwnerService)
    mock_owner_svc.get_current_teacher_id = AsyncMock(return_value=owner_teacher_id)
    mock_owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    mock_institute_svc = MagicMock(spec=InstituteService)
    mock_institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    return owner, institute, mock_owner_svc, mock_institute_svc


# ---------------------------------------------------------------------------
# POST /enrollment/
# ---------------------------------------------------------------------------


async def test_enroll_student_success(client):
    owner_teacher_id = uuid4()
    owner, institute, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(
        owner_teacher_id, institute_id=10
    )
    batch = _make_batch(batch_id=5, institute_id=10)
    student = _make_student(student_id=20, institute_id=10)
    enrollment = _make_enrollment()

    mock_enrollment_svc = MagicMock(spec=EnrollmentService)
    mock_enrollment_svc.enroll_student = AsyncMock(return_value=enrollment)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    with (
        patch("routes.enrollment_route._verify_batch_belongs_to_institute", new=AsyncMock()),
        patch("routes.enrollment_route._verify_student_belongs_to_institute", new=AsyncMock()),
    ):
        response = await client.post(
            "/enrollment/",
            json={"student_id": 20, "batch_id": 5, "due_day": 15},
            headers={"Authorization": "Bearer sometoken"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["student_id"] == 20
    assert body["batch_id"] == 5
    assert body["due_day"] == 15
    assert body["is_active"] is True


async def test_enroll_student_returns_409_on_duplicate(client):
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    mock_enrollment_svc = MagicMock(spec=EnrollmentService)
    mock_enrollment_svc.enroll_student = AsyncMock(
        side_effect=ValueError("Student is already actively enrolled in this batch")
    )

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    with (
        patch("routes.enrollment_route._verify_batch_belongs_to_institute", new=AsyncMock()),
        patch("routes.enrollment_route._verify_student_belongs_to_institute", new=AsyncMock()),
    ):
        response = await client.post(
            "/enrollment/",
            json={"student_id": 20, "batch_id": 5},
            headers={"Authorization": "Bearer sometoken"},
        )

    assert response.status_code == 409
    assert "already actively enrolled" in response.json()["detail"]


async def test_enroll_student_requires_auth(client):
    response = await client.post(
        "/enrollment/",
        json={"student_id": 20, "batch_id": 5},
    )
    assert response.status_code in (401, 422)


async def test_enroll_student_invalid_student_id_returns_422(client):
    """student_id must be > 0."""
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc

    response = await client.post(
        "/enrollment/",
        json={"student_id": 0, "batch_id": 5},
        headers={"Authorization": "Bearer sometoken"},
    )
    assert response.status_code == 422


async def test_enroll_student_with_first_month_amount(client):
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    enrollment = _make_enrollment(first_month_amount=Decimal("750.00"))
    mock_enrollment_svc = MagicMock(spec=EnrollmentService)
    mock_enrollment_svc.enroll_student = AsyncMock(return_value=enrollment)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    with (
        patch("routes.enrollment_route._verify_batch_belongs_to_institute", new=AsyncMock()),
        patch("routes.enrollment_route._verify_student_belongs_to_institute", new=AsyncMock()),
    ):
        response = await client.post(
            "/enrollment/",
            json={"student_id": 20, "batch_id": 5, "due_day": 10, "first_month_amount": 750.00},
            headers={"Authorization": "Bearer sometoken"},
        )

    assert response.status_code == 201
    assert response.json()["first_month_amount"] == "750.00"


# ---------------------------------------------------------------------------
# GET /enrollment/batch/{batch_id}
# ---------------------------------------------------------------------------


async def test_list_enrollments_by_batch(client):
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    e1 = _make_enrollment(enrollment_id=1, is_active=True)
    e2 = _make_enrollment(enrollment_id=2, is_active=False)

    mock_enrollment_svc = MagicMock(spec=EnrollmentService)
    mock_enrollment_svc.get_enrollments_by_batch = AsyncMock(return_value=[e1, e2])

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    with patch("routes.enrollment_route._verify_batch_belongs_to_institute", new=AsyncMock()):
        response = await client.get(
            "/enrollment/batch/5",
            headers={"Authorization": "Bearer sometoken"},
        )

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_list_enrollments_returns_empty_list(client):
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    mock_enrollment_svc = MagicMock(spec=EnrollmentService)
    mock_enrollment_svc.get_enrollments_by_batch = AsyncMock(return_value=[])

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    with patch("routes.enrollment_route._verify_batch_belongs_to_institute", new=AsyncMock()):
        response = await client.get(
            "/enrollment/batch/5",
            headers={"Authorization": "Bearer sometoken"},
        )

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# PATCH /enrollment/{enrollment_id}
# ---------------------------------------------------------------------------


async def test_update_enrollment_success(client):
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    updated = _make_enrollment(due_day=20)
    mock_enrollment_svc = MagicMock(spec=EnrollmentService)
    mock_enrollment_svc.update_enrollment = AsyncMock(return_value=updated)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    with (
        patch("routes.enrollment_route._verify_batch_belongs_to_institute", new=AsyncMock()),
        patch(
            "routes.enrollment_route.select",
            return_value=MagicMock(),
        ),
    ):
        # We need to mock the db.execute call in the route that loads enrollment_check
        from sqlalchemy.ext.asyncio import AsyncSession

        async def mock_execute(stmt):
            result = MagicMock()
            result.scalar_one_or_none.return_value = _make_enrollment()
            return result

        app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

        # Patch db.execute for the route's ownership check
        with patch("routes.enrollment_route.AsyncSession", AsyncSession):
            pass

    # Simpler approach: mock the entire db execute via client's db fixture
    # The route does a db.execute() to fetch the enrollment for ownership check.
    # We override the db dependency to return a mock session.
    from db.session import get_db

    async def override_get_db():
        mock_db = AsyncMock()
        result = MagicMock()
        enrollment_mock = _make_enrollment(batch_id=5)
        result.scalar_one_or_none.return_value = enrollment_mock
        mock_db.execute = AsyncMock(return_value=result)
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    with patch("routes.enrollment_route._verify_batch_belongs_to_institute", new=AsyncMock()):
        response = await client.patch(
            "/enrollment/1",
            json={"due_day": 20},
            headers={"Authorization": "Bearer sometoken"},
        )

    assert response.status_code == 200
    assert response.json()["due_day"] == 20

    # Clean up db override
    app.dependency_overrides.pop(get_db, None)


async def test_update_enrollment_returns_422_if_no_fields(client):
    """UpdateEnrollmentRequest requires at least one field."""
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    from app import app

    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc

    response = await client.patch(
        "/enrollment/1",
        json={},
        headers={"Authorization": "Bearer sometoken"},
    )
    assert response.status_code == 422


async def test_update_enrollment_returns_404_if_not_found(client):
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    mock_enrollment_svc = MagicMock(spec=EnrollmentService)

    from app import app
    from db.session import get_db

    async def override_get_db():
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None  # enrollment not found
        mock_db.execute = AsyncMock(return_value=result)
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    response = await client.patch(
        "/enrollment/999",
        json={"due_day": 10},
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404
    assert "Enrollment not found" in response.json()["detail"]

    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# DELETE /enrollment/{enrollment_id}
# ---------------------------------------------------------------------------


async def test_remove_enrollment_success(client):
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    mock_enrollment_svc = MagicMock(spec=EnrollmentService)
    mock_enrollment_svc.remove_enrollment = AsyncMock(return_value=None)

    from app import app
    from db.session import get_db

    async def override_get_db():
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = _make_enrollment(batch_id=5)
        mock_db.execute = AsyncMock(return_value=result)
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    with patch("routes.enrollment_route._verify_batch_belongs_to_institute", new=AsyncMock()):
        response = await client.delete(
            "/enrollment/1",
            headers={"Authorization": "Bearer sometoken"},
        )

    assert response.status_code == 204

    app.dependency_overrides.pop(get_db, None)


async def test_remove_enrollment_returns_404_if_not_found(client):
    owner_teacher_id = uuid4()
    _, __, mock_owner_svc, mock_institute_svc = _setup_owner_and_institute(owner_teacher_id)

    mock_enrollment_svc = MagicMock(spec=EnrollmentService)

    from app import app
    from db.session import get_db

    async def override_get_db():
        mock_db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_owner_service] = lambda: mock_owner_svc
    app.dependency_overrides[get_institute_service] = lambda: mock_institute_svc
    app.dependency_overrides[get_enrollment_service] = lambda: mock_enrollment_svc

    response = await client.delete(
        "/enrollment/999",
        headers={"Authorization": "Bearer sometoken"},
    )

    assert response.status_code == 404

    app.dependency_overrides.pop(get_db, None)


async def test_remove_enrollment_requires_auth(client):
    response = await client.delete("/enrollment/1")
    assert response.status_code in (401, 422)
