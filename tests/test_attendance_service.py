"""
Tests for services/attendance_service.py — AttendanceService.

Covers the two service methods required by the roadmap:
  - create_session: creates N ABSENT rows (one per active enrollment)
  - bulk_mark: flips given IDs to PRESENT, others stay ABSENT
"""

from datetime import date, time

import pytest

from models.batch_base import BatchSchema, BatchStatus
from models.enrollment_base import EnrollmentSchema
from models.attendance_base import AttendanceStatus
from services.attendance_service import AttendanceService


@pytest.fixture
def service():
    return AttendanceService()


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_batch(db_session, **kwargs):
    defaults = dict(
        institute_id=1,
        name="Test Batch",
        subject="Maths",
        grade="10",
        start_time=time(16, 0),
        end_time=time(17, 0),
        days_of_week=["MON", "WED"],
        max_capacity=30,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        status=BatchStatus.ACTIVE,
    )
    defaults.update(kwargs)
    batch = BatchSchema(**defaults)
    db_session.add(batch)
    return batch


def _make_enrollment(batch_id: int, student_id: int, is_active: bool = True) -> EnrollmentSchema:
    return EnrollmentSchema(
        student_id=student_id,
        batch_id=batch_id,
        due_day=5,
        is_active=is_active,
    )


# ─── create_session tests ─────────────────────────────────────────────────────


async def test_create_session_generates_absent_rows_for_each_active_enrollment(
    db_session, service
):
    """create_session must pre-create one ABSENT row per active enrollment."""
    batch = _make_batch(db_session)
    await db_session.flush()

    # 3 active enrollments
    enrollments = [_make_enrollment(batch.id, student_id=i) for i in range(1, 4)]
    db_session.add_all(enrollments)
    await db_session.flush()

    session = await service.create_session(
        db=db_session,
        batch_id=batch.id,
        session_date=date(2026, 5, 5),
        start_time=time(16, 0),
        end_time=time(17, 0),
    )

    attendance_rows = await service.attendance_repo.get_by_session(db_session, session.id)
    assert len(attendance_rows) == 3
    assert all(row.status == AttendanceStatus.ABSENT for row in attendance_rows)


async def test_create_session_excludes_inactive_enrollments(db_session, service):
    """Inactive enrollments should NOT get an attendance row."""
    batch = _make_batch(db_session)
    await db_session.flush()

    active = _make_enrollment(batch.id, student_id=1, is_active=True)
    inactive = _make_enrollment(batch.id, student_id=2, is_active=False)
    db_session.add_all([active, inactive])
    await db_session.flush()

    session = await service.create_session(
        db=db_session,
        batch_id=batch.id,
        session_date=date(2026, 5, 6),
        start_time=time(16, 0),
        end_time=time(17, 0),
    )

    rows = await service.attendance_repo.get_by_session(db_session, session.id)
    assert len(rows) == 1
    assert rows[0].enrollment_id == active.id


async def test_create_session_raises_on_duplicate_date(db_session, service):
    """A second session for the same batch+date raises ValueError."""
    batch = _make_batch(db_session)
    await db_session.flush()

    session_date = date(2026, 5, 7)
    await service.create_session(
        db=db_session,
        batch_id=batch.id,
        session_date=session_date,
        start_time=time(16, 0),
        end_time=time(17, 0),
    )

    with pytest.raises(ValueError, match="already exists"):
        await service.create_session(
            db=db_session,
            batch_id=batch.id,
            session_date=session_date,
            start_time=time(16, 0),
            end_time=time(17, 0),
        )


# ─── bulk_mark tests ──────────────────────────────────────────────────────────


async def test_bulk_mark_marks_given_ids_present(db_session, service):
    """bulk_mark with IDs [e1, e3] must mark those PRESENT and leave e2 ABSENT."""
    batch = _make_batch(db_session)
    await db_session.flush()

    enrollments = [_make_enrollment(batch.id, student_id=i) for i in range(1, 4)]
    db_session.add_all(enrollments)
    await db_session.flush()

    session = await service.create_session(
        db=db_session,
        batch_id=batch.id,
        session_date=date(2026, 5, 8),
        start_time=time(16, 0),
        end_time=time(17, 0),
    )

    e1, e2, e3 = enrollments
    rows = await service.bulk_mark(
        db=db_session,
        session_id=session.id,
        present_enrollment_ids=[e1.id, e3.id],
    )

    statuses = {row.enrollment_id: row.status for row in rows}
    assert statuses[e1.id] == AttendanceStatus.PRESENT
    assert statuses[e2.id] == AttendanceStatus.ABSENT
    assert statuses[e3.id] == AttendanceStatus.PRESENT


async def test_bulk_mark_all_present(db_session, service):
    """All students present → all rows become PRESENT."""
    batch = _make_batch(db_session)
    await db_session.flush()

    enrollments = [_make_enrollment(batch.id, student_id=i) for i in range(1, 4)]
    db_session.add_all(enrollments)
    await db_session.flush()

    session = await service.create_session(
        db=db_session,
        batch_id=batch.id,
        session_date=date(2026, 5, 9),
        start_time=time(16, 0),
        end_time=time(17, 0),
    )

    all_ids = [e.id for e in enrollments]
    rows = await service.bulk_mark(db=db_session, session_id=session.id, present_enrollment_ids=all_ids)
    assert all(r.status == AttendanceStatus.PRESENT for r in rows)


async def test_bulk_mark_none_present(db_session, service):
    """Empty present list → all rows stay ABSENT."""
    batch = _make_batch(db_session)
    await db_session.flush()

    enrollments = [_make_enrollment(batch.id, student_id=i) for i in range(1, 3)]
    db_session.add_all(enrollments)
    await db_session.flush()

    session = await service.create_session(
        db=db_session,
        batch_id=batch.id,
        session_date=date(2026, 5, 10),
        start_time=time(16, 0),
        end_time=time(17, 0),
    )

    rows = await service.bulk_mark(db=db_session, session_id=session.id, present_enrollment_ids=[])
    assert all(r.status == AttendanceStatus.ABSENT for r in rows)


async def test_bulk_mark_raises_on_invalid_session(db_session, service):
    """bulk_mark for a non-existent session should raise ValueError."""
    with pytest.raises(ValueError, match="not found"):
        await service.bulk_mark(
            db=db_session,
            session_id=99999,
            present_enrollment_ids=[],
        )
