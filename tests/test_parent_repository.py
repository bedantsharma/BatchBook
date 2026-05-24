"""
Tests for repositories/parent_repository.py

Covers:
- create_parent: persists a ParentSchema row
- get_by_user_id: finds by UUID, returns None for unknown
- get_by_phone: finds by phone number, returns None for unknown
- get_students_by_parent_id: returns linked students
- update_parent: modifies fields in-place
"""

from datetime import datetime
from uuid import uuid4

import pytest

from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from DTO.student_model import StudentFeesStatus
from repositories.parent_repository import ParentRepository


def _make_parent(phone: str | None = None, user_id=None) -> ParentSchema:
    return ParentSchema(
        name="Test Parent",
        phone_number=phone or "9876543210",
        user_id=user_id or uuid4(),
        created_at=datetime.now(),
    )


def _make_student(parent_id: int) -> StudentSchema:
    return StudentSchema(
        name="Test Student",
        fees_status=StudentFeesStatus.NOT_PAID,
        parent_id=parent_id,
        created_at=datetime.now(),
    )


@pytest.fixture
def repo():
    return ParentRepository()


async def test_create_parent_persists_record(db_session, repo):
    parent = _make_parent()
    created = await repo.create_parent(db_session, parent)

    assert created.id is not None
    assert created.phone_number == "9876543210"
    assert created.name == "Test Parent"


async def test_get_by_user_id_returns_parent(db_session, repo):
    user_id = uuid4()
    parent = _make_parent(user_id=user_id)
    await repo.create_parent(db_session, parent)

    found = await repo.get_by_user_id(db_session, user_id)
    assert found is not None
    assert found.user_id == user_id


async def test_get_by_user_id_returns_none_for_unknown(db_session, repo):
    result = await repo.get_by_user_id(db_session, uuid4())
    assert result is None


async def test_get_by_phone_returns_parent(db_session, repo):
    parent = _make_parent(phone="9123456789")
    await repo.create_parent(db_session, parent)

    found = await repo.get_by_phone(db_session, "9123456789")
    assert found is not None
    assert found.phone_number == "9123456789"


async def test_get_by_phone_returns_none_for_unknown(db_session, repo):
    result = await repo.get_by_phone(db_session, "9000000000")
    assert result is None


async def test_get_students_by_parent_id_returns_children(db_session, repo):
    parent = _make_parent()
    created_parent = await repo.create_parent(db_session, parent)

    # Add two students linked to this parent
    for name in ["Child One", "Child Two"]:
        student = StudentSchema(
            name=name,
            fees_status=StudentFeesStatus.NOT_PAID,
            parent_id=created_parent.id,
            created_at=datetime.now(),
        )
        db_session.add(student)
    await db_session.commit()

    children = await repo.get_students_by_parent_id(db_session, created_parent.id)
    assert len(children) == 2
    names = {c.name for c in children}
    assert names == {"Child One", "Child Two"}


async def test_get_students_by_parent_id_returns_empty_when_no_children(db_session, repo):
    parent = _make_parent()
    created_parent = await repo.create_parent(db_session, parent)

    children = await repo.get_students_by_parent_id(db_session, created_parent.id)
    assert children == []


async def test_update_parent_modifies_fields(db_session, repo):
    parent = _make_parent()
    created = await repo.create_parent(db_session, parent)

    updated = await repo.update_parent(db_session, created, {"name": "Updated Name"})
    assert updated.name == "Updated Name"
    assert updated.phone_number == created.phone_number


async def test_update_parent_only_changes_given_fields(db_session, repo):
    user_id = uuid4()
    parent = _make_parent(user_id=user_id)
    created = await repo.create_parent(db_session, parent)

    await repo.update_parent(db_session, created, {"name": "New Name"})
    found = await repo.get_by_user_id(db_session, user_id)
    assert found is not None
    assert found.user_id == user_id
    assert found.phone_number == parent.phone_number
