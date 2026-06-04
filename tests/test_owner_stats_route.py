"""
Tests for GET /owner/stats — the new aggregate stats endpoint.

Strategy:
  - OwnerService and InstituteService are mocked for auth and institute lookup.
  - The real in-memory SQLite DB handles the aggregate queries.
    With an empty DB, all three stats return zero, which is the expected
    "no data yet" state.
  - One additional test seeds the DB with enrollments, fee records, and
    attendance to verify the numeric calculations.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
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

# ─── helpers ──────────────────────────────────────────────────────────────────


def _mock_supabase():
    sb = MagicMock()
    sb.auth = MagicMock()
    return sb


def _make_owner(teacher_id=None):
    o = MagicMock(spec=OwnerSchema)
    o.id = 1
    o.teacher_id = teacher_id or uuid4()
    o.name = "Sharma Sir"
    return o


def _make_institute(owner_id=1):
    i = MagicMock(spec=InstituteSchema)
    i.id = 10
    i.owner_id = owner_id
    i.name = "Sharma Classes"
    i.city = "Gurugram"
    i.created_at = datetime(2026, 1, 1)
    return i


# ─── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def override_supabase(client):
    from app import app
    sb = _mock_supabase()
    app.dependency_overrides[get_supabase_client] = lambda: sb
    yield sb


def _setup_owner_institute(client, teacher_id=None):
    """Return a configured teacher_id and wire up OwnerService + InstituteService mocks."""
    tid = teacher_id or uuid4()
    owner = _make_owner(teacher_id=tid)
    institute = _make_institute()

    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(return_value=tid)
    owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    inst_svc = MagicMock(spec=InstituteService)
    inst_svc.get_institute_by_owner_id = AsyncMock(return_value=institute)

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: inst_svc

    return tid, owner, institute


# ─── tests ────────────────────────────────────────────────────────────────────


async def test_get_owner_stats_returns_zeros_when_no_data(client):
    """Empty DB → all three stats are 0."""
    tid, _, _ = _setup_owner_institute(client)

    response = await client.get(
        "/owner/stats",
        headers={"Authorization": f"Bearer fake-token-{tid}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["students_enrolled"] == 0
    assert Decimal(str(body["fees_collected_this_month"])) == Decimal("0")
    assert body["avg_attendance_pct"] == 0.0


async def test_get_owner_stats_returns_401_with_invalid_token(client):
    """Invalid/expired token → OwnerService raises → 401."""
    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(side_effect=Exception("invalid token"))

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: owner_svc

    response = await client.get(
        "/owner/stats",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401


async def test_get_owner_stats_returns_404_when_owner_not_found(client):
    """Authenticated but no owner record → 404."""
    tid = uuid4()

    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(return_value=tid)
    owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=None)

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: owner_svc

    response = await client.get(
        "/owner/stats",
        headers={"Authorization": f"Bearer fake-token-{tid}"},
    )
    assert response.status_code == 404
    assert "Owner" in response.json()["detail"]


async def test_get_owner_stats_returns_404_when_no_institute(client):
    """Owner exists but no institute yet → 404."""
    tid = uuid4()
    owner = _make_owner(teacher_id=tid)

    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(return_value=tid)
    owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    inst_svc = MagicMock(spec=InstituteService)
    inst_svc.get_institute_by_owner_id = AsyncMock(return_value=None)

    from app import app
    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: inst_svc

    response = await client.get(
        "/owner/stats",
        headers={"Authorization": f"Bearer fake-token-{tid}"},
    )
    assert response.status_code == 404
    assert "institute" in response.json()["detail"].lower()


async def test_get_owner_stats_counts_active_enrollments(client, db_session):
    """Seeded DB with 2 active + 1 inactive enrollment → students_enrolled = 2.

    SQLite does not enforce FK constraints, so we can use stub student_ids.
    """
    tid, owner, institute = _setup_owner_institute(client)

    batch = BatchSchema(
        institute_id=10,
        name="Class 10 Maths",
        subject="Maths",
        days_of_week=["MON", "WED", "FRI"],
        max_capacity=30,
        start_time=datetime(2026, 1, 1, 16, 0).time(),
        end_time=datetime(2026, 1, 1, 17, 30).time(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add(batch)
    await db_session.flush()

    # 2 active + 1 inactive — student_ids are stubs (SQLite won't enforce FK)
    for i in range(3):
        e = EnrollmentSchema(
            student_id=100 + i,
            batch_id=batch.id,
            due_day=5,
            is_active=(i < 2),
        )
        db_session.add(e)

    await db_session.flush()

    response = await client.get(
        "/owner/stats",
        headers={"Authorization": f"Bearer fake-token-{tid}"},
    )

    assert response.status_code == 200
    assert response.json()["students_enrolled"] == 2


async def test_get_owner_stats_sums_fees_this_month(client, db_session):
    """Seeded fee records: 2 paid this month + 1 paid last month → collected = sum of this month."""
    tid, owner, institute = _setup_owner_institute(client)
    today = date.today()
    this_month = date(today.year, today.month, 1)
    prev_year = today.year - (1 if today.month == 1 else 0)
    prev_month_num = (today.month - 2) % 12 + 1
    last_month = date(prev_year, prev_month_num, 1)

    batch = BatchSchema(
        institute_id=10,
        name="Batch A",
        subject="Science",
        days_of_week=["TUE"],
        max_capacity=25,
        start_time=datetime(2026, 1, 1, 14, 0).time(),
        end_time=datetime(2026, 1, 1, 15, 0).time(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add(batch)
    await db_session.flush()

    # 3 enrollments with stub student_ids; 2 fee records this month, 1 last month
    for i, (month, amount) in enumerate(
        [(this_month, Decimal("1200.00")), (this_month, Decimal("800.00")), (last_month, Decimal("500.00"))]
    ):
        e = EnrollmentSchema(student_id=200 + i, batch_id=batch.id, due_day=5, is_active=True)
        db_session.add(e)
        await db_session.flush()
        r = FeeRecordSchema(
            enrollment_id=e.id,
            month=month,
            amount_due=Decimal("1500.00"),
            amount_paid=amount,
            status=FeeStatus.PARTIALLY_PAID,
        )
        db_session.add(r)

    await db_session.flush()

    response = await client.get(
        "/owner/stats",
        headers={"Authorization": f"Bearer fake-token-{tid}"},
    )

    assert response.status_code == 200
    collected = Decimal(str(response.json()["fees_collected_this_month"]))
    assert collected == Decimal("2000.00")


async def test_get_owner_stats_computes_attendance_pct(client, db_session):
    """4 attendance records: 3 PRESENT, 1 ABSENT → avg_attendance_pct = 75.0."""
    tid, owner, institute = _setup_owner_institute(client)
    today = date.today()

    batch = BatchSchema(
        institute_id=10,
        name="Batch Att",
        subject="Maths",
        days_of_week=["MON"],
        max_capacity=20,
        start_time=datetime(2026, 1, 1, 10, 0).time(),
        end_time=datetime(2026, 1, 1, 11, 0).time(),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    db_session.add(batch)
    await db_session.flush()

    session = ClassSessionSchema(
        batch_id=batch.id,
        date=today,
        start_time=datetime(2026, 1, 1, 10, 0).time(),
        end_time=datetime(2026, 1, 1, 11, 0).time(),
    )
    db_session.add(session)
    await db_session.flush()

    statuses = [AttendanceStatus.PRESENT, AttendanceStatus.PRESENT, AttendanceStatus.PRESENT, AttendanceStatus.ABSENT]
    for i, status in enumerate(statuses):
        e = EnrollmentSchema(student_id=300 + i, batch_id=batch.id, due_day=5, is_active=True)
        db_session.add(e)
        await db_session.flush()
        a = AttendanceSchema(session_id=session.id, enrollment_id=e.id, status=status)
        db_session.add(a)

    await db_session.flush()

    response = await client.get(
        "/owner/stats",
        headers={"Authorization": f"Bearer fake-token-{tid}"},
    )

    assert response.status_code == 200
    assert response.json()["avg_attendance_pct"] == 75.0
