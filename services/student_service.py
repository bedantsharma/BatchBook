from typing import Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from models.student_base import StudentSchema
from DTO.student_model import Student, StudentFeesStatus
from repositories.student_repository import StudentRepository


class StudentService():
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
        name: Optional[str],
        email: Optional[str],
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

    async def update_student(
        self, db: AsyncSession, user_id: UUID, updates: dict
    ) -> StudentSchema | None:
        student = await self.student_repo.get_by_user_id(db, user_id)
        if not student:
            return None
        return await self.student_repo.update_student(db, student, updates)
