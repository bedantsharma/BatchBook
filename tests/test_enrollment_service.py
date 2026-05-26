"""
Unit tests for services/enrollment_service.py.

All repository calls are mocked — no DB or network required.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.enrollment_base import EnrollmentSchema
from services.enrollment_service import EnrollmentService


def _make_enrollment(
    enrollment_id=1,
    student_id=10,
    batch_id=20,
    is_active=True,
    due_day=15,
    first_month_amount=None,
):
    e = MagicMock(spec=EnrollmentSchema)
    e.id = enrollment_id
    e.student_id = student_id
    e.batch_id = batch_id
    e.is_active = is_active
    e.due_day = due_day
    e.first_month_amount = first_month_amount
    e.enrolled_at = datetime(2026, 5, 1)
    e.created_at = datetime(2026, 5, 1)
    return e


# ---------------------------------------------------------------------------
# enroll_student
# ---------------------------------------------------------------------------


async def test_enroll_student_creates_enrollment():
    svc = EnrollmentService()
    db = MagicMock()

    created = _make_enrollment()
    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_student_and_batch = AsyncMock(return_value=None)
    svc.enrollment_repo.create = AsyncMock(return_value=created)

    result = await svc.enroll_student(
        db=db, student_id=10, batch_id=20, due_day=15, first_month_amount=None
    )

    svc.enrollment_repo.get_by_student_and_batch.assert_called_once_with(db, 10, 20)
    svc.enrollment_repo.create.assert_called_once()
    assert result == created


async def test_enroll_student_raises_on_duplicate_active_enrollment():
    svc = EnrollmentService()
    db = MagicMock()

    existing = _make_enrollment(is_active=True)
    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_student_and_batch = AsyncMock(return_value=existing)

    with pytest.raises(ValueError, match="already actively enrolled"):
        await svc.enroll_student(db=db, student_id=10, batch_id=20)


async def test_enroll_student_allows_re_enroll_after_inactive():
    """A student who was removed (is_active=False) can be re-enrolled."""
    svc = EnrollmentService()
    db = MagicMock()

    existing_inactive = _make_enrollment(is_active=False)
    new_enrollment = _make_enrollment(is_active=True)

    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_student_and_batch = AsyncMock(return_value=existing_inactive)
    svc.enrollment_repo.create = AsyncMock(return_value=new_enrollment)

    result = await svc.enroll_student(db=db, student_id=10, batch_id=20, due_day=10)

    svc.enrollment_repo.create.assert_called_once()
    assert result == new_enrollment


async def test_enroll_student_defaults_due_day_to_today():
    """When due_day is None, it should default to today's day-of-month (clamped to 28)."""
    svc = EnrollmentService()
    db = MagicMock()

    created = _make_enrollment()
    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_student_and_batch = AsyncMock(return_value=None)
    svc.enrollment_repo.create = AsyncMock(return_value=created)

    # Patch datetime.now() to return a known date (e.g. the 17th)
    with patch("services.enrollment_service.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 5, 17, 12, 0, 0)

        await svc.enroll_student(db=db, student_id=10, batch_id=20, due_day=None)

    # The EnrollmentSchema should have been created with due_day=17
    call_args = svc.enrollment_repo.create.call_args
    enrollment_obj = call_args[0][1]  # second positional arg is the EnrollmentSchema
    assert enrollment_obj.due_day == 17


async def test_enroll_student_clamps_due_day_for_late_month_join():
    """A student joining on day 29+ should have due_day clamped to 28."""
    svc = EnrollmentService()
    db = MagicMock()

    created = _make_enrollment()
    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_student_and_batch = AsyncMock(return_value=None)
    svc.enrollment_repo.create = AsyncMock(return_value=created)

    with patch("services.enrollment_service.datetime") as mock_dt:
        mock_dt.now.return_value = datetime(2026, 1, 31, 12, 0, 0)

        await svc.enroll_student(db=db, student_id=10, batch_id=20, due_day=None)

    call_args = svc.enrollment_repo.create.call_args
    enrollment_obj = call_args[0][1]
    assert enrollment_obj.due_day == 28


async def test_enroll_student_raises_on_invalid_due_day():
    svc = EnrollmentService()
    db = MagicMock()

    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_student_and_batch = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="due_day must be between 1 and 28"):
        await svc.enroll_student(db=db, student_id=10, batch_id=20, due_day=29)


