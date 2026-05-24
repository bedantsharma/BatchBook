from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from models.parent_base import ParentSchema
from models.student_base import StudentSchema
from repositories.parent_repository import ParentRepository
from services.auth_service import get_current_user_id


class ParentService:
    def __init__(self):
        self.parent_repo = ParentRepository()

    async def get_or_create_after_otp(
        self,
        db: AsyncSession,
        user_id: UUID,
        phone: str,
        name: str | None,
    ) -> ParentSchema:
        existing = await self.parent_repo.get_by_user_id(db, user_id)
        if existing:
            return existing
        parent = ParentSchema(user_id=user_id, phone_number=phone, name=name)
        return await self.parent_repo.create_parent(db, parent)

    async def verify_otp(
        self,
        supabase: AsyncClient,
        db: AsyncSession,
        phone: str,
        token: str,
        name: str | None,
    ) -> tuple[str, str, str, UUID, list[StudentSchema]]:
        """Verify OTP, upsert parent, return (access_token, refresh_token, aud, user_id, children)."""
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
        user_id = UUID(str(data.user.id))
        parent = await self.get_or_create_after_otp(db, user_id, phone, name)
        children = await self.parent_repo.get_students_by_parent_id(db, parent.id)
        return (
            data.session.access_token,
            data.session.refresh_token,
            data.user.aud,
            user_id,
            children,
        )

    async def get_current_user_id(self, supabase: AsyncClient, authorization: str) -> UUID:
        return await get_current_user_id(supabase, authorization)

    async def get_parent_by_user_id(
        self, db: AsyncSession, user_id: UUID
    ) -> ParentSchema | None:
        return await self.parent_repo.get_by_user_id(db, user_id)

    async def get_children(
        self, db: AsyncSession, user_id: UUID
    ) -> list[StudentSchema]:
        parent = await self.parent_repo.get_by_user_id(db, user_id)
        if not parent:
            return []
        return await self.parent_repo.get_students_by_parent_id(db, parent.id)

    async def update_parent(
        self, db: AsyncSession, user_id: UUID, updates: dict
    ) -> ParentSchema | None:
        parent = await self.parent_repo.get_by_user_id(db, user_id)
        if not parent:
            return None
        return await self.parent_repo.update_parent(db, parent, updates)


def get_parent_service() -> ParentService:
    return ParentService()
