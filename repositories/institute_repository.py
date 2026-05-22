from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.institute_base import InstituteSchema


class InstituteRepository:
    async def create(self, db: AsyncSession, institute: InstituteSchema) -> InstituteSchema:
        db.add(institute)
        await db.commit()
        await db.refresh(institute)
        return institute

    async def get_by_owner_id(self, db: AsyncSession, owner_id: int) -> InstituteSchema | None:
        result = await db.execute(
            select(InstituteSchema).where(InstituteSchema.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self, db: AsyncSession, institute: InstituteSchema, updates: dict
    ) -> InstituteSchema:
        for key, value in updates.items():
            setattr(institute, key, value)
        await db.commit()
        await db.refresh(institute)
        return institute
