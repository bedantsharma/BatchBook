from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String

from db.base import Base
from DTO.student_model import StudentFeesStatus


class StudentSchema(Base):
    __tablename__ = "Student"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=True)
    fees_status = Column(
        Enum(StudentFeesStatus), default=StudentFeesStatus.NOT_PAID, nullable=False
    )
    email = Column(String, nullable=True)
    parent_id = Column(Integer, ForeignKey("Parent.id"), nullable=True)
    institute_id = Column(Integer, ForeignKey("Institute.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
