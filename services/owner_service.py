from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from models.owner_base import OwnerSchema
from repositories.owner_repository import OwnerRepository
from services.auth_service import get_current_user_id


class OwnerService:
    def __init__(self):
        self.owner_repo = OwnerRepository()

    async def get_or_create_after_otp(
        self,
        db: AsyncSession,
        teacher_id: UUID,
        phone: str,
        name: str | None,
        email: str | None,
    ) -> OwnerSchema:
        # Primary lookup: existing session (returning owner)
        existing = await self.owner_repo.get_by_teacher_id(db, teacher_id)
        if existing:
            return existing

        # Secondary lookup: same phone, different UUID (Supabase account was re-created)
        by_phone = await self.owner_repo.get_by_phone(db, phone)
        if by_phone:
            # OTP proves phone ownership — update to the new UUID
            return await self.owner_repo.update_owner(db, by_phone, {"teacher_id": teacher_id})

        # Brand-new owner
        try:
            owner = OwnerSchema(teacher_id=teacher_id, phone_number=phone, name=name, email=email)
            return await self.owner_repo.create_owner(db, owner)
        except IntegrityError:
            # Lost a tiny race between the two lookups and the insert; fetch whatever won
            await db.rollback()
            existing = await self.owner_repo.get_by_teacher_id(db, teacher_id)
            if existing:
                return existing
            by_phone = await self.owner_repo.get_by_phone(db, phone)
            if by_phone:
                return by_phone
            raise

    async def verify_otp(
        self,
        supabase: AsyncClient,
        db: AsyncSession,
        phone: str,
        token: str,
        name: str | None,
        email: str | None,
    ) -> tuple[str, str, str, UUID]:
        try:
            data = await supabase.auth.verify_otp({
                "phone": f"+91{phone}",
                "token": token,
                "type": "sms",
            })
        except Exception as e:
            raise ValueError(str(e)) from e
        if not data.user or not data.session:
            raise ValueError("OTP verification failed")
        teacher_id = UUID(str(data.user.id))
        await self.get_or_create_after_otp(db, teacher_id, phone, name, email)
        return data.session.access_token, data.session.refresh_token, data.user.aud, teacher_id

    async def get_current_teacher_id(self, supabase: AsyncClient, authorization: str) -> UUID:
        return await get_current_user_id(supabase, authorization)

    async def get_owner_by_teacher_id(
        self, db: AsyncSession, teacher_id: UUID
    ) -> OwnerSchema | None:
        return await self.owner_repo.get_by_teacher_id(db, teacher_id)

    async def update_owner(
        self, db: AsyncSession, teacher_id: UUID, updates: dict
    ) -> OwnerSchema | None:
        owner = await self.owner_repo.get_by_teacher_id(db, teacher_id)
        if not owner:
            return None
        return await self.owner_repo.update_owner(db, owner, updates)


def get_owner_service() -> OwnerService:
    return OwnerService()
