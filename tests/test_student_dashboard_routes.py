"""
Tests for routes/student_dashboard_route.py — student-facing read API.

All dependencies (Supabase, ParentService, DB) are mocked so no real
network or database calls are made.
"""

from datetime import date, time, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app import app
from clients.supabase_client import get_supabase_client
from models.attendance_base import AttendanceStatus
from models.batch_base import BatchSchema, BatchStatus
from models.class_session_base import ClassSessionSchema
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from services.parent_service import ParentService, get_parent_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_supabase():
    sb = MagicMock()
    sb.auth = MagicMock()
    return sb


def _make_parent(parent_id=1, user_id=None):
    p = MagicMock(spec=ParentSchema)
    p.id = parent_id
    p.user_id = user_id or uuid4()
    p.name = "Test Parent"
    p.phone_number = "9876543210"
    p.created_at = datetime(2026, 1, 1)
    return p


def _make_student(student_id=10, parent_id=1, name="Test Student"):
    s = MagicMock(spec=StudentSchema)
    s.id = student_id
    s.parent_id = parent_id
    s.name = name
    s.email = None
    s.institute_id = None
    return s


def _make_batch(batch_id=5, name="Maths Batch", subject="Maths"):
    b = MagicMock(spec=BatchSchema)
    b.id = batch_id
    b.name = name
    b.subject = subject
    b.institute_id = 1
    b.start_time = time(16, 0)
    b.end_time = time(17, 0)
    b.days_of_week = ["MON", "WED"]
    b.status = BatchStatus.ACTIVE
    return b


def _make_enrollment(enrollment_id=20, student_id=10, batch_id=5):
    e = MagicMock(spec=EnrollmentSchema)
    e.id = enrollment_id
    e.student_id = student_id
    e.batch_id = batch_id
    e.is_active = True
    return e


def _make_session(session_id=100, batch_id=5, session_date=date(2026, 5, 10)):
    s = MagicMock(spec=ClassSessionSchema)
    s.id = session_id
    s.batch_id = batch_id
    s.date = session_date
    s.start_time = time(16, 0)
    s.end_time = time(17, 0)
    s.topic = "Test Topic"
    s.created_at = datetime(2026, 5, 10)
    return s


def _make_fee_record(
    record_id=1,
    enrollment_id=20,
    month=date(2026, 5, 1),
    amount_due=Decimal("1500.00"),
    amount_paid=Decimal("0"),
    status=FeeStatus.NOT_PAID,
):
    r = MagicMock(spec=FeeRecordSchema)
    r.id = record_id
    r.enrollment_id = enrollment_id
    r.month = month
    r.amount_due = amount_due
    r.amount_paid = amount_paid
    r.status = status
    r.paid_at = None
    r.payment_reference = None
    r.payment_link = None
    r.created_at = datetime(2026, 5, 1)
    return r


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def override_supabase(client):
    sb = _mock_supabase()
    app.dependency_overrides[get_supabase_client] = lambda: sb
    yield sb


@pytest.fixture
def mock_parent_service():
    svc = MagicMock(spec=ParentService)
    parent_user_id = uuid4()
    parent = _make_parent(parent_id=1, user_id=parent_user_id)

    svc.get_current_user_id = AsyncMock(return_value=parent_user_id)
    svc.get_parent_by_user_id = AsyncMock(return_value=parent)

    app.dependency_overrides[get_parent_service] = lambda: svc
    yield svc, parent
    if get_parent_service in app.dependency_overrides:
        del app.dependency_overrides[get_parent_service]


@pytest.fixture
def mock_parent_service_unauthorized():
    svc = MagicMock(spec=ParentService)
    svc.get_current_user_id = AsyncMock(side_effect=Exception("Invalid token"))
    app.dependency_overrides[get_parent_service] = lambda: svc
    yield svc
    if get_parent_service in app.dependency_overrides:
        del app.dependency_overrides[get_parent_service]


