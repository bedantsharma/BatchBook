from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from models.enrollment_base import EnrollmentSchema
from repositories.enrollment_repository import EnrollmentRepository


class EnrollmentService:
    """Business logic for enrolling students in batches.

    Security contract:
    - Callers (routes) are responsible for verifying that the batch belongs
      to the authenticated owner's institute before calling any method here.
    - This service trusts the batch_id and student_id it receives.
    """

    def __init__(self) -> None:
        self.enrollment_repo = EnrollmentRepository()

    async def enroll_student(
        self,
        db: AsyncSession,
        student_id: int,
        batch_id: int,
        due_day: int | None = None,
        first_month_amount: Decimal | None = None,
    ) -> EnrollmentSchema:
        """Enroll a student in a batch.

        Args:
            student_id: ID of the student to enroll.
            batch_id: ID of the target batch.
            due_day: Fee due day of month (1–28). Defaults to today's day-of-month,
                     clamped to 28 to avoid month-end issues.
            first_month_amount: Pro-rated fee for the joining month.
                                 None → fee service will use FeeStructure.monthly_amount.

        Raises:
            ValueError: If the student is already actively enrolled in this batch.
        """
        # Check for duplicate active enrollment
        existing = await self.enrollment_repo.get_by_student_and_batch(
            db, student_id, batch_id
        )
        if existing and existing.is_active:
            raise ValueError(
                "Student is already actively enrolled in this batch"
            )

        # Default due_day to today's day-of-month, clamped to 28
        if due_day is None:
            due_day = min(datetime.now().day, 28)

        if due_day < 1 or due_day > 28:
            raise ValueError("due_day must be between 1 and 28")

        enrollment = EnrollmentSchema(
            student_id=student_id,
            batch_id=batch_id,
            enrolled_at=datetime.now(),
            is_active=True,
            due_day=due_day,
            first_month_amount=first_month_amount,
        )
        return await self.enrollment_repo.create(db, enrollment)

    async def get_enrollments_by_batch(
        self, db: AsyncSession, batch_id: int
    ) -> list[EnrollmentSchema]:
        """Return all enrollments (active + inactive) for a batch."""
        return await self.enrollment_repo.get_by_batch_id(db, batch_id)

    async def get_active_enrollments_by_batch(
        self, db: AsyncSession, batch_id: int
    ) -> list[EnrollmentSchema]:
        """Return only active enrollments for a batch."""
        return await self.enrollment_repo.get_active_by_batch_id(db, batch_id)

    async def update_enrollment(
        self,
        db: AsyncSession,
        enrollment_id: int,
        due_day: int | None = None,
        first_month_amount: Decimal | None = None,
    ) -> EnrollmentSchema:
        """Update ``due_day`` and/or ``first_month_amount`` on an enrollment.

        Raises:
            ValueError: If the enrollment is not found.
        """
        enrollment = await self.enrollment_repo.get_by_id(db, enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")

        updates: dict = {}
        if due_day is not None:
            if due_day < 1 or due_day > 28:
                raise ValueError("due_day must be between 1 and 28")
            updates["due_day"] = due_day
        if first_month_amount is not None:
            updates["first_month_amount"] = first_month_amount

        if not updates:
            return enrollment

        return await self.enrollment_repo.update(db, enrollment, updates)

    async def remove_enrollment(self, db: AsyncSession, enrollment_id: int) -> None:
        """Soft-delete an enrollment by setting is_active = False.

        Raises:
            ValueError: If the enrollment is not found.
        """
        enrollment = await self.enrollment_repo.get_by_id(db, enrollment_id)
        if not enrollment:
            raise ValueError("Enrollment not found")
        await self.enrollment_repo.deactivate(db, enrollment)


def get_enrollment_service() -> EnrollmentService:
    return EnrollmentService()
