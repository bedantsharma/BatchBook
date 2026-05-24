from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.teacher_base import TeacherSchema


class TeacherRepository:
    async def create(self, db: AsyncSession, teacher: TeacherSchema) -> TeacherSchema:
        db.add(teacher)
        await db.commit()
        await db.refresh(teacher)
        return teacher

    async def get_by_user_id(self, db: AsyncSession, user_id: UUID) -> TeacherSchema | None:
        result = await db.execute(select(TeacherSchema).where(TeacherSchema.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_phone(self, db: AsyncSession, phone: str) -> TeacherSchema | None:
        result = await db.execute(select(TeacherSchema).where(TeacherSchema.phone_number == phone))
        return result.scalar_one_or_none()

    async def get_by_id(self, db: AsyncSession, teacher_id: int) -> TeacherSchema | None:
        result = await db.execute(select(TeacherSchema).where(TeacherSchema.id == teacher_id))
        return result.scalar_one_or_none()

    async def get_by_institute_id(self, db: AsyncSession, institute_id: int) -> list[TeacherSchema]:
        result = await db.execute(
            select(TeacherSchema).where(TeacherSchema.institute_id == institute_id)
        )
        return list(result.scalars().all())

    async def update(
        self, db: AsyncSession, teacher: TeacherSchema, updates: dict
    ) -> TeacherSchema:
        for key, value in updates.items():
            setattr(teacher, key, value)
        await db.commit()
        await db.refresh(teacher)
        return teacher

    async def delete(self, db: AsyncSession, teacher: TeacherSchema) -> None:
        await db.delete(teacher)
        await db.commit()
