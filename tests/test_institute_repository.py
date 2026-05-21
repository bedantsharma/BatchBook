"""
Tests for repositories/institute_repository.py — InstituteRepository.

Symbols under test:
  Class:repositories/institute_repository.py:InstituteRepository
    create, get_by_owner_id, update
"""

import pytest

from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from repositories.institute_repository import InstituteRepository
from repositories.owner_repository import OwnerRepository
from uuid import uuid4


@pytest.fixture
def repo():
    return InstituteRepository()


@pytest.fixture
def owner_repo():
    return OwnerRepository()


async def _create_owner(db_session, owner_repo: OwnerRepository) -> OwnerSchema:
    """Helper: persist a real Owner row so FK constraints are satisfied."""
    owner = OwnerSchema(
        teacher_id=uuid4(),
        phone_number=f"9{uuid4().int % 10**9:09d}",
        name="Test Owner",
        email=None,
        institute_name=None,
        city=None,
    )
    return await owner_repo.create_owner(db_session, owner)


# --- create ---

async def test_create_institute_persists_record(db_session, repo, owner_repo):
    owner = await _create_owner(db_session, owner_repo)
    institute = InstituteSchema(owner_id=owner.id, name="Sharma Classes", city="Gurugram")

    created = await repo.create(db_session, institute)

    assert created.id is not None
    assert created.owner_id == owner.id
    assert created.name == "Sharma Classes"
    assert created.city == "Gurugram"
    assert created.created_at is not None


async def test_create_institute_sets_all_fields(db_session, repo, owner_repo):
    owner = await _create_owner(db_session, owner_repo)
    institute = InstituteSchema(owner_id=owner.id, name="Mehta Coaching", city="Jaipur")

    created = await repo.create(db_session, institute)

    assert created.name == "Mehta Coaching"
    assert created.city == "Jaipur"


# --- get_by_owner_id ---

async def test_get_by_owner_id_returns_institute(db_session, repo, owner_repo):
    owner = await _create_owner(db_session, owner_repo)
    await repo.create(db_session, InstituteSchema(owner_id=owner.id, name="Test Institute", city="Delhi"))

    found = await repo.get_by_owner_id(db_session, owner.id)

    assert found is not None
    assert found.owner_id == owner.id
    assert found.name == "Test Institute"


async def test_get_by_owner_id_returns_none_when_not_found(db_session, repo):
    result = await repo.get_by_owner_id(db_session, 99999)
    assert result is None


async def test_get_by_owner_id_does_not_return_other_owners_institute(db_session, repo, owner_repo):
    owner_a = await _create_owner(db_session, owner_repo)
    owner_b = await _create_owner(db_session, owner_repo)
    await repo.create(db_session, InstituteSchema(owner_id=owner_a.id, name="A Classes", city="Delhi"))

    result = await repo.get_by_owner_id(db_session, owner_b.id)

    assert result is None


# --- update ---

async def test_update_changes_name_and_city(db_session, repo, owner_repo):
    owner = await _create_owner(db_session, owner_repo)
    institute = await repo.create(
        db_session, InstituteSchema(owner_id=owner.id, name="Old Name", city="Old City")
    )

    updated = await repo.update(db_session, institute, {"name": "New Name", "city": "New City"})

    assert updated.name == "New Name"
    assert updated.city == "New City"


async def test_update_only_changes_specified_fields(db_session, repo, owner_repo):
    owner = await _create_owner(db_session, owner_repo)
    institute = await repo.create(
        db_session, InstituteSchema(owner_id=owner.id, name="Original Name", city="Original City")
    )

    await repo.update(db_session, institute, {"city": "New City"})

    assert institute.name == "Original Name"
    assert institute.city == "New City"
