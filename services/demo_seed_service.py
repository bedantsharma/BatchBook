import secrets
import string
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from models.batch_base import BatchSchema
from models.enrollment_base import EnrollmentSchema
from models.fee_record_base import FeeStatus
from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from models.student_base import StudentSchema
from repositories.institute_repository import InstituteRepository
from repositories.owner_repository import OwnerRepository
from repositories.parent_repository import ParentRepository
from repositories.student_repository import StudentRepository
from services.attendance_service import AttendanceService
from services.batch_service import BatchService
from services.enrollment_service import EnrollmentService
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
    student_created: bool = False
    sessions_created: int = 0
    fee_records_created: int = 0


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
        self.parent_repo = ParentRepository()
        self.student_repo = StudentRepository()
        self.batch_service = BatchService()
        self.fee_service = FeeService()
        self.enrollment_service = EnrollmentService()
        self.attendance_service = AttendanceService()

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

    async def _seed_parent_and_student(
        self, db: AsyncSession, institute: InstituteSchema, batches: list[BatchSchema]
    ) -> tuple[StudentSchema, list[EnrollmentSchema], bool]:
        parent = await self.parent_repo.get_by_phone(db, STUDENT_PARENT_PHONE)
        existing_children = (
            await self.parent_repo.get_students_by_parent_id(db, parent.id) if parent else []
        )

        if existing_children:
            student = existing_children[0]
            student_created = False
        else:
            enrollment = await self.enrollment_service.invite_student(
                db,
                student_name="Aarav Sharma",
                parent_phone=STUDENT_PARENT_PHONE,
                institute_id=institute.id,
                batch_id=batches[0].id,
                due_day=5,
                parent_name="Rina Sharma",
            )
            student = await self.student_repo.get_by_id(db, enrollment.student_id)
            student_created = True

        for batch in batches:
            try:
                await self.enrollment_service.enroll_student(
                    db, student_id=student.id, batch_id=batch.id, due_day=5
                )
            except ValueError:
                pass  # already enrolled in this batch

        enrollments: list[EnrollmentSchema] = []
        for batch in batches:
            enrollment = await self.enrollment_service.enrollment_repo.get_by_student_and_batch(
                db, student.id, batch.id
            )
            enrollments.append(enrollment)

        return student, enrollments, student_created

    async def _seed_sessions_and_attendance(
        self,
        db: AsyncSession,
        batches: list[BatchSchema],
        enrollments: list[EnrollmentSchema],
    ) -> int:
        today = date.today()
        offsets = [21, 14, 7]  # oldest first
        created = 0
        for batch, enrollment in zip(batches, enrollments, strict=True):
            for i, offset in enumerate(offsets):
                session_date = today - timedelta(days=offset)
                try:
                    session = await self.attendance_service.create_session(
                        db,
                        batch_id=batch.id,
                        session_date=session_date,
                        start_time=batch.start_time,
                        end_time=batch.end_time,
                    )
                except ValueError:
                    continue  # session for this batch+date already exists
                created += 1
                if i > 0:  # mark present for all but the oldest session
                    await self.attendance_service.bulk_mark(db, session.id, [enrollment.id])
        return created

    async def _seed_fee_records(
        self, db: AsyncSession, enrollments: list[EnrollmentSchema]
    ) -> int:
        today = date.today()
        current_month = today.replace(day=1)
        last_month = (current_month - timedelta(days=1)).replace(day=1)

        created = 0
        for enrollment in enrollments:
            for month in (last_month, current_month):
                new_records = await self.fee_service.generate_monthly_records(
                    db, enrollment.batch_id, month
                )
                created += len(new_records)

            last_month_record = await self.fee_service.fee_repo.get_record_by_enrollment_and_month(
                db, enrollment.id, last_month
            )
            if last_month_record and last_month_record.status != FeeStatus.FULLY_PAID:
                await self.fee_service.mark_payment(
                    db,
                    last_month_record.id,
                    last_month_record.amount_due,
                    reference="DEMO-SEED",
                )
        return created

    async def seed(self, db: AsyncSession) -> DemoSeedResult:
        owner, owner_created = await self._seed_owner(db)
        institute, institute_created = await self._seed_institute(db, owner)
        batches, batches_created = await self._seed_batches(db, institute)
        _student, enrollments, student_created = await self._seed_parent_and_student(
            db, institute, batches
        )
        sessions_created = await self._seed_sessions_and_attendance(db, batches, enrollments)
        fee_records_created = await self._seed_fee_records(db, enrollments)

        return DemoSeedResult(
            owner_created=owner_created,
            institute_created=institute_created,
            batches_created=batches_created,
            student_created=student_created,
            sessions_created=sessions_created,
            fee_records_created=fee_records_created,
        )


def get_demo_seed_service() -> DemoSeedService:
    return DemoSeedService()
