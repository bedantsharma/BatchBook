import secrets
import string

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from models.institute_base import InstituteSchema
from models.owner_base import OwnerSchema
from repositories.institute_repository import InstituteRepository


def _generate_join_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


@dataclass
class InstituteSearchResult:
    institute: InstituteSchema
    owner: OwnerSchema


@dataclass
class InstituteQRInfo:
    join_code: str
    join_url: str
    institute_name: str
    owner_phone: str


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
        join_code = _generate_join_code()
        institute = InstituteSchema(owner_id=owner_id, name=name, city=city, join_code=join_code)
        return await self.institute_repo.create(db, institute)

    async def get_institute_by_owner_id(
        self, db: AsyncSession, owner_id: int
    ) -> InstituteSchema | None:
        return await self.institute_repo.get_by_owner_id(db, owner_id)

    async def get_by_owner_id(
        self, db: AsyncSession, owner_id: int
    ) -> InstituteSchema | None:
        return await self.institute_repo.get_by_owner_id(db, owner_id)

    async def get_by_join_code(
        self, db: AsyncSession, join_code: str
    ) -> InstituteSchema | None:
        return await self.institute_repo.get_by_join_code(db, join_code)

    async def find_by_owner_phone(
        self, db: AsyncSession, owner_phone: str
    ) -> InstituteSearchResult | None:
        row = await self.institute_repo.find_by_owner_phone(db, owner_phone)
        if row is None:
            return None
        institute, owner = row
        return InstituteSearchResult(institute=institute, owner=owner)

    async def get_qr_info(
        self, db: AsyncSession, owner_id: int, owner_phone: str, base_url: str
    ) -> InstituteQRInfo | None:
        institute = await self.institute_repo.get_by_owner_id(db, owner_id)
        if not institute:
            return None
        join_url = f"{base_url.rstrip('/')}/join/{institute.join_code}"
        return InstituteQRInfo(
            join_code=institute.join_code,
            join_url=join_url,
            institute_name=institute.name,
            owner_phone=owner_phone,
        )

    async def update_institute(
        self, db: AsyncSession, owner_id: int, updates: dict
    ) -> InstituteSchema | None:
        institute = await self.institute_repo.get_by_owner_id(db, owner_id)
        if not institute:
            return None
        return await self.institute_repo.update(db, institute, updates)


def get_institute_service() -> InstituteService:
    return InstituteService()
