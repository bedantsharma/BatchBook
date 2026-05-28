from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enrollment_base import EnrollmentSchema


class EnrollmentRepository:
    async def create(
        self, db: AsyncSession, enrollment: EnrollmentSchema
    ) -> EnrollmentSchema:
        db.add(enrollment)
        await db.commit()
        await db.refresh(enrollment)
        return enrollment

    async def get_by_id(self, db: AsyncSession, enrollment_id: int) -> EnrollmentSchema | None:
        result = await db.execute(
            select(EnrollmentSchema).where(EnrollmentSchema.id == enrollment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_batch_id(
        self, db: AsyncSession, batch_id: int
    ) -> list[EnrollmentSchema]:
        result = await db.execute(
            select(EnrollmentSchema).where(EnrollmentSchema.batch_id == batch_id)
        )
        return list(result.scalars().all())

    async def get_active_by_batch_id(
        self, db: AsyncSession, batch_id: int
    ) -> list[EnrollmentSchema]:
        result = await db.execute(
            select(EnrollmentSchema).where(
                EnrollmentSchema.batch_id == batch_id,
                EnrollmentSchema.is_active.is_(True),
            )
        )
        return list(result.scalars().all())

    async def get_by_student_id(
        self, db: AsyncSession, student_id: int
    ) -> list[EnrollmentSchema]:
        result = await db.execute(
            select(EnrollmentSchema).where(EnrollmentSchema.student_id == student_id)
        )
        return list(result.scalars().all())

    async def get_by_student_and_batch(
        self, db: AsyncSession, student_id: int, batch_id: int
    ) -> EnrollmentSchema | None:
        result = await db.execute(
            select(EnrollmentSchema).where(
                EnrollmentSchema.student_id == student_id,
                EnrollmentSchema.batch_id == batch_id,
            )
        )
        return result.scalar_one_or_none()

    async def update(
        self, db: AsyncSession, enrollment: EnrollmentSchema, updates: dict
    ) -> EnrollmentSchema:
        for key, value in updates.items():
            setattr(enrollment, key, value)
        await db.commit()
        await db.refresh(enrollment)
        return enrollment

    async def deactivate(
        self, db: AsyncSession, enrollment: EnrollmentSchema
    ) -> EnrollmentSchema:
        return await self.update(db, enrollment, {"is_active": False})
