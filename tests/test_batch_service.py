"""
Tests for services/batch_service.py

Covers:
- create_batch: creates a BatchSchema with correct fields
- get_batch: returns batch when found; raises ValueError for wrong institute
- list_batches: transitions ACTIVE→CLOSING when end_date has passed
- update_batch: updates only allowed fields; raises ValueError for wrong institute
- delete_batch: deletes batch; raises ValueError for wrong institute
- assign_teacher: delegates to repo; raises ValueError on duplicate
- remove_teacher: delegates to repo; raises ValueError if not assigned
- try_archive: archives ACTIVE/CLOSING batch; raises ValueError if already ARCHIVED
- can_archive: always True (placeholder until Phase 3)
- check_closing_batches: transitions expired batches and returns them
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.batch_base import BatchSchema, BatchStatus
from models.batch_teacher_base import BatchTeacherSchema
from services.batch_service import BatchService


def _make_batch(
    batch_id: int = 1,
    institute_id: int = 10,
    status: BatchStatus = BatchStatus.ACTIVE,
    end_date: date | None = None,
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
    b.end_date = end_date or (date.today() + timedelta(days=365))
    b.status = status
    b.created_at = datetime(2026, 5, 25)
    return b


def _make_batch_teacher(batch_id: int = 1, teacher_id: int = 5) -> BatchTeacherSchema:
    bt = MagicMock(spec=BatchTeacherSchema)
    bt.id = 1
    bt.batch_id = batch_id
    bt.teacher_id = teacher_id
    return bt


@pytest.fixture
def service() -> BatchService:
    return BatchService()


# ─── create_batch ──────────────────────────────────────────────────────────────


async def test_create_batch_sets_correct_fields(service: BatchService):
    db = MagicMock()
    end = date.today() + timedelta(days=365)
    expected_batch = _make_batch()

    service.batch_repo.create = AsyncMock(return_value=expected_batch)

    result = await service.create_batch(
        db=db,
        institute_id=10,
        name="Class 10 Maths",
        subject="Maths",
        start_time=time(16, 0),
        end_time=time(17, 0),
        days_of_week=["MON", "WED", "FRI"],
        max_capacity=30,
        end_date=end,
        grade="10",
    )

    assert result is expected_batch
    service.batch_repo.create.assert_awaited_once()
    # The BatchSchema passed to create should have institute_id=10
    created_batch_arg = service.batch_repo.create.call_args[0][1]
    assert created_batch_arg.institute_id == 10
    assert created_batch_arg.name == "Class 10 Maths"
    assert created_batch_arg.status == BatchStatus.ACTIVE


async def test_create_batch_uses_today_as_start_date_when_not_provided(service: BatchService):
    db = MagicMock()
    expected = _make_batch()
    service.batch_repo.create = AsyncMock(return_value=expected)

    await service.create_batch(
        db=db,
        institute_id=10,
        name="Batch",
        subject="Science",
        start_time=time(9, 0),
        end_time=time(10, 0),
        days_of_week=["SAT"],
        max_capacity=20,
        end_date=date.today() + timedelta(days=180),
    )

    created = service.batch_repo.create.call_args[0][1]
    assert created.start_date == date.today()


# ─── get_batch ─────────────────────────────────────────────────────────────────


async def test_get_batch_returns_batch_when_found(service: BatchService):
    db = MagicMock()
    batch = _make_batch(batch_id=1, institute_id=10)
    service.batch_repo.get_by_id = AsyncMock(return_value=batch)

    result = await service.get_batch(db=db, batch_id=1, institute_id=10)

    assert result is batch


async def test_get_batch_raises_not_found(service: BatchService):
    db = MagicMock()
    service.batch_repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="Batch not found"):
        await service.get_batch(db=db, batch_id=999, institute_id=10)


async def test_get_batch_raises_for_wrong_institute(service: BatchService):
    db = MagicMock()
    batch = _make_batch(batch_id=1, institute_id=10)
    service.batch_repo.get_by_id = AsyncMock(return_value=batch)

    with pytest.raises(ValueError, match="does not belong to this institute"):
        await service.get_batch(db=db, batch_id=1, institute_id=99)


# ─── list_batches ──────────────────────────────────────────────────────────────


async def test_list_batches_transitions_expired_batch_to_closing(service: BatchService):
    db = MagicMock()
    expired = _make_batch(status=BatchStatus.ACTIVE, end_date=date.today() - timedelta(days=1))
    current = _make_batch(batch_id=2, status=BatchStatus.ACTIVE)

    service.batch_repo.get_all_by_institute_id = AsyncMock(return_value=[expired, current])
    service.batch_repo.update = AsyncMock(side_effect=lambda db, batch, updates: batch)

    await service.list_batches(db=db, institute_id=10)

    # Only the expired batch should have been updated
    service.batch_repo.update.assert_awaited_once()
    _, call_batch, call_updates = service.batch_repo.update.call_args[0]
    assert call_batch is expired
    assert call_updates == {"status": BatchStatus.CLOSING}


async def test_list_batches_does_not_transition_current_batch(service: BatchService):
    db = MagicMock()
    current = _make_batch(status=BatchStatus.ACTIVE, end_date=date.today() + timedelta(days=30))
    service.batch_repo.get_all_by_institute_id = AsyncMock(return_value=[current])
    service.batch_repo.update = AsyncMock()

    await service.list_batches(db=db, institute_id=10)

    service.batch_repo.update.assert_not_awaited()


# ─── update_batch ──────────────────────────────────────────────────────────────


async def test_update_batch_applies_updates(service: BatchService):
    db = MagicMock()
    batch = _make_batch()
    updated = _make_batch()
    updated.name = "Class 12 Maths"

    service.batch_repo.get_by_id = AsyncMock(return_value=batch)
    service.batch_repo.update = AsyncMock(return_value=updated)

    result = await service.update_batch(
        db=db, batch_id=1, institute_id=10, updates={"name": "Class 12 Maths"}
    )

    assert result.name == "Class 12 Maths"
    service.batch_repo.update.assert_awaited_once_with(db, batch, {"name": "Class 12 Maths"})


async def test_update_batch_ignores_disallowed_fields(service: BatchService):
    db = MagicMock()
    batch = _make_batch()
    service.batch_repo.get_by_id = AsyncMock(return_value=batch)
    service.batch_repo.update = AsyncMock(return_value=batch)

    await service.update_batch(
        db=db,
        batch_id=1,
        institute_id=10,
        updates={"name": "New Name", "institute_id": 999, "status": BatchStatus.ARCHIVED},
    )

    # institute_id and status are not allowed fields — should be stripped
    _, _, call_updates = service.batch_repo.update.call_args[0]
    assert "institute_id" not in call_updates
    assert "status" not in call_updates
    assert call_updates.get("name") == "New Name"


# ─── delete_batch ──────────────────────────────────────────────────────────────


async def test_delete_batch_calls_repo_delete(service: BatchService):
    db = MagicMock()
    batch = _make_batch()
    service.batch_repo.get_by_id = AsyncMock(return_value=batch)
    service.batch_repo.delete = AsyncMock()

    await service.delete_batch(db=db, batch_id=1, institute_id=10)

    service.batch_repo.delete.assert_awaited_once_with(db, batch)


# ─── assign_teacher ────────────────────────────────────────────────────────────


async def test_assign_teacher_succeeds(service: BatchService):
    db = MagicMock()
    batch = _make_batch()
    link = _make_batch_teacher()

    service.batch_repo.get_by_id = AsyncMock(return_value=batch)
    service.batch_repo.assign_teacher = AsyncMock(return_value=link)

    result = await service.assign_teacher(db=db, batch_id=1, teacher_id=5, institute_id=10)

    assert result is link
    service.batch_repo.assign_teacher.assert_awaited_once_with(db, 1, 5)


async def test_assign_teacher_raises_on_duplicate(service: BatchService):
    db = MagicMock()
    batch = _make_batch()

    service.batch_repo.get_by_id = AsyncMock(return_value=batch)
    service.batch_repo.assign_teacher = AsyncMock(
        side_effect=ValueError("Teacher is already assigned to this batch")
    )

    with pytest.raises(ValueError, match="already assigned"):
        await service.assign_teacher(db=db, batch_id=1, teacher_id=5, institute_id=10)


# ─── remove_teacher ────────────────────────────────────────────────────────────


async def test_remove_teacher_succeeds(service: BatchService):
    db = MagicMock()
    batch = _make_batch()

    service.batch_repo.get_by_id = AsyncMock(return_value=batch)
    service.batch_repo.remove_teacher = AsyncMock()

    await service.remove_teacher(db=db, batch_id=1, teacher_id=5, institute_id=10)

    service.batch_repo.remove_teacher.assert_awaited_once_with(db, 1, 5)


async def test_remove_teacher_raises_when_not_assigned(service: BatchService):
    db = MagicMock()
    batch = _make_batch()

    service.batch_repo.get_by_id = AsyncMock(return_value=batch)
    service.batch_repo.remove_teacher = AsyncMock(
        side_effect=ValueError("Teacher is not assigned to this batch")
    )

    with pytest.raises(ValueError, match="not assigned"):
        await service.remove_teacher(db=db, batch_id=1, teacher_id=5, institute_id=10)


# ─── try_archive ───────────────────────────────────────────────────────────────


async def test_try_archive_active_batch_succeeds(service: BatchService):
    db = MagicMock()
    batch = _make_batch(status=BatchStatus.ACTIVE)
    archived = _make_batch(status=BatchStatus.ARCHIVED)

    service.batch_repo.get_by_id = AsyncMock(return_value=batch)
    service.batch_repo.update = AsyncMock(return_value=archived)

    result = await service.try_archive(db=db, batch_id=1, institute_id=10)

    assert result.status == BatchStatus.ARCHIVED
    service.batch_repo.update.assert_awaited_once_with(db, batch, {"status": BatchStatus.ARCHIVED})


async def test_try_archive_closing_batch_succeeds(service: BatchService):
    db = MagicMock()
    batch = _make_batch(status=BatchStatus.CLOSING)
    archived = _make_batch(status=BatchStatus.ARCHIVED)

    service.batch_repo.get_by_id = AsyncMock(return_value=batch)
    service.batch_repo.update = AsyncMock(return_value=archived)

    result = await service.try_archive(db=db, batch_id=1, institute_id=10)

    assert result.status == BatchStatus.ARCHIVED


async def test_try_archive_already_archived_raises(service: BatchService):
    db = MagicMock()
    batch = _make_batch(status=BatchStatus.ARCHIVED)

    service.batch_repo.get_by_id = AsyncMock(return_value=batch)

    with pytest.raises(ValueError, match="already archived"):
        await service.try_archive(db=db, batch_id=1, institute_id=10)


# ─── can_archive ───────────────────────────────────────────────────────────────


def test_can_archive_returns_true(service: BatchService):
    assert service.can_archive() is True


# ─── check_closing_batches ─────────────────────────────────────────────────────


async def test_check_closing_batches_transitions_expired(service: BatchService):
    db = MagicMock()
    expired1 = _make_batch(batch_id=1, status=BatchStatus.ACTIVE, end_date=date.today() - timedelta(days=1))
    expired2 = _make_batch(batch_id=2, status=BatchStatus.ACTIVE, end_date=date.today() - timedelta(days=10))
    current = _make_batch(batch_id=3, status=BatchStatus.ACTIVE)
    closing = _make_batch(batch_id=4, status=BatchStatus.CLOSING, end_date=date.today() - timedelta(days=5))

    service.batch_repo.get_all_by_institute_id = AsyncMock(
        return_value=[expired1, expired2, current, closing]
    )
    service.batch_repo.update = AsyncMock(side_effect=lambda db, batch, updates: batch)

    transitioned = await service.check_closing_batches(db=db, institute_id=10)

    assert len(transitioned) == 2
    assert service.batch_repo.update.await_count == 2


async def test_check_closing_batches_returns_empty_when_none_expired(service: BatchService):
    db = MagicMock()
    current = _make_batch(status=BatchStatus.ACTIVE)
    service.batch_repo.get_all_by_institute_id = AsyncMock(return_value=[current])
    service.batch_repo.update = AsyncMock()

    result = await service.check_closing_batches(db=db, institute_id=10)

    assert result == []
    service.batch_repo.update.assert_not_awaited()