async def test_enroll_student_stores_first_month_amount():
    svc = EnrollmentService()
    db = MagicMock()

    created = _make_enrollment(first_month_amount=Decimal("750.00"))
    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_student_and_batch = AsyncMock(return_value=None)
    svc.enrollment_repo.create = AsyncMock(return_value=created)

    result = await svc.enroll_student(
        db=db,
        student_id=10,
        batch_id=20,
        due_day=5,
        first_month_amount=Decimal("750.00"),
    )

    call_args = svc.enrollment_repo.create.call_args
    enrollment_obj = call_args[0][1]
    assert enrollment_obj.first_month_amount == Decimal("750.00")


# ---------------------------------------------------------------------------
# get_enrollments_by_batch
# ---------------------------------------------------------------------------


async def test_get_enrollments_by_batch_returns_all():
    svc = EnrollmentService()
    db = MagicMock()

    e1 = _make_enrollment(enrollment_id=1, is_active=True)
    e2 = _make_enrollment(enrollment_id=2, is_active=False)

    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_batch_id = AsyncMock(return_value=[e1, e2])

    result = await svc.get_enrollments_by_batch(db=db, batch_id=20)

    assert len(result) == 2
    svc.enrollment_repo.get_by_batch_id.assert_called_once_with(db, 20)


async def test_get_active_enrollments_by_batch_filters_inactive():
    svc = EnrollmentService()
    db = MagicMock()

    active = _make_enrollment(enrollment_id=1, is_active=True)

    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_active_by_batch_id = AsyncMock(return_value=[active])

    result = await svc.get_active_enrollments_by_batch(db=db, batch_id=20)

    assert len(result) == 1
    assert result[0].is_active is True


# ---------------------------------------------------------------------------
# update_enrollment
# ---------------------------------------------------------------------------


async def test_update_enrollment_updates_due_day():
    svc = EnrollmentService()
    db = MagicMock()

    enrollment = _make_enrollment(due_day=5)
    updated = _make_enrollment(due_day=10)

    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_id = AsyncMock(return_value=enrollment)
    svc.enrollment_repo.update = AsyncMock(return_value=updated)

    result = await svc.update_enrollment(db=db, enrollment_id=1, due_day=10)

    svc.enrollment_repo.update.assert_called_once_with(db, enrollment, {"due_day": 10})
    assert result == updated


async def test_update_enrollment_updates_first_month_amount():
    svc = EnrollmentService()
    db = MagicMock()

    enrollment = _make_enrollment()
    updated = _make_enrollment(first_month_amount=Decimal("500.00"))

    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_id = AsyncMock(return_value=enrollment)
    svc.enrollment_repo.update = AsyncMock(return_value=updated)

    result = await svc.update_enrollment(
        db=db, enrollment_id=1, first_month_amount=Decimal("500.00")
    )

    svc.enrollment_repo.update.assert_called_once_with(
        db, enrollment, {"first_month_amount": Decimal("500.00")}
    )


async def test_update_enrollment_raises_if_not_found():
    svc = EnrollmentService()
    db = MagicMock()

    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="Enrollment not found"):
        await svc.update_enrollment(db=db, enrollment_id=999, due_day=10)


async def test_update_enrollment_raises_on_invalid_due_day():
    svc = EnrollmentService()
    db = MagicMock()

    enrollment = _make_enrollment()
    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_id = AsyncMock(return_value=enrollment)

    with pytest.raises(ValueError, match="due_day must be between 1 and 28"):
        await svc.update_enrollment(db=db, enrollment_id=1, due_day=0)


async def test_update_enrollment_returns_unchanged_if_no_fields():
    """If neither due_day nor first_month_amount is provided, return the enrollment unchanged."""
    svc = EnrollmentService()
    db = MagicMock()

    enrollment = _make_enrollment()
    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_id = AsyncMock(return_value=enrollment)

    result = await svc.update_enrollment(
        db=db, enrollment_id=1, due_day=None, first_month_amount=None
    )

    # update should NOT be called when there's nothing to change
    svc.enrollment_repo.update.assert_not_called()
    assert result == enrollment


# ---------------------------------------------------------------------------
# remove_enrollment
# ---------------------------------------------------------------------------


async def test_remove_enrollment_deactivates_enrollment():
    svc = EnrollmentService()
    db = MagicMock()

    enrollment = _make_enrollment(is_active=True)
    deactivated = _make_enrollment(is_active=False)

    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_id = AsyncMock(return_value=enrollment)
    svc.enrollment_repo.deactivate = AsyncMock(return_value=deactivated)

    await svc.remove_enrollment(db=db, enrollment_id=1)

    svc.enrollment_repo.deactivate.assert_called_once_with(db, enrollment)


async def test_remove_enrollment_raises_if_not_found():
    svc = EnrollmentService()
    db = MagicMock()

    svc.enrollment_repo = MagicMock()
    svc.enrollment_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="Enrollment not found"):
        await svc.remove_enrollment(db=db, enrollment_id=999)
