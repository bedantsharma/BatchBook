"""Integration tests for DemoSeedService — seeds the Play Store reviewer accounts."""

from repositories.institute_repository import InstituteRepository
from repositories.owner_repository import OwnerRepository
from services.batch_service import BatchService
from services.demo_seed_service import (
    OWNER_PHONE,
    DemoSeedService,
)


async def test_seed_creates_owner_institute_and_batches(db_session):
    service = DemoSeedService()

    result = await service.seed(db_session)

    assert result.owner_created is True
    assert result.institute_created is True
    assert sorted(result.batches_created) == ["Class 10 Maths", "Class 12 Physics"]

    owner = await OwnerRepository().get_by_phone(db_session, OWNER_PHONE)
    assert owner is not None
    assert owner.name == "Demo Owner"

    institute = await InstituteRepository().get_by_owner_id(db_session, owner.id)
    assert institute is not None
    assert institute.name == "BatchBook Demo Academy"

    batches = await BatchService().list_batches(db_session, institute.id)
    assert {b.name for b in batches} == {"Class 10 Maths", "Class 12 Physics"}
    for batch in batches:
        assert batch.days_of_week  # schedule set
        assert batch.max_capacity > 0


async def test_seed_is_idempotent_on_second_call(db_session):
    service = DemoSeedService()
    await service.seed(db_session)

    result = await service.seed(db_session)

    assert result.owner_created is False
    assert result.institute_created is False
    assert result.batches_created == []

    owner = await OwnerRepository().get_by_phone(db_session, OWNER_PHONE)
    institute = await InstituteRepository().get_by_owner_id(db_session, owner.id)
    batches = await BatchService().list_batches(db_session, institute.id)
    assert len(batches) == 2  # not 4 — no duplicates
