from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.batch_base import BatchSchema
from models.batch_teacher_base import BatchTeacherSchema


class BatchRepository:
    # ─── Batch CRUD ────────────────────────────────────────────────────────────

    async def create(self, db: AsyncSession, batch: BatchSchema) -> BatchSchema:
        db.add(batch)
        await db.commit()
        await db.refresh(batch)
        return batch

    async def get_by_id(self, db: AsyncSession, batch_id: int) -> BatchSchema | None:
        result = await db.execute(select(BatchSchema).where(BatchSchema.id == batch_id))
        return result.scalar_one_or_none()

    async def get_all_by_institute_id(
        self, db: AsyncSession, institute_id: int
    ) -> list[BatchSchema]:
        result = await db.execute(
            select(BatchSchema).where(BatchSchema.institute_id == institute_id)
        )
        return list(result.scalars().all())

    async def update(
        self, db: AsyncSession, batch: BatchSchema, updates: dict
    ) -> BatchSchema:
        for key, value in updates.items():
            setattr(batch, key, value)
        await db.commit()
        await db.refresh(batch)
        return batch

    async def delete(self, db: AsyncSession, batch: BatchSchema) -> None:
        await db.delete(batch)
        await db.commit()

    # ─── BatchTeacher (assignment) ──────────────────────────────────────────────

    async def assign_teacher(
        self, db: AsyncSession, batch_id: int, teacher_id: int
    ) -> BatchTeacherSchema:
        link = BatchTeacherSchema(batch_id=batch_id, teacher_id=teacher_id)
        db.add(link)
        try:
            await db.commit()
            await db.refresh(link)
        except IntegrityError:
            await db.rollback()
            raise ValueError("Teacher is already assigned to this batch")
        return link

    async def remove_teacher(
        self, db: AsyncSession, batch_id: int, teacher_id: int
    ) -> None:
        result = await db.execute(
            select(BatchTeacherSchema).where(
                BatchTeacherSchema.batch_id == batch_id,
                BatchTeacherSchema.teacher_id == teacher_id,
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            raise ValueError("Teacher is not assigned to this batch")
        await db.delete(link)
        await db.commit()

    async def get_teachers_for_batch(
        self, db: AsyncSession, batch_id: int
    ) -> list[BatchTeacherSchema]:
        result = await db.execute(
            select(BatchTeacherSchema).where(BatchTeacherSchema.batch_id == batch_id)
        )
        return list(result.scalars().all())

    async def get_batches_for_teacher(
        self, db: AsyncSession, teacher_id: int
    ) -> list[BatchTeacherSchema]:
        result = await db.execute(
            select(BatchTeacherSchema).where(BatchTeacherSchema.teacher_id == teacher_id)
        )
        return list(result.scalars().all())
