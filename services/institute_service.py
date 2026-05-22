from sqlalchemy.ext.asyncio import AsyncSession

from models.institute_base import InstituteSchema
from repositories.institute_repository import InstituteRepository


class InstituteService:
    def __init__(self):
        self.institute_repo = InstituteRepository()

    async def create_institute(
        self, db: AsyncSession, owner_id: int, name: str, city: str
    ) -> InstituteSchema:
        """Create institute for owner. Raises ValueError if one already exists."""
        existing = await self.institute_repo.get_by_owner_id(db, owner_id)
        if existing:
            raise ValueError("Institute already exists for this owner")
        institute = InstituteSchema(owner_id=owner_id, name=name, city=city)
        return await self.institute_repo.create(db, institute)

    async def get_by_owner_id(
        self, db: AsyncSession, owner_id: int
    ) -> InstituteSchema | None:
        return await self.institute_repo.get_by_owner_id(db, owner_id)


def get_institute_service() -> InstituteService:
    return InstituteService()
