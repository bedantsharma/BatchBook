from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from supabase import AsyncClient

from DTO.student_model import StudentFeesStatus
from models.student_base import StudentSchema
from repositories.student_repository import StudentRepository
from services.auth_service import get_current_user_id as _get_user_id


class StudentService:
    def __init__(self):
        self.student_repo = StudentRepository()

    async def create_student(
        self,
        db: AsyncSession,
        name: str,
        parent_id: int | None = None,
        institute_id: int | None = None,
        email: str | None = None,
    ) -> StudentSchema:
        student = StudentSchema(
            name=name,
            parent_id=parent_id,
            institute_id=institute_id,
            email=email,
            fees_status=StudentFeesStatus.NOT_PAID,
        )
        return await self.student_repo.create_student(db, student)

    async def get_current_user_id(self, supabase: AsyncClient, authorization: str) -> UUID:
        return await _get_user_id(supabase, authorization)

    async def get_student_by_id(
        self, db: AsyncSession, student_id: int
    ) -> StudentSchema | None:
        return await self.student_repo.get_by_id(db, student_id)

    async def update_student(
        self, db: AsyncSession, student_id: int, updates: dict
    ) -> StudentSchema | None:
        student = await self.student_repo.get_by_id(db, student_id)
        if not student:
            return None
        return await self.student_repo.update_student(db, student, updates)


def get_student_service() -> StudentService:
    return StudentService()
