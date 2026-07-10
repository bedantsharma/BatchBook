import secrets
import string
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from models.batch_base import BatchSchema
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from repositories.institute_repository import InstituteRepository
from repositories.owner_repository import OwnerRepository
from services.batch_service import BatchService
from services.fee_service import FeeService

OWNER_PHONE = "9999999999"
STUDENT_PARENT_PHONE = "9999999998"

_BATCH_SPECS = [
    {
        "name": "Class 10 Maths",
        "subject": "Maths",
        "grade": "10",
        "start_time": time(16, 0),
        "end_time": time(17, 0),
        "days_of_week": ["MON", "WED", "FRI"],
        "max_capacity": 30,
        "end_date": date(2027, 3, 31),
        "monthly_amount": Decimal("1500.00"),
    },
    {
        "name": "Class 12 Physics",
        "subject": "Physics",
        "grade": "12",
        "start_time": time(17, 30),
        "end_time": time(18, 30),
        "days_of_week": ["TUE", "THU", "SAT"],
        "max_capacity": 25,
        "end_date": date(2027, 3, 31),
        "monthly_amount": Decimal("1800.00"),
    },
]


def _generate_join_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


@dataclass
class DemoSeedResult:
    owner_created: bool
    institute_created: bool
    batches_created: list[str] = field(default_factory=list)


class DemoSeedService:
    """Seeds the two Play Store reviewer accounts with realistic demo data.

    Every method is idempotent — safe to call `seed()` any number of times.
    Mirrors production creation paths (BatchService, FeeService, and in
    demo_seed_service Task 2, EnrollmentService.invite_student) rather than
    inserting rows directly, so the seeded data has the same shape real
    signups produce.
    """

    def __init__(self) -> None:
        self.owner_repo = OwnerRepository()
        self.institute_repo = InstituteRepository()
        self.batch_service = BatchService()
        self.fee_service = FeeService()

    async def _seed_owner(self, db: AsyncSession) -> tuple[OwnerSchema, bool]:
        owner = await self.owner_repo.get_by_phone(db, OWNER_PHONE)
        if owner:
            return owner, False
        owner = OwnerSchema(
            name="Demo Owner",
            phone_number=OWNER_PHONE,
            teacher_id=uuid4(),
            institute_name="BatchBook Demo Academy",
            city="Gurugram",
        )
        owner = await self.owner_repo.create_owner(db, owner)
        return owner, True

    async def _seed_institute(
        self, db: AsyncSession, owner: OwnerSchema
    ) -> tuple[InstituteSchema, bool]:
        institute = await self.institute_repo.get_by_owner_id(db, owner.id)
        if institute:
            return institute, False
        institute = InstituteSchema(
            owner_id=owner.id,
            name="BatchBook Demo Academy",
            city="Gurugram",
            join_code=_generate_join_code(),
        )
        institute = await self.institute_repo.create(db, institute)
        return institute, True

    async def _seed_batches(
        self, db: AsyncSession, institute: InstituteSchema
    ) -> tuple[list[BatchSchema], list[str]]:
        existing = await self.batch_service.list_batches(db, institute.id)
        by_name = {b.name: b for b in existing}

        batches: list[BatchSchema] = []
        created_names: list[str] = []
        for spec in _BATCH_SPECS:
            spec = dict(spec)
            monthly_amount = spec.pop("monthly_amount")
            batch = by_name.get(spec["name"])
            if batch is None:
                batch = await self.batch_service.create_batch(
                    db, institute_id=institute.id, **spec
                )
                created_names.append(batch.name)
            await self.fee_service.setup_fee_structure(db, batch.id, monthly_amount)
            batches.append(batch)
        return batches, created_names

    async def seed(self, db: AsyncSession) -> DemoSeedResult:
        owner, owner_created = await self._seed_owner(db)
        institute, institute_created = await self._seed_institute(db, owner)
        _batches, batches_created = await self._seed_batches(db, institute)

        return DemoSeedResult(
            owner_created=owner_created,
            institute_created=institute_created,
            batches_created=batches_created,
        )


def get_demo_seed_service() -> DemoSeedService:
    return DemoSeedService()
