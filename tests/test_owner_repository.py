"""
Tests for repositories/owner_repository.py — OwnerRepository.

Symbols under test (from GitNexus):
  Class:repositories/owner_repository.py:OwnerRepository
    create_owner, get_by_teacher_id, get_by_phone, update_owner
"""

from uuid import uuid4

import pytest

from models.owner_base import OwnerSchema
from repositories.owner_repository import OwnerRepository


@pytest.fixture
def repo():
    return OwnerRepository()


def _make_owner(**kwargs):
    defaults = dict(
        teacher_id=uuid4(),
        phone_number="9876543210",
        name="Test Owner",
        email="test@example.com",
        institute_name=None,
        city=None,
    )
    defaults.update(kwargs)
    return OwnerSchema(**defaults)


async def test_create_owner_persists_record(db_session, repo):
    owner = _make_owner()
    created = await repo.create_owner(db_session, owner)

    assert created.id is not None
    assert created.phone_number == "9876543210"
    assert created.name == "Test Owner"


async def test_get_by_teacher_id_returns_owner(db_session, repo):
    teacher_id = uuid4()
    owner = _make_owner(teacher_id=teacher_id)
    await repo.create_owner(db_session, owner)

    found = await repo.get_by_teacher_id(db_session, teacher_id)

    assert found is not None
    assert found.teacher_id == teacher_id


async def test_get_by_teacher_id_returns_none_for_unknown(db_session, repo):
    result = await repo.get_by_teacher_id(db_session, uuid4())
    assert result is None


async def test_get_by_phone_returns_owner(db_session, repo):
    phone = "9123456789"
    owner = _make_owner(phone_number=phone)
    await repo.create_owner(db_session, owner)

    found = await repo.get_by_phone(db_session, phone)

    assert found is not None
    assert found.phone_number == phone


async def test_get_by_phone_returns_none_for_unknown(db_session, repo):
    result = await repo.get_by_phone(db_session, "0000000000")
    assert result is None


async def test_update_owner_modifies_fields(db_session, repo):
    owner = _make_owner()
    created = await repo.create_owner(db_session, owner)

    updated = await repo.update_owner(
        db_session, created, {"institute_name": "Sharma Classes", "city": "Delhi"}
    )

    assert updated.institute_name == "Sharma Classes"
    assert updated.city == "Delhi"
    assert updated.name == "Test Owner"


async def test_update_owner_only_changes_given_fields(db_session, repo):
    owner = _make_owner(name="Original Name", city="Mumbai")
    created = await repo.create_owner(db_session, owner)

    await repo.update_owner(db_session, created, {"city": "Delhi"})

    assert created.name == "Original Name"
    assert created.city == "Delhi"
