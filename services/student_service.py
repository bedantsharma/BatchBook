from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from DTO.student_model import Student, StudentFeesStatus
from models.student_base import StudentSchema
from repositories.student_repository import StudentRepository


class StudentService:
    def __init__(self):
        self.student_repo = StudentRepository()

    async def create_student(self, data: Student, db: AsyncSession):
        student_schema = StudentSchema(**data.model_dump())
        return await self.student_repo.create_student(db, student_schema)

    async def get_or_create_after_otp(
        self,
        db: AsyncSession,
        user_id: UUID,
        phone: str,
        name: str | None,
        email: str | None,
    ) -> StudentSchema:
        existing = await self.student_repo.get_by_user_id(db, user_id)
        if existing:
            return existing
        student = StudentSchema(
            user_id=user_id,
            phone_number=phone,
            name=name,
            email=email,
            fees_status=StudentFeesStatus.NOT_PAID,
        )
        return await self.student_repo.create_student(db, student)

    async def verify_otp(
        self,
        supabase,
        db: AsyncSession,
        phone: str,
        token: str,
        name: str | None,
        email: str | None,
    ) -> tuple[str, str, UUID]:
        """Verify the OTP with Supabase, upsert the student, and return (access_token, aud, user_id)."""
        data = await supabase.auth.verify_otp({
            "phone": f"+91{phone}",
            "token": token,
            "type": "sms",
        })
        if not data.user or not data.session:
            raise ValueError("OTP verification failed")
        user_id = UUID(str(data.user.id))
        await self.get_or_create_after_otp(db, user_id, phone, name, email)
        return data.session.access_token, data.user.aud, user_id

    async def get_current_user_id(self, supabase, authorization: str) -> UUID:
        """Validate the Bearer token and return the authenticated user's UUID."""
        token = authorization.removeprefix("Bearer ").strip()
        response = await supabase.auth.get_user(token)
        return UUID(str(response.user.id))

    async def update_student(
        self, db: AsyncSession, user_id: UUID, updates: dict
    ) -> StudentSchema | None:
        student = await self.student_repo.get_by_user_id(db, user_id)
        if not student:
            return None
        return await self.student_repo.update_student(db, student, updates)

def get_student_service() -> StudentService:
    return StudentService()
