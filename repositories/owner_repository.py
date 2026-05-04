from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.owner_base import OwnerSchema


class OwnerRepository:
    async def create_owner(self, db: AsyncSession, owner: OwnerSchema) -> OwnerSchema:
        db.add(owner)
        await db.commit()
        await db.refresh(owner)
        return owner

    async def get_by_teacher_id(self, db: AsyncSession, teacher_id: UUID) -> OwnerSchema | None:
        result = await db.execute(
            select(OwnerSchema).where(OwnerSchema.teacher_id == teacher_id)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, db: AsyncSession, phone: str) -> OwnerSchema | None:
        result = await db.execute(
            select(OwnerSchema).where(OwnerSchema.phone_number == phone)
        )
        return result.scalar_one_or_none()

    async def update_owner(
        self, db: AsyncSession, owner: OwnerSchema, updates: dict
    ) -> OwnerSchema:
        for key, value in updates.items():
            setattr(owner, key, value)
        await db.commit()
        await db.refresh(owner)
        return owner
