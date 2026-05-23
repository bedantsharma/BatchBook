from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.parent_base import ParentSchema
from models.student_base import StudentSchema


class ParentRepository:
    async def create_parent(self, db: AsyncSession, parent: ParentSchema) -> ParentSchema:
        db.add(parent)
        await db.commit()
        await db.refresh(parent)
        return parent

    async def get_by_user_id(self, db: AsyncSession, user_id: UUID) -> ParentSchema | None:
        result = await db.execute(
            select(ParentSchema).where(ParentSchema.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, db: AsyncSession, phone: str) -> ParentSchema | None:
        result = await db.execute(
            select(ParentSchema).where(ParentSchema.phone_number == phone)
        )
        return result.scalar_one_or_none()

    async def get_students_by_parent_id(
        self, db: AsyncSession, parent_id: int
    ) -> list[StudentSchema]:
        result = await db.execute(
            select(StudentSchema).where(StudentSchema.parent_id == parent_id)
        )
        return list(result.scalars().all())

    async def update_parent(
        self, db: AsyncSession, parent: ParentSchema, updates: dict
    ) -> ParentSchema:
        for key, value in updates.items():
            setattr(parent, key, value)
        await db.commit()
        await db.refresh(parent)
        return parent