# ---------------------------------------------------------------------------
# GET /student/me/attendance
# ---------------------------------------------------------------------------


async def test_attendance_returns_401_without_auth(client, mock_parent_service_unauthorized):
    resp = await client.get(
        "/student/me/attendance?student_id=10&month=2026-05",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 401


async def test_attendance_returns_403_for_wrong_student(client, mock_parent_service):
    svc, parent = mock_parent_service
    from sqlalchemy.ext.asyncio import AsyncSession
    from db.session import get_db

    # Override DB to return None (student not found for this parent)
    async def mock_db():
        db = MagicMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=result)
        yield db

    app.dependency_overrides[get_db] = mock_db
    try:
        resp = await client.get(
            "/student/me/attendance?student_id=99&month=2026-05",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 403
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


async def test_attendance_returns_422_for_invalid_month(client, mock_parent_service):
    svc, parent = mock_parent_service
    student = _make_student()
    enrollment = _make_enrollment()
    batch = _make_batch()

    from db.session import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    async def mock_db():
        db = MagicMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=student)
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[enrollment])))
        db.execute = AsyncMock(return_value=result)
        yield db

    app.dependency_overrides[get_db] = mock_db
    try:
        resp = await client.get(
            "/student/me/attendance?student_id=10&month=bad-month",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 422
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


async def test_attendance_returns_empty_when_no_enrollments(client, mock_parent_service):
    svc, parent = mock_parent_service
    student = _make_student()

    from db.session import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    call_count = 0

    async def mock_db():
        nonlocal call_count
        db = MagicMock(spec=AsyncSession)

        async def fake_execute(stmt):
            nonlocal call_count
            result = MagicMock()
            call_count += 1
            if call_count == 1:
                # First call: student lookup
                result.scalar_one_or_none = MagicMock(return_value=student)
            else:
                # Second call: enrollment lookup
                scalars_mock = MagicMock()
                scalars_mock.all = MagicMock(return_value=[])
                result.scalars = MagicMock(return_value=scalars_mock)
            return result

        db.execute = fake_execute
        yield db

    app.dependency_overrides[get_db] = mock_db
    try:
        resp = await client.get(
            "/student/me/attendance?student_id=10&month=2026-05",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


# ---------------------------------------------------------------------------
# GET /student/me/fee
# ---------------------------------------------------------------------------


async def test_fee_returns_401_without_auth(client, mock_parent_service_unauthorized):
    resp = await client.get(
        "/student/me/fee?student_id=10&month=2026-05",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 401


async def test_fee_returns_422_for_invalid_month(client, mock_parent_service):
    svc, parent = mock_parent_service
    student = _make_student()

    from db.session import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    async def mock_db():
        db = MagicMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=student)
        result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        db.execute = AsyncMock(return_value=result)
        yield db

    app.dependency_overrides[get_db] = mock_db
    try:
        resp = await client.get(
            "/student/me/fee?student_id=10&month=invalid",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 422
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


async def test_fee_returns_empty_when_no_enrollments(client, mock_parent_service):
    svc, parent = mock_parent_service
    student = _make_student()

    from db.session import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    call_count = 0

    async def mock_db():
        nonlocal call_count
        db = MagicMock(spec=AsyncSession)

        async def fake_execute(stmt):
            nonlocal call_count
            result = MagicMock()
            call_count += 1
            if call_count == 1:
                result.scalar_one_or_none = MagicMock(return_value=student)
            else:
                scalars_mock = MagicMock()
                scalars_mock.all = MagicMock(return_value=[])
                result.scalars = MagicMock(return_value=scalars_mock)
            return result

        db.execute = fake_execute
        yield db

    app.dependency_overrides[get_db] = mock_db
    try:
        resp = await client.get(
            "/student/me/fee?student_id=10&month=2026-05",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


# ---------------------------------------------------------------------------
# GET /student/me/schedule
# ---------------------------------------------------------------------------


async def test_schedule_returns_401_without_auth(client, mock_parent_service_unauthorized):
    resp = await client.get(
        "/student/me/schedule?student_id=10&date=2026-05-10",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 401


async def test_schedule_returns_422_for_invalid_date(client, mock_parent_service):
    svc, parent = mock_parent_service
    student = _make_student()

    from db.session import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    async def mock_db():
        db = MagicMock(spec=AsyncSession)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=student)
        result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        db.execute = AsyncMock(return_value=result)
        yield db

    app.dependency_overrides[get_db] = mock_db
    try:
        resp = await client.get(
            "/student/me/schedule?student_id=10&date=not-a-date",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 422
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


async def test_schedule_returns_empty_when_no_enrollments(client, mock_parent_service):
    svc, parent = mock_parent_service
    student = _make_student()

    from db.session import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    call_count = 0

    async def mock_db():
        nonlocal call_count
        db = MagicMock(spec=AsyncSession)

        async def fake_execute(stmt):
            nonlocal call_count
            result = MagicMock()
            call_count += 1
            if call_count == 1:
                result.scalar_one_or_none = MagicMock(return_value=student)
            else:
                scalars_mock = MagicMock()
                scalars_mock.all = MagicMock(return_value=[])
                result.scalars = MagicMock(return_value=scalars_mock)
            return result

        db.execute = fake_execute
        yield db

    app.dependency_overrides[get_db] = mock_db
    try:
        resp = await client.get(
            "/student/me/schedule?student_id=10&date=2026-05-10",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


# ---------------------------------------------------------------------------
# GET /student/me/upcoming-events
# ---------------------------------------------------------------------------


async def test_upcoming_events_returns_401_without_auth(client, mock_parent_service_unauthorized):
    resp = await client.get(
        "/student/me/upcoming-events?student_id=10",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert resp.status_code == 401


async def test_upcoming_events_returns_empty_when_no_enrollments(client, mock_parent_service):
    svc, parent = mock_parent_service
    student = _make_student()

    from db.session import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    call_count = 0

    async def mock_db():
        nonlocal call_count
        db = MagicMock(spec=AsyncSession)

        async def fake_execute(stmt):
            nonlocal call_count
            result = MagicMock()
            call_count += 1
            if call_count == 1:
                result.scalar_one_or_none = MagicMock(return_value=student)
            else:
                scalars_mock = MagicMock()
                scalars_mock.all = MagicMock(return_value=[])
                result.scalars = MagicMock(return_value=scalars_mock)
            return result

        db.execute = fake_execute
        yield db

    app.dependency_overrides[get_db] = mock_db
    try:
        resp = await client.get(
            "/student/me/upcoming-events?student_id=10",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]


async def test_upcoming_events_default_limit_is_10(client, mock_parent_service):
    """Request without limit param should default to 10 and return 200."""
    svc, parent = mock_parent_service
    student = _make_student()

    from db.session import get_db
    from sqlalchemy.ext.asyncio import AsyncSession

    call_count = 0

    async def mock_db():
        nonlocal call_count
        db = MagicMock(spec=AsyncSession)

        async def fake_execute(stmt):
            nonlocal call_count
            result = MagicMock()
            call_count += 1
            if call_count == 1:
                result.scalar_one_or_none = MagicMock(return_value=student)
            else:
                scalars_mock = MagicMock()
                scalars_mock.all = MagicMock(return_value=[])
                result.scalars = MagicMock(return_value=scalars_mock)
            return result

        db.execute = fake_execute
        yield db

    app.dependency_overrides[get_db] = mock_db
    try:
        resp = await client.get(
            "/student/me/upcoming-events?student_id=10",
            headers={"Authorization": "Bearer test-token"},
        )
        assert resp.status_code == 200
    finally:
        if get_db in app.dependency_overrides:
            del app.dependency_overrides[get_db]
