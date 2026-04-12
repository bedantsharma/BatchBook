from sqlalchemy.ext.asyncio import AsyncSession
from models.student_base import StudentSchema
from DTO.student_model import Student
from repositories.student_repository import StudentRepository


class StudentService():
    def __init__(self):
        self.student_repo = StudentRepository()

    async def create_student(self, data: Student, db:AsyncSession):
        student_schema = StudentSchema(**data.model_dump())
        return await self.student_repo.create_student(db,student_schema)
