from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema


class InstituteRepository:
    async def create(self, db: AsyncSession, institute: InstituteSchema) -> InstituteSchema:
        db.add(institute)
        await db.commit()
        await db.refresh(institute)
        return institute

    async def get_by_id(self, db: AsyncSession, institute_id: int) -> InstituteSchema | None:
        result = await db.execute(
            select(InstituteSchema).where(InstituteSchema.id == institute_id)
        )
        return result.scalar_one_or_none()

    async def get_by_owner_id(self, db: AsyncSession, owner_id: int) -> InstituteSchema | None:
        result = await db.execute(
            select(InstituteSchema).where(InstituteSchema.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def get_by_join_code(self, db: AsyncSession, join_code: str) -> InstituteSchema | None:
        result = await db.execute(
            select(InstituteSchema).where(InstituteSchema.join_code == join_code.upper())
        )
        return result.scalar_one_or_none()

    async def find_by_owner_phone(
        self, db: AsyncSession, owner_phone: str
    ) -> tuple[InstituteSchema, OwnerSchema] | None:
        result = await db.execute(
            select(InstituteSchema, OwnerSchema)
            .join(OwnerSchema, OwnerSchema.id == InstituteSchema.owner_id)
            .where(OwnerSchema.phone_number == owner_phone)
        )
        row = result.first()
        if row is None:
            return None
        return row.InstituteSchema, row.OwnerSchema

    async def update(
        self, db: AsyncSession, institute: InstituteSchema, updates: dict
    ) -> InstituteSchema:
        for key, value in updates.items():
            setattr(institute, key, value)
        await db.commit()
        await db.refresh(institute)
        return institute
