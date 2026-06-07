"""
Tests for routes/owner_route.py — all endpoints.

Symbols under test:
  Function:routes/owner_route.py:send_otp
  Function:routes/owner_route.py:verify_otp
  Function:routes/owner_route.py:get_owner
  Function:routes/owner_route.py:update_owner
  Function:routes/owner_route.py:get_owner_stats

Supabase and OwnerService are mocked so no real network calls are made.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from clients.supabase_client import get_supabase_client
from models.attendance_base import AttendanceSchema, AttendanceStatus
from models.batch_base import BatchSchema
from models.class_session_base import ClassSessionSchema
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from services.institute_service import InstituteService, get_institute_service
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
    mock_service.verify_otp = AsyncMock(return_value=("tok_abc_1234567890", "ref_xyz_1234567890", "authenticated", teacher_id))

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
    assert body["refresh_token"] == "ref_xyz_1234567890"
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


# --- GET /owner/stats ---


def _setup_stats_mocks(client, teacher_id, owner_id=1, institute_id=10):
    """Wire OwnerService + InstituteService mocks for the stats endpoint."""
    from app import app

    owner = MagicMock(spec=OwnerSchema)
    owner.id = owner_id
    owner.teacher_id = teacher_id

    institute = MagicMock(spec=InstituteSchema)
    institute.id = institute_id
    institute.owner_id = owner_id

    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(return_value=teacher_id)
    owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    inst_svc = MagicMock(spec=InstituteService)
    inst_svc.get_institute_by_owner_id = AsyncMock(return_value=institute)

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: inst_svc
    return owner, institute


async def test_get_owner_stats_empty_institute(client, db_session):
    """Stats endpoint returns zeros when institute has no batches/enrollments/fees."""
    teacher_id = uuid4()
    _setup_stats_mocks(client, teacher_id, institute_id=99)

    response = await client.get("/owner/stats", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["enrolled_students"] == 0
    assert float(body["fees_collected_this_month"]) == 0.0
    assert body["avg_attendance_this_month"] == 0.0


async def test_get_owner_stats_with_enrollments_and_fees(client, db_session):
    """Stats endpoint counts active enrollments and sums fees paid this month."""
    institute_id = 20
    teacher_id = uuid4()
    _setup_stats_mocks(client, teacher_id, institute_id=institute_id)

    today = date.today()
    month_start = date(today.year, today.month, 1)

    import datetime as _dt
    # Seed a batch
    batch = BatchSchema(id=200, institute_id=institute_id, name="Class 10 Maths",
                        subject="Maths", status="ACTIVE", start_date=month_start,
                        end_date=date(today.year + 1, 1, 1),
                        start_time=_dt.time(16, 0), end_time=_dt.time(18, 0),
                        days_of_week=["MON", "WED"], max_capacity=30)
    db_session.add(batch)
    await db_session.flush()

    # Seed two active enrollments
    for student_id in [101, 102]:
        e = EnrollmentSchema(student_id=student_id, batch_id=batch.id, due_day=5, is_active=True)
        db_session.add(e)
    await db_session.flush()

    # Fetch enrollment IDs
    from sqlalchemy import select
    rows = await db_session.execute(select(EnrollmentSchema).where(EnrollmentSchema.batch_id == batch.id))
    enrollments = rows.scalars().all()

    # Seed fee records for this month — first paid, second not paid
    fee1 = FeeRecordSchema(
        enrollment_id=enrollments[0].id, month=month_start,
        amount_due=Decimal("1500"), amount_paid=Decimal("1500"),
        status=FeeStatus.FULLY_PAID,
    )
    fee2 = FeeRecordSchema(
        enrollment_id=enrollments[1].id, month=month_start,
        amount_due=Decimal("1500"), amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
    )
    db_session.add(fee1)
    db_session.add(fee2)
    await db_session.commit()

    response = await client.get("/owner/stats", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["enrolled_students"] == 2
    assert float(body["fees_collected_this_month"]) == 1500.0
    assert body["avg_attendance_this_month"] == 0.0  # no sessions seeded


async def test_get_owner_stats_with_attendance(client, db_session):
    """Avg attendance reflects PRESENT / total ratio for sessions this month."""
    institute_id = 30
    teacher_id = uuid4()
    _setup_stats_mocks(client, teacher_id, institute_id=institute_id)

    today = date.today()

    import datetime as _dt
    # Seed batch + enrollment
    batch = BatchSchema(id=300, institute_id=institute_id, name="Physics",
                        subject="Physics", status="ACTIVE",
                        start_date=date(today.year, today.month, 1),
                        end_date=date(today.year + 1, 1, 1),
                        start_time=_dt.time(16, 0), end_time=_dt.time(18, 0),
                        days_of_week=["TUE", "THU"], max_capacity=25)
    db_session.add(batch)
    await db_session.flush()

    enrollment = EnrollmentSchema(student_id=201, batch_id=batch.id, due_day=1, is_active=True)
    db_session.add(enrollment)
    await db_session.flush()

    # Seed a session today
    session = ClassSessionSchema(
        batch_id=batch.id, date=today,
        start_time=__import__("datetime").time(16, 0),
        end_time=__import__("datetime").time(18, 0),
    )
    db_session.add(session)
    await db_session.flush()

    # Mark the student PRESENT
    att = AttendanceSchema(session_id=session.id, enrollment_id=enrollment.id,
                           status=AttendanceStatus.PRESENT)
    db_session.add(att)
    await db_session.commit()

    response = await client.get("/owner/stats", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 200
    body = response.json()
    assert body["avg_attendance_this_month"] == 100.0


async def test_get_owner_stats_returns_404_when_no_institute(client):
    """Stats endpoint returns 404 when the owner has no institute."""
    teacher_id = uuid4()
    owner = MagicMock(spec=OwnerSchema)
    owner.id = 1
    owner.teacher_id = teacher_id

    from app import app

    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(return_value=teacher_id)
    owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    inst_svc = MagicMock(spec=InstituteService)
    inst_svc.get_institute_by_owner_id = AsyncMock(return_value=None)

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: inst_svc

    response = await client.get("/owner/stats", headers={"Authorization": "Bearer tok"})

    assert response.status_code == 404


async def test_get_owner_stats_returns_401_without_auth(client):
    """Stats endpoint requires Bearer token."""
    teacher_id = uuid4()

    from app import app

    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(side_effect=Exception("bad token"))

    app.dependency_overrides[get_owner_service] = lambda: owner_svc

    response = await client.get("/owner/stats", headers={"Authorization": "Bearer bad"})

    assert response.status_code == 401
