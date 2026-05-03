from sqlalchemy import Column, Integer, String, DateTime, Enum, UUID
from DTO.student_model import StudentFeesStatus
from db.base import Base
from datetime import datetime


class StudentSchema(Base):
    __tablename__ = "Student"
    id = Column(Integer, primary_key=True,index=True,autoincrement=True)
    name = Column(String)
    phone_number = Column(String,unique=True)
    fees_status = Column(Enum(StudentFeesStatus), default=StudentFeesStatus.NOT_PAID,nullable=False)
    created_at = Column(DateTime,default=datetime.now,nullable=False)
    email = Column(String)
    user_id = Column(UUID(as_uuid=True),unique=True,nullable=False)