from sqlalchemy.ext.asyncio import AsyncSession
from models.student_base import StudentSchema

class StudentRepository:

    async def create_student(self, db: AsyncSession, student: StudentSchema):
        db.add(student)
        await db.commit()
        await db.refresh(student)
        return student