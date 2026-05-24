from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from models.teacher_base import TeacherSchema
from repositories.teacher_repository import TeacherRepository
from services.auth_service import get_current_user_id


class TeacherService:
    def __init__(self):
        self.teacher_repo = TeacherRepository()

    async def invite_teacher(
        self,
        supabase: AsyncClient,
        db: AsyncSession,
        institute_id: int,
        name: str,
        phone: str,
    ) -> TeacherSchema:
        """Owner creates a Teacher record and triggers an OTP to the teacher's phone.

        If a teacher with this phone already exists in the institute, raises ValueError.
        If the phone belongs to a teacher in a different institute, also raises ValueError
        (phone_number is globally unique in the Teacher table).
        """
        existing = await self.teacher_repo.get_by_phone(db, phone)
        if existing:
            raise ValueError("A teacher with this phone number already exists")

        # Create the teacher record (user_id is None until they verify OTP)
        teacher = TeacherSchema(institute_id=institute_id, name=name, phone_number=phone)
        teacher = await self.teacher_repo.create(db, teacher)

        # Trigger OTP to teacher's phone via Supabase
        try:
            await supabase.auth.sign_in_with_otp({"phone": f"+91{phone}"})
        except Exception as e:
            # Roll back the created record if OTP send fails
            await self.teacher_repo.delete(db, teacher)
            raise ValueError(f"Could not send OTP to teacher's phone: {e}") from e

        return teacher

    async def verify_otp(
        self,
        supabase: AsyncClient,
        db: AsyncSession,
        phone: str,
        token: str,
    ) -> tuple[str, str, str, UUID]:
        """Teacher activates their account by verifying the OTP sent during invite.

        Links the Supabase user_id to the Teacher record and returns a JWT pair.
        """
        try:
            data = await supabase.auth.verify_otp(
                {
                    "phone": f"+91{phone}",
                    "token": token,
                    "type": "sms",
                }
            )
        except Exception as e:
            raise ValueError(str(e)) from e

        if not data.user or not data.session:
            raise ValueError("OTP verification failed")

        user_id = UUID(str(data.user.id))

        # Find the invited teacher record by phone and link the user_id
        teacher = await self.teacher_repo.get_by_phone(db, phone)
        if not teacher:
            raise ValueError("No pending teacher invite found for this phone number")

        await self.teacher_repo.update(db, teacher, {"user_id": user_id})

        return data.session.access_token, data.session.refresh_token, data.user.aud, user_id

    async def get_current_teacher_user_id(self, supabase: AsyncClient, authorization: str) -> UUID:
        return await get_current_user_id(supabase, authorization)

    async def get_teacher_by_user_id(self, db: AsyncSession, user_id: UUID) -> TeacherSchema | None:
        return await self.teacher_repo.get_by_user_id(db, user_id)

    async def get_teachers_by_institute(
        self, db: AsyncSession, institute_id: int
    ) -> list[TeacherSchema]:
        return await self.teacher_repo.get_by_institute_id(db, institute_id)

    async def remove_teacher(self, db: AsyncSession, institute_id: int, teacher_id: int) -> None:
        """Owner removes a teacher from their institute. Raises ValueError if not found
        or if the teacher belongs to a different institute."""
        teacher = await self.teacher_repo.get_by_id(db, teacher_id)
        if not teacher:
            raise ValueError("Teacher not found")
        if teacher.institute_id != institute_id:
            raise ValueError("Teacher does not belong to this institute")
        await self.teacher_repo.delete(db, teacher)


def get_teacher_service() -> TeacherService:
    return TeacherService()
