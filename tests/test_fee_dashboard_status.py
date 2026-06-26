"""
Integration test for Task 7: parent verification + last-notification status
in the fee dashboard response.

Seeds real data in the test DB.  Mocks auth and owner/institute look-ups only
to bypass JWT / Supabase round-trips.  FeeService.get_fee_dashboard runs for
real so the new DB join and notification fetch are actually exercised.
"""

import secrets
import string
from datetime import date, time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from clients.supabase_client import get_supabase_client
from models.batch_base import BatchSchema, BatchStatus
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.institute_base import InstituteSchema
from models.notification_base import NotificationSchema, NotificationStatus, NotificationType
from models.owner_base import OwnerSchema
from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from services.institute_service import InstituteService, get_institute_service
from services.owner_service import OwnerService, get_owner_service


def _join_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


async def _seed(db):
    """Seed one unverified parent, student, fee record, and SKIPPED_UNVERIFIED notification."""
    teacher_uid = uuid4()

    owner = OwnerSchema(name="Test Owner", phone_number="9900000001", teacher_id=teacher_uid)
    db.add(owner)
    await db.flush()

    institute = InstituteSchema(
        owner_id=owner.id, name="Test Institute", city="Delhi", join_code=_join_code()
    )
    db.add(institute)
    await db.flush()

    batch = BatchSchema(
        institute_id=institute.id,
        name="Maths Batch",
        subject="Maths",
        start_time=time(9, 0),
        end_time=time(10, 0),
        days_of_week=["MON", "WED"],
        max_capacity=30,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status=BatchStatus.ACTIVE,
    )
    db.add(batch)
    await db.flush()

    # Unverified parent: user_id is None
    parent = ParentSchema(phone_number="9900000002", name="Unverified Parent", user_id=None)
    db.add(parent)
    await db.flush()

    student = StudentSchema(name="Test Student", parent_id=parent.id, institute_id=institute.id)
    db.add(student)
    await db.flush()

    enrollment = EnrollmentSchema(
        student_id=student.id, batch_id=batch.id, due_day=1, is_active=True
    )
    db.add(enrollment)
    await db.flush()

    fee_record = FeeRecordSchema(
        enrollment_id=enrollment.id,
        month=date(2026, 5, 1),
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
    )
    db.add(fee_record)
    await db.flush()

    notification = NotificationSchema(
        parent_id=parent.id,
        student_id=student.id,
        institute_id=institute.id,
        type=NotificationType.FEE_REMINDER,
        status=NotificationStatus.SKIPPED_UNVERIFIED,
        reason="parent number not verified",
    )
    db.add(notification)
    await db.commit()

    return teacher_uid, owner, institute


async def test_fee_dashboard_surfaces_verification_and_last_notification(client, db_session):
    """
    FeeRecordSummary must expose:
      - parent_is_verified: False when parent.user_id IS NULL
      - last_notification_status: "SKIPPED_UNVERIFIED" (latest notification status)
      - last_notification_reason: the reason string from the notification row
    """
    from app import app

    teacher_uid, owner, institute = await _seed(db_session)

    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(return_value=teacher_uid)
    owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    institute_svc = MagicMock(spec=InstituteService)
    institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    sb = MagicMock()
    sb.auth = MagicMock()

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: institute_svc
    app.dependency_overrides[get_supabase_client] = lambda: sb

    try:
        resp = await client.get(
            "/fee/dashboard",
            params={"month": "2026-05"},
            headers={"authorization": "Bearer test-token"},
        )
    finally:
        app.dependency_overrides.pop(get_owner_service, None)
        app.dependency_overrides.pop(get_institute_service, None)
        app.dependency_overrides.pop(get_supabase_client, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["records"]) == 1, "Expected exactly one fee record in dashboard"

    rec = data["records"][0]
    assert rec["parent_is_verified"] is False, "Unverified parent must yield parent_is_verified=False"
    assert rec["last_notification_status"] == "SKIPPED_UNVERIFIED"
    assert rec["last_notification_reason"] == "parent number not verified"


async def test_fee_dashboard_verified_parent_and_no_notification(client, db_session):
    """
    When parent.user_id IS NOT NULL and no notification exists for the student:
      - parent_is_verified: True
      - last_notification_status: null
      - last_notification_reason: null
    """
    from app import app

    # Verified parent
    teacher_uid = uuid4()
    owner = OwnerSchema(name="Owner 2", phone_number="9900000003", teacher_id=teacher_uid)
    db_session.add(owner)
    await db_session.flush()

    institute = InstituteSchema(
        owner_id=owner.id, name="Institute 2", city="Mumbai", join_code=_join_code()
    )
    db_session.add(institute)
    await db_session.flush()

    batch = BatchSchema(
        institute_id=institute.id,
        name="Physics Batch",
        subject="Physics",
        start_time=time(11, 0),
        end_time=time(12, 0),
        days_of_week=["TUE", "THU"],
        max_capacity=20,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status=BatchStatus.ACTIVE,
    )
    db_session.add(batch)
    await db_session.flush()

    parent = ParentSchema(phone_number="9900000004", name="Verified Parent", user_id=uuid4())
    db_session.add(parent)
    await db_session.flush()

    student = StudentSchema(name="Student 2", parent_id=parent.id, institute_id=institute.id)
    db_session.add(student)
    await db_session.flush()

    enrollment = EnrollmentSchema(
        student_id=student.id, batch_id=batch.id, due_day=1, is_active=True
    )
    db_session.add(enrollment)
    await db_session.flush()

    fee_record = FeeRecordSchema(
        enrollment_id=enrollment.id,
        month=date(2026, 5, 1),
        amount_due=Decimal("2000.00"),
        amount_paid=Decimal("0"),
        status=FeeStatus.NOT_PAID,
    )
    db_session.add(fee_record)
    await db_session.commit()

    owner_svc = MagicMock(spec=OwnerService)
    owner_svc.get_current_teacher_id = AsyncMock(return_value=teacher_uid)
    owner_svc.get_owner_by_teacher_id = AsyncMock(return_value=owner)

    institute_svc = MagicMock(spec=InstituteService)
    institute_svc.get_by_owner_id = AsyncMock(return_value=institute)

    sb = MagicMock()
    sb.auth = MagicMock()

    app.dependency_overrides[get_owner_service] = lambda: owner_svc
    app.dependency_overrides[get_institute_service] = lambda: institute_svc
    app.dependency_overrides[get_supabase_client] = lambda: sb

    try:
        resp = await client.get(
            "/fee/dashboard",
            params={"month": "2026-05"},
            headers={"authorization": "Bearer test-token"},
        )
    finally:
        app.dependency_overrides.pop(get_owner_service, None)
        app.dependency_overrides.pop(get_institute_service, None)
        app.dependency_overrides.pop(get_supabase_client, None)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["records"]) == 1

    rec = data["records"][0]
    assert rec["parent_is_verified"] is True
    assert rec["last_notification_status"] is None
    assert rec["last_notification_reason"] is None
