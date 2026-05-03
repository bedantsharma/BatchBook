from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.student_base import StudentSchema

class StudentRepository:

    async def create_student(self, db: AsyncSession, student: StudentSchema):
        db.add(student)
        await db.commit()
        await db.refresh(student)
        return student

    async def get_by_user_id(self, db: AsyncSession, user_id: UUID) -> StudentSchema | None:
        result = await db.execute(select(StudentSchema).where(StudentSchema.user_id == user_id))
        return result.scalar_one_or_none()

    async def update_student(self, db: AsyncSession, student: StudentSchema, updates: dict) -> StudentSchema:
        for key, value in updates.items():
            setattr(student, key, value)
        await db.commit()
        await db.refresh(student)
        return student