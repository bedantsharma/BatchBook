from datetime import date, time

from sqlalchemy.ext.asyncio import AsyncSession

from models.batch_base import BatchSchema, BatchStatus
from models.batch_teacher_base import BatchTeacherSchema
from repositories.batch_repository import BatchRepository


class BatchService:
    def __init__(self) -> None:
        self.batch_repo = BatchRepository()

    # ─── Core CRUD ─────────────────────────────────────────────────────────────

    async def create_batch(
        self,
        db: AsyncSession,
        institute_id: int,
        name: str,
        subject: str,
        start_time: time,
        end_time: time,
        days_of_week: list[str],
        max_capacity: int,
        end_date: date,
        grade: str | None = None,
        start_date: date | None = None,
    ) -> BatchSchema:
        """Create a new batch for the given institute."""
        batch = BatchSchema(
            institute_id=institute_id,
            name=name,
            subject=subject,
            grade=grade,
            start_time=start_time,
            end_time=end_time,
            days_of_week=days_of_week,
            max_capacity=max_capacity,
            start_date=start_date or date.today(),
            end_date=end_date,
            status=BatchStatus.ACTIVE,
        )
        return await self.batch_repo.create(db, batch)

    async def get_batch(
        self, db: AsyncSession, batch_id: int, institute_id: int
    ) -> BatchSchema:
        """Fetch a batch, raising ValueError if not found or not owned by the institute."""
        batch = await self.batch_repo.get_by_id(db, batch_id)
        if not batch:
            raise ValueError("Batch not found")
        if batch.institute_id != institute_id:
            raise ValueError("Batch does not belong to this institute")
        return batch

    async def list_batches(
        self, db: AsyncSession, institute_id: int
    ) -> list[BatchSchema]:
        """Return all batches for the institute, auto-transitioning any expired ones to CLOSING."""
        batches = await self.batch_repo.get_all_by_institute_id(db, institute_id)
        today = date.today()
        for batch in batches:
            if batch.status == BatchStatus.ACTIVE and batch.end_date < today:
                await self.batch_repo.update(db, batch, {"status": BatchStatus.CLOSING})
        return batches

    async def update_batch(
        self, db: AsyncSession, batch_id: int, institute_id: int, updates: dict
    ) -> BatchSchema:
        """Update batch fields. Raises ValueError if not found or not owned by institute."""
        batch = await self.get_batch(db, batch_id, institute_id)
        allowed_fields = {
            "name",
            "subject",
            "grade",
            "start_time",
            "end_time",
            "days_of_week",
            "max_capacity",
            "end_date",
        }
        filtered = {k: v for k, v in updates.items() if k in allowed_fields and v is not None}
        return await self.batch_repo.update(db, batch, filtered)

    async def delete_batch(
        self, db: AsyncSession, batch_id: int, institute_id: int
    ) -> None:
        """Delete a batch. Raises ValueError if not found or not owned by institute."""
        batch = await self.get_batch(db, batch_id, institute_id)
        await self.batch_repo.delete(db, batch)

    # ─── Teacher assignment ─────────────────────────────────────────────────────

    async def assign_teacher(
        self, db: AsyncSession, batch_id: int, teacher_id: int, institute_id: int
    ) -> BatchTeacherSchema:
        """Assign a teacher to a batch. Verifies batch ownership before assigning."""
        await self.get_batch(db, batch_id, institute_id)
        return await self.batch_repo.assign_teacher(db, batch_id, teacher_id)

    async def remove_teacher(
        self, db: AsyncSession, batch_id: int, teacher_id: int, institute_id: int
    ) -> None:
        """Remove a teacher from a batch. Verifies batch ownership first."""
        await self.get_batch(db, batch_id, institute_id)
        await self.batch_repo.remove_teacher(db, batch_id, teacher_id)

    # ─── Archival ──────────────────────────────────────────────────────────────

    def can_archive(self) -> bool:  # noqa: PLR6301
        """Placeholder: returns True until FeeRecord model is built in Phase 3.

        Phase 3 will implement real fee-record checks here:
          return not any unsettled fee records for this batch.
        """
        return True

    async def try_archive(
        self, db: AsyncSession, batch_id: int, institute_id: int
    ) -> BatchSchema:
        """Attempt to archive a batch.

        Raises ValueError if batch is not in CLOSING status or if there are
        outstanding fee records (Phase 3 check — currently always passes).
        """
        batch = await self.get_batch(db, batch_id, institute_id)
        if batch.status not in (BatchStatus.CLOSING, BatchStatus.ACTIVE):
            raise ValueError("Batch is already archived")
        if not self.can_archive():
            raise ValueError(
                "Cannot archive batch — there are unsettled fee records. "
                "Please settle all dues first."
            )
        return await self.batch_repo.update(db, batch, {"status": BatchStatus.ARCHIVED})

    async def check_closing_batches(
        self, db: AsyncSession, institute_id: int
    ) -> list[BatchSchema]:
        """Flip any ACTIVE batch whose end_date has passed to CLOSING.

        Call this at owner login to keep statuses fresh.
        Returns the list of batches that were transitioned.
        """
        batches = await self.batch_repo.get_all_by_institute_id(db, institute_id)
        today = date.today()
        transitioned = []
        for batch in batches:
            if batch.status == BatchStatus.ACTIVE and batch.end_date < today:
                await self.batch_repo.update(db, batch, {"status": BatchStatus.CLOSING})
                transitioned.append(batch)
        return transitioned


def get_batch_service() -> BatchService:
    return BatchService()
