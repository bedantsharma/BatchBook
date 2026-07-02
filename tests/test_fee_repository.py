"""
Integration tests for FeeRepository.get_records_missing_payment_link_for_month.

Seeds real data in the test DB (sqlite in-memory) so the join across
Enrollment -> Batch -> Institute is actually exercised, not mocked.
"""

import secrets
import string
from datetime import date, time
from decimal import Decimal
from uuid import uuid4

from models.batch_base import BatchSchema, BatchStatus
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeRecordSchema, FeeStatus
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from models.student_base import StudentSchema
from repositories.fee_repository import FeeRepository


def _join_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


async def _seed_institute(db, name="Test Institute"):
    owner = OwnerSchema(
        name="Owner", phone_number=f"9{uuid4().int % 10**9:09d}", teacher_id=uuid4()
    )
    db.add(owner)
    await db.flush()

    institute = InstituteSchema(owner_id=owner.id, name=name, city="Delhi", join_code=_join_code())
    db.add(institute)
    await db.flush()
    return institute


async def _seed_fee_record(db, institute, month, payment_link=None, status=FeeStatus.NOT_PAID):
    batch = BatchSchema(
        institute_id=institute.id,
        name="Maths Batch",
        subject="Maths",
        start_time=time(9, 0),
        end_time=time(10, 0),
        days_of_week=["MON"],
        max_capacity=30,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status=BatchStatus.ACTIVE,
    )
    db.add(batch)
    await db.flush()

    student = StudentSchema(name="Student", institute_id=institute.id)
    db.add(student)
    await db.flush()

    enrollment = EnrollmentSchema(student_id=student.id, batch_id=batch.id, due_day=1, is_active=True)
    db.add(enrollment)
    await db.flush()

    fee_record = FeeRecordSchema(
        enrollment_id=enrollment.id,
        month=month,
        amount_due=Decimal("1500.00"),
        amount_paid=Decimal("0"),
        status=status,
        payment_link=payment_link,
    )
    db.add(fee_record)
    await db.commit()
    return fee_record


async def test_returns_records_missing_payment_link_for_the_month(db_session):
    repo = FeeRepository()
    institute = await _seed_institute(db_session)
    record = await _seed_fee_record(db_session, institute, date(2026, 6, 1))

    rows = await repo.get_records_missing_payment_link_for_month(db_session, date(2026, 6, 1))

    assert len(rows) == 1
    assert rows[0][0].id == record.id
    assert rows[0][1].id == institute.id


async def test_excludes_records_that_already_have_a_payment_link(db_session):
    repo = FeeRepository()
    institute = await _seed_institute(db_session)
    await _seed_fee_record(
        db_session, institute, date(2026, 6, 1), payment_link="https://rzp.io/i/existing"
    )

    rows = await repo.get_records_missing_payment_link_for_month(db_session, date(2026, 6, 1))

    assert rows == []


async def test_excludes_fully_paid_records(db_session):
    repo = FeeRepository()
    institute = await _seed_institute(db_session)
    await _seed_fee_record(db_session, institute, date(2026, 6, 1), status=FeeStatus.FULLY_PAID)

    rows = await repo.get_records_missing_payment_link_for_month(db_session, date(2026, 6, 1))

    assert rows == []


async def test_excludes_records_from_a_different_month(db_session):
    repo = FeeRepository()
    institute = await _seed_institute(db_session)
    await _seed_fee_record(db_session, institute, date(2026, 5, 1))

    rows = await repo.get_records_missing_payment_link_for_month(db_session, date(2026, 6, 1))

    assert rows == []


async def test_institute_id_filter_scopes_to_one_institute(db_session):
    repo = FeeRepository()
    institute_a = await _seed_institute(db_session, name="Institute A")
    institute_b = await _seed_institute(db_session, name="Institute B")
    record_a = await _seed_fee_record(db_session, institute_a, date(2026, 6, 1))
    await _seed_fee_record(db_session, institute_b, date(2026, 6, 1))

    rows = await repo.get_records_missing_payment_link_for_month(
        db_session, date(2026, 6, 1), institute_id=institute_a.id
    )

    assert len(rows) == 1
    assert rows[0][0].id == record_a.id
