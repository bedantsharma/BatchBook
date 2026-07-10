"""Integration tests for DemoSeedService — seeds the Play Store reviewer accounts."""

from datetime import date, timedelta

from models.fee_record_base import FeeStatus
from repositories.institute_repository import InstituteRepository
from repositories.owner_repository import OwnerRepository
from repositories.parent_repository import ParentRepository
from services.batch_service import BatchService
from services.demo_seed_service import (
    OWNER_PHONE,
    STUDENT_PARENT_PHONE,
    DemoSeedService,
)
from services.fee_service import FeeService


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


async def test_seed_creates_parent_student_and_full_demo_data(db_session):
    service = DemoSeedService()

    result = await service.seed(db_session)

    assert result.student_created is True
    assert result.sessions_created == 6  # 3 sessions x 2 batches
    assert result.fee_records_created == 4  # 2 months x 2 batches

    parent = await ParentRepository().get_by_phone(db_session, STUDENT_PARENT_PHONE)
    assert parent is not None
    assert parent.name == "Rina Sharma"
    assert parent.institute_id is not None
    assert parent.user_id is None  # owner-invited stub shape, not yet OTP-verified

    children = await ParentRepository().get_students_by_parent_id(db_session, parent.id)
    assert len(children) == 1
    assert children[0].name == "Aarav Sharma"
    assert children[0].institute_id == parent.institute_id

    from repositories.enrollment_repository import EnrollmentRepository
    from services.batch_service import BatchService

    institute_id = parent.institute_id
    batches = await BatchService().list_batches(db_session, institute_id)
    assert len(batches) == 2
    for batch in batches:
        enrollment = await EnrollmentRepository().get_by_student_and_batch(
            db_session, children[0].id, batch.id
        )
        assert enrollment is not None
        assert enrollment.is_active is True

        last_month_record = await FeeService().fee_repo.get_record_by_enrollment_and_month(
            db_session,
            enrollment.id,
            (date.today().replace(day=1) - timedelta(days=1)).replace(day=1),
        )
        assert last_month_record is not None
        assert last_month_record.status == FeeStatus.FULLY_PAID


async def test_seed_is_fully_idempotent_on_second_call(db_session):
    service = DemoSeedService()
    await service.seed(db_session)

    result = await service.seed(db_session)

    assert result.student_created is False
    assert result.sessions_created == 0
    assert result.fee_records_created == 0

    parent = await ParentRepository().get_by_phone(db_session, STUDENT_PARENT_PHONE)
    children = await ParentRepository().get_students_by_parent_id(db_session, parent.id)
    assert len(children) == 1  # not 2 — no duplicate student
